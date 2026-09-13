"""Audit a P5 candidate before city integration; this is not a GLB acceptance test."""
import argparse
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path

from shapely.geometry import Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

from prepare_geodata import geom_for, parts
from prepare_building_quality import POLICY, SOURCE, use_group


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(before, after, snapshot):
    import math
    assert len(before['buildings']) == len(after['buildings'])
    for key, value in before.items():
        if key != 'buildings':
            assert after[key] == value, f'Unintended non-building change: {key}'
    assert set(after) == set(before) | {'buildingQuality'}
    plan = after['buildingQuality']
    assert plan['sourceHash'] == digest(SOURCE)
    refs = {f"osm/{e['type']}/{e['id']}": e for e in snapshot['elements']}
    cx, cy = before['center']
    project = lambda lon, lat: ((lon-cx)*1113.2*math.cos(math.radians(cy)), (lat-cy)*1113.2)
    originals = {b['id']: b for b in plan['originalBuildings']}
    assert len(originals) == len(plan['originalBuildings'])
    counts = Counter()
    rows = []
    known = {}
    for b in before['buildings']:
        if b['source'] == 'osm' and b.get('mappedHeight'):
            known.setdefault(b['sourceRef'], []).append(b)
    infill = [Polygon(b['rings'][0]) for b in before['buildings'] if b['source'] == 'procedural']
    infill_tree = STRtree(infill)
    for old, new in zip(before['buildings'], after['buildings']):
        assert new['id'] == old['id'] and new.get('legacyIndex') == old.get('legacyIndex')
        if old['source'] != 'osm':
            assert new == old, f'Infill changed: {old["id"]}'
            continue
        assert new['sourceRef'] == old['sourceRef']
        polygon = Polygon(new['rings'][0], new['rings'][1:])
        assert polygon.is_valid and polygon.area > 0
        assert not len(infill_tree.query(Polygon(new['rings'][0]), predicate='intersects')), f'Expanded footprint overlaps infill: {new["id"]}'
        source = new['footprintSource']
        raw = list(parts(geom_for(refs[new['sourceRef']], project=project,
                                  clip=box(*before['bounds'])), 'Polygon'))[source['sourcePart']]
        assert len(polygon.interiors) == len(raw.interiors)
        error = raw.symmetric_difference(polygon).area/raw.area
        assert error <= POLICY['footprints']['maximumSymmetricDifferenceFraction']+1e-9
        assert abs(error*100-source['symmetricDifferencePercent']) < 1e-6
        triangles = [Polygon(t) for t in new['roofTriangles']]
        assert all(t.is_valid and t.area > 0 for t in triangles)
        roof = unary_union(triangles)
        assert roof.symmetric_difference(polygon).area < 1e-8, f'Roof coverage: {new["id"]}'
        assert abs(sum(t.area for t in triangles)-polygon.area) < 1e-8, f'Overlapping roof: {new["id"]}'
        if old.get('mappedHeight'):
            assert old['height'] == new['height']
            assert new['heightSource']['kind'] in ['height', 'levels']
        height_source = new['heightSource']
        if height_source['method'] == 'nearby-use-median':
            donors = height_source['donors']
            policy = POLICY['heightEstimation']
            assert policy['minimumDistinctSources'] <= len(donors) <= policy['maximumSources']
            assert len({d['sourceRef'] for d in donors}) == len(donors)
            center = polygon.centroid
            group = use_group(refs[new['sourceRef']].get('tags', {}).get('building', new['use']))
            for d in donors:
                assert d['sourceRef'] != new['sourceRef'] and d['sourceRef'] in known
                source_group = use_group(refs[d['sourceRef']].get('tags', {}).get('building', known[d['sourceRef']][0]['use']))
                assert source_group == group
                candidates = known[d['sourceRef']]
                distances = [center.distance(Polygon(b['rings'][0], b['rings'][1:]).centroid)*100 for b in candidates]
                closest = min(range(len(candidates)), key=lambda i: distances[i])
                assert distances[closest] <= policy['radiusMeters']
                assert abs(distances[closest]-d['distanceMeters']) <= .000501
                assert candidates[closest]['height'] == d['heightMeters']
            values = [d['heightMeters'] for d in donors]
            assert max(values)/min(values) <= policy['maximumDonorHeightRatio']
            assert round(statistics.median(values), 1) == new['height']
        elif height_source['method'] == 'retained-legacy-fallback':
            assert new['height'] == old['height']
        if new['qualityGeometry']:
            assert originals[new['id']] == old
            import numpy as np
            mesh_rings=[np.asarray(r,dtype=np.float32).astype(float).tolist() for r in new['rings']]
            mesh_shape=Polygon(mesh_rings[0],mesh_rings[1:])
            mesh_faces=[Polygon(t) for t in new['meshRoofTriangles']]
            assert all(t.area>1e-12 for t in mesh_faces),new['id']
            mesh_roof=unary_union(mesh_faces)
            assert mesh_roof.symmetric_difference(mesh_shape).area<1e-9,new['id']
            assert sum(t.area for t in mesh_faces)-mesh_roof.area<1e-9,new['id']
        else:
            assert new['id'] not in originals
            assert old['rings'] == new['rings'] and old['height'] == new['height']
        counts['mappedBuildings'] += 1
        counts['footprintsChanged'] += old['rings'] != new['rings']
        counts['heightsChanged'] += old['height'] != new['height']
        counts['buildingsWithInteriors'] += bool(polygon.interiors)
        counts['geometryChanges'] += new['qualityGeometry']
        counts[new['heightSource']['method']] += 1
        # Base extrusion only: both outer and inner walls, plus triangulated roof.
        # These counts intentionally precede visibility masks and terrain support.
        old_faces = 3*(len(old['rings'][0])-1)-2
        new_faces = 2*sum(len(ring)-1 for ring in new['rings'])+len(triangles)
        rows.append({'id': new['id'], 'sourceRef': new['sourceRef'],
                     'beforeTriangles': old_faces, 'candidateTriangles': new_faces,
                     'deltaTriangles': new_faces-old_faces,
                     'symmetricDifferencePercent': source['symmetricDifferencePercent']})
    assert dict(counts) == plan['statistics']
    assert len(plan['records']) == counts['mappedBuildings']
    assert {r['id'] for r in plan['records']} == {r['id'] for r in rows}
    return {'status': 'candidate-data-checks-passed; city integration pending',
            'statistics': dict(counts),
            'scope': 'All mapped records, roof coverage, source footprint error, known heights, donor evidence, IDs, infill non-overlap and non-building features',
            'baseExtrusion': {'beforeTriangles': sum(r['beforeTriangles'] for r in rows),
                              'candidateTriangles': sum(r['candidateTriangles'] for r in rows),
                              'deltaTriangles': sum(r['deltaTriangles'] for r in rows)},
            'limitations': ['Extrusion estimates include buildings hidden by landmarks, railways or roads',
                            'Terrain support, GLB export, browser appearance and final budgets are not verified here',
                            'Nearby height values remain estimates; tests check source selection separately'],
            'largestGeometryChanges': sorted(rows, key=lambda r: (-r['deltaTriangles'], r['id']))[:30]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(*[json.loads(path.read_text()) for path in [args.before, args.candidate, args.snapshot]])
    assert json.loads(args.candidate.read_text())['buildingQuality']['snapshotSha256'] == digest(args.snapshot)
    report['inputs'] = {k: {'path': str(p), 'sha256': digest(p)} for k, p in
                        [('before', args.before), ('candidate', args.candidate), ('snapshot', args.snapshot)]}
    report['tools'] = {str(p): digest(p) for p in [Path(__file__), SOURCE,
                        Path(__file__).with_name('prepare_building_quality.py'),
                        Path(__file__).with_name('prepare_geodata.py'),
                        Path(__file__).with_name('test_building_quality.py')]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ['inputs', 'tools', 'largestGeometryChanges']}, ensure_ascii=False, indent=2))
