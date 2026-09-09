"""Check coordinate bounds, water triangulation, infill exclusion and GLB structure."""
import json
import math
import struct
import sys
from pathlib import Path
from shapely.geometry import Polygon, LineString
from shapely.ops import unary_union
from shapely.prepared import prep
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'blender'))
from arts_landmark import outline as arts_outline, DISPLAY_SCALE, SITE_ANGLE
from sports_landmark import PLAN as SPORTS_PLAN, SITE_PADS, inside_site
from tingzi_landmark import SITE as TINGZI_SITE, site_xy as tingzi_xy, inside_site as inside_tingzi
from bridge_landmark import BridgePath, MAIN_SPAN, NORTH_APPROACH
g = json.loads((ROOT/'public/data/geography.json').read_text())
t = json.loads((ROOT/'public/data/terrain.json').read_text())
places = json.loads((ROOT/'public/data/landmarks.json').read_text())
catalog = json.loads((ROOT/'data/landmarks.json').read_text())
region = json.loads((ROOT/'data/region.json').read_text())
assert g['bbox'] == t['bbox'] == region['bbox']
assert g['bbox'][0] < region['previousBbox'][0] - .1
assert len(g['buildings']) > 9000, 'Expanded city unexpectedly lost its building coverage'
assert len(t['heights']) == t['cols'] * t['rows']
assert all(math.isfinite(h) and -500 < h < 9000 for h in t['heights'])
assert t['minElevation'] == min(t['heights']) and t['maxElevation'] == max(t['heights'])
water = unary_union([Polygon(p[0], p[1:]) for p in g['water']])
triangles = unary_union([Polygon(tri) for tri in g['waterTriangles']])
coverage = triangles.area / water.area
assert .995 < coverage < 1.001, f'Water coverage mismatch: {coverage}'
assert triangles.difference(water.buffer(.005)).area < .001
excluded = prep(water.union(unary_union([Polygon(p[0], p[1:]) for p in g['parks']])))
urban = prep(unary_union([Polygon(p[0], p[1:]) for p in g['urban'] + g['inferredUrban']]))
mapped = prep(unary_union([Polygon(b['rings'][0]) for b in g['buildings'] if b['source'] == 'osm']))
roads = prep(unary_union([
    LineString(r['points']).buffer(.13 if r['class'] in ['primary', 'trunk', 'motorway']
                                  else (.085 if r['class'] == 'secondary' else .0475))
    for r in g['roads']
]))
infill = []
for b in g['buildings']:
    if b['source'] == 'procedural':
        footprint = Polygon(b['rings'][0])
        assert footprint.is_valid and footprint.area > 0, 'Invalid infill footprint'
        assert urban.covers(footprint), 'Procedural building outside urban land or inferred street blocks'
        assert not excluded.intersects(footprint), 'Procedural building on water/park'
        assert not roads.intersects(footprint), 'Procedural building on a rendered road'
        assert not mapped.intersects(footprint), 'Procedural building overlaps mapped building'
        infill.append(footprint)
assert len(infill) >= 9000, 'Denser city lost its additional building coverage'
pairs = STRtree(infill).query(infill, predicate='intersects')
assert not (pairs[0] != pairs[1]).any(), 'Procedural buildings overlap one another'
assert len({p['id'] for p in places}) == len(places), 'Duplicate landmark IDs'
assert [p['id'] for p in places] == [p['id'] for p in catalog], 'Landmark list and tour catalog differ'
assert 'luowen' not in {p['id'] for p in places}, 'Removed Arts Institute landmark is still present'
for place, source in zip(places, catalog):
    assert all(place[key] == source[key] for key in ['name','lon','lat','cameraDistance','anchorHeight','modelled'])
    assert 5 <= place['cameraDistance'] <= 60
    if place.get('closeDistance'): assert 2 <= place['closeDistance'] <= place['cameraDistance']
    assert place.get('cameraBearing') == source.get('cameraBearing')
    if place.get('cameraBearing') is not None:
        assert math.isfinite(place['cameraBearing']) and 0 <= place['cameraBearing'] < 360
    x=(place['lon']-g['center'][0])*1113.2*math.cos(math.radians(g['center'][1]))
    z=-(place['lat']-g['center'][1])*1113.2
    assert abs(place['position'][0]-x)<.001 and abs(place['position'][2]-z)<.001, 'Landmark projection mismatch'
w,s,e,n = g['bbox']
assert all(w < p['lon'] < e and s < p['lat'] < n for p in places)
# Check the enlarged arts-center podium against the actual water database and
# the scene's replacement boundary, not just the abstract source-model bounds.
arts = next(p for p in catalog if p['id'] == 'arts-center')
ax = (arts['lon']-g['center'][0])*1113.2*math.cos(math.radians(g['center'][1]))
ay = (arts['lat']-g['center'][1])*1113.2
c, s = math.cos(SITE_ANGLE), math.sin(SITE_ANGLE)
podium = Polygon([(ax+DISPLAY_SCALE*1.12*(u*c-v*s), ay+DISPLAY_SCALE*1.12*(u*s+v*c))
                  for u, v in arts_outline()])
assert podium.is_valid and not podium.intersects(water), 'Arts-center podium extends into mapped water'
assert all(abs(x-ax) < arts['clearExtent'][0]/2 and abs(y-ay) < arts['clearExtent'][1]/2
           for x, y in podium.exterior.coords), 'Arts-center podium exceeds its replacement area'
