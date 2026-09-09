"""Prepare local railway geometry from the attributed stations-source snapshot.

Run with the geodata Python environment; Blender only reads the resulting plan.
The source query and OSM timestamp are retained for reproducible rebuilding.
"""
import hashlib
import json
import math
from pathlib import Path

import mapbox_earcut
import numpy as np
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]


def prepare():
    source = json.loads((ROOT/'data/stations-source.json').read_text())
    geo = json.loads((ROOT/'public/data/geography.json').read_text())
    elements = {(e['type'], e['id']): e for e in source['elements']}
    kx = 1113.2*math.cos(math.radians(geo['center'][1]))
    stations = {}
    for name, kind, identity in [('nanning-station', 'way', 286249877),
                                 ('east-station', 'relation', 11968494)]:
        feature = elements[kind, identity]
        raw = (feature['geometry'] if kind == 'way' else
               next(m['geometry'] for m in feature['members'] if m['role'] == 'outer'))
        projected = Polygon([((p['lon']-geo['center'][0])*kx,
                              (p['lat']-geo['center'][1])*1113.2) for p in raw])
        rect = list(projected.minimum_rotated_rectangle.exterior.coords)
        # The public entrances face southeast at the old station and south at
        # the east station. U runs across the entrance, V points into the hall.
        edges = [(b[0]-a[0], b[1]-a[1]) for a, b in zip(rect, rect[1:])]
        dx, dy = max(edges, key=lambda d: abs(d[0]))
        if dx < 0: dx, dy = -dx, -dy
        angle = math.atan2(dy, dx)
        c, s = math.cos(angle), math.sin(angle)
        cx, cy = projected.minimum_rotated_rectangle.centroid.coords[0]

        def local(p):
            x, y = (p['lon']-geo['center'][0])*kx-cx, (p['lat']-geo['center'][1])*1113.2-cy
            return (round(x*c+y*s, 6), round(-x*s+y*c, 6))

        def mesh(shape):
            rings = [list(shape.exterior.coords)[:-1]]+[list(r.coords)[:-1] for r in shape.interiors]
            points = [[round(x, 6), round(y, 6)] for ring in rings for x, y in ring]
            indices = mapbox_earcut.triangulate_float64(np.array(points), np.cumsum([len(r) for r in rings], dtype=np.uint32))
            return {'points': points, 'triangles': indices.reshape(-1, 3).tolist()}

        footprint = Polygon([local(p) for p in raw])
        platforms = []
        for e in source['elements']:
            tags = e.get('tags', {})
            if tags.get('railway') != 'platform' or tags.get('train') != 'yes': continue
            ring = Polygon([local(p) for p in e['geometry']])
            if ring.centroid.distance(footprint) > 3: continue
            platforms.append({'osmId': e['id'], 'ring': list(ring.exterior.coords), **mesh(ring)})
        assert len(platforms) == (7 if name == 'nanning-station' else 13)
        u0, v0, u1, v1 = footprint.bounds
        forecourt = box(u0-.04, v0-(.45 if name == 'nanning-station' else .40), u1+.04, v0+.04)
        parts = [footprint, forecourt]+[Polygon(p['ring']) for p in platforms]
        if name == 'east-station': parts.append(box(u0-.04, v1-.04, u1+.04, v1+.40))
        site = unary_union(parts).convex_hull.buffer(.04, join_style=2)
        rails = []
        for e in source['elements']:
            if e.get('tags', {}).get('railway') != 'rail': continue
            line = LineString([local(p) for p in e['geometry']]).intersection(site)
            for piece in ([line] if line.geom_type == 'LineString' else getattr(line, 'geoms', [])):
                if piece.geom_type == 'LineString' and piece.length > .05:
                    rails.append({'osmId': e['id'], 'points': list(piece.simplify(.003).coords)})
        stations[name] = {'center': [round(cx/kx+geo['center'][0], 9), round(cy/1113.2+geo['center'][1], 9)],
                          'angle': angle, 'source': f'https://www.openstreetmap.org/{kind}/{identity}',
                          'footprint': list(footprint.exterior.coords), 'platforms': platforms,
                          'site': list(site.exterior.coords), 'siteMesh': mesh(site), 'rails': rails}
        print(name, 'center', stations[name]['center'], 'angle', round(math.degrees(angle), 2),
              'building bounds', tuple(round(v, 3) for v in footprint.bounds), 'platforms', len(platforms), 'rails', len(rails))
    plan = {'osmTimestamp': source['osm3s']['timestamp_osm_base'], 'sceneCenter': geo['center'],
            'sourceHash': hashlib.sha256((ROOT/'data/stations-source.json').read_bytes()).hexdigest(),
            'stations': stations}
    (ROOT/'data/stations-plan.json').write_text(json.dumps(plan, ensure_ascii=False, separators=(',', ':'))+'\n')


if __name__ == '__main__':
    prepare()
