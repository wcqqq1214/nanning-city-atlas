"""P5 integration inventory using shared visibility and explicitly frozen road masks.

Outputs potential extrusion counts, not final GLB or terrain acceptance. Existing
road/rail masks are mapped by stable building ID, never candidate array position.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from shapely.geometry import Polygon
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'blender'))
from city_visibility import CityVisibility


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_masks(before, railway, roads):
    hidden = {before['buildings'][i]['id'] for i in railway['removedBuildings']}
    limits = {}
    for road in roads:
        for r in road['buildings']:
            identity = before['buildings'][r['index']]['id']
            if identity not in limits: limits[identity] = r['top']
            elif limits[identity] is None or r['top'] is None: limits[identity] = None
            else: limits[identity] = min(limits[identity], r['top'])
    return hidden, limits


def extrusion_triangles(b):
    if b.get('massing'):
        return sum(2*sum(len(r)-1 for r in p['rings'])+len(p['roofTriangles']) for p in b['massing'])
    if b.get('qualityGeometry'):
        return 2*sum(len(r)-1 for r in b['rings'])+len(b['roofTriangles'])
    if b.get('blockId'):
        raise ValueError('Unchanged P1 massing must not enter the P5 extrusion delta')
    return 3*(len(b['rings'][0])-1)-2


def audit(before, candidate, catalog, railway, roads, support):
    hidden, limits = frozen_masks(before, railway, roads)
    visibility = CityVisibility(before, catalog)
    old = {b['id']: b for b in before['buildings']}
    new = {b['id']: b for b in candidate['buildings']}
    assert len(old) == len(before['buildings']) and len(new) == len(candidate['buildings'])
    measurements = {r['id']: r for r in support['records']}
    water = unary_union([Polygon(r[0], r[1:]) for r in candidate.get('water', [])])
    def shown(b):
        return b is not None and visibility.building_visible(b, b['id'] in hidden) and (
            b['id'] not in limits or limits[b['id']] is not None)
    rows = []
    for identity in sorted(old.keys() | new.keys()):
        a, b = old.get(identity), new.get(identity)
        if a == b or (a is not None and b is not None and not b.get('qualityGeometry') and not b.get('massing')):
            continue
        was, now = shown(a), shown(b)
        count_a = extrusion_triangles(a) if was else 0
        count_b = extrusion_triangles(b) if now else 0
        r = {'id': identity, 'sourceRef': (b or a).get('sourceRef'), 'name': (b or a).get('name'),
             'use': (b or a).get('use'), 'blockId': (b or a).get('blockId'),
             'beforeVisible': was, 'candidateVisible': now, 'beforeTriangles': count_a,
             'candidateTriangles': count_b, 'deltaTriangles': count_b-count_a,
             'baselineRoadLimitSceneZ': limits.get(identity), 'baselineRoadMaskPresent': identity in limits,
             'requiresNewInfrastructureChecks': b is not None}
        if b is not None and identity in measurements:
            m = measurements[identity]
            assert m['footprintHash'] == hashlib.sha256(json.dumps(b['rings'], separators=(',', ':')).encode()).hexdigest()
            r.update(supportStatus=m['status'], reliefMeters=m.get('reliefMeters'),
                     groundRangeSceneZ=m.get('groundRangeSceneZ'))
            if m['status'] != 'supported':
                footprint = Polygon(b['rings'][0], b['rings'][1:])
                r['mappedWaterOverlapSquareMeters'] = footprint.intersection(water).area*10000
                r['footprintAreaSquareMeters'] = footprint.area*10000
        rows.append(r)
    shown_rows = [r for r in rows if r['candidateVisible']]
    return {'status': 'provisional visible extrusion and P4 terrain inventory; final integration pending',
            'statistics': {'changedOrReplacedRecords': len(rows), 'visibleCandidateRecords': len(shown_rows),
                           'visibleSupportStatus': dict(Counter(r.get('supportStatus', 'unmeasured') for r in shown_rows)),
                           'beforeTriangles': sum(r['beforeTriangles'] for r in rows),
                           'candidateTriangles': sum(r['candidateTriangles'] for r in rows),
                           'deltaTriangles': sum(r['deltaTriangles'] for r in rows)},
            'visibleIncompleteGround': [r for r in shown_rows if r.get('supportStatus') != 'supported'],
            'visibleReliefAboveFiveMeters': sorted([r for r in shown_rows if (r.get('reliefMeters') or 0)>5],
                                                  key=lambda r: -r['reliefMeters']),
            'visibilityTransitions': [r for r in rows if r['beforeVisible'] != r['candidateVisible'] and r['id'] in old and r['id'] in new],
            'records': rows,
            'limitations': ['Road and railway exclusions are P4 masks, remapped by stable ID; new footprints need fresh checks',
                            'Positive road caps may change rendered roof/foundation counts after terrain integration',
                            'Ground extrema refer to P4 terrain; new platforms and campus urban mask require fresh terrain',
                            'Extrusion delta excludes platform/terrain changes, export triangulation and compression']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--support', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--summary', type=Path, help='Compact checked-in inventory, omitting individual ordinary buildings')
    args = p.parse_args()
    paths = {'before': args.before, 'candidate': args.candidate, 'support': args.support,
             'catalog': ROOT/'data/landmarks.json', 'railway': ROOT/'data/railways-plan.json',
             'detailRoads': ROOT/'data/road-solids-detail.json', 'smoothRoads': ROOT/'data/road-solids-smooth.json'}
    inputs = {k: json.loads(v.read_text()) for k, v in paths.items()}
    # The frozen index mapping is only valid for this exact baseline geography.
    assert inputs['railway']['inputHashes']['public/data/geography.json'] == digest(args.before)
    for key in ['detailRoads', 'smoothRoads']:
        assert inputs[key]['inputHashes']['public/data/geography.json'] == digest(args.before)
    assert inputs['support']['inputs']['geography']['sha256'] == digest(args.candidate)
    result = audit(inputs['before'], inputs['candidate'], inputs['catalog'], inputs['railway'],
                   [inputs['detailRoads'], inputs['smoothRoads']], inputs['support'])
    result['inputs'] = {k: {'path': str(v), 'sha256': digest(v)} for k, v in paths.items()}
    # Reservation helpers transitively import individual landmark modules.
    result['toolHashes'] = {str(v.relative_to(ROOT)): digest(v) for v in
                           [Path(__file__).resolve()]+sorted((ROOT/'blender').glob('*.py'))}
    result['reservationDataHashes'] = {str(v.relative_to(ROOT)): digest(v) for v in
                                     sorted((ROOT/'data').glob('*landmark*.json'))+
                                     [ROOT/'data/malls-plan.json', ROOT/'data/stations-plan.json',
                                      ROOT/'data/sports-center-footprints.json']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    if args.summary:
        summary = {k: v for k, v in result.items() if k not in ['records', 'visibleReliefAboveFiveMeters']}
        summary.update(terrainStatistics=inputs['support']['statistics'],
                       visibleReliefAboveFiveMetersCount=len(result['visibleReliefAboveFiveMeters']),
                       highestVisibleRelief=result['visibleReliefAboveFiveMeters'][:12],
                       templateSupport=[r for r in result['records'] if r.get('blockId') and r['candidateVisible']],
                       terrainInputs=inputs['support']['inputs'], terrainTools=inputs['support']['tools'])
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result['statistics'], ensure_ascii=False, indent=2))
