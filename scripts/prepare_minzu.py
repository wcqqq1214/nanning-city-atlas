"""Capture and prepare Minzu Avenue from the retained city OSM snapshot."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
NAMES = {'民族大道', '民族大道辅路'}


def prepare(capture=False):
    source_path = ROOT / 'data/minzu-source.json'
    if capture:
        raw = json.loads((ROOT / 'work/geodata/osm.json').read_text())
        ways = [e for e in raw['elements'] if e['type'] == 'way' and e.get('tags', {}).get('highway')]
        selected = [e for e in ways if e['tags'].get('name') in NAMES]
        nodes = {n for e in selected for n in e['nodes']}
        source = {'osmTimestamp': raw['osm3s']['timestamp_osm_base'],
                  'attribution': '© OpenStreetMap contributors, ODbL 1.0',
                  'origin': 'Retained city Overpass snapshot; original geometry, node IDs and tags.',
                  'selectedIds': sorted(e['id'] for e in selected),
                  'elements': [e for e in ways if e in selected or nodes.intersection(e['nodes'])]}
        source_path.write_text(json.dumps(source, ensure_ascii=False, indent=2) + '\n')
    source = json.loads(source_path.read_text())
    geo = json.loads((ROOT / 'public/data/geography.json').read_text())
    cx, cy = geo['center']
    kx = 1113.2 * math.cos(math.radians(cy))
    def xy(p): return ((p['lon'] - cx) * kx, (p['lat'] - cy) * 1113.2)
    clip = box(*geo['bounds'])
    selected = set(source['selectedIds'])
    uses = defaultdict(list)
    for e in source['elements']:
        for n in e['nodes']: uses[n].append(e)
    paths, tunnels, omitted, replaced = [], [], [], []
    candidates = {i: r for i, r in enumerate(geo['roads']) if r['name'] in NAMES}
    for e in source['elements']:
        if e['id'] not in selected: continue
        tags = e['tags']
        original = LineString([xy(p) for p in e['geometry']]).intersection(clip)
        lines = [original] if original.geom_type == 'LineString' else list(original.geoms)
        for part, line in enumerate(lines):
            if line.is_empty or line.length < .001: continue
            if tags.get('tunnel') == 'yes':
                tunnels.append({'osmId': e['id'], 'points': list(line.coords), 'tags': tags})
                continue
            matches = [i for i, r in candidates.items() if r['name'] == tags['name']
                       and r['class'] == tags['highway']
                       and r['bridge'] == (tags.get('bridge', 'no') != 'no')
                       and math.dist(r['points'][0], line.coords[0]) < .002
                       and math.dist(r['points'][-1], line.coords[-1]) < .002]
            assert len(matches) == 1, (e['id'], matches)
            replaced.extend(matches)
            frontage = tags['name'] == '民族大道辅路'
            if frontage:
                omitted.append({'osmId': e['id'], 'roadIndex': matches[0], 'tags': tags,
                                'points': list(line.coords), 'reason': 'Main carriageway only; omit side roads and non-motor traffic.'})
                continue
            source_points = list(line.coords)
            line = line.simplify(.025, preserve_topology=True)
            # Deliberately simplified six-lane boulevard, with three lanes per
            # direction. Original lane/turn tags remain available as provenance.
            lanes, width = 3, .10
            junctions, node_keys = [], []
            for n, p in zip(e['nodes'], e['geometry']):
                pos = xy(p)
                if not clip.covers(Point(pos)): continue
                others = [o for o in uses[n] if o['id'] != e['id']]
                s = line.project(Point(pos))
                node_keys.append([round(s, 6), str(n)])
                if any(o['id'] not in selected or o['tags'].get('name') != tags['name'] for o in others) or len(others) > 1:
                    junctions.append(round(s, 6))
            # Sample original curves at <= 12 m, retaining every OSM vertex.
            stations = {0., line.length}
            for p in line.coords: stations.add(line.project(Point(p)))
            for i in range(1, math.ceil(line.length / .12)):
                stations.add(i * line.length / math.ceil(line.length / .12))
            stations.update(s for s, _ in node_keys)
            ordered = sorted(stations)
            cleaned = [ordered[0]]
            for s in ordered[1:]:
                if s - cleaned[-1] > 1e-5: cleaned.append(s)
            cleaned[-1] = line.length
            paths.append({'id': f'{e["id"]}:{part}', 'osmId': e['id'], 'roadIndex': matches[0],
                          'tags': tags, 'lanes': lanes, 'width': width, 'frontage': frontage,
                          'bridge': tags.get('bridge', 'no') != 'no',
                          'points': [[round(v, 6) for v in line.interpolate(s).coords[0]] for s in cleaned],
                          'sourcePoints': source_points,
                          'sourceNodes': node_keys, 'junctions': junctions,
                          'lengthMeters': round(line.length * 100, 2)})
    assert sorted(replaced) == sorted(candidates), 'Some old Minzu strips would remain or be replaced twice'
    # Existing trees within the more accurate carriageways must not pierce asphalt.
    paved = unary_union([LineString(p['points']).buffer(p['width']/2 + .012) for p in paths])
    removed = [i for i, (x, y, r) in enumerate(geo['trees']) if paved.intersects(Point(x, y).buffer(r * .65))]
    plan = {'sceneCenter': geo['center'], 'bbox': geo['bbox'], 'osmTimestamp': source['osmTimestamp'],
            'inputHashes': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                            for p in ['data/minzu-source.json', 'public/data/geography.json', 'public/data/terrain.json']},
            'assumptions': {'laneWidthMeters': 3, 'geometryMaxSpanMeters': 12,
                            'alignmentToleranceMeters': 2.5, 'displayLanesPerDirection': 3,
                            'nanhuLevelExtent': [52.5, 59.0, -10.7, -10.0],
                            'junctionOpeningMeters': 20, 'lampSpacingMeters': 90,
                            'note': 'Main carriageways only, simplified to six lanes; side roads omitted. Nanhu crossing and approaches share one level. Source tags retain actual OSM lane counts; this is not a surveyed road design.'},
            'paths': paths, 'tunnels': tunnels, 'omittedPaths': omitted,
            'replacedRoads': sorted(replaced), 'removedTrees': removed,
            'stats': {'mainWays': sum(not p['frontage'] for p in paths),
                      'frontageWays': sum(p['frontage'] for p in paths),
                      'omittedFrontageWays': len(omitted),
                      'bridgeWays': sum(p['bridge'] for p in paths), 'tunnelWays': len(tunnels),
                      'carriagewayLengthMeters': round(sum(p['lengthMeters'] for p in paths), 2)}}
    (ROOT / 'data/minzu-plan.json').write_text(json.dumps(plan, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(plan['stats'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--capture', action='store_true')
    prepare(parser.parse_args().capture)
