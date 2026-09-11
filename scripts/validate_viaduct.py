"""Verify full-route coverage, topology and exported Qingxiang geometry."""
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely.prepared import prep


def validate_viaduct(network, geo, catalog, root):
    from viaduct import PLAN
    for name, digest in PLAN['inputHashes'].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, f'Stale viaduct plan: {name}'
    assert PLAN['sceneCenter'] == geo['center']
    source = json.loads((root / 'data/viaduct-source.json').read_text())
    ways = {e['id']: e for e in source['elements']}
    main_ids = set(source['mainIds'])
    link_ids = set(source['linkIds'])
    assert PLAN['scope'] == 'complete'
    assert set(PLAN['main']['osmIds']) == main_ids == {i for i, e in ways.items() if e['tags'].get('name') == '清厢快速路'}
    assert len(main_ids) == 27 and 14_000 < PLAN['main']['lengthMeters'] < 14_500
    assert all(abs(a - b) < .000001 for a, b in zip(PLAN['main']['lonBounds'], [108.251108, 108.374333]))
    assert sorted(i for chain in PLAN['main']['chains'] for i in chain) == sorted(main_ids)
    for chain in PLAN['main']['chains']:
        for a, b in zip(chain, chain[1:]):
            assert ways[a]['nodes'][-1] == ways[b]['nodes'][0], 'A direction of the mainline is disconnected'
    assert {str(i) for i, r in enumerate(geo['roads']) if r['name'] == '清厢快速路'} <= set(PLAN['roadOverrides']), 'Some named mainline roads remain generic or unmodelled'
    assert all(not p for p in PLAN['roadOverrides'].values())
    assert set(PLAN['roadOsmIds'].values()) | set(PLAN['restoredWays']) == main_ids | link_ids
    assert all(ways[i]['tags'].get('tunnel') == 'yes' for i in PLAN['restoredWays'])
    cx, cy = geo['center']
    kx = 1113.2 * math.cos(math.radians(cy))
    def xy(p):
        return ((p['lon'] - cx) * kx, (p['lat'] - cy) * 1113.2)
    paths = network.paths
    decks = {}
    slope_max, floor_min = 0., float('inf')
    for identity, path in paths.items():
        quads = []
        for a, b in zip(network.sections[identity], network.sections[identity][1:]):
            polygon = Polygon([path.at(s, side * network.width(identity, s))[:2]
                               for s, side in [(a, -1), (b, -1), (b, 1), (a, 1)]])
            assert polygon.is_valid and polygon.area > 0, f'Folded road cross section: {identity} at {a}'
            quads.append(polygon)
        decks[identity] = unary_union(quads)
        for a, b in zip(path.lengths, path.lengths[1:]):
            za, zb = network.render_level(identity, a), network.render_level(identity, b)
            assert math.isfinite(za) and math.isfinite(zb)
            slope_max = max(slope_max, abs(za - zb) / (b - a))
        tunnel = identity != 'main' and network.ramps[identity][0]['tunnel']
        for s in path.lengths:
            z, w = network.render_level(identity, s), network.width(identity, s)
            assert abs(z - network.level(identity, s)) <= PLAN['assumptions']['geometryToleranceMeters'] / 100 + 1e-8
            if tunnel:
                continue
            gap = z - max(network.surface(*path.at(s, offset)[:2], mobile)
                          for offset in [-w, 0, w] for mobile in [False, True])
            assert gap > .027, f'{identity} intersects displayed terrain at {s}: {gap}'
            if network.is_bridge(identity, s):
                floor_min = min(floor_min, gap)
                assert gap > .115, f'Bridge has inadequate display clearance: {identity}'
    assert slope_max < .20, f'Excessive display grade: {slope_max}'
    main_coverage = decks['main'].buffer(.012)
    for identity in main_ids:
        raw = LineString([xy(p) for p in ways[identity]['geometry']])
        assert raw.difference(main_coverage).length < .001, f'Incomplete mainline way {identity}'
    node_levels, covered = defaultdict(list), defaultdict(set)
    for ramp in PLAN['ramps']:
        identity = ramp['id']
        path = paths[identity]
        original = ways[ramp['osmId']]
        a, b = ramp['nodeRange']
        covered[ramp['osmId']].update(range(a, b))
        raw = LineString([xy(p) for p in original['geometry'][a:b + 1]])
        assert raw.hausdorff_distance(LineString(path.points)) * 100 <= PLAN['assumptions']['rampPlanAdjustmentMaxMeters']
        assert ramp['bridge'] == (original['tags'].get('bridge', 'no') != 'no')
        assert ramp['tunnel'] == (original['tags'].get('tunnel') == 'yes')
        for end, node in enumerate(ramp['nodes']):
            s = 0 if end == 0 else path.length
            z = network.render_level(identity, s)
            node_levels[node].append(z)
            if str(end) in ramp['mainJoints']:
                binding = ramp['mainJoints'][str(end)]
                assert abs(z - network.render_level('main', binding['distance'])) < .002, f'Mainline seam: {identity}'
                if .1 < binding['distance'] < network.main.length - .1:
                    side_open = any(network.barrier_open(network.main.nearest(*path.at(s)[:2])[1], binding['side'])
                                    for s in path.lengths if network.merge_at(identity, s))
                    terminal_entry = any(decks[identity].intersects(LineString([
                        network.main.at(s, side * network.width('main', s))[:2] for side in [-1, 1]]))
                        for s in [0, network.main.length])
                    assert side_open or terminal_entry, f'Guardrail blocks a merge: {identity}'
            else:
                expected = xy(original['geometry'][a if end == 0 else b])
                assert math.dist(expected, path.at(s)[:2]) < .00001, 'Moved a real ramp junction'
            if str(end) in ramp['boundaryJoints']:
                assert abs(z - network.road_level(*path.at(s)[:2])) < .0001, f'Ramp misses its ground approach: {identity}'
    assert set(covered) == link_ids
    for identity, segments in covered.items():
        assert segments == set(range(len(ways[identity]['nodes']) - 1)), f'Missing source section: {identity}'
    assert all(max(v) - min(v) < .00001 for v in node_levels.values()), 'Split ramps have a height seam'
    buildings = unary_union([Polygon(b['rings'][0], b['rings'][1:]) for b in geo['buildings']])
    prepared_buildings = prep(buildings)
    assert not prepared_buildings.intersects(unary_union(list(decks.values()))), 'Route overlaps mapped or infill buildings'
    crossing = unary_union([LineString(geo['roads'][i]['points']).buffer(
        .13 if geo['roads'][i]['class'] in ['trunk', 'primary', 'motorway'] else .085 if geo['roads'][i]['class'] == 'secondary' else .0475)
        for i in PLAN['blockedRoads']])
    prepared_crossing = prep(crossing)
    prepared_decks = {identity: prep(deck) for identity, deck in decks.items()}
    assert len(network.piers) > 250, 'Full route is missing bridge supports'
    for pier in network.piers:
        path, s = paths[pier['path']], pier['s']
        assert network.is_bridge(pier['path'], s), 'Ground section has viaduct supports'
        footprint = Polygon([path.at(s + ds, offset)[:2] for ds, offset in [(-.039, -.025), (.039, -.025), (.039, .025), (-.039, .025)]])
        assert not prepared_buildings.intersects(footprint), 'Support blocks a building'
        assert not prepared_crossing.intersects(footprint), 'Support blocks a ground cross street'
        for other, deck in prepared_decks.items():
            if other == pier['path'] or not deck.intersects(footprint):
                continue
            along = paths[other].nearest(pier['x'], pier['y'])[1]
            assert network.render_level(other, along) >= pier['top'] + .07, 'Upper support penetrates a lower route'
    # These are actual source-separated interior crossings, including the
    # layer-2 Qingchuan and Fengling ramps and the Xiangzhu underpass.
    interiors = 0
    entries = list(paths.items())
    for i, (a, pa) in enumerate(entries):
        la = LineString(pa.points)
        for b, pb in entries[i + 1:]:
            lb = LineString(pb.points)
            cross = la.intersection(lb)
            points = [cross] if cross.geom_type == 'Point' else list(cross.geoms) if cross.geom_type == 'MultiPoint' else []
            for p in points:
                sa, sb = la.project(p), lb.project(p)
                if min(sa, pa.length - sa, sb, pb.length - sb) < .03:
                    continue
                gap = abs(network.render_level(a, sa) - network.render_level(b, sb))
                assert gap > .055, f'Grade-separated roads collide: {a} / {b}: {gap}'
                interiors += 1
    assert interiors >= 7, 'Interchange crossing checks are missing'
    place = next(p for p in catalog if p['id'] == PLAN['id'])
    assert place['modelled'] and place['layer'] == 'roads' and 'closeDistance' not in place
    assert place['cameraDistance'] >= 65, 'Full route needs overall framing'
    assert network.main.nearest(*xy(place))[0] < .001
    print(f'Complete Qingxiang: {PLAN["main"]["lengthMeters"]} m, {len(main_ids)} main ways, {len(link_ids)} complete link ways, '
          f'{PLAN["mainConnections"]} mainline connections, {len(network.piers)} piers, {interiors} separated crossings; '
          f'bridge clearance >= {floor_min * 100:.2f} display m; max display slope {slope_max:.1%}.', flush=True)


