"""P4 checks on decoded release meshes, against the immutable P3 baseline.

Keep exact earlier terrain/water/samples. Inspect local site support on actual
compressed triangles, and compare ordinary buildings outside the four sites.
"""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from shapely import intersects_xy
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from check_urban_block_exports import meshes
from validate_cultural_landmarks import glb
from landmark_sites import SPECS, reservation_rings, rect_ring
from landmark_vegetation import SETTINGS as VEGETATION_SETTINGS

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'work/urban-structure/baseline-p3'


def terrain_peak(triangles, site):
    peak = -math.inf
    w, s, e, n = site.bounds
    xy = triangles[:, :, [0, 2]]*np.array([1, -1])
    lo, hi = xy.min(axis=1), xy.max(axis=1)
    mask = (lo[:, 0] <= e) & (hi[:, 0] >= w) & (lo[:, 1] <= n) & (hi[:, 1] >= s)
    for tri, ring in zip(triangles[mask], xy[mask]):
        matrix = np.column_stack((ring, np.ones(3)))
        if abs(np.linalg.det(matrix)) < 1e-12:
            continue
        clipped = Polygon(ring).intersection(site)
        affine = np.linalg.solve(matrix, tri[:, 1])
        pieces = [clipped] if clipped.geom_type == 'Polygon' else getattr(clipped, 'geoms', [])
        for piece in pieces:
            if piece.geom_type == 'Polygon' and piece.area > 1e-12:
                points = np.asarray(piece.exterior.coords)
                peak = max(peak, float((np.column_stack((points, np.ones(len(points))))@affine).max()))
    assert math.isfinite(peak), 'No exported terrain under site'
    return peak


def surface_at(faces, x, y):
    """Vertical ray against horizontal triangles, including shared diagonals."""
    levels = []
    for face in faces:
        xy = face[:, [0, 2]]*np.array([1, -1])
        if np.ptp(face[:, 1]) < .0001 and Polygon(xy).buffer(.000001).covers(Point(x, y)):
            levels.append(float(face[:, 1].mean()))
    assert levels, 'Missing stair landing surface'
    return max(levels)


def decode_node(doc, decode, name):
    nodes = [n for n in doc['nodes'] if n.get('name') == name]
    assert len(nodes) == 1 and 'mesh' in nodes[0], f'Missing/duplicate node: {name}'
    node = nodes[0]
    assert not any(k in node for k in ['matrix', 'translation', 'rotation', 'scale'])
    result = {}
    for p in doc['meshes'][node['mesh']]['primitives']:
        mesh = decode(p)
        material = doc['materials'][p['material']]['name']
        result[material] = mesh.points[mesh.faces]
    return result


def outside_faces(materials, area):
    result = {}
    for material, faces in materials.items():
        centers = faces.mean(axis=1)
        result[material] = faces[~intersects_xy(area, centers[:, 0], -centers[:, 2])]
    return result


def same_faces(before, after):
    """Same per-material triangles within 1 cm, allowing Draco ordering jitter."""
    worst = 0
    for material in before.keys() | after.keys():
        a = before.get(material, np.empty((0, 3, 3)))
        b = after.get(material, np.empty((0, 3, 3)))
        assert len(a) == len(b), f'Outside face count changed: {material}: {len(a)} / {len(b)}'
        if not len(a):
            continue
        distance, order = cKDTree(b.mean(axis=1)).query(a.mean(axis=1))
        assert distance.max() < .0001, f'Outside triangle moved: {material}: {distance.max()}'
        matched = b[order]
        error = np.linalg.norm(a[:, :, None, :] - matched[:, None, :, :], axis=3).min(axis=2).max()
        assert error < .0001, f'Outside geometry changed: {material}: {error}'
        worst = max(worst, float(error))
    return worst*100


