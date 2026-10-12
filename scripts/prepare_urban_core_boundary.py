#!/usr/bin/env python3
"""Generate approved display scope and the exportable subset of source coverage."""
import hashlib
import json
import math
from pathlib import Path

from shapely import make_valid
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box, mapping
from shapely.geometry.polygon import orient
from shapely.ops import transform, unary_union
from shapely.validation import explain_validity
from urban_scope import UrbanScope

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/urban-core-boundary-source.json'
OUT = ROOT / 'work/urban-scope-review/implementation'


def prepare():
    source = json.loads(SOURCE.read_text())
    geo_path = ROOT / 'public/data/geography.json'
    geo = json.loads(geo_path.read_text())
    scope = UrbanScope(source, geo)
    scope.require_approved()
    cx, cy = geo['center']
    kx, ky = math.cos(math.radians(cy)) * 1113.2, 1113.2
    project = lambda x, y, z=None: ((x-cx)*kx, (y-cy)*ky)
    inverse = lambda x, y, z=None: (x/kx+cx, y/ky+cy)
    segments = source['segments']
    ring = []
    for segment in segments:
        if ring and ring[-1] != segment['points'][0]:
            raise ValueError('Disconnected boundary segment: ' + segment['id'])
        ring.extend(segment['points'][1:] if ring else segment['points'])
    if ring[0] != ring[-1]:
        raise ValueError('Core ring must be closed explicitly')
    core_lonlat = Polygon(ring)
    if not core_lonlat.is_valid:
        raise ValueError(explain_validity(core_lonlat))
    core = transform(project, core_lonlat)
    current = box(*geo['bounds'])
    context = core.buffer(source['contextWidthMeters'] / geo['metersPerUnit'], quad_segs=8)
    landmarks = json.loads((ROOT / 'public/data/landmarks.json').read_text())
    areas = json.loads((ROOT / 'data/landmark-areas.json').read_text())['areas']
    landmark_checks = []
    for place in landmarks:
        p = transform(project, Point(place['lon'], place['lat']))
        landmark_checks.append({'id': place['id'], 'name': place['name'], 'inside': core.covers(p),
                                'edgeDistanceMeters': round(core.boundary.distance(p)*100, 1)})
    area_checks = []
    for identity, area in areas.items():
        shape = transform(project, MultiPolygon([(p[0], p[1:]) for p in area['polygons']]))
        missing = shape.difference(core).area
        area_checks.append({'id': identity, 'name': area['name'], 'fullyInside': missing < 1e-6,
                            'excludedSquareMeters': round(missing*10000, 2)})
    if not all(p['inside'] for p in landmark_checks) or not all(a['fullyInside'] for a in area_checks):
        raise ValueError('A protected landmark or mapped landmark area is outside the proposed core')
    features = []
    def add(identity, shape, properties):
        if shape.geom_type == 'Polygon':
            shape = orient(shape, sign=1)  # RFC 7946 winding; browser adapter reverses for D3.
        features.append({'type': 'Feature', 'id': identity, 'properties': properties,
                         'geometry': mapping(transform(inverse, shape))})
    add('urban-core', core, {'role': 'core', 'name': '城区设计范围（含待补数据延伸）', 'status': source['status'],
                            'readyForModelExport': False, 'approximateAreaKm2': round(core.area/100, 2)})
    add('urban-context', context, {'role': 'context', 'name': '设计过渡带外缘', 'status': source['status'],
                                  'widthMeters': source['contextWidthMeters'],
                                  'approximateAreaKm2': round(context.area/100, 2)})
    add('urban-export-core', scope.core,
        {'role': 'export-core', 'name': '本次精细模型范围', 'status': source['status'],
         'readyForModelExport': True, 'wholeCrossingFootprints': len(scope.crossing_buildings),
         'approximateAreaKm2': round(scope.core.area/100, 2)})
    add('urban-export-context', scope.context,
        {'role': 'export-context', 'name': '长方形模型外框（含简化环境）', 'status': source['status'],
         'readyForModelExport': True, 'approximateAreaKm2': round(scope.context.area/100, 2)})
    add('urban-export-transition', scope.transition,
        {'role': 'export-transition', 'name': '城区与连续江岸的原地形范围', 'status': source['status'],
         'readyForModelExport': True, 'approximateAreaKm2': round(scope.transition.area/100, 2)})
    add('urban-export-landscape', scope.landscape,
        {'role': 'export-landscape', 'name': '山林起伏渐退范围', 'status': source['status'],
         'readyForModelExport': True, 'fadeMeters': source['landscapeFadeMeters'],
         'approximateAreaKm2': round(scope.landscape.area/100, 2)})
    for segment in segments:
        add(segment['id'], transform(project, LineString(segment['points'])),
            {k: v for k, v in segment.items() if k != 'points'} | {'role': 'review-segment'})
    collection = {'type': 'FeatureCollection', 'name': source['id'], 'status': source['status'],
                  'exportRoles': ['export-core', 'export-transition', 'export-landscape', 'export-context'], 'coordinateSystem': 'WGS84',
                  'source': SOURCE.relative_to(ROOT).as_posix(), 'features': features}
    (ROOT / 'data/urban-core-boundary.geojson').write_text(json.dumps(collection, ensure_ascii=False, indent=2)+'\n')
    # Spatial exposure, not a compressed-file or performance saving forecast.
    forest = json.loads((ROOT / 'data/forest-plan.json').read_text())
    woodland = unary_union([make_valid(Polygon(r[0], r[1:]))
                           for region in forest['regions'] for r in region['woodland']])
    buildings = [make_valid(Polygon(b['rings'][0], b['rings'][1:])) for b in geo['buildings']]
    footprint_counts = {'inside': 0, 'crossing': 0, 'outside': 0}
    for building in buildings:
        key = 'inside' if core.covers(building) else 'crossing' if core.intersects(building) else 'outside'
        footprint_counts[key] += 1
    dependencies = ['data/urban-core-boundary-source.json', 'public/data/geography.json',
                    'data/landmark-areas.json', 'public/data/landmarks.json', 'data/forest-plan.json']
    report = {'status': source['status'], 'geometryValid': core.is_valid and context.is_valid,
              'readyForModelExport': True, 'sourceSha256': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in dependencies},
              'areaKm2': {'currentRectangle': round(current.area/100, 2), 'coreTotal': round(core.area/100, 2),
                          'coreInsideCurrent': round(core.intersection(current).area/100, 2),
                          'coreOutsideCurrentNeedsData': round(core.difference(current).area/100, 2),
                          'contextIncludingCore': round(context.area/100, 2),
                          'currentOutsideCore': round(current.difference(core).area/100, 2),
                          'currentOutsideContext': round(current.difference(context).area/100, 2),
                          'exportCore': round(scope.core.area/100, 2),
                          'exportTransition': round(scope.transition.area/100, 2),
                          'exportLandscape': round(scope.landscape.area/100, 2),
                          'exportContextIncludingCore': round(scope.context.area/100, 2)},
              'landscape': {k: source[k] for k in ['landscapeFadeMeters', 'riverbankContextMeters',
                                                  'contextGridMeters', 'continuousWaterMinAreaKm2']},
              'landmarks': landmark_checks, 'protectedAreas': area_checks,
              'buildingFootprints': footprint_counts,
              'woodlandKm2': {'total': round(woodland.area/100, 2), 'insideCore': round(woodland.intersection(core).area/100, 2),
                              'outsideCore': round(woodland.difference(core).area/100, 2)},
              'notes': ['Area uses the project local planar approximation, not an official city area.',
                        'Landmark checks cover destinations and eight mapped selection areas, not every GLB triangle.',
                        'Footprint counts include procedural buildings and are not counts of real buildings.',
                        'This preparation script only generates boundaries. scope_city.py exports the cropped GLBs.',
                        'Export core includes crossing buildings with a 20 m apron; unmapped extensions stay deferred.']}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ['geometryValid', 'areaKm2', 'buildingFootprints', 'woodlandKm2']}, ensure_ascii=False))
    print(f"Protected: {len(landmark_checks)} landmarks, {len(area_checks)} mapped areas; exportable subset ready")


if __name__ == '__main__':
    prepare()
