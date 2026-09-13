"""Source-bounded residential massing; estimated layout is never labelled surveyed.

Run against a copy first: --input .../geography.json --output .../candidate.json.
The normal geodata pipeline calls apply_blocks after the legacy city generation,
so a local edit cannot perturb the legacy random packing or tree sequence.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from shapely.affinity import rotate, translate
from shapely.geometry import Polygon, LineString, box
from shapely.ops import unary_union
import mapbox_earcut
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/block-sources/xiangxieli.json'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def building_id(building):
    return building.get('id') or f"{building['source']}/{fingerprint(building['rings'])[:20]}"


def rings(poly):
    return [[[round(x, 3), round(y, 3)] for x, y in r.coords]
            for r in [poly.exterior, *poly.interiors]]


def roof_triangles(poly):
    outlines = [list(r.coords)[:-1] for r in [poly.exterior, *poly.interiors]]
    vertices = np.asarray([p for ring in outlines for p in ring], dtype=np.float64)
    ends = np.cumsum([len(r) for r in outlines], dtype=np.uint32)
    faces = mapbox_earcut.triangulate_float64(vertices, ends).reshape(-1, 3)
    return [[[round(float(c), 3) for c in vertices[i]] for i in face] for face in faces]


def apply_blocks(geo):
    """Accept only the legacy input, retaining removed footprints for provenance/palette."""
    if geo.get('urbanBlocks'):
        raise ValueError('Generate from legacy input; refusing to replace an already applied block')
    source = json.loads(SOURCE.read_text())
    cx, cy = geo['center']
    kx, ky = 1113.2 * math.cos(math.radians(cy)), 1113.2
    boundary = Polygon([((p['lon']-cx)*kx, (p['lat']-cy)*ky) for p in source['osm']['geometry']])
    original = geo['buildings']
    for i, b in enumerate(original):
        b['id'] = building_id(b)
        b['legacyIndex'] = i
        b.setdefault('heightSource', {'kind': 'mapped-unspecified' if b['mappedHeight'] else 'estimate',
                                     'method': 'legacy-generator'})
    removed = [b for b in original if b['source'] == 'procedural'
               and Polygon(b['rings'][0], b['rings'][1:]).intersects(boundary)]
    removed_ids = {b['id'] for b in removed}
    retained = [b for b in original if b['id'] not in removed_ids]
    # The exact mapped use boundary is stricter than the general city infill area.
    water = unary_union([Polygon(p[0], p[1:]) for p in geo['water']])
    parks = unary_union([Polygon(p[0], p[1:]) for p in geo['parks']])
    neighbors = unary_union([Polygon(b['rings'][0], b['rings'][1:]) for b in retained
                            if Polygon(b['rings'][0]).distance(boundary) < .2])
    roads = unary_union([LineString(r['points']).buffer(
        .19 if r['class'] in ['primary', 'trunk', 'motorway'] else
        .135 if r['class'] == 'secondary' else .10) for r in geo['roads']
        if LineString(r['points']).distance(boundary) < .3])
    permitted = boundary.buffer(-.12).difference(water.buffer(.25)).difference(parks)
    permitted = permitted.difference(neighbors.buffer(.12)).difference(roads)
    # West boundary supplies orientation; dimensions and all internal positions
    # below are explicit design estimates, not reconstructed OSM buildings.
    first, last = list(boundary.exterior.coords)[0], list(boundary.exterior.coords)[3]
    angle = math.degrees(math.atan2(first[1]-last[1], first[0]-last[0]))-90
    origin = tuple(boundary.centroid.coords)[0]
    local = rotate(boundary, -angle, origin=origin)
    west, south, east, north = local.bounds
    config = source['template']
    generated, courts = [], []
    for row in range(config['rows']):
        for col in range(config['columns']):
            width, depth = config['slabSizeMeters']
            x = west + config['firstCenterMeters'][0]/100 + col*config['columnPitchMeters']/100
            y = south + config['firstCenterMeters'][1]/100 + row*config['rowPitchMeters']/100
            footprint = rotate(translate(box(-width/200, -depth/200, width/200, depth/200), x, y), angle, origin=origin)
            footprint = Polygon(rings(footprint)[0])
            if not permitted.covers(footprint):
                continue
            levels = config['levelsByRow'][row]
            identity = f"{source['id']}/slab/{row}/{col}"
            generated.append({'id': identity, 'blockId': source['id'], 'groupId': f'row-{row}',
                'rings': rings(footprint), 'height': levels*config['floorHeightMeters'],
                'levels': levels, 'heightSource': {'kind': 'estimate', 'method': 'residential-typology',
                                                  'reference': 'data/block-sources/xiangxieli.json'},
                'mappedHeight': False, 'source': 'procedural', 'use': 'residential',
                'template': 'slab', 'layoutSource': 'estimate', 'displayHeightScale': config['displayHeightScale'],
                'materialKey': ['building', 'building', 'building3'][int(fingerprint(identity)[:8], 16)%3],
                'roofTriangles': roof_triangles(footprint)})
    assert generated, 'No residential slabs fit the source boundary'
    # Reserve the connected space between slab rows. No roof or podium spans it.
    occupied = unary_union([Polygon(b['rings'][0]).buffer(.035, join_style=2) for b in generated])
    courtyard = permitted.difference(occupied)
    for p in ([courtyard] if courtyard.geom_type == 'Polygon' else courtyard.geoms):
        if p.area > .1:
            courts.append(rings(p))
    plan = {'id': source['id'], 'name': source['name'], 'sourceFile': str(SOURCE.relative_to(ROOT)),
            'sourceHash': hashlib.sha256(SOURCE.read_bytes()).hexdigest(), 'use': 'residential',
            'layoutSource': 'estimate', 'boundary': rings(boundary),
            'orientationDegrees': angle, 'template': config,
            'removedBuildings': removed, 'buildingIds': [b['id'] for b in generated],
            'openSpace': courts, 'statistics': {'removed': len(removed), 'generated': len(generated),
                'footprintM2': round(sum(Polygon(b['rings'][0]).area for b in generated)*10000, 2),
                'siteM2': round(boundary.area*10000, 2)}}
    geo['buildings'] = retained + generated
    geo['urbanBlocks'] = [plan]
    geo['stats']['infillBuildings'] = sum(b['source'] == 'procedural' for b in geo['buildings'])
    geo['stats']['plannedBlocks'] = 1
    return geo


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = apply_blocks(json.loads(args.input.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
    print(json.dumps(result['urbanBlocks'][0]['statistics']))
