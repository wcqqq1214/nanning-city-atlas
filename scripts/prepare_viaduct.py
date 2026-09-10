"""Prepare the complete Qingxiang route from the retained OSM city snapshot."""
import argparse
import bisect
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]


def rounded(points):
    return [[round(float(v), 6) for v in p] for p in points]


def sample(line, step):
    count = max(1, math.ceil(line.length / step))
    return [line.interpolate(i / count, normalized=True).coords[0] for i in range(count + 1)]


def smooth(t):
    t = max(0, min(1, t))
    return t * t * (3 - 2 * t)


def elevated(e):
    return e['tags'].get('bridge', 'no') != 'no'


def capture_source(path):
    raw = json.loads((ROOT / 'work/geodata/osm.json').read_text())
    ways = {e['id']: e for e in raw['elements'] if e['type'] == 'way' and e.get('tags', {}).get('highway')}
    mains = {i for i, e in ways.items() if e['tags'].get('name') == '清厢快速路'}
    adjacency = defaultdict(set)
    for i, e in ways.items():
        for n in e['nodes']:
            adjacency[n].add(i)
    attached = {i for m in mains for n in ways[m]['nodes'] for i in adjacency[n]
                if ways[i]['tags']['highway'].endswith('_link')}
    links, todo = set(attached), list(attached)
    while todo:
        i = todo.pop()
        for n in ways[i]['nodes']:
            for j in adjacency[n] - mains - links:
                e = ways[j]
                if not e['tags']['highway'].endswith('_link'):
                    continue
                # Complete the Fengling junction. Other exits retain all bridge
                # pieces and their first ground tail, ending before the separate
                # Daxue interchange to the north of Qingchuan.
                if min(p['lon'] for p in e['geometry']) > 108.364 or elevated(ways[i]):
                    links.add(j)
                    todo.append(j)
    selected = mains | links
    boundary = {j for i in selected for n in ways[i]['nodes'] for j in adjacency[n] - selected}
    source = {'osmTimestamp': raw['osm3s']['timestamp_osm_base'],
              'attribution': '© OpenStreetMap contributors, ODbL 1.0',
              'origin': 'Retained city Overpass snapshot; original tags, node IDs and geometry.',
              'scope': 'Every named Qingxiang mainline way, Qingchuan approaches, urban exits and Fengling junction links.',
              'mainIds': sorted(mains), 'linkIds': sorted(links),
              'references': ['https://www.ngzb.com.cn/news/10144.html', 'https://v.gxnews.com.cn/a/17298053'],
              'elements': [ways[i] for i in sorted(selected | boundary)]}
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2) + '\n')


