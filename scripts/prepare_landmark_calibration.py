"""Prepare P4 footprints and provenance without changing the public city.

The OSM records are an isolated copy of the original city snapshot. Only the
Diwang tower's tiny, almost-collinear edge is simplified for its fitted axes;
the original rings remain in the plan for independent coverage comparisons.
"""
import hashlib
import json
import math
from pathlib import Path

from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parents[1]


def prepare():
    paths = ['data/landmark-calibration-source.json',
             'data/landmark-calibration-osm.json', 'data/landmarks.json']
    source, osm, catalog = [json.loads((ROOT / p).read_text()) for p in paths]
    catalog = {p['id']: p for p in catalog}
    elements = {e['id']: e for e in osm['elements']}
    geo = json.loads((ROOT / 'public/data/geography.json').read_text())
    kx = 1113.2 * math.cos(math.radians(geo['center'][1]))
    sites = {}
    for identity, spec in source['sites'].items():
        if 'osmWay' not in spec:
            continue
        place = catalog[identity]
        def local(way):
            return [[(p['lon'] - place['lon']) * kx,
                     (p['lat'] - place['lat']) * 1113.2]
                    for p in elements[way]['geometry']]
        ring = local(spec['osmWay'])
        polygon = Polygon(ring)
        assert polygon.is_valid and polygon.area > 0
        bounds = polygon.bounds
        site = {**spec, 'center': [place['lon'], place['lat']],
                'outlineSceneXY': ring, 'sourceTags': elements[spec['osmWay']]['tags'],
                'mappedAreaSquareMeters': polygon.area * 10_000,
                'mappedBoundsMeters': [p * 100 for p in bounds],
                'mappedExtentMeters': [(bounds[2]-bounds[0])*100,
                                       (bounds[3]-bounds[1])*100]}
        if identity == 'diwang':
            assert float(site['sourceTags']['height']) == spec['heightMeters']
            rect = list(polygon.minimum_rotated_rectangle.exterior.coords)[:-1]
            a, b = rect[0], rect[1]
            angle = math.atan2(b[1]-a[1], b[0]-a[0])
            # Keep one deterministic axis convention for the photo-based details.
            angle %= math.pi / 2
            c, s = math.cos(angle), math.sin(angle)
            uv = [(x*c+y*s, -x*s+y*c) for x, y in rect]
            lower = [min(p[i] for p in uv) for i in range(2)]
            upper = [max(p[i] for p in uv) for i in range(2)]
            site['fittedAxes'] = {'angleRadians': angle,
                                  'centerUV': [(a+b)/2 for a,b in zip(lower,upper)],
                                  'extentUV': [b-a for a,b in zip(lower,upper)]}
            site['podiumOutlineSceneXY'] = local(spec['podiumOsmWay'])
            site['parcelOutlineSceneXY'] = local(spec['parcelOsmWay'])
            site['fittedRectangleDifferenceSquareMeters'] = polygon.symmetric_difference(
                polygon.minimum_rotated_rectangle).area * 10_000
            for key in ['podiumOutlineSceneXY', 'parcelOutlineSceneXY']:
                assert Polygon(site[key]).is_valid
        sites[identity] = site
    return {'version': 1, 'status': source['status'], 'sceneMetersPerUnit': 100,
            'osmTimestamp': osm['osmTimestamp'], 'sites': sites,
            'inputHashes': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
                            for p in paths},
            'projectionLatitude': geo['center'][1]}


if __name__ == '__main__':
    output = ROOT / 'data/landmark-calibration-plan.json'
    plan = prepare()
    output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: {'extentMeters': v['mappedExtentMeters'],
                         'areaSquareMeters': v['mappedAreaSquareMeters']}
                      for k,v in plan['sites'].items()}, ensure_ascii=False, indent=2))
