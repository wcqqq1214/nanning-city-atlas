"""Audit actual scoped GLBs, optionally against preserved full-city inputs."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import Point, box, shape

from asset_budgets import validate_model_bytes
from scope_city import CityGLB
from city_context import TerrainSampler, canopy_clearance
from urban_scope import ROOT, UrbanScope


def payload_hash(city, primitive):
    view = primitive['extensions']['KHR_draco_mesh_compression']['bufferView']
    return hashlib.sha256(city.payloads[view]).hexdigest()


def validate(candidate=ROOT/'public', baseline=None):
    scope = UrbanScope.read()
    scope.require_approved()
    overview = json.loads((candidate/'data/overview.json').read_text())
    manifest = json.loads((candidate/'data/urban-scope-models.json').read_text())
    source_sha = hashlib.sha256((ROOT/'data/urban-core-boundary-source.json').read_bytes()).hexdigest()
    assert source_sha == manifest['scopeSourceSha256'] == overview['urbanScope']['sourceBoundarySha256'], 'Stale display scope'
    assert manifest['geographySha256'] == hashlib.sha256((ROOT/'public/data/geography.json').read_bytes()).hexdigest(), 'Stale geographic input'
    assert manifest['forestSourceSha256'] == hashlib.sha256((ROOT/'data/forest-plan.json').read_bytes()).hexdigest(), 'Stale landscape mask'
    assert shape(overview['urbanScope']['core']).equals_exact(scope.core, 1e-8)
    assert shape(overview['urbanScope']['context']).equals_exact(scope.context, 1e-8)
    assert shape(overview['urbanScope']['transition']).equals_exact(scope.transition, 1e-8)
    assert scope.context.equals(scope.context.envelope), 'Visible city must be rectangular'
    assert overview['urbanScope']['outline'] == 'rectangle'
    assert np.allclose(overview['bounds'], scope.context.bounds)
    assert scope.transition.buffer(.00001).covers(scope.water_corridors), 'Major water body crosses coarse terrain'
    assert overview['urbanScope']['landscapeFadeMeters'] >= 1000
    assert shape(overview['urbanScope']['woodland']).area > 0
    places = json.loads((candidate/'data/landmarks.json').read_text())
    for place in places:
        assert scope.core.covers(Point(scope.project(place['lon'], place['lat']))), place['id']
    for area in json.loads((ROOT/'data/landmark-areas.json').read_text())['areas'].values():
        from shapely.ops import transform
        for polygon in area['polygons']:
            geographic = shapely.Polygon(polygon[0], polygon[1:])
            assert scope.core.covers(transform(scope.project, geographic)), area['name']
    results = {}
    for profile, filename in [('detail', 'nanning-city.glb'), ('smooth', 'nanning-city-mobile.glb')]:
        city = CityGLB(candidate/'models'/filename)
        expected = manifest['models'][profile]
        assert city.sha == expected['sha256'], 'Model differs from validated export: ' + profile
        assert city.bytes == overview['models'][profile]['bytes'] == expected['bytes']
        validate_model_bytes(profile, city.bytes)
        assert city.bytes < expected['beforeBytes'], 'Cropping must reduce downloaded bytes'
        assert city.doc['extras']['urbanScope'] == scope.source['id']
        meshes = {m['name']: m for m in city.doc['meshes']}
        assert {'Plinth', 'Water', 'Terrain_context', 'GroundRoads_context'} <= meshes.keys()
        names = {n.get('name') for n in city.doc['nodes']}
        assert {'Buildings', 'Terrain', 'Water', 'Roads', 'Vegetation', 'Bridges', 'Plinth', 'Railways'} <= names
        for place in places:
            if place['modelled']:
                assert 'Landmark_'+place['id'] in meshes
        for name, digests in expected['protectedLandmarkPayloads'].items():
            assert name in meshes, 'Missing protected landmark: ' + name
            assert [payload_hash(city, p) for p in meshes[name]['primitives']] == digests, 'Landmark geometry changed: ' + name
        triangles = 0
        payloads = set()
        max_outside = 0
        context_area = 0
        retained_terrain = []
        context_vertices = []
        # Boundary structures use a verified 5 cm compression budget. Whole
        # buildings/tree crowns may cross the inner core, within this skirt.
        outer = scope.context.buffer(.0006)
        canopy = scope.landscape.buffer(.0002)
        peripheral_canopy = []
        canopy_triangles = []
        context_triangles = []
        context_roads = []
        shapely.prepare(outer)
        shapely.prepare(canopy)
        for name, mesh in meshes.items():
            for primitive in mesh['primitives']:
                d = city.decode(primitive)
                assert np.isfinite(d.points).all() and np.isfinite(d.normals).all(), name
                assert d.faces.min() >= 0 and d.faces.max() < len(d.points), name
                triangles += len(d.faces)
                payloads.add(payload_hash(city, primitive))
                xy = d.points[:, [0, 2]] * [1, -1]
                mask = canopy if '_canopy' in name else outer
                inside = shapely.intersects_xy(mask, xy[:, 0], xy[:, 1])
                if not inside.all():
                    distance = float(shapely.distance(shapely.points(xy[~inside]), mask).max())*100
                    max_outside = max(max_outside, distance)
                    raise AssertionError(f'{name} extends {distance:.4f} m beyond scoped geometry')
                if name == 'Plinth':
                    assert float(d.points[:, 1].min()) < -2.59
                    # No vertical skirt may follow the irregular detail line.
                    top = d.points[:, 1] > -2.59
                    assert (shapely.distance(shapely.points(xy[top]), scope.context.boundary) < .0006).all()
                if name == 'GroundRoads_context':
                    context_roads.append(d.points[d.faces])
                if name == 'Terrain_context':
                    context_vertices.append(d.points)
                    context_triangles.append(d.points[d.faces])
                    tri = xy[d.faces]
                    context_area += np.abs(np.linalg.det(np.stack([
                        tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0]], axis=2))).sum()/2
                    centers = tri.mean(axis=1)
                    assert shapely.intersects_xy(scope.context.difference(scope.transition).buffer(.0006),
                                                  centers[:, 0], centers[:, 1]).all()
                    assert len(d.faces) < 50000, 'Surroundings must remain coarse'
                elif name.startswith('Terrain'):
                    retained_terrain.append(d.points[d.faces])
                if '_canopy' in name:
                    canopy_triangles.append(d.points[d.faces])
                    distance = shapely.distance(shapely.points(xy), scope.core)*100
                    # The outer forest edge must meet the ground, never end as
                    # another raised wall at the end of the fade band.
                    peripheral_canopy.append(d.points[distance > scope.source['landscapeFadeMeters']-1])
        expected_area = scope.context.difference(scope.transition).area
        assert abs(context_area-expected_area)/expected_area < 1e-5, 'Rectangular corners are not filled'
        points = np.unique(np.concatenate(context_vertices), axis=0)
        xy = points[:, [0, 2]]*[1, -1]
        seam = shapely.distance(shapely.points(xy), scope.transition.boundary) < .0001
        assert seam.sum() > 100, 'Missing terrain transition edge'
        sampler = TerrainSampler(np.concatenate(retained_terrain))
        seam_error = float(np.abs(points[seam, 1]-sampler(xy[seam])).max())*100
        assert seam_error < .05, f'Background terrain seam exceeds 5 cm: {seam_error:.4f} m'
        all_ground = TerrainSampler(np.concatenate([*retained_terrain, *context_triangles]))
        clearance = canopy_clearance(np.concatenate(canopy_triangles), all_ground, scope.core)
        minimum_clearance = float(clearance.min())*100
        assert minimum_clearance >= -.02, f'Canopy face intersects terrain: {minimum_clearance:.4f} m'
        road_gap = float(canopy_clearance(np.concatenate(context_roads), all_ground, scope.core).min())*100
        assert road_gap > 0, f'Context roads intersect terrain: {road_gap:.4f} m'
        canopy_edge = np.concatenate(peripheral_canopy)
        assert len(canopy_edge) > 20, 'Forest must extend across the city line'
        canopy_gap = float(np.abs(canopy_edge[:, 1]-all_ground(canopy_edge[:, [0, 2]]*[1, -1])).max())*100
        assert canopy_gap < .05, f'Peripheral forest ends above ground: {canopy_gap:.4f} m'
        assert triangles == expected['triangles'] < expected['beforeTriangles']
        verified_copies = 0
        if baseline is not None:
            original = CityGLB(baseline/'models'/filename)
            assert original.sha == expected['inputSha256'], 'Wrong baseline model'
            count = len(original.doc['materials'])
            assert original.doc['materials'] == city.doc['materials'][:count], 'Original materials changed during crop'
            assert [m['name'] for m in city.doc['materials'][count:]] == ['Terrain_context', 'GroundRoads_context']
            assert (baseline/'data/landmarks.json').read_bytes() == (candidate/'data/landmarks.json').read_bytes()
            original_canopy = []
            for mesh in original.doc['meshes']:
                name = mesh['name']
                if name == 'Plinth':
                    continue
                mask = scope.core if '_canopy' in name else scope.mask_for(name)
                for p in mesh['primitives']:
                    if '_canopy' in name:
                        d = original.decode(p)
                        original_canopy.append(d.points[d.faces])
                    a = original.doc['accessors'][p['attributes']['POSITION']]
                    lo, hi = a['min'], a['max']
                    if mask.covers(box(lo[0], -hi[2], hi[0], -lo[2])):
                        assert payload_hash(original, p) in payloads, 'Untouched primitive changed: ' + name
                        verified_copies += 1
            from shapely.ops import unary_union
            def footprint(parts):
                return unary_union(shapely.polygons(np.concatenate(parts)[:, :, [0, 2]]*[1, -1]))
            expected_forest = footprint(original_canopy).intersection(scope.landscape)
            actual_forest = footprint(canopy_triangles)
            # Source Draco coordinates are the reference. Allow 3 mm of XY
            # rounding when cutting/refining their original woodland footprint.
            assert expected_forest.difference(actual_forest.buffer(.00003)).area < .0001, 'Canopy refinement lost woodland coverage'
            assert actual_forest.difference(expected_forest.buffer(.00003)).area < .0001, 'Canopy refinement filled woodland clearings'
        results[profile] = {'bytes': city.bytes, 'triangles': triangles,
                            'protectedLandmarkMeshes': len(expected['protectedLandmarkPayloads']),
                            'verifiedUnchangedPrimitives': verified_copies if baseline is not None else None,
                            'rectangularBackgroundKm2': round(context_area/100, 2),
                            'maximumBackgroundSeamErrorMeters': seam_error,
                            'maximumPeripheralCanopyGapMeters': canopy_gap,
                            'minimumCanopyFaceClearanceMeters': minimum_clearance,
                            'minimumContextRoadClearanceMeters': road_gap,
                            'maximumOutsideMeters': max_outside}
    assert results['smooth']['bytes'] < results['detail']['bytes']
    print(json.dumps({'urbanScope': 'PASS', 'landmarks': len(places), 'models': results}, ensure_ascii=False), flush=True)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, default=ROOT/'public')
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    validate(args.candidate, args.baseline)