def main():
    geo = json.loads((ROOT/'public/data/geography.json').read_text())
    catalog = {p['id']: p for p in json.loads((ROOT/'data/landmarks.json').read_text())}
    published = {p['id']: p for p in json.loads((ROOT/'public/data/landmarks.json').read_text())}
    overview = json.loads((ROOT/'public/data/overview.json').read_text())
    support = overview['landmarkCalibration']['support']
    plan = json.loads((ROOT/'data/landmark-calibration-plan.json').read_text())['sites']
    assert overview['landmarkCalibration']['sourceHash'] == hashlib.sha256((ROOT/'data/landmark-calibration-source.json').read_bytes()).hexdigest()
    origins, sites, affected = {}, {}, []
    for identity, spec in SPECS.items():
        p = catalog[identity]
        x = (p['lon']-geo['center'][0])*1113.2*math.cos(math.radians(geo['center'][1]))
        y = (p['lat']-geo['center'][1])*1113.2
        origins[identity] = x, y
        sites[identity] = unary_union([Polygon([(x+u, y+v) for u, v in ring]) for ring in reservation_rings(identity)])
        affected.append(sites[identity])
        extent = spec.get('legacyClearExtentScene')
        if extent:
            w, h = extent
            affected.append(box(x-w/2, y-h/2, x+w/2, y+h/2))
        assert np.max(np.abs(np.array(published[identity]['position'])[[0, 2]]-[x, -y])) < .00051
    affected = unary_union(affected).buffer(.7)
    # Forest replacement uses a 15 m clearing margin and 55 m inward core;
    # allow the removed/reinstated edge tree's own crown beyond that boundary.
    vegetation_affected = affected.buffer(max(t[2] for t in geo['trees']))
    for identity, spec in VEGETATION_SETTINGS.items():
        radius = (spec['coreRadiusMeters']+spec['transitionMeters'])/100+max(t[2] for t in geo['trees'])
        vegetation_affected = vegetation_affected.union(Point(*origins[identity]).buffer(radius))
    dem = json.loads((ROOT/'public/data/terrain.json').read_text())
    w, s, e, n = geo['bounds']
    coarse_diagonal = math.hypot(2*(e-w)/(dem['cols']-1), 2*(n-s)/(dem['rows']-1))
    # A clearing affects a 15 m buffer, the 40 m crown-height transition,
    # then interpolation throughout a neighbouring coarse canopy triangle.
    forest_radius = .15+.4+coarse_diagonal
    forest_affected = affected.buffer(forest_radius-.7)
    for name in ['geography.json', 'terrain.json']:
        assert (ROOT/'public/data'/name).read_bytes() == (BASE/'public/data'/name).read_bytes()
    obstacle_data = json.loads((ROOT/'data/ground-roads-context.json').read_text())['obstacles']
    obstacles = unary_union([Polygon(p[0], p[1:]) for p in obstacle_data])
    for identity, shape in sites.items():
        assert shape.difference(obstacles.buffer(.001)).area < 1e-5, f'{identity}: missing road reservation'
    report = {'baseline': 'baseline-p3', 'profiles': {}}
    for profile, suffix, budget in [('detail', '', 26_000_000), ('smooth', '-mobile', 18_000_000)]:
        relative = Path(f'public/models/nanning-city{suffix}.glb')
        old, before = meshes(BASE/relative)
        new, after = meshes(ROOT/relative)
        assert after['bytes'] < budget, f'{profile}: exceeded original file budget'
        changed = sorted(k for k in old.keys() | new.keys() if old.get(k) != new.get(k))
        protected = [k for k in old if k.startswith('Terrain_')]
        protected += ['Water', 'ParkPaths_qingxiu', 'Landmark_qingxiu', 'Landmark_changyou',
                      'Landmark_yongjiang-bridge', 'RiverBridge_Details_yongjiang-bridge']
        for name in protected:
            assert old[name] == new[name], f'Accepted P1/P2/P3 geometry changed: {name}'
        doc, decode = glb(ROOT/relative)
        old_doc, old_decode = glb(BASE/relative)
        permitted = {'Landmark_'+identity for identity in SPECS}
        ordinary_checks = {}
        tree_checks = {}
        forest_checks = {}
        for name in changed:
            if name.startswith(('GroundRoads', 'ElevatedRoads', 'MinzuAvenue')):
                permitted.add(name)  # Full road interface and asset checks run separately.
            elif name.startswith(('Buildings_', 'Vegetation_')):
                parts = decode_node(doc, decode, name) if name in new else {}
                prior = decode_node(old_doc, old_decode, name) if name in old else {}
                all_points = np.concatenate([a.reshape(-1, 3) for a in [*parts.values(), *prior.values()]])
                low, high = all_points.min(axis=0), all_points.max(axis=0)
                assert box(low[0], -high[2], high[0], -low[2]).intersects(affected), f'Unrelated spatial node changed: {name}'
                permitted.add(name)
                if name.startswith('Buildings_'):
                    ordinary_checks[name] = same_faces(outside_faces(prior, affected), outside_faces(parts, affected))
                else:
                    # Forest surfaces can be retriangulated around changed
                    # holes. Independent trees must retain geometry and color.
                    before_trees = {m: f for m, f in prior.items() if not m.startswith('Forest ')}
                    after_trees = {m: f for m, f in parts.items() if not m.startswith('Forest ')}
                    tree_checks[name] = same_faces(outside_faces(before_trees, vegetation_affected), outside_faces(after_trees, vegetation_affected))
                    before_forest = {m: f for m, f in prior.items() if m.startswith('Forest ')}
                    after_forest = {m: f for m, f in parts.items() if m.startswith('Forest ')}
                    forest_checks[name] = same_faces(outside_faces(before_forest, forest_affected), outside_faces(after_forest, forest_affected))
        assert set(changed) <= permitted, f'Unexpected changes: {set(changed)-permitted}'
        terrain = []
        for node in doc['nodes']:
            if node.get('name', '').startswith('Terrain_'):
                for p in doc['meshes'][node['mesh']]['primitives']:
                    accessor = doc['accessors'][p['attributes']['POSITION']]
                    lo, hi = accessor['min'], accessor['max']
                    if box(lo[0], -hi[2], hi[0], -lo[2]).intersects(affected):
                        m = decode(p)
                        terrain.append(m.points[m.faces])
        terrain = np.concatenate(terrain)
        measured = {}
        for identity, shape in sites.items():
            materials = decode_node(doc, decode, 'Landmark_'+identity)
            faces = np.concatenate(list(materials.values()))
            points = faces.reshape(-1, 3)
            assert np.isfinite(points).all()
            areas = np.linalg.norm(np.cross(faces[:, 1]-faces[:, 0], faces[:, 2]-faces[:, 0]), axis=1)/2
            assert (areas > 1e-12).all(), f'{identity}: collapsed compressed triangles'
            x, y = origins[identity]
            w, h = catalog[identity]['clearExtent']
            assert intersects_xy(box(x-w/2, y-h/2, x+w/2, y+h/2).buffer(.0003), points[:, 0], -points[:, 2]).all()
            datum = published[identity]['position'][1]
            info = {'triangles': len(faces), 'bounds': [points.min(axis=0).tolist(), points.max(axis=0).tolist()]}
            if identity == 'confucius':
                stone = materials['Temple pale stone courts']
                courts = []
                for court in SPECS[identity]['courts']:
                    level = support[identity]['courtLevels'][court['id']]
                    ring = [(x+u/100, y+v/100) for u, v in rect_ring(court['rectMeters'])]
                    site = Polygon(ring)
                    peak = terrain_peak(terrain, site)
                    assert level-peak > .001, f'{profile}: terrain enters {court["id"]}'
                    selected = stone[np.max(np.abs(stone[:, :, 1]-level), axis=1) < .0001]
                    coverage = unary_union([Polygon(t[:, [0, 2]]*np.array([1, -1])) for t in selected]).intersection(site)
                    expected = site.area-(.24*.12 if court['id'] == 'entrance' else 0)
                    assert coverage.area/expected > .995, f'Court paving missing: {court["id"]}'
                    courts.append({'id': court['id'], 'level': level, 'minimumTerrainClearanceMeters': (level-peak)*100})
                pond = materials['Temple ceremonial pond']
                assert len(pond) == 2 and np.ptp(pond[:, :, 1]) < .0001
                assert abs(float(pond[:, :, 1].mean())-support[identity]['courtLevels']['entrance']+.008) < .0001
                info['courts'] = courts
                assert abs(datum-support[identity]['anchorLevel']) < .00051
            elif identity == 'diwang':
                peak = terrain_peak(terrain, shape)
                assert datum-peak > .001, f'{profile}: terrain enters Diwang podium'
                height = (points[:, 1].max()-datum)*100
                assert abs(height-276) < .06
                info.update(heightMeters=float(height), minimumTerrainClearanceMeters=(datum-peak)*100)
            elif identity == 'arts-center':
                platform = Polygon([(x+u, y+v) for u, v in reservation_rings(identity)[0]])
                peak = terrain_peak(terrain, platform)
                assert datum-peak > .005, f'{profile}: terrain enters arts plinth'
                height = float(points[:, 1].max()-datum)*100
                assert 49 < height < 56
                info.update(roofHeightMeters=height, minimumTerrainClearanceMeters=(datum-peak)*100)
            else:
                assert 17_000 < len(faces) < 21_000
                info['heightAboveAnchorMeters'] = float(points[:, 1].max()-datum)*100
                landings = {}
                for side, extent in [(-1, .267), (1, .2382)]:
                    px, py = x, y+side*extent
                    top = surface_at(materials['Zhenning warm stone paving'], px, py)
                    floor = terrain_peak(terrain, Point(px, py).buffer(.00005))
                    gap = (top-floor)*100
                    assert 0 < gap < .35, f'{profile}: fort entry ends above ground: {gap} m'
                    landings['north' if side == 1 else 'south'] = gap
                info['firstTreadClearanceMeters'] = landings
                from test_waterfront import ground, DEM
                from forest_canopy import terrain_surface
                leaves = decode_node(doc, decode, 'Vegetation_2_1')
                leaves = np.concatenate([f.reshape(-1, 3) for m, f in leaves.items() if m.startswith('Canopy ')])
                sources = np.asarray(geo['trees'])
                _, nearest = cKDTree(sources[:, :2]).query(leaves[:, [0, 2]]*np.array([1, -1]))
                tree_heights = {}
                for i in np.unique(nearest):
                    u, v, radius = sources[i]
                    if math.hypot(u-x, v-y) > VEGETATION_SETTINGS[identity]['coreRadiusMeters']/100:
                        continue
                    floor = max(.32, terrain_surface(u, v, ground, geo['bounds'], DEM['cols'], DEM['rows'], profile == 'smooth'))
                    height = float(leaves[nearest == i, 1].max()-floor)*100
                    assert height < 15, f'{profile}: unscaled fort tree {i}: {height} m'
                    tree_heights[int(i)] = height
                if profile == 'detail':
                    assert tree_heights, 'No fort trees measured in the full vegetation tier'
                info['coreTreeHeightMeters'] = tree_heights
            measured[identity] = info
        report['profiles'][profile] = {'before': before, 'after': after,
            'byteDelta': after['bytes']-before['bytes'], 'triangleDelta': after['triangles']-before['triangles'],
            'changedNodes': changed, 'protectedNodes': len(protected),
            'outsideBuildingsMaxErrorMeters': ordinary_checks, 'outsideTreesMaxErrorMeters': tree_checks,
            'forestInfluenceRadiusMeters': forest_radius*100, 'outsideForestMaxErrorMeters': forest_checks, 'sites': measured}
    for identity in SPECS:
        a, b = [report['profiles'][p]['sites'][identity] for p in ['detail', 'smooth']]
        assert a['triangles'] == b['triangles'] and np.allclose(a['bounds'], b['bounds'], atol=.0001)
    (ROOT/'work/urban-structure/p4/exports.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