def prepare(capture=False):
    source_path = ROOT / 'data/viaduct-source.json'
    if capture:
        capture_source(source_path)
    source = json.loads(source_path.read_text())
    geo = json.loads((ROOT / 'public/data/geography.json').read_text())
    cx, cy = geo['center']
    kx, ky = 1113.2 * math.cos(math.radians(cy)), 1113.2
    def xy(p):
        return ((p['lon'] - cx) * kx, (p['lat'] - cy) * ky)
    ways = {e['id']: e for e in source['elements']}
    lines = {i: LineString([xy(p) for p in e['geometry']]) for i, e in ways.items()}
    main_ids, link_ids = source['mainIds'], source['linkIds']
    selected = set(main_ids + link_ids)
    indices = {}
    for identity in selected:
        e, line = ways[identity], lines[identity]
        matches = [i for i, r in enumerate(geo['roads']) if r['class'] == e['tags']['highway']
                   and r['name'] == e['tags'].get('name', '') and r['bridge'] == elevated(e)
                   and math.dist(r['points'][0], line.coords[0]) < .002
                   and math.dist(r['points'][-1], line.coords[-1]) < .002]
        if not matches and e['tags'].get('tunnel') == 'yes':
            # The city importer omits tunnels. Retain the source below ground;
            # there is no legacy surface mesh to replace.
            continue
        assert len(matches) == 1, f'Cannot match OSM way {identity} to the city road snapshot'
        indices[identity] = matches[0]
    chains = []
    for eastbound in [True, False]:
        ids = [i for i in main_ids if (lines[i].coords[-1][0] > lines[i].coords[0][0]) == eastbound]
        starts = {ways[i]['nodes'][0]: i for i in ids}
        ends = {ways[i]['nodes'][-1] for i in ids}
        first = next(i for i in ids if ways[i]['nodes'][0] not in ends)
        ordered, coords = [], []
        while first is not None:
            ordered.append(first)
            coords.extend(list(lines[first].coords)[bool(coords):])
            first = starts.get(ways[first]['nodes'][-1])
        assert set(ordered) == set(ids), 'Named mainline is disconnected'
        if not eastbound:
            coords.reverse()
        chains.append({'osmIds': ordered, 'line': LineString(coords)})
    wx = min(c['line'].bounds[0] for c in chains)
    ex = max(c['line'].bounds[2] for c in chains)
    def at_x(line, x):
        x = max(line.bounds[0], min(line.bounds[2], x))
        cut = line.intersection(LineString([(x, -1000), (x, 1000)]))
        assert cut.geom_type == 'Point', 'Ambiguous mainline alignment'
        return cut.coords[0]
    center, widths, bridge = [], [], []
    count = math.ceil((ex - wx) / .10)
    for j in range(count + 1):
        x = wx + (ex - wx) * j / count
        ys = [at_x(c['line'], x)[1] for c in chains]
        active = [i for i, c in enumerate(chains) if c['line'].bounds[0] <= x <= c['line'].bounds[2]]
        avg = sum(ys) / 2
        if len(active) == 1:
            other = chains[1 - active[0]]['line']
            distance = max(other.bounds[0] - x, x - other.bounds[2], 0)
            avg += (ys[active[0]] - avg) * smooth(distance / .45)
        center.append((x, avg))
        widths.append(max(.145 if len(active) == 2 else .073, max(abs(ys[i] - avg) + .073 for i in active)))
        bridge.append(any(elevated(ways[i]) and lines[i].bounds[0] <= x <= lines[i].bounds[2] for i in main_ids))
    main = LineString(center)
    def frame(s):
        p = main.interpolate(s)
        a, b = main.interpolate(max(0, s - .025)), main.interpolate(min(main.length, s + .025))
        dx, dy = b.x - a.x, b.y - a.y
        length = math.hypot(dx, dy)
        return p.x, p.y, -dy / length, dx / length
    main_nodes = {n for i in main_ids for n in ways[i]['nodes']}
    uses = Counter(n for i in selected for n in ways[i]['nodes'])
    boundary_nodes = {n for i in set(ways) - selected for n in ways[i]['nodes']}
    bindings = {}
    for i in link_ids:
        for n, p in zip(ways[i]['nodes'], ways[i]['geometry']):
            if n not in main_nodes:
                continue
            pos = xy(p)
            s = main.project(Point(pos))
            x, y, nx, ny = frame(s)
            offset = (pos[0] - x) * nx + (pos[1] - y) * ny
            side = 1 if offset > 0 else -1
            target = side * .10 if .1 < s < main.length - .1 else offset
            bindings[n] = {'distance': round(s, 6), 'side': side, 'point': [x + nx * target, y + ny * target]}
    ramps = []
    for identity in link_ids:
        e = ways[identity]
        cuts = [0] + [j for j, n in enumerate(e['nodes'][1:-1], 1) if uses[n] > 1 or n in boundary_nodes] + [len(e['nodes']) - 1]
        for part, (a, b) in enumerate(zip(cuts, cuts[1:])):
            original = LineString([xy(p) for p in e['geometry'][a:b + 1]])
            points = sample(original, .06)
            joints = [e['nodes'][a], e['nodes'][b]]
            shifts = [(bindings[n]['point'][0] - points[k][0], bindings[n]['point'][1] - points[k][1])
                      if n in bindings else (0, 0) for n, k in zip(joints, [0, -1])]
            shifted = []
            for j, p in enumerate(points):
                s = original.length * j / (len(points) - 1)
                delta = [0., 0.]
                for end, node in enumerate(joints):
                    if node not in bindings:
                        continue
                    distance = s if end == 0 else original.length - s
                    _, _, nx, ny = frame(main.project(Point(p)))
                    blend = smooth(distance / .55)
                    fade = smooth((original.length - distance) / .35)
                    for k, normal in enumerate([nx, ny]):
                        delta[k] += (shifts[end][k] * (1 - blend) + bindings[node]['side'] * normal * .055 * blend) * fade
                shifted.append([p[k] + delta[k] for k in [0, 1]])
            ramps.append({'id': f'{identity}:{part}', 'osmId': identity, 'nodeRange': [a, b],
                          'points': rounded(shifted), 'nodes': joints, 'bridge': elevated(e),
                          'tunnel': e['tags'].get('tunnel') == 'yes',
                          'layer': int(e['tags'].get('layer', 1 if elevated(e) else 0)),
                          'mainJoints': {str(k): bindings[n] for k, n in enumerate(joints) if n in bindings},
                          'boundaryJoints': {str(k): sorted(q for q in set(ways) - selected if n in ways[q]['nodes'])
                                             for k, n in enumerate(joints) if n in boundary_nodes}})
    overrides = {str(index): [] for index in indices.values()}
    envelope = main.buffer(max(widths) + .07).union(unary_union([LineString(r['points']).buffer(.07) for r in ramps]))
    buildings = unary_union([Polygon(b['rings'][0], b['rings'][1:]) for b in geo['buildings'] if Polygon(b['rings'][0]).intersects(envelope.buffer(.2))])
    blocked_roads = []
    for index, r in enumerate(geo['roads']):
        if r['bridge'] or not LineString(r['points']).intersects(envelope.buffer(.3)):
            continue
        for a, b in zip(r['points'], r['points'][1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            if length < .001:
                continue
            _, _, nx, ny = frame(main.project(Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)))
            if abs((dx * nx + dy * ny) / length) > .4:
                blocked_roads.append(index)
                break
    crossing = unary_union([LineString(geo['roads'][i]['points']).buffer(
        .13 if geo['roads'][i]['class'] in ['trunk', 'primary', 'motorway'] else .085 if geo['roads'][i]['class'] == 'secondary' else .0475)
        for i in blocked_roads])
    blockers = buildings.union(crossing).buffer(.025)
    pier_plans = []
    for identity, line in [('main', main)] + [(r['id'], LineString(r['points'])) for r in ramps if r['bridge']]:
        distances = []
        for j in range(1, math.floor(line.length / .34)):
            for shift in [0, -.04, .04, -.08, .08]:
                s = j * .34 + shift
                p = line.interpolate(s)
                if blockers.intersects(p.buffer(.032)) or any(abs(s - old) < .22 for old in distances):
                    continue
                distances.append(round(s, 6))
                break
        pier_plans.append({'path': identity, 'distances': distances})
    removed_trees = [i for i, (x, y, radius) in enumerate(geo['trees']) if envelope.distance(Point(x, y)) < radius + .035]
    # Exact stations at every mainline attachment keep its graph node and the
    # exported cross section identical, including unequal direction endpoints.
    lengths = [0.]
    for a, b in zip(center, center[1:]):
        lengths.append(lengths[-1] + math.dist(a, b))
    stations = sorted(set(lengths + [b['distance'] for b in bindings.values()]))
    expanded_widths, expanded_bridge = [], []
    for s in stations:
        j = max(0, min(len(lengths) - 2, bisect.bisect_right(lengths, s) - 1))
        t = (s - lengths[j]) / (lengths[j + 1] - lengths[j])
        expanded_widths.append(widths[j] * (1 - t) + widths[j + 1] * t)
        expanded_bridge.append(bridge[j if t < .5 else j + 1])
    center, widths, bridge = [], [], []
    for s, width, elevated_section in zip(stations, expanded_widths, expanded_bridge):
        point = rounded([main.interpolate(s).coords[0]])[0]
        if center and math.dist(point, center[-1]) < .01:
            continue
        center.append(point)
        widths.append(width)
        bridge.append(elevated_section)
    boundaries = []
    for chain in chains:
        for identity, endpoint in [(chain['osmIds'][0], 0), (chain['osmIds'][-1], -1)]:
            node = ways[identity]['nodes'][endpoint]
            others = sorted(i for i in set(ways) - selected if node in ways[i]['nodes'])
            if others:
                point = xy(ways[identity]['geometry'][endpoint])
                boundaries.append({'node': node, 'point': list(point), 'distance': main.project(Point(point)), 'ways': others})
    plan = {'id': 'qingxiang-viaduct', 'name': '清厢快速路 · 全线', 'scope': 'complete',
            'sceneCenter': geo['center'], 'osmTimestamp': source['osmTimestamp'],
            'inputHashes': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
                            ['data/viaduct-source.json', 'public/data/geography.json', 'public/data/terrain.json', 'data/stations-plan.json']},
            'main': {'osmIds': main_ids, 'chains': [c['osmIds'] for c in chains], 'points': rounded(center),
                     'halfWidths': [round(w, 6) for w in widths], 'bridge': bridge, 'boundaries': boundaries,
                     'lengthMeters': round(main.length * 100, 2), 'lonBounds': [wx / kx + cx, ex / kx + cx]},
            'ramps': ramps, 'mainConnections': len(bindings), 'roadOverrides': overrides,
            'roadOsmIds': {str(index): i for i, index in indices.items()},
            'restoredWays': sorted(selected - set(indices)), 'piers': pier_plans,
            'blockedRoads': blocked_roads, 'removedTrees': removed_trees,
            'assumptions': {'mainWidthMeters': 29, 'lanes': 6, 'rampWidthMeters': 7.3, 'pierSpacingMeters': 34,
                            'rampPlanAdjustmentMaxMeters': 10, 'geometryToleranceMeters': .4,
                            'geometryMaxSpanMeters': 60, 'landingBlendMeters': 100,
                            'verticalProfile': 'Bridge/ground classification from OSM; display elevations fit both DEM meshes, not a survey.'}}
    (ROOT / 'data/viaduct-plan.json').write_text(json.dumps(plan, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(f'Viaduct: {main.length * 100:.1f} m mainline, {len(main_ids)} main ways, {len(link_ids)} link ways / '
          f'{len(ramps)} sections, {len(bindings)} mainline connections, {len(removed_trees)} tree exclusions.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', action='store_true', help='Capture original features from work/geodata/osm.json')
    prepare(parser.parse_args().capture)