def load_network():
    import sys
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'blender'))
    from viaduct import Viaduct
    from station_landmarks import STATIONS, ground_blend
    from forest_canopy import terrain_surface
    geo = json.loads((root / 'public/data/geography.json').read_text())
    dem = json.loads((root / 'public/data/terrain.json').read_text())
    west, south, east, north = geo['bounds']
    cols, rows = dem['cols'], dem['rows']
    values = dem.get('sceneHeights', dem['heights'])

    def terrain(x, y):
        u = max(0, min(cols - 1.001, (x - west) / (east - west) * (cols - 1)))
        v = max(0, min(rows - 1.001, (north - y) / (north - south) * (rows - 1)))
        i, j, a, b = int(u), int(v), u - int(u), v - int(v)
        h = ((1 - a) * values[j * cols + i] + a * values[j * cols + i + 1]) * (1 - b)
        h += ((1 - a) * values[(j + 1) * cols + i] + a * values[(j + 1) * cols + i + 1]) * b
        from terrain_height import scene_height
        return scene_height(h,dem)

    kx = 1113.2 * math.cos(math.radians(geo['center'][1]))
    sites = {key: ((p['center'][0] - geo['center'][0]) * kx, (p['center'][1] - geo['center'][1]) * 1113.2)
             for key, p in STATIONS.items()}

    def height(x, y):
        z = terrain(x, y)
        for identity, (sx, sy) in sites.items():
            if abs(x - sx) < 10 and abs(y - sy) < 10:
                blend = ground_blend(identity, x - sx, y - sy)
                z = terrain(sx, sy) * (1 - blend) + z * blend
        return z

    network = Viaduct(height, lambda x, y, mobile: terrain_surface(x, y, height, geo['bounds'], cols, rows, lightweight=mobile))
    return network, geo, json.loads((root / 'data/landmarks.json').read_text()), root


if __name__ == '__main__':
    network, geo, catalog, root = load_network()
    validate_viaduct(network, geo, catalog, root)
