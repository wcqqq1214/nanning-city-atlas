"""Export same-scale source/legacy/candidate footprint panels for P5 review."""
import argparse
import json
import math
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree

from shapely.geometry import Polygon, box
from prepare_geodata import geom_for, parts


def write_panels(before, candidate, snapshot, output):
    old = {b['id']: b for b in before['buildings']}
    new = {b['id']: b for b in candidate['buildings']}
    refs = {f"osm/{e['type']}/{e['id']}": e for e in snapshot['elements']}
    changed = [r for r in candidate['buildingQuality']['records'] if r['footprintChanged']]
    # Four different review questions: courtyard, complex campus, curved public
    # building, and small footprint. Selection is deterministic and reproducible.
    selectors = [
        ('院落开口', lambda r: r['interiorRings'] > 0),
        ('校园复杂足印', lambda r: new[r['id']]['use'] in ['school', 'university'] and not r['interiorRings']),
        ('高顶点轮廓', lambda r: not r['interiorRings']),
        ('小型建筑', lambda r: r['sourceAreaSquareMeters'] < 400),
    ]
    selected = []
    for label, predicate in selectors:
        eligible = [r for r in changed if predicate(r) and r['id'] not in [v[1]['id'] for v in selected]]
        record = max(eligible, key=lambda r: (r['displayVertices']-(len(old[r['id']]['rings'][0])-1), r['id']))
        selected.append((label, record))
    root = Element('svg', {'xmlns': 'http://www.w3.org/2000/svg', 'width': '1200', 'height': '1370',
                           'viewBox': '0 0 1200 1370'})
    SubElement(root, 'rect', {'width': '1200', 'height': '1370', 'fill': '#f5f4ef'})

    def text(x, y, message, size=16, color='#24313d'):
        item = SubElement(root, 'text', {'x': str(x), 'y': str(y), 'font-family': 'PingFang SC, sans-serif',
                                         'font-size': str(size), 'fill': color})
        item.text = message

    text(35, 42, 'P5 · OSM 建筑轮廓候选对照', 27)
    text(35, 71, '每行共用尺度与边界；仅验证二维轮廓，尚未接入正式城市模型。', 16)
    for x, title in zip([40, 425, 810], ['P4 旧轮廓', 'OSM 来源轮廓', 'P5 候选轮廓']):
        text(x, 110, title, 20)
    cx, cy = before['center']
    project = lambda lon, lat: ((lon-cx)*1113.2*math.cos(math.radians(cy)), (lat-cy)*1113.2)
    records = []
    for row, (label, record) in enumerate(selected):
        current = new[record['id']]
        raw = list(parts(geom_for(refs[current['sourceRef']], project=project,
                                  clip=box(*before['bounds'])), 'Polygon'))[record['sourcePart']]
        shapes = [Polygon(old[current['id']]['rings'][0], old[current['id']]['rings'][1:]),
                  raw, Polygon(current['rings'][0], current['rings'][1:])]
        west, south, east, north = raw.union(shapes[0]).bounds
        scale = min(325/(east-west), 210/(north-south))
        top = 140+row*290
        for column, (shape, fill, stroke) in enumerate(zip(shapes, ['#d9b9a9', '#c4c7c9', '#9bc5cb'],
                                                        ['#9f5133', '#4c555b', '#12636e'])):
            left = 35+385*column
            SubElement(root, 'rect', {'x': str(left), 'y': str(top), 'width': '360', 'height': '235',
                                     'rx': '5', 'fill': '#ffffff'})
            ox = left+180-(west+east)*scale/2
            oy = top+117.5+(south+north)*scale/2
            paths = []
            for ring in [shape.exterior, *shape.interiors]:
                points = [(ox+x*scale, oy-y*scale) for x, y in ring.coords]
                paths.append('M '+' L '.join(f'{x:.3f} {y:.3f}' for x, y in points)+' Z')
            SubElement(root, 'path', {'d': ' '.join(paths), 'fill': fill, 'stroke': stroke,
                                     'stroke-width': '1.5', 'fill-rule': 'evenodd'})
        text(35, top+258, f'{label} · {current.get("name") or current["use"]} · {current["sourceRef"]}', 15)
        text(35, top+278, f'来源面积 {record["sourceAreaSquareMeters"]:.1f} m²；候选对称差 {record["symmetricDifferencePercent"]:.3f}%；内洞 {record["interiorRings"]}', 14)
        records.append({'topic': label, 'id': current['id'], 'sourceRef': current['sourceRef']})
    text(35, 1345, 'OSM 为志愿地图来源；候选保留已知内环。三维屋顶开口、地面支承和资源预算仍需正式导出验收。', 14)
    output.parent.mkdir(parents=True, exist_ok=True)
    ElementTree(root).write(output, encoding='utf-8', xml_declaration=True)
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    records = write_panels(*[json.loads(path.read_text()) for path in [args.before, args.candidate, args.snapshot]], args.output)
    print(json.dumps(records, ensure_ascii=False, indent=2))
