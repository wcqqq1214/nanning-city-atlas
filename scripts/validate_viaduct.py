"""Geometry checks for the actual elevated-road pilot, called by asset validation."""
import hashlib
import json
import math
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union


def validate_viaduct(network, geo, catalog, root):
    from viaduct import PLAN
    for name, digest in PLAN['inputHashes'].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, f'Stale viaduct plan: {name}'
    assert PLAN['sceneCenter'] == geo['center']
    assert 1800 < PLAN['main']['lengthMeters'] < 2100
    assert len(PLAN['ramps']) == 4
    source = json.loads((root / 'data/viaduct-source.json').read_text())
    ways = {e['id']: e for e in source['elements']}
    main_nodes = {n for i in PLAN['main']['osmIds'] for n in ways[i]['nodes']}
    cx, cy = geo['center']
    kx = 1113.2 * math.cos(math.radians(cy))
    floor_min, slope_max = float('inf'), 0
    for identity, path in network.paths.items():
        for a, b in zip(path.lengths, path.lengths[1:]):
            za, zb = network.level(identity, a), network.level(identity, b)
            assert all(math.isfinite(value) for value in [za, zb])
            slope_max = max(slope_max, abs(za - zb) / (b - a))
        for s in path.lengths:
            z, w = network.level(identity, s), network.width(identity, s)
            for offset in [-w, 0, w]:
                x, y, _ = path.at(s, offset)
                floor = max(network.surface(x, y, False), network.surface(x, y, True))
                gap = z - floor
                if identity == 'main':
                    floor_min = min(floor_min, gap)
                    assert gap > .115, f'Highway deck intersects terrain or the lower street at {s}'
                else:
                    assert gap > .027, f'Ramp {identity} intersects displayed terrain at {s}: {gap}'
    assert slope_max < .20, f'Discontinuous or excessively steep display ramp: {slope_max}'
    for ramp in PLAN['ramps']:
        identity = str(ramp['osmId'])
        path = network.paths[identity]
        assert ramp['joinNode'] in main_nodes
        assert any(ramp['groundNode'] in ways[i]['nodes'] for i in ramp['groundWays'])
        original = ways[ramp['osmId']]
        endpoint = original['geometry'][original['nodes'].index(ramp['groundNode'])]
        expected = ((endpoint['lon'] - cx) * kx, (endpoint['lat'] - cy) * 1113.2)
        assert math.dist(expected, path.points[-1]) < .00001, 'Ramp misses its actual mapped landing'
        mapped_line = LineString([((p['lon'] - cx) * kx, (p['lat'] - cy) * 1113.2) for p in original['geometry']])
        assert mapped_line.hausdorff_distance(LineString(path.points)) * 100 <= PLAN['assumptions']['rampPlanAdjustmentMaxMeters'], 'Ramp moved outside its bounded display adjustment'
        assert abs(network.level(identity, 0) - network.level('main', ramp['joinDistance'])) < .001
        assert abs(network.level(identity, path.length) - network.height(*path.points[-1]) - .065) < .00001
        assert any(network.barrier_open(ramp['joinDistance'] + delta, ramp['side'])
                   for delta in [-.5, -.25, 0, .25, .5]), 'A guardrail blocks the ramp merge'
        for s in path.lengths:
            distance, main_s = network.main.nearest(*path.at(s)[:2])
            if s > ramp['departure'] + .12 and distance < network.width('main', main_s) + network.width(identity, s):
                assert network.level('main', main_s) - network.level(identity, s) > .055, 'Ramp cuts through the side of the box girder'

    # Verify the retained generic parts are exactly the original line outside
    # the pilot. In particular, no full 10 km carriageway can disappear.
    wx, ex = [(lon - cx) * kx for lon in PLAN['main']['lonBounds']]
    clip = box(wx, -1000, ex, 1000)
    for index, pieces in PLAN['roadOverrides'].items():
        road = geo['roads'][int(index)]
        if road['name'] == '清厢快速路':
            original = LineString(road['points']).difference(clip)
            remaining = unary_union([LineString(p) for p in pieces])
            assert original.hausdorff_distance(remaining) < .00001
            assert abs(original.length - remaining.length) < .00001
        else:
            assert road['bridge'] and road['class'] == 'trunk_link' and not pieces
    assert len(network.piers) >= 35, 'Missing structural supports'
    buildings = unary_union([Polygon(b['rings'][0], b['rings'][1:]) for b in geo['buildings']])
    deck_footprints = unary_union([LineString(network.main.points).buffer(.145)] +
                                 [LineString(path.points).buffer(.0475) for _, path in network.ramps.values()])
    assert not deck_footprints.intersects(buildings), 'Elevated deck cuts through a mapped or infill building'
    crossing = unary_union([LineString(geo['roads'][i]['points']).buffer(
        .13 if geo['roads'][i]['class'] in ['trunk', 'primary', 'motorway'] else
        .085 if geo['roads'][i]['class'] == 'secondary' else .0475) for i in PLAN['blockedRoads']])
    for pier in network.piers:
        path, s = network.paths[pier['path']], pier['s']
        footprint = Polygon([path.at(s + ds, offset)[:2] for ds, offset in
                             [(-.039, -.025), (.039, -.025), (.039, .025), (-.039, .025)]])
        assert not footprint.intersects(buildings), 'Pier foundation overlaps a building'
        assert not footprint.intersects(crossing), 'Pier foundation blocks a cross street'
        assert pier['top'] > pier['bottom'] + .075
    place = next(p for p in catalog if p['id'] == PLAN['id'])
    assert place['modelled'] and place['layer'] == 'roads'
    point = ((place['lon'] - cx) * kx, (place['lat'] - cy) * 1113.2)
    assert network.main.nearest(*point)[0] < .001, 'Viaduct label is away from its bridge deck'
    print(f'Viaduct: {PLAN["main"]["lengthMeters"]} m, four connected ramps, {len(network.piers)} piers; '
          f'main terrain clearance >= {floor_min * 100:.2f} display metres; max display slope {slope_max:.1%}.', flush=True)


if __name__ == '__main__':
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
        return max(-.08, (h - 55) / 100 * 3)

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
    validate_viaduct(network, geo, json.loads((root / 'data/landmarks.json').read_text()), root)
