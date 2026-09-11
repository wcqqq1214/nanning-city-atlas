"""Prepare the two Minzu Avenue malls from the retained OSM source (offline)."""
import hashlib
import json
import math
from pathlib import Path

import mapbox_earcut
import numpy as np
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

ROOT = Path(__file__).resolve().parents[1]


def prepare():
    source = ROOT/'data/malls-source.json'
    data = json.loads(source.read_text())
    elements = {e['id']: e for e in data['elements']}
    scene = json.loads((ROOT/'public/data/geography.json').read_text())['center']
    kx = 1113.2*math.cos(math.radians(scene[1]))
    sites = {}
    for identity, ref, towers in [
        ('hangyang', 651998761, [1482525421, 822320620, 1516356770, 1516356769]),
        ('mixc', 974187256, []),
    ]:
        shape = Polygon([(p['lon'], p['lat']) for p in elements[ref]['geometry']])
        center = [round(shape.centroid.x, 9), round(shape.centroid.y, 9)]

        def ring(way):
            poly = Polygon([((p['lon']-center[0])*kx, (p['lat']-center[1])*1113.2)
                            for p in elements[way]['geometry']])
            return [[round(x, 6), round(y, 6)] for x, y in orient(poly).exterior.coords[:-1]]

        points = ring(ref)
        indices = mapbox_earcut.triangulate_float64(np.array(points), np.array([len(points)], dtype=np.uint32))
        sites[identity] = {'center': center, 'osmId': ref, 'site': points,
                           'triangles': indices.reshape(-1, 3).tolist(),
                           'entranceRects': ([[-.055,.78,.655,.995],[-1.11,-.745,-.98,-.215]]
                                             if identity == 'mixc' else []),
                           'towers': [{'osmId': way, 'ring': ring(way)} for way in towers]}
    output = {'sceneCenter': scene, 'osmTimestamp': data['osmTimestamp'],
              'sourceHash': hashlib.sha256(source.read_bytes()).hexdigest(), 'sites': sites}
    (ROOT/'data/malls-plan.json').write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    print('Prepared Hangyang and MixC site plans from retained OSM outlines.')


if __name__ == '__main__':
    prepare()
