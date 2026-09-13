"""Measure P3 in decoded GLBs and preserve the accepted P1/P2 samples."""
import json
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from check_urban_block_exports import meshes
from validate_cultural_landmarks import glb
from test_waterfront import ground, GEO, DEM
from mountain_terrain import PLAN, vertex_heights, canopy_factor
from forest_canopy import coarse_terrain_surface, terrain_surface
from terrain_height import scene_height

ROOT = Path(__file__).resolve().parents[1]


def main():
    results = {}
    patch = box(*PLAN['bounds'])
    footprints = unary_union([Polygon(p[0], p[1:]) for group in PLAN['pathFootprints'].values() for p in group])
    source_points = np.asarray(PLAN['points'])
    affected_buildings = [b for b in GEO['buildings'] if patch.contains(Point(np.mean(b['rings'][0][:-1], axis=0)))]
    affected_footprints = unary_union([Polygon(b['rings'][0]) for b in affected_buildings]).buffer(.015)
    path_ids = sorted({i for tri, key in zip(PLAN['triangles'], PLAN['materials'])
                       if key in ['walk', 'steps', 'service'] for i in tri})
    for name in ['geography.json', 'terrain.json']:
        assert (ROOT/'public/data'/name).read_bytes() == (ROOT/'work/urban-structure/baseline-p2/public/data'/name).read_bytes()
    for profile, suffix, budget in [('detail', '', 26_000_000), ('smooth', '-mobile', 18_000_000)]:
        relative = Path(f'public/models/nanning-city{suffix}.glb')
        old, before = meshes(ROOT/'work/urban-structure/baseline-p2'/relative)
        new, after = meshes(ROOT/relative)
        assert after['bytes'] < budget
        changed = sorted(name for name in old.keys()|new.keys() if old.get(name) != new.get(name))
        for name in ['Terrain_2_1', 'Landmark_changyou', 'Landmark_yongjiang-bridge', 'RiverBridge_Details_yongjiang-bridge']:
            assert old[name] == new[name], f'Accepted P1/P2 sample changed: {name}'
        doc, decode = glb(ROOT/relative)
        pilot = unary_union([Polygon(b['rings'][0]) for b in GEO['buildings'] if b.get('blockId')]).buffer(.01)
        def building_faces(document, decoder, area, inside):
            record = Counter()
            node = next(n for n in document['nodes'] if n.get('name')=='Buildings_3_1')
            for primitive in document['meshes'][node['mesh']]['primitives']:
                mesh = decoder(primitive)
                material = document['materials'][primitive['material']]['name']
                for face in mesh.points[mesh.faces]:
                    x, y, z = face.mean(axis=0)
                    if area.contains(Point(x, -z))==inside:
                        record[(material, tuple(sorted(tuple(p) for p in np.round(face, 6))))] += 1
            return record
        old_doc, old_decode = glb(ROOT/'work/urban-structure/baseline-p2'/relative)
        old_pilot = building_faces(old_doc, old_decode, pilot, True)
        assert len(old_pilot)>100 and old_pilot==building_faces(doc, decode, pilot, True), 'P1 slab geometry or materials changed'
        assert building_faces(old_doc, old_decode, affected_footprints, False)==building_faces(doc, decode, affected_footprints, False), 'Unrelated buildings in the shared spatial node changed'
        paths, waters, tower, trees, terrain, tower_walls = [], [], [], [], [], []
        allowed = {'Water', 'Landmark_qingxiu', 'ParkPaths_qingxiu', 'Landmark_confucius'}
        # Confucius Temple is an existing consumer of the local ground sampler.
        # Its shape/materials must remain unchanged apart from that vertical move.
        def temple(document, decoder):
            node = next(n for n in document['nodes'] if n.get('name')=='Landmark_confucius')
            return {document['materials'][p['material']]['name']: decoder(p)
                    for p in document['meshes'][node['mesh']]['primitives']}
        old_temple, new_temple = temple(old_doc, old_decode), temple(doc, decode)
        assert old_temple.keys()==new_temple.keys()
        shift = np.median(np.concatenate([m.points[:, 1] for m in new_temple.values()]))-np.median(np.concatenate([m.points[:, 1] for m in old_temple.values()]))
        for material, mesh in old_temple.items():
            actual = new_temple[material]
            assert len(mesh.faces)==len(actual.faces)
            error, _ = cKDTree(actual.points).query(mesh.points+np.array([0, shift, 0]))
            assert error.max()<.0001, 'Confucius Temple changed beyond its ground anchor'
        # Local spatial nodes may contain unchanged geometry outside the patch.
        # Require their actual bounds to touch it; roads have their own full audit.
        for node in doc['nodes']:
            if 'mesh' not in node:
                continue
            name = node.get('name', '')
            primitives = doc['meshes'][node['mesh']]['primitives']
            if name.startswith('Vegetation_') and name.split('_')[1].lstrip('-').isdigit():
                for primitive in primitives:
                    if doc['materials'][primitive['material']]['name'].startswith('Canopy '):
                        trees.append(decode(primitive).points)
            if name.startswith(('GroundRoads', 'ElevatedRoads', 'MinzuAvenue')):
                allowed.add(name)
            elif name.startswith(('Terrain_', 'Buildings_', 'Vegetation_')):
                for primitive in primitives:
                    a = doc['accessors'][primitive['attributes']['POSITION']]
                    lo, hi = a['min'], a['max']
                    if box(lo[0], -hi[2], hi[0], -lo[2]).intersects(patch.buffer(.7)):
                        allowed.add(name)
                        if name.startswith('Terrain_'):
                            terrain.append(decode(primitive).points)
            if name not in {'ParkPaths_qingxiu', 'Water', 'Landmark_qingxiu'}:
                continue
            for primitive in primitives:
                material = doc['materials'][primitive['material']]['name']
                mesh = decode(primitive)
                faces = mesh.points[mesh.faces]
                if name == 'ParkPaths_qingxiu' and material != 'Qingxiu path edge':
                    paths.append(faces)
                elif name == 'Water':
                    waters.append(faces)
                elif name == 'Landmark_qingxiu':
                    tower.append(mesh.points)
                    if material=='Longxiang warm brick plaster':
                        tower_walls.append(mesh.points)
        unexpected = set(changed)-allowed
        assert not unexpected, f'Unexpected scope changes: {sorted(unexpected)}'
        paths = np.concatenate(paths)
        coverage = unary_union([Polygon(tri[:, [0, 2]]*np.array([1, -1])) for tri in paths])
        coverage_error = coverage.symmetric_difference(footprints).area/footprints.area
        assert coverage_error < .01, f'Park paving export coverage error: {coverage_error}'
        actual = paths.reshape(-1, 3)
        levels = np.asarray(vertex_heights(ground, tuple(GEO['bounds']), DEM['cols'], DEM['rows'], profile=='smooth', coarse_terrain_surface))
        used_ids = sorted({i for tri in PLAN['triangles'] for i in tri})
        expected_land = np.column_stack((source_points[used_ids, 0], levels[used_ids], -source_points[used_ids, 1]))
        terrain_error, _ = cKDTree(np.concatenate(terrain)).query(expected_land)
        assert terrain_error.max()<.001, 'Decoded mountain terrain differs from its final shared surface'
        expected = np.column_stack((source_points[path_ids, 0], levels[path_ids]+.006, -source_points[path_ids, 1]))
        distance, _ = cKDTree(actual).query(expected)
        assert distance.max() < .001, f'Park surface differs from final terrain: {distance.max()*100} m'
        waters = np.concatenate(waters)
        centers = waters.mean(axis=1)
        selected = np.zeros(len(waters), dtype=bool)
        lakes = []
        for lake in PLAN['waterBodies']:
            shape = Polygon(lake['rings'][0], lake['rings'][1:])
            mask = np.array([shape.contains(Point(x, -z)) for x, y, z in centers])
            assert mask.any(), 'Mountain lake missing from exported water mesh'
            selected |= mask
            level = scene_height(lake['levelMeters'], DEM)
            error = float(np.abs(waters[mask, :, 1]-level).max())
            assert error < .0001, 'Lake is not horizontal at its independent level'
            lakes.append({'osmId': lake.get('osmId'), 'sourceLevelMeters': lake['levelMeters'], 'maxExportErrorMeters': error*100})
        assert np.abs(waters[~selected, :, 1]-.26).max() < .0001, 'Changed water level outside mountain lakes'
        tower = np.concatenate(tower)
        place = next(p for p in json.loads((ROOT/'public/data/landmarks.json').read_text()) if p['id']=='qingxiu')
        tower_walls = np.concatenate(tower_walls)
        tower_floor = float(tower_walls[:, 1].min())
        tower_height = (float(tower[:, 1].max())-tower_floor)*100
        tower_diameter = float(np.linalg.norm(tower_walls[:, [0, 2]]*np.array([1, -1])-PLAN['towerCenterSceneXY'], axis=1).max())*200
        assert abs(tower_height-PLAN['source']['tower']['heightMeters']) < .002
        assert abs(tower_diameter-PLAN['source']['tower']['baseDiameterMeters']) < .01
        assert abs(tower_floor-place['position'][1]) < .00051, 'Published tower anchor differs from the model floor'
        tree_points = np.concatenate(trees)
        tree_sources = np.asarray(GEO['trees'])
        _, nearest = cKDTree(tree_sources[:, :2]).query(tree_points[:, [0, 2]]*np.array([1, -1]))
        measured_trees = {}
        for i in np.unique(nearest):
            x, y, radius = tree_sources[i]
            if not patch.buffer(-.5).contains(Point(x, y)):
                continue
            factor = canopy_factor(x, y)
            floor = terrain_surface(x, y, ground, GEO['bounds'], DEM['cols'], DEM['rows'], profile=='smooth')
            high = float(tree_points[nearest==i, 1].max())-floor
            assert high < (.43+.33*.850651)*factor+.007, 'A legacy oversized tree remains in the mountain sample'
            measured_trees[int(i)] = round(high*100, 3)
        assert len(measured_trees)>4
        results[profile] = {'before': before, 'after': after, 'byteDelta': after['bytes']-before['bytes'],
                            'triangleDelta': after['triangles']-before['triangles'], 'changedMeshNodes': changed,
                            'preservedP1P2Samples': True, 'pavingCoverageErrorPercent': coverage_error*100,
                            'maxPavingVertexErrorCm': float(distance.max())*10000,
                            'maxTerrainVertexErrorCm': float(terrain_error.max())*10000,
                            'towerHeightMeters': tower_height, 'towerBaseDiameterMeters': tower_diameter, 'scaledTreesChecked': len(measured_trees),
                            'localBuildingAnchors': len(affected_buildings), 'otherBuildingsUnchanged': True,
                            'confuciusAnchorShiftMeters': float(shift)*100, 'lakes': lakes}
    output = ROOT/'work/urban-structure/p3/exports.json'
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