sports = next(p for p in catalog if p['id'] == 'sports-center')
assert [sports['lon'], sports['lat']] == SPORTS_PLAN['center'], 'Sports model and map use different origins'
sx = (sports['lon']-g['center'][0])*1113.2*math.cos(math.radians(g['center'][1]))
sy = (sports['lat']-g['center'][1])*1113.2
for name in ['roofEast', 'roofWest', 'arena', 'aquatics']:
    item = SPORTS_PLAN[name]
    points = item.get('outline') or item['outer']+item['inner'][1:-1]
    footprint = Polygon([(sx+u, sy+v) for u, v in points])
    assert footprint.is_valid and not footprint.intersects(water), f'{name} overlaps mapped water'
    assert all(inside_site(u, v) for u, v in points), f'{name} extends outside its replacement boundary'
for cx, cy, rx, ry in SITE_PADS:
    pad = Polygon([(sx+cx+rx*math.cos(i/96*math.tau), sy+cy+ry*math.sin(i/96*math.tau))
                   for i in range(96)])
    assert not pad.intersects(water), 'Sports ground correction overlaps mapped water'
tingzi = next(p for p in catalog if p['id'] == 'tingzi')
tx = (tingzi['lon']-g['center'][0])*1113.2*math.cos(math.radians(g['center'][1]))
ty = (tingzi['lat']-g['center'][1])*1113.2
terrace = Polygon([(tx+tingzi_xy(u, v)[0], ty+tingzi_xy(u, v)[1]) for u, v in TINGZI_SITE])
assert terrace.is_valid and not terrace.intersects(water), 'Tingzi terrace extends into the river'
for building in g['buildings']:
    if building.get('name') == '广西民族剧院':
        footprint = Polygon(building['rings'][0])
        center = footprint.centroid
        assert not inside_tingzi(center.x-tx, center.y-ty), 'Tingzi replacement removes the neighbouring theatre'
        assert not footprint.intersects(terrace), 'Tingzi terrace intersects the neighbouring theatre'
bridge_path = BridgePath(g['roads'])
bridge = next(p for p in places if p['id'] == 'bridge')
span_center = bridge_path.at(NORTH_APPROACH+MAIN_SPAN/2)
assert math.dist([bridge['position'][0], -bridge['position'][2]], span_center[:2]) < .002, 'Bridge label is away from its main span'
def inspect_model(filename, budget):
    raw=(ROOT/'public/models'/filename).read_bytes()
    magic,version,length=struct.unpack_from('<III',raw)
    assert magic==0x46546C67 and version==2 and length==len(raw)
    json_len,json_kind=struct.unpack_from('<II',raw,12)
    assert json_kind==0x4E4F534A
    model=json.loads(raw[20:20+json_len])
    assert 'KHR_draco_mesh_compression' in model['extensionsRequired']
    names={node.get('name') for node in model['nodes']}
    assert {'Buildings','Terrain','Water','Roads','Vegetation','Bridges','Plinth'} <= names
    assert all('Landmark_'+p['id'] in names for p in places if p['modelled'])
    assert len(raw) < budget, f'{filename} exceeds loading budget'
    counts={}
    for mesh in model['meshes']:
        counts[mesh['name']]=sum(model['accessors'][p['indices']]['count']//3 for p in mesh['primitives'])
        if mesh['name'] == 'Landmark_sports-center':
            track = next(p for p in mesh['primitives']
                         if model['materials'][p['material']]['name'] == 'Sports terracotta track')
            floor = model['accessors'][track['attributes']['POSITION']]['min'][1]
            marker = next(p for p in places if p['id'] == 'sports-center')['position'][1]
            assert marker < floor, 'Stadium ground anchor is above the running track'
    return len(raw),counts
# Fine landmarks are identical in both qualities. Allow their shared geometry
# within bounded file sizes, while requiring substantial terrain/tree savings.
full_bytes,full=inspect_model('nanning-city.glb',9_500_000)
mobile_bytes,mobile=inspect_model('nanning-city-mobile.glb',5_300_000)
assert 30_000 < full['Landmark_sports-center'] < 55_000, 'Detailed sports venue geometry missing or over budget'
assert 15_000 < full['Landmark_tingzi'] < 30_000, 'Detailed Tingzi geometry missing or over budget'
assert 15_000 < full['Landmark_bridge'] < 40_000, 'Detailed bridge geometry missing or over budget'
assert mobile_bytes < full_bytes*.6
assert sum(mobile.values()) < sum(full.values())*.52
assert sum(full.values())-sum(mobile.values()) > 680_000
for name, count in full.items():
    if not name.startswith(('Terrain','Vegetation')):
        assert mobile[name]==count, f'Mobile lost geometry in {name}'
# Validate measurable content west of the previous boundary, not merely a wider base.
old_w=region['previousBbox'][0]
west_x=(old_w-g['center'][0])*1113.2*math.cos(math.radians(g['center'][1]))
western=sum(1 for b in g['buildings'] if max(p[0] for p in b['rings'][0])<west_x)
assert western>1000, f'Western coverage unexpectedly sparse: {western}'
print(f'PASS: {len(g["buildings"])} building features ({western} west of the old boundary); infill stays within urban land without overlapping water, parks, roads or other buildings; water coverage {coverage:.5%}; {len(places)} geolocated points.')
print(f'GLB: detail {full_bytes:,} bytes / {sum(full.values()):,} triangles; smooth {mobile_bytes:,} bytes / {sum(mobile.values()):,} triangles. Buildings, roads, water and landmarks preserved.')
