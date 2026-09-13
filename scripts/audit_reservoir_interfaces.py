"""List neighboring waters and mapped road/footprint interfaces before local terrain changes."""
import argparse
import hashlib
import json
from pathlib import Path

from shapely.geometry import Polygon, LineString, mapping
from shapely.ops import unary_union


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ['before', 'after', 'source', 'inventory', 'output']:
        parser.add_argument('--'+key, type=Path, required=True)
    parser.add_argument('--margin-meters', type=float, default=150)
    args = parser.parse_args()
    if not 0 < args.margin_meters <= 500:
        raise ValueError('Choose a bounded positive interface search margin')
    before, after, source, inventory = [json.loads(getattr(args, k).read_text())
                                         for k in ['before', 'after', 'source', 'inventory']]
    if inventory['inputs']['geography']['sha256'] != digest(args.before):
        raise ValueError('Inventory does not describe the frozen pre-restoration geography')
    if before['roads'] != after['roads']:
        raise ValueError('Road records changed; reconcile their identities before auditing')
    selected = {w['geographyWaterIndex'] for w in source['water']}
    water = [Polygon(r[0], r[1:]) for r in after['water']]
    target = unary_union([water[i] for i in selected])
    previous = unary_union([Polygon(before['water'][i][0], before['water'][i][1:]) for i in selected])
    gained, lost = target.difference(previous), previous.difference(target)
    study = target.buffer(args.margin_meters/100)
    source_matches = {}
    for entry in inventory['waters']:
        for match in entry['displayMatches']:
            source_matches.setdefault(match['index'], []).append({
                'sourceRef': entry['sourceRef'], 'sourceCoverageFraction': match['sourceCoverageFraction'],
                'displayCoverageFraction': match['displayCoverageFraction'],
                'rawPixelStatisticsMetersByInset': entry['rawPixelStatisticsMetersByInset'],
                'displayLevelCandidate': entry['displayLevelCandidate']})
    neighbors = [{'geographyWaterIndex': i, 'distanceMeters': shape.distance(target)*100,
                  'areaSquareMeters': shape.area*10000,
                  'sourceMatchesInDamInventory': source_matches.get(i, []), 'geometry': mapping(shape)}
                 for i, shape in enumerate(water) if i not in selected and shape.intersects(study)]
    roads = []
    for i, road in enumerate(after['roads']):
        line = LineString(road['points'])
        if not line.intersects(study):
            continue
        roads.append({'index': i, 'record': road, 'lengthInStudyMeters': line.intersection(study).length*100,
                      'selectedWaterCrossingBeforeMeters': line.intersection(previous).length*100,
                      'selectedWaterCrossingAfterMeters': line.intersection(target).length*100,
                      'newWaterCrossingMeters': line.intersection(gained).length*100,
                      'removedWaterCrossingMeters': line.intersection(lost).length*100,
                      'damIntersections': [b['id'] for b in after['buildings'] if b['id'] in source['affectedBuildingIds']
                                            and line.intersects(Polygon(b['rings'][0], b['rings'][1:]))]})
    buildings = [{'index': i, 'id': b['id'], 'sourceRef': b.get('sourceRef'), 'use': b.get('use'),
                  'distanceToSelectedWaterMeters': Polygon(b['rings'][0], b['rings'][1:]).distance(target)*100}
                 for i, b in enumerate(after['buildings']) if Polygon(b['rings'][0], b['rings'][1:]).intersects(study)]
    result = {'status': 'interface inventory; road centerlines only, no road width or height acceptance',
              'marginMeters': args.margin_meters, 'selectedWaterIndices': sorted(selected),
              'studyGeometry': mapping(study), 'neighboringWaters': neighbors, 'roads': roads, 'buildings': buildings,
              'statistics': {'neighboringWaters': len(neighbors), 'nearbyRoadRecords': len(roads),
                             'nearbyBuildingRecords': len(buildings),
                             'newWaterAreaSquareMeters': gained.area*10000,
                             'removedWaterAreaSquareMeters': lost.area*10000,
                             'newWaterRoadCrossingMeters': sum(r['newWaterCrossingMeters'] for r in roads),
                             'roadsCrossingDamFootprints': sum(bool(r['damIntersections']) for r in roads)},
              'inputs': {k: {'path': str(getattr(args, k).resolve()), 'sha256': digest(getattr(args, k))}
                         for k in ['before', 'after', 'source', 'inventory']},
              'toolSha256': digest(Path(__file__))}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result['statistics']))


if __name__ == '__main__':
    main()
