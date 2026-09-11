"""Simplify retained OSM outlines for selection hints, without rebuilding the city."""
import json
import math
from pathlib import Path

from shapely import make_valid
from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize, unary_union

ROOT = Path(__file__).resolve().parents[1]
SITES = [
    ('gxu', '广西大学', [('way', 398115378)], 0),
    ('gxmzu', '广西民族大学相思湖校区', [('way', 1011595714)], 0),
    ('xiangsi', '相思湖公园及湖面', [('way', 1465268029), ('relation', 6695831)], 0),
    ('zoo', '南宁动物园', [('relation', 20998616)], 0),
    ('mingyue', '明月湖及沿岸', [('relation', 6695830)], .2),
    ('nanhu', '南湖公园', [('relation', 12477526)], 0),
    ('zhenning', '人民公园', [('way', 388690530)], 0),
    ('qingxiu', '青秀山周边林地', [('relation', 11922560)], 0),
]


def polygons(geom):
    if geom.geom_type == 'Polygon':
        yield geom
    elif hasattr(geom, 'geoms'):
        for part in geom.geoms:
            yield from polygons(part)


def prepare():
    snapshot = json.loads((ROOT/'work/geodata/osm.json').read_text())
    elements = {(e['type'], e['id']): e for e in snapshot['elements']}
    center = json.loads((ROOT/'data/region.json').read_text())['bbox']
    cx, cy = (center[0]+center[2])/2, (center[1]+center[3])/2
    kx, ky = 1113.2*math.cos(math.radians(cy)), 1113.2

    def points(coords):
        return [((p['lon']-cx)*kx, (p['lat']-cy)*ky) for p in coords]

    def outline(element):
        if element['type'] == 'way':
            return make_valid(Polygon(points(element['geometry'])))
        lines = [LineString(points(m['geometry'])) for m in element['members']
                 if m.get('role') != 'inner' and len(m.get('geometry', [])) > 1]
        return unary_union(list(polygonize(unary_union(lines))))

    areas = {}
    for identity, name, refs, buffer in SITES:
        area = unary_union([outline(elements[ref]) for ref in refs])
        # Selection hints describe the overall place, including its inner lakes
        # and paths. They do not claim cadastral or administrative precision.
        area = unary_union([Polygon(p.exterior) for p in polygons(area)])
        if identity == 'mingyue':
            area = area.convex_hull
        area = area.buffer(buffer).simplify(.1, preserve_topology=True)
        assert area.is_valid and not area.is_empty, name
        areas[identity] = {
            'name': name,
            'sourceUrls': [f'https://www.openstreetmap.org/{kind}/{ref}' for kind, ref in refs],
            'polygons': [[[[round(cx+x/kx, 6), round(cy+y/ky, 6)] for x, y in ring.coords]
                          for ring in [p.exterior, *p.interiors]] for p in polygons(area)],
        }
    output = {'approximate': True, 'osmTimestamp': snapshot['osm3s']['timestamp_osm_base'],
              'attribution': '© OpenStreetMap contributors, ODbL 1.0',
              'note': '既有外轮廓按约 10 米简化，包含内部水面与道路；明月湖采用湖面外包轮廓并外扩约 20 米。青秀山采用周边林地轮廓。仅作选中范围示意。',
              'areas': areas}
    (ROOT/'data/landmark-areas.json').write_text(json.dumps(output, ensure_ascii=False, separators=(',', ':'))+'\n')
    print(f'Prepared {len(areas)} approximate landmark areas.')


if __name__ == '__main__':
    prepare()
