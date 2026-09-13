"""Prepare source-bounded P5 typologies without modifying the public city.

The input may include the independent OSM quality candidate. Existing mapped
buildings and P1 groups are retained; only listed legacy infill is replaced.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

from shapely.affinity import rotate, scale, translate
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from shapely.strtree import STRtree

from prepare_urban_blocks import fingerprint, rings, roof_triangles

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'data/block-sources/p5-rollout.json'


def polygon_rings(poly):
    serialized = rings(orient(poly, sign=1.0))
    return Polygon(serialized[0], serialized[1:])


def orientation(boundary):
    edges = list(zip(boundary.exterior.coords, list(boundary.exterior.coords)[1:]))
    a, b = max(edges, key=lambda e: (math.dist(*e), tuple(e[0])))
    # A consistent eastward local x keeps upper/lower rows stable under reversal.
    angle = math.degrees(math.atan2(b[1]-a[1], b[0]-a[0]))
    return (angle+90) % 180-90


def map_projection(site, project):
    c = site['template']['controlPoints']
    p, q = [complex(*v['pixel']) for v in c]
    boundary = site['osm']['geometry']
    points = [project(boundary[v['osmBoundaryVertex']]['lon'], boundary[v['osmBoundaryVertex']]['lat']) for v in c]
    # Reflect the image y axis before solving an orientation-preserving similarity.
    p, q = p.conjugate(), q.conjugate()
    a, b = [complex(*v) for v in points]
    factor = (b-a)/(q-p)
    def transform(pixel):
        value = a+(complex(*pixel).conjugate()-p)*factor
        return value.real, value.imag
    return transform


def candidates(site, boundary, project):
    config = site['template']; kind = config['type']
    angle = orientation(boundary)
    center = tuple(boundary.centroid.coords)[0]
    local = rotate(boundary, -angle, origin=center)
    west, south, east, north = local.bounds
    center = ((west+east)/2, (south+north)/2)
    # Rotation is around the original site centroid, including translations.
    pivot = tuple(boundary.centroid.coords)[0]
    def rectangle(x, y, size):
        width, depth = size
        shape = translate(box(-width/200, -depth/200, width/200, depth/200), center[0]+x/100, center[1]+y/100)
        return polygon_rings(rotate(shape, angle, origin=pivot))
    result, spaces = [], []
    if kind == 'residential-court-towers':
        for row in range(config['rows']):
            for col in range(config['columns']):
                x = (col-(config['columns']-1)/2)*config['columnPitchMeters']
                y = (row-(config['rows']-1)/2)*config['rowPitchMeters']
                height = config['towerHeightsMeters'][col % len(config['towerHeightsMeters'])]
                result.append((f'tower-{row}-{col}', f'court-row-{row}', [
                    (rectangle(x, y, config['podiumSizeMeters']), 0, config['podiumHeightMeters']),
                    (rectangle(x, y, config['towerSizeMeters']), config['podiumHeightMeters'], height)], None))
        spaces.append(('shared-garden', 'courtyard', rectangle(0, 0, [(east-west)*100-30, config['centralGardenWidthMeters']])))
    elif kind == 'commercial-promenade':
        columns = max(1, math.floor((east-west)*100/config['columnPitchMeters']))
        for row in range(2):
            for col in range(columns):
                x = (col-(columns-1)/2)*config['columnPitchMeters']
                y = (row-.5)*config['rowPitchMeters']
                height = config['towerHeightsMeters'][col % len(config['towerHeightsMeters'])]
                result.append((f'office-{row}-{col}', f'frontage-{row}', [
                    (rectangle(x, y, config['podiumSizeMeters']), 0, config['podiumHeightMeters']),
                    (rectangle(x, y, config['towerSizeMeters']), config['podiumHeightMeters'], height)], None))
        spaces.append(('promenade', 'pedestrian-space', rectangle(0, 0, [(east-west)*100-20, config['promenadeWidthMeters']])))
    elif kind == 'warehouse-loading-court':
        for index in range(2):
            x = (index-.5)*config['pitchMeters']
            result.append((f'warehouse-{index}', 'loading-court', [
                (rectangle(x, 0, config['warehouseSizesMeters'][index]), 0, config['warehouseHeightMeters'])], None))
        spaces.append(('loading-court', 'loading-space', rectangle(0, 0, [config['loadingCourtWidthMeters'], max(s[1] for s in config['warehouseSizesMeters'])+25])))
    elif kind == 'campus-academic-courts':
        transform = map_projection(site, project)
        for b in config['buildings']:
            shape = polygon_rings(Polygon([transform(p) for p in b['outerPixels']],
                [[transform(p) for p in ring] for ring in b['innerPixels']]))
            result.append((b['id'], 'academic-core', [(shape, 0, b['levels']*config['floorHeightMeters'])],
                           {'levels': b['levels'], 'name': b['name']}))
        spaces = [(s['id'], s['kind'], polygon_rings(Polygon([transform(p) for p in s['outerPixels']])))
                  for s in config['protectedSpaces']]
        angle = None
    else:
        raise ValueError(f'Unknown rollout typology: {kind}')
    return result, spaces, angle


def record(site, key, group, components, extra):
    footprint = polygon_rings(unary_union([c[0] for c in components]))
    massing = []
    for i, (shape, base, top) in enumerate(components):
        # The lower roof has an opening where a higher volume continues upward.
        above = unary_union([other for j, (other, low, high) in enumerate(components)
                             if j != i and low <= top and high > top])
        exposed = shape.difference(above)
        polygons = [exposed] if exposed.geom_type == 'Polygon' else list(exposed.geoms)
        massing.append({'rings': rings(shape), 'baseMeters': base, 'topMeters': top,
                       'fullRoofTriangles': roof_triangles(shape),
                       'roofTriangles': [tri for p in polygons if p.area > 1e-10 for tri in roof_triangles(p)]})
    return {'id': f"{site['id']}/{key}", 'blockId': site['id'], 'groupId': group,
            'source': 'procedural', 'use': site['use'], 'mappedHeight': False,
            'rings': rings(footprint), 'height': max(c[2] for c in components),
            'roofTriangles': roof_triangles(footprint), 'massing': massing,
            'heightSource': {'kind': 'estimate', 'method': 'official-plan-levels' if extra else 'source-bounded-typology',
                             'reference': str(SOURCE.relative_to(ROOT)),
                             **({'sourceLevels': extra['levels'], 'floorHeightMeters': site['template']['floorHeightMeters']} if extra else {})},
            'template': site['template']['type'], 'layoutSource': 'estimate', 'displayHeightScale': 1.0,
            'materialKey': {'residential': 'building', 'commercial': 'building3', 'campus': 'building2', 'industrial': 'building'}[site['use']],
            **(extra or {})}


def fit_traced_components(components, permitted, reserved, occupied, config):
    """Reconcile an approximate map trace with OSM boundaries within a stated cap.

    Do not clip off wings or courtyard edges. Shift/scale the complete shape, and
    retain the exact adjustment so the candidate remains reviewable.
    """
    cap = config['maximumRegistrationAdjustmentMeters']
    offsets = sorted([(x, y) for x in range(-cap, cap+1, 2) for y in range(-cap, cap+1, 2)
                      if math.hypot(x, y) <= cap], key=lambda p: (math.hypot(*p), p))
    footprint = unary_union([p for p, _, _ in components])
    pivot = tuple(footprint.centroid.coords)[0]
    for factor in [1.0, .95, config['minimumFootprintScale']]:
        for x, y in offsets:
            transformed = [(polygon_rings(translate(scale(p, xfact=factor, yfact=factor, origin=pivot), x/100, y/100)), low, high)
                           for p, low, high in components]
            shape = unary_union([p for p, _, _ in transformed])
            if (permitted.covers(shape) and not reserved.intersects(shape)
                    and not occupied.buffer(.08).intersects(shape)):
                return transformed, {'translationMeters': [x, y], 'footprintScale': factor}
    return components, None


def prepare(geography, config=None):
    if geography.get('blockRollout'):
        raise ValueError('Generate from input before this rollout')
    config = config or json.loads(SOURCE.read_text())
    geo = copy.deepcopy(geography)
    cx, cy = geo['center']; kx = math.cos(math.radians(cy))*1113.2
    project = lambda lon, lat: ((lon-cx)*kx, (lat-cy)*1113.2)
    water = unary_union([Polygon(p[0], p[1:]) for p in geo['water']])
    parks = unary_union([Polygon(p[0], p[1:]) for p in geo['parks']])
    roads = unary_union([LineString(r['points']).buffer(.19 if r['class'] in ['primary', 'trunk', 'motorway'] else
                            .135 if r['class'] == 'secondary' else .10) for r in geo['roads']])
    accepted_sites = []
    for site in config['sites']:
        boundary = polygon_rings(Polygon([project(p['lon'], p['lat']) for p in site['osm']['geometry']]))
        removed = [b for b in geo['buildings'] if b['source'] == 'procedural' and not b.get('blockId')
                   and Polygon(b['rings'][0], b['rings'][1:]).intersects(boundary)]
        removed_ids = {b['id'] for b in removed}
        retained = [b for b in geo['buildings'] if b['id'] not in removed_ids]
        neighbours = unary_union([Polygon(b['rings'][0], b['rings'][1:]) for b in retained
                                  if Polygon(b['rings'][0]).distance(boundary) < .3])
        limits = site['limits']
        permitted = boundary.buffer(-limits['siteSetbackMeters']/100).difference(parks).difference(roads)
        permitted = permitted.difference(water.buffer(limits['waterClearanceMeters']/100))
        permitted = permitted.difference(neighbours.buffer(limits['neighbourClearanceMeters']/100))
        proposals, spaces, angle = candidates(site, boundary, project)
        reserved = unary_union([p for _, _, p in spaces])
        generated, rejected = [], []
        occupied = Polygon()
        for key, group, components, extra in proposals:
            if site['use'] == 'campus':
                components, adjustment = fit_traced_components(components, permitted, reserved, occupied, site['template'])
                if adjustment is not None:
                    extra = {**extra, 'registrationAdjustment': adjustment}
            footprint = unary_union([c[0] for c in components])
            reason = ('outside-permitted-area' if not permitted.covers(footprint) else
                      'reserved-open-space' if reserved.intersects(footprint) else
                      'other-template-building' if occupied.buffer(.08).intersects(footprint) else None)
            if reason:
                rejected.append({'id': key, 'reason': reason})
                continue
            generated.append(record(site, key, group, components, extra))
            occupied = occupied.union(footprint)
        if len(generated) < site['template']['minimumBuildings']:
            raise ValueError(f"{site['id']}: only {len(generated)} candidates fit; rejected {rejected}")
        added_urban = []
        if site['use'] == 'campus':
            # Existing generic infill excludes amenity=university. This explicit,
            # source-bounded campus addition needs its own recorded land-use area.
            urban = unary_union([Polygon(p[0], p[1:]) for p in geo['urban']+geo['inferredUrban']])
            if not urban.covers(occupied):
                geo['urban'].append(rings(boundary)); added_urban.append(rings(boundary))
        plan = {'id': site['id'], 'name': site['name'], 'use': site['use'],
                'sourceFile': str(SOURCE.relative_to(ROOT)), 'sourceHash': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                'configurationHash': fingerprint(site),
                'layoutSource': 'estimate', 'boundary': rings(boundary), 'orientationDegrees': angle,
                'template': site['template'], 'removedBuildings': removed, 'buildingIds': [b['id'] for b in generated],
                'preservedBuildingIds': [b['id'] for b in retained if Polygon(b['rings'][0], b['rings'][1:]).intersects(boundary)],
                'openSpace': [rings(p.intersection(boundary)) for _, _, p in spaces if p.intersection(boundary).geom_type == 'Polygon'],
                'reservedSpaces': [{'id': i, 'kind': k, 'rings': rings(p)} for i, k, p in spaces],
                'addedUrban': added_urban, 'rejectedCandidates': rejected,
                'statistics': {'removed': len(removed), 'generated': len(generated),
                    'siteM2': round(boundary.area*10000, 2), 'footprintM2': round(occupied.area*10000, 2)}}
        geo['buildings'] = retained+generated
        geo.setdefault('urbanBlocks', []).append(plan)
        accepted_sites.append(plan)
    new_shapes = [Polygon(b['rings'][0], b['rings'][1:]) for b in geo['buildings']
                  if b.get('blockId') in {s['id'] for s in accepted_sites}]
    tree = STRtree(new_shapes)
    hidden_trees = [i for i, t in enumerate(geo['trees']) if len(tree.query(Point(t[:2]).buffer(t[2]), predicate='intersects'))]
    geo['blockRollout'] = {'id': config['id'], 'sourceHash': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                           'configurationHash': fingerprint(config),
                           'siteIds': [s['id'] for s in accepted_sites], 'hiddenTreeIndices': hidden_trees,
                           'status': 'candidate; model support, dependency rebuild and browser acceptance pending'}
    geo['stats']['infillBuildings'] = sum(b['source'] == 'procedural' for b in geo['buildings'])
    geo['stats']['plannedBlocks'] = len(geo['urbanBlocks'])
    return geo


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(json.loads(args.input.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
    print(json.dumps({s['id']: s['statistics'] for s in result['urbanBlocks'] if s['id'] in result['blockRollout']['siteIds']}, ensure_ascii=False, indent=2))
