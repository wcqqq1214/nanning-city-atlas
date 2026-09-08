"""Check coordinate bounds, water triangulation, infill exclusion and GLB structure."""
import json
import math
import struct
from pathlib import Path
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.prepared import prep

ROOT = Path(__file__).resolve().parents[1]
g = json.loads((ROOT/'public/data/geography.json').read_text())
t = json.loads((ROOT/'public/data/terrain.json').read_text())
places = json.loads((ROOT/'public/data/landmarks.json').read_text())
assert len(t['heights']) == t['cols'] * t['rows']
assert all(math.isfinite(h) and -500 < h < 9000 for h in t['heights'])
assert t['minElevation'] == min(t['heights']) and t['maxElevation'] == max(t['heights'])
water = unary_union([Polygon(p[0], p[1:]) for p in g['water']])
triangles = unary_union([Polygon(tri) for tri in g['waterTriangles']])
coverage = triangles.area / water.area
assert .995 < coverage < 1.001, f'Water coverage mismatch: {coverage}'
assert triangles.difference(water.buffer(.005)).area < .001
excluded = prep(water.union(unary_union([Polygon(p[0], p[1:]) for p in g['parks']])))
for b in g['buildings']:
    if b['source'] == 'procedural':
        assert not excluded.intersects(Polygon(b['rings'][0])), 'Procedural building on water/park'
assert len({p['id'] for p in places}) == 7
w,s,e,n = g['bbox']
assert all(w < p['lon'] < e and s < p['lat'] < n for p in places)
raw = (ROOT/'public/models/nanning-city.glb').read_bytes()
magic,version,length = struct.unpack_from('<III',raw)
assert magic == 0x46546C67 and version == 2 and length == len(raw)
json_len,json_kind = struct.unpack_from('<II',raw,12)
assert json_kind == 0x4E4F534A
model = json.loads(raw[20:20+json_len])
assert 'KHR_draco_mesh_compression' in model['extensionsRequired']
names = {node.get('name') for node in model['nodes']}
assert {'Buildings','Terrain','Water','Roads','Vegetation','Bridges','Plinth'} <= names
assert all('Landmark_'+p['id'] in names for p in places if p['id'] != 'nanhu')
assert len(raw) < 8_000_000, 'Model exceeds 8 MB loading budget'
print(f'PASS: {len(g["buildings"])} building features; no infill on water or park; water coverage {coverage:.5%}; seven geolocated landmarks; valid Draco GLB {len(raw):,} bytes.')
