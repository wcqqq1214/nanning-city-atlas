"""Prepare the extended Qingxiang urban viaduct from the retained OSM snapshot.

The two mapped carriageways and eight node-connected ramps control the route.
Cross sections and support locations are display interpretations, not a survey.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
MAIN_IDS = [685249176, 808502317]
RAMP_IDS = [685249164, 685249167, 685249169, 685249170,
            685249160, 685249162, 685249180, 685249181]
WEST, EAST = 108.285, 108.339


def rounded(points):
    return [[round(float(v), 6) for v in p] for p in points]


def sample(line, step):
    count = max(1, math.ceil(line.length / step))
    return [line.interpolate(i / count, normalized=True).coords[0] for i in range(count + 1)]


def smooth(t):
    t = max(0, min(1, t))
    return t * t * (3 - 2 * t)


def prepare(capture=False):
    source_path = ROOT / 'data/viaduct-source.json'
    geo = json.loads((ROOT / 'public/data/geography.json').read_text())
    cx, cy = geo['center']
    kx, ky = 1113.2 * math.cos(math.radians(cy)), 1113.2

    def xy(p):
        return ((p['lon'] - cx) * kx, (p['lat'] - cy) * ky)

    if capture:
        raw = json.loads((ROOT / 'work/geodata/osm.json').read_text())
        selected = [e for e in raw['elements'] if e['type'] == 'way' and e['id'] in MAIN_IDS + RAMP_IDS]
        assert len(selected) == len(MAIN_IDS) + len(RAMP_IDS)
        nodes = {n for e in selected if e['id'] in RAMP_IDS for n in [e['nodes'][0], e['nodes'][-1]]}
        ground = [e for e in raw['elements'] if e['type'] == 'way' and e.get('tags', {}).get('highway')
                  and e['id'] not in MAIN_IDS + RAMP_IDS and nodes.intersection(e.get('nodes', []))]
        source = {'osmTimestamp': raw['osm3s']['timestamp_osm_base'],
                  'attribution': '© OpenStreetMap contributors, ODbL 1.0',
                  'origin': 'Retained city Overpass snapshot; original tags, node IDs and geometry.',
                  'references': ['https://v.gxnews.com.cn/a/17298053',
                                 'https://news.gxnews.com.cn/staticpages/20180330/newgx5abd6cc5-17197559.shtml'],
                  'elements': selected + ground}
        source_path.write_text(json.dumps(source, ensure_ascii=False, indent=2) + '\n')
    source = json.loads(source_path.read_text())
    ways = {e['id']: e for e in source['elements']}
    lines = {i: LineString([xy(p) for p in e['geometry']]) for i, e in ways.items()}
    wx, ex = (WEST - cx) * kx, (EAST - cx) * kx
    clip = box(wx, -1000, ex, 1000)
    indices = {}
    for identity in MAIN_IDS + RAMP_IDS:
        e, line = ways[identity], lines[identity]
        matches = [i for i, r in enumerate(geo['roads']) if r['class'] == e['tags']['highway']
                   and r['name'] == e['tags'].get('name', '') and r['bridge']
                   and math.dist(r['points'][0], line.coords[0]) < .002
                   and math.dist(r['points'][-1], line.coords[-1]) < .002]
        assert len(matches) == 1, f'Cannot match OSM way {identity} to the city road snapshot'
        indices[identity] = matches[0]

    def at_x(line, x):
        cut = line.intersection(LineString([(x, -1000), (x, 1000)]))
        assert cut.geom_type == 'Point', 'Pilot must not contain an ambiguous folded alignment'
        return cut.coords[0]

    legacy = [LineString(geo['roads'][indices[i]]['points']) for i in MAIN_IDS]
    count = math.ceil((ex - wx) / .10)
    center = []
    for j in range(count + 1):
        x = wx + (ex - wx) * j / count
        raw_y = sum(at_x(lines[i], x)[1] for i in MAIN_IDS) / 2
        old_y = sum(at_x(line, x)[1] for line in legacy) / 2
        blend = smooth(min(x - wx, ex - x) / .9)
        center.append((x, old_y * (1 - blend) + raw_y * blend))
    main = LineString(center)
    main_points = sample(main, .10)
    main = LineString(main_points)
    lengths = [0]
    for a, b in zip(main_points, main_points[1:]):
        lengths.append(lengths[-1] + math.dist(a, b))
    end_widths = [math.dist(at_x(legacy[0], x), at_x(legacy[1], x)) / 2 + .13 for x in [wx, ex]]
    widths = []
    for s in lengths:
        edge = end_widths[0] if s < main.length / 2 else end_widths[1]
        widths.append(.145 + (edge - .145) * (1 - smooth(min(s, main.length - s) / 1.1)))

    def frame(s):
        p = main.interpolate(s)
        a, b = main.interpolate(max(0, s - .025)), main.interpolate(min(main.length, s + .025))
        dx, dy = b.x - a.x, b.y - a.y
        length = math.hypot(dx, dy)
        return p.x, p.y, -dy / length, dx / length

    ramps = []
    for identity in RAMP_IDS:
        e = ways[identity]
        start_joins = any(e['nodes'][0] in ways[i]['nodes'] for i in MAIN_IDS)
        nodes = e['nodes'] if start_joins else e['nodes'][::-1]
        pts = list(lines[identity].coords)
        if not start_joins:
            pts.reverse()
        join_s = main.project(Point(pts[0]))
        x, y, nx, ny = frame(join_s)
        side = 1 if (pts[0][0] - x) * nx + (pts[0][1] - y) * ny > 0 else -1
        raw_line = LineString(pts)
        shifted = []
        for p in sample(raw_line, .06):
            d = raw_line.project(Point(p))
            sx, sy, nnx, nny = frame(main.project(Point(p)))
            original_offset = (pts[0][0] - x) * nx + (pts[0][1] - y) * ny
            initial = .10 - abs(original_offset)
            shift = (initial + (.055 - initial) * smooth(d / .55)) * smooth((raw_line.length - d) / .35)
            shifted.append((p[0] + side * nnx * shift, p[1] + side * nny * shift))
        line = LineString(shifted)
        points = sample(line, .06)
        line = LineString(points)
        departure = next((line.project(Point(p)) for p in points
                          if main.distance(Point(p)) >= .145 + .073 / 2 + .003), None)
        assert departure is not None and departure < line.length * .58, f'Ramp {identity} cannot leave the deck before descending'
        ground = [q['id'] for q in source['elements'] if q['id'] not in MAIN_IDS + RAMP_IDS
                  and nodes[-1] in q['nodes']]
        assert ground, f'Ramp {identity} has no mapped ground connection'
        ramps.append({'osmId': identity, 'points': rounded(points), 'joinNode': nodes[0],
                      'groundNode': nodes[-1], 'groundWays': ground, 'joinDistance': round(join_s, 6),
                      'departure': round(departure, 6), 'side': side, 'towardsMain': not start_joins})

    overrides = {}
    for identity, index in indices.items():
        line = LineString(geo['roads'][index]['points'])
        if identity in RAMP_IDS:
            pieces = []
        else:
            remaining = line.difference(clip)
            pieces = [remaining] if remaining.geom_type == 'LineString' else list(remaining.geoms)
        overrides[str(index)] = [rounded(p.coords) for p in pieces if p.length > .001]
    envelope = main.buffer(.23).union(unary_union([LineString(r['points']).buffer(.055) for r in ramps]))
    nearby_buildings = [b for b in geo['buildings'] if Polygon(b['rings'][0]).intersects(envelope.buffer(.2))]
    buildings = unary_union([Polygon(b['rings'][0], b['rings'][1:]) for b in nearby_buildings])
    blocked_roads = []
    for index, r in enumerate(geo['roads']):
        if r['bridge'] or not LineString(r['points']).intersects(envelope.buffer(.3)):
            continue
        # Parallel streets get narrow raised support islands. Cross streets,
        # access roads and junctions remain clear of all pier foundations.
        for a, b in zip(r['points'], r['points'][1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            if length < .001:
                continue
            _, _, nx, ny = frame(main.project(Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)))
            if abs((dx * nx + dy * ny) / length) > .4:
                blocked_roads.append(index)
                break
    blocked_roads = sorted(set(blocked_roads))
    crossing = unary_union([LineString(geo['roads'][i]['points']).buffer(
        .13 if geo['roads'][i]['class'] in ['trunk', 'primary', 'motorway'] else
        .085 if geo['roads'][i]['class'] == 'secondary' else .0475) for i in blocked_roads])
    blockers = buildings.union(crossing).buffer(.025)
    pier_plans = []
    for identity, line in [('main', main)] + [(str(r['osmId']), LineString(r['points'])) for r in ramps]:
        distances = []
        for j in range(1, math.floor(line.length / .34)):
            nominal = j * .34
            for shift in [0, -.04, .04, -.08, .08]:
                s = nominal + shift
                p = line.interpolate(s)
                if blockers.intersects(p.buffer(.032)) or any(abs(s - old) < .22 for old in distances):
                    continue
                distances.append(round(s, 6))
                break
        pier_plans.append({'path': identity, 'distances': distances})
    removed_trees = [i for i, (x, y, radius) in enumerate(geo['trees'])
                     if envelope.distance(Point(x, y)) < radius + .035]
    plan = {'id': 'qingxiang-viaduct', 'name': '清厢快速路 · 城区高架',
            'sceneCenter': geo['center'], 'osmTimestamp': source['osmTimestamp'],
            'inputHashes': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                            for p in ['data/viaduct-source.json', 'public/data/geography.json',
                                      'public/data/terrain.json', 'data/stations-plan.json']},
            'main': {'osmIds': MAIN_IDS, 'points': rounded(main_points), 'halfWidths': [round(w, 6) for w in widths],
                     'lengthMeters': round(main.length * 100, 2), 'lonBounds': [WEST, EAST]},
            'ramps': ramps, 'roadOverrides': overrides, 'piers': pier_plans,
            'blockedRoads': blocked_roads, 'removedTrees': removed_trees,
            'assumptions': {'mainWidthMeters': 29, 'lanes': 6, 'rampWidthMeters': 7.3,
                            'pierSpacingMeters': 34, 'rampPlanAdjustmentMaxMeters': 6.5,
                            'geometryToleranceMeters': .4, 'geometryMaxSpanMeters': 60,
                            'landingBlendMeters': 100,
                            'verticalProfile': 'Display clearance fitted to both terrain meshes; no surveyed bridge elevation.'}}
    (ROOT / 'data/viaduct-plan.json').write_text(json.dumps(plan, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(f'Viaduct: {main.length * 100:.1f} m mainline, {len(ramps)} ramps, {len(removed_trees)} tree exclusions, {len(overrides)} replaced road features.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', action='store_true', help='Capture the original features from work/geodata/osm.json')
    prepare(parser.parse_args().capture)
