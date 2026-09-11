"""Check coordinate bounds, water triangulation, infill exclusion and GLB structure."""
import json
import hashlib
import math
import struct
import sys
from pathlib import Path
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union
from shapely.prepared import prep
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'blender'))
from arts_landmark import outline as arts_outline, DISPLAY_SCALE, SITE_ANGLE
from sports_landmark import PLAN as SPORTS_PLAN, SITE_PADS, inside_site
from tingzi_landmark import SITE as TINGZI_SITE, site_xy as tingzi_xy, inside_site as inside_tingzi
from bridge_landmark import BridgePath, MAIN_SPAN, NORTH_APPROACH
from changyou_landmark import ANGLE as CHANGYOU_ANGLE, WIDTH as CHANGYOU_WIDTH, DEPTH as CHANGYOU_DEPTH
from nanhu_landmark import PLAN as NANHU_PLAN, BRIDGE_LENGTH as NANHU_BRIDGE_LENGTH
from forest_canopy import PLAN as FOREST_PLAN, REGIONS as FOREST_REGIONS, build_canopy, terrain_surface
from station_landmarks import PLAN as STATION_PLAN, STATIONS, inside_site as inside_station, ground_blend as station_ground_blend
from viaduct import Viaduct
from validate_viaduct import validate_viaduct
from railways import TerrainCut
from validate_railways import validate_railways
from validate_minzu import validate_minzu
from validate_ground_roads import validate_ground_roads
from validate_elevated_roads import validate_elevated_roads
from validate_road_solids import validate_road_solids
from validate_zhuxi import validate_zhuxi
from validate_bridges import validate_bridges, SPECS as RIVER_BRIDGE_SPECS
g = json.loads((ROOT/'public/data/geography.json').read_text())
t = json.loads((ROOT/'public/data/terrain.json').read_text())
places = json.loads((ROOT/'public/data/landmarks.json').read_text())
catalog = json.loads((ROOT/'data/landmarks.json').read_text())
scene_region = json.loads((ROOT/'data/region.json').read_text())
assert g['bbox'] == t['bbox'] == scene_region['bbox']
assert g['bbox'][0] < scene_region['previousBbox'][0] - .1
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
assert not {'luowen','meili'} & {p['id'] for p in places}, 'Removed landmark is still present'
for place, source in zip(places, catalog):
    assert all(place[key] == source[key] for key in ['name','lon','lat','cameraDistance','anchorHeight','modelled'])
    assert 5 <= place['cameraDistance'] <= (90 if place['id'] == 'qingxiang-viaduct' else 60)
    if place.get('closeDistance'): assert 2 <= place['closeDistance'] <= place['cameraDistance']
    assert place.get('closeDistance') == source.get('closeDistance')
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
changyou = next(p for p in places if p['id'] == 'changyou')
cx, cy = changyou['position'][0], -changyou['position'][2]
c, s = math.cos(CHANGYOU_ANGLE), math.sin(CHANGYOU_ANGLE)
changyou_site = Polygon([(cx+u*c-v*s, cy+u*s+v*c) for u, v in [
    (-CHANGYOU_WIDTH/2, -CHANGYOU_DEPTH/2), (CHANGYOU_WIDTH/2, -CHANGYOU_DEPTH/2),
    (CHANGYOU_WIDTH/2, CHANGYOU_DEPTH/2+.14), (-CHANGYOU_WIDTH/2, CHANGYOU_DEPTH/2+.14)]])
assert not changyou_site.intersects(water), 'Changyou platform or inland stairs extend into the river'
nanhu = next(p for p in places if p['id'] == 'nanhu')
assert nanhu['modelled'] and [nanhu['lon'], nanhu['lat']] == NANHU_PLAN['center']
assert .60 < NANHU_BRIDGE_LENGTH < .66, 'Nine-arch bridge was stretched across its approach embankments'
nx = (nanhu['lon']-g['center'][0])*1113.2*math.cos(math.radians(g['center'][1]))
ny = (nanhu['lat']-g['center'][1])*1113.2
nanhu_park = Polygon([(nx+u, ny+v) for u, v in NANHU_PLAN['park']])
nanhu_paving = []
for kind in ['paths', 'square']:
    for mesh in NANHU_PLAN[kind]:
        for tri in mesh['triangles']:
            shape = Polygon([(nx+mesh['points'][i][0], ny+mesh['points'][i][1]) for i in tri])
            assert shape.is_valid and shape.area > 1e-10, 'Invalid park paving triangle'
            nanhu_paving.append(shape)
nanhu_paving = unary_union(nanhu_paving)
assert nanhu_paving.intersection(water).area < 1e-7, 'Garden paving covers the existing lake water'
assert nanhu_paving.difference(nanhu_park.buffer(.0001)).area < 1e-7, 'Garden paths leave the mapped park'
for u, v, radius in NANHU_PLAN['trees']:
    assert nanhu_park.contains(Point(nx+u, ny+v)) and not water.contains(Point(nx+u, ny+v)), 'Park tree trunk placed outside garden land'
patch = NANHU_PLAN['terrainPatch']
assert all(v % 2 == 0 for key in ['columnRange', 'rowRange'] for v in patch[key]), 'Park terrain patch does not align with the mobile terrain grid'
patch_triangles = []
for mesh in patch['meshes']:
    for tri in mesh['triangles']:
        shape = Polygon([(nx+mesh['points'][i][0], ny+mesh['points'][i][1]) for i in tri])
        assert shape.is_valid and shape.area > 1e-10, 'Invalid Nanhu terrain triangle'
        patch_triangles.append(shape)
patch_land = unary_union(patch_triangles)
assert patch_land.intersection(water.buffer(-.00002)).area < 1e-8, 'Nanhu display terrain still covers the lake'
west, south, east, north = patch['bounds']
expected_land = box(nx+west, ny+south, nx+east, ny+north).difference(water)
assert patch_land.symmetric_difference(expected_land).area < .003, 'Nanhu display terrain lost land coverage'
assert sum(p['modelled'] for p in places) == 20+len(RIVER_BRIDGE_SPECS), 'A detailed landmark is missing from the scene catalog'

# Verify mapped station placement, platform coverage, and reproducible sources.
assert STATION_PLAN['sceneCenter'] == g['center']
assert STATION_PLAN['sourceHash'] == hashlib.sha256((ROOT/'data/stations-source.json').read_bytes()).hexdigest(), 'Stale railway plan'
station_sites = {}
for identity, station in STATIONS.items():
    place = next(p for p in catalog if p['id'] == identity)
    assert [place['lon'],place['lat']] == station['center']
    assert place['modelled'] and place.get('cameraBearing') is not None
    sx=(place['lon']-g['center'][0])*1113.2*math.cos(math.radians(g['center'][1]))
    sy=(place['lat']-g['center'][1])*1113.2
    c,s=math.cos(station['angle']),math.sin(station['angle'])
    local_site=Polygon(station['site'])
    site=Polygon([(sx+u*c-v*s,sy+u*s+v*c) for u,v in station['site']])
    assert local_site.is_valid and not site.intersects(water), 'Station apron overlaps water'
    assert local_site.covers(Polygon(station['footprint']))
    assert len(station['platforms']) == (7 if identity=='nanning-station' else 13)
    for platform in station['platforms']:
        ring=Polygon(platform['ring'])
        triangulated=unary_union([Polygon([platform['points'][i] for i in tri]) for tri in platform['triangles']])
        assert ring.symmetric_difference(triangulated).area < .00001, 'Rail platform coverage mismatch'
        assert local_site.covers(ring), 'Platform extends outside station replacement area'
        assert all(inside_station(identity,u*c-v*s,u*s+v*c,.00001) for u,v in platform['ring'])
    assert all(local_site.buffer(.00001).covers(LineString(rail['points'])) for rail in station['rails'])
    station_sites[identity]=(sx,sy,site)

# Validate the rendered canopy footprint and terrain clearance in both profiles.
# This catches fills across mapped holes, hidden roads/buildings, and the coarse
# mobile terrain piercing a canopy that was only fitted to bilinear heights.
for path, fingerprint in FOREST_PLAN['inputHashes'].items():
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==fingerprint, f'Stale forest plan: {path}'
assert all(s['classification'] in ['natural=wood','landuse=forest'] for s in FOREST_PLAN['sources'])
assert [r['id'] for r in FOREST_REGIONS] == [s['stage'] for s in FOREST_PLAN['rollout'] if s['enabled']]
forest = unary_union([Polygon(p[0],p[1:]) for r in FOREST_REGIONS for p in r['woodland']])
canopy_regions = [unary_union([Polygon(p[0],p[1:]) for p in r['coverage']]) for r in FOREST_REGIONS]
canopy_area = unary_union(canopy_regions)
assert all(shape.is_valid for shape in canopy_regions), 'Invalid woodland rings'
assert sum(shape.area for shape in canopy_regions)-canopy_area.area < .001, 'Rollout stages overlap'
assert abs(canopy_area.area/100-FOREST_PLAN['areaKm2']) < .001
assert canopy_area.difference(forest.buffer(.00002)).area < .001
assert canopy_area.intersection(water).area < .001
assert canopy_area.intersection(roads.context).area < .001
assert canopy_area.intersection(unary_union([Polygon(b['rings'][0]) for b in g['buildings']])).area < .001
assert canopy_area.intersection(nanhu_park).area < .001, 'Canopy obscures the hand-modelled Nanhu garden'
tower = next(p['position'] for p in places if p['id']=='qingxiu')
assert not canopy_area.contains(Point(tower[0],-tower[2])), 'Keep a clearing around Longxiang Tower'
removed = set()
for region, area in zip(FOREST_REGIONS,canopy_regions):
    assert not removed.intersection(region['replacedTreeIndices']), 'Tree replaced in multiple rollout stages'
    removed.update(region['replacedTreeIndices'])
    for index in region['replacedTreeIndices']:
        assert area.contains(Point(g['trees'][index][:2])), 'Removed a tree outside its woodland region'
    buffered = prep(area.buffer(.00002))
    for x,y,r,aspect,angle,color in region['crownClusters']:
        assert buffered.contains(Point(x,y).buffer(r)), 'Crown cluster crosses a woodland clearing'

def terrain_ground(x, y):
    west, south, east, north = g['bounds']
    u = max(0, min(t['cols']-1.000001, (x-west)/(east-west)*(t['cols']-1)))
    v = max(0, min(t['rows']-1.000001, (north-y)/(north-south)*(t['rows']-1)))
    i, j = int(u), int(v)
    a, b = u-i, v-j
    hs = t.get('sceneHeights',t['heights'])
    h = ((1-a)*hs[j*t['cols']+i]+a*hs[j*t['cols']+i+1])*(1-b)
    h += ((1-a)*hs[(j+1)*t['cols']+i]+a*hs[(j+1)*t['cols']+i+1])*b
    from terrain_height import scene_height
    return scene_height(h,t)

railway_cuts=TerrainCut(json.loads((ROOT/'public/data/overview.json').read_text())['railways']['terrainCuts'])
def raw_ground(x, y):
    h=terrain_ground(x,y)
    for identity,(sx,sy,_) in station_sites.items():
        if abs(x-sx)<10 and abs(y-sy)<10:
            blend=station_ground_blend(identity,x-sx,y-sy)
            h=terrain_ground(sx,sy)*(1-blend)+h*blend
    return railway_cuts.height(x,y,h)

viaduct=Viaduct(raw_ground, lambda x,y,mobile: terrain_surface(x,y,raw_ground,g['bounds'],t['cols'],t['rows'],lightweight=mobile))
validate_viaduct(viaduct,g,catalog,ROOT)

for identity,(sx,sy,site) in station_sites.items():
    level=terrain_ground(sx,sy)
    x0,y0,x1,y1=site.bounds
    for i in range(25):
        for j in range(25):
            x,y=x0+(x1-x0)*i/24,y0+(y1-y0)*j/24
            if not site.covers(Point(x,y)): continue
            for mobile_profile in [False,True]:
                floor=terrain_surface(x,y,raw_ground,g['bounds'],t['cols'],t['rows'],mobile_profile)
                assert abs(floor-level)<.00001, f'{identity} terrace intersects displayed terrain'

class CanopyProbe:
    def __init__(self, lightweight):
        self.lightweight = lightweight
        self.footprints = []

    def face(self, vertices, color, normals=None):
        assert all(math.isfinite(c) for v in vertices for c in v)
        polygon = Polygon([v[:2] for v in vertices])
        assert polygon.is_valid and polygon.area > 1e-10
        self.footprints.append(polygon)
        for weights in [(1/3,1/3,1/3),(.5,.5,0),(.5,0,.5),(0,.5,.5)]:
            x,y,z = [sum(v[k]*w for v,w in zip(vertices,weights)) for k in range(3)]
            floor = terrain_surface(x,y,raw_ground,g['bounds'],t['cols'],t['rows'],self.lightweight)
            assert z-floor > .095, 'Forest canopy intersects the displayed terrain'

for region, area in zip(FOREST_REGIONS,canopy_regions):
    for profile in ['detail','smooth']:
        probe = CanopyProbe(profile=='smooth')
        build_canopy(probe,region,raw_ground,g['bounds'],t['cols'],t['rows'],profile=='smooth')
        merged = unary_union(probe.footprints)
        # Coordinates are retained to 0.001 m. Check the positional envelope
        # instead of summing harmless rounding slivers over hundreds of km².
        assert merged.difference(area.buffer(.00002)).area < .00001, 'Canopy filled a woodland clearing'
        assert area.buffer(-.00002).difference(merged).area < .00001, 'Canopy lost woodland coverage'
        assert sum(p.area for p in probe.footprints)-merged.area < .005, 'Canopy triangles overlap'
        print(f'Forest {region["id"]} / {profile}: footprint and terrain clearance verified.',flush=True)

def inspect_model(filename, budget):
    raw=(ROOT/'public/models'/filename).read_bytes()
    magic,version,length=struct.unpack_from('<III',raw)
    assert magic==0x46546C67 and version==2 and length==len(raw)
    json_len,json_kind=struct.unpack_from('<II',raw,12)
    assert json_kind==0x4E4F534A
    model=json.loads(raw[20:20+json_len])
    assert 'KHR_draco_mesh_compression' in model['extensionsRequired']
    names={node.get('name') for node in model['nodes']}
    assert {'Buildings','Terrain','Water','Roads','Vegetation','Bridges','Plinth','Railways'} <= names
    assert all('Landmark_'+p['id'] in names for p in places if p['modelled'])
    vegetation = next(node for node in model['nodes'] if node.get('name')=='Vegetation')
    descendants = set()
    def collect_children(node):
        for index in node.get('children',[]):
            descendants.add(index)
            collect_children(model['nodes'][index])
    collect_children(vegetation)
    for region in FOREST_REGIONS:
        for suffix in ['canopy','crowns']:
            index = next(i for i,node in enumerate(model['nodes']) if node.get('name')==f'Vegetation_{region["id"]}_{suffix}')
            assert index in descendants, 'Forest mesh is disconnected from the vegetation layer'
            assert model['nodes'][index].get('children'), 'Forest lost its spatial batches'
    nanhu_index = next(i for i,node in enumerate(model['nodes']) if node.get('name')=='Vegetation_nanhu')
    assert nanhu_index in descendants, 'Nanhu trees ignore the vegetation switch'
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
# The 60 m terrain and newly split ground streets add 4.3 / 1.6 MB.
# Keep the detailed model below a 25 MiB asset budget.
full_bytes,full=inspect_model('nanning-city.glb',26_000_000)
mobile_bytes,mobile=inspect_model('nanning-city-mobile.glb',18_000_000)
assert 30_000 < full['Landmark_sports-center'] < 55_000, 'Detailed sports venue geometry missing or over budget'
assert 15_000 < full['Landmark_tingzi'] < 30_000, 'Detailed Tingzi geometry missing or over budget'
assert 15_000 < full['Landmark_bridge'] < 40_000, 'Detailed bridge geometry missing or over budget'
assert 25_000 < full['Landmark_changyou'] < 45_000, 'Changyou detailed roof and colonnade missing or over budget'
assert 15_000 < full['Landmark_nanhu'] < 22_000, 'Nanhu bridge and garden geometry missing or over budget'
assert 6_000 < full['Landmark_nanning-station'] < 20_000, 'Nanning station geometry missing or over budget'
assert 15_000 < full['Landmark_east-station'] < 45_000, 'East station geometry missing or over budget'
assert 17_000 < full['Landmark_zhenning'] < 21_000, 'Detailed Zhenning fort missing or over budget'
assert 45_000 < full['Landmark_qingxiang-viaduct'] < 60_000, 'Full-route structure missing or over budget'
assert 0 < mobile['QingxiangViaduct_Details'] < full['QingxiangViaduct_Details'] < 20_000
# Optimizing the full-detail trees also narrows the gap between profiles. Use
# independent absolute budgets so improving detail cannot fail a ratio check.
# The complete Qingxiang road adds 0.2 MB / 45k triangles to the mobile cap.
assert sum(v for k,v in full.items() if not k.startswith(('Railways','Railway_Details','RiverBridge_Details_','GroundRoads_','ElevatedRoads_')) and k not in {'Landmark_'+identity for identity in RIVER_BRIDGE_SPECS}) < 1_650_000
# The complete fort and Minzu road structure are shared across both profiles.
assert sum(v for k,v in mobile.items() if not k.startswith(('Railways','Railway_Details','RiverBridge_Details_','GroundRoads_','ElevatedRoads_')) and k not in {'Landmark_'+identity for identity in RIVER_BRIDGE_SPECS}) < 1_000_000
assert sum(v for k,v in full.items() if k.startswith(('Railways','Railway_Details'))) < 650_000
assert sum(v for k,v in mobile.items() if k.startswith(('Railways','Railway_Details'))) < 500_000
assert mobile_bytes < full_bytes and sum(mobile.values()) < sum(full.values())
overview = json.loads((ROOT/'public/data/overview.json').read_text())
for counts, profile, tree_count, triangles_per_tree in [
    (full,'detail',overview['stats']['trees'],30),(mobile,'smooth',overview['mobileTrees'],8)]:
    singles = sum(c for name,c in counts.items() if name.startswith('Vegetation_') and name.split('_')[1].lstrip('-').isdigit())
    assert singles == tree_count*triangles_per_tree, 'City trees lost their bounded shared geometry'
    for region in FOREST_REGIONS:
        surface = sum(c for name,c in counts.items() if name.startswith(f'Vegetation_{region["id"]}_canopy_'))
        assert surface == len(region[profile]['triangles']), 'Exported forest coverage is incomplete'
        crowns = sum(c for name,c in counts.items() if name.startswith(f'Vegetation_{region["id"]}_crowns_'))
        assert crowns == len(region['crownClusters'][::2 if profile=='smooth' else 1])*20
    assert sum(c for name,c in counts.items() if name.startswith('Vegetation_nanhu')) == 83*30+36*92
for name, count in full.items():
    # Resolved Minzu joins follow each profile's ground mesh. validate_minzu()
    # independently checks the shared native structure and both resolved meshes.
    if not name.startswith(('Terrain','Vegetation','Railway_Details','MinzuAvenue_','RiverBridge_Details_','GroundRoads','ElevatedRoads','ZhuxiInterchange')) and name != 'QingxiangViaduct_Details':
        assert mobile[name]==count, f'Mobile lost geometry in {name}'
# Validate measurable content west of the previous boundary, not merely a wider base.
old_w=scene_region['previousBbox'][0]
west_x=(old_w-g['center'][0])*1113.2*math.cos(math.radians(g['center'][1]))
western=sum(1 for b in g['buildings'] if max(p[0] for p in b['rings'][0])<west_x)
assert western>1000, f'Western coverage unexpectedly sparse: {western}'
print(f'PASS: {len(g["buildings"])} building features ({western} west of the old boundary); infill stays within urban land without overlapping water, parks, roads or other buildings; water coverage {coverage:.5%}; {len(places)} geolocated points.')
print(f'GLB: detail {full_bytes:,} bytes / {sum(full.values()):,} triangles; smooth {mobile_bytes:,} bytes / {sum(mobile.values()):,} triangles. Buildings, roads, water and landmarks preserved.')
validate_railways()
validate_minzu()

validate_bridges()

# Ground streets are terrain-conforming in each profile; budget them separately.
# Joined approach solids retain their exposed walls and split paint at the
# resulting boundaries; cap these complete surfaces rather than old strips.
assert sum(v for k,v in full.items() if k.startswith('GroundRoads_')) < 530_000
assert sum(v for k,v in mobile.items() if k.startswith('GroundRoads_')) < 350_000
validate_ground_roads()
assert sum(v for k,v in full.items() if k.startswith('ElevatedRoads_'))<500_000
validate_elevated_roads()
validate_road_solids()
validate_zhuxi()

# Mall checks decode both quality profiles and audit their prepared road masks.
from validate_malls import validate_malls
validate_malls()

# Fine cultural landmarks retain their road reservations and terrain clearance.
from validate_cultural_landmarks import validate as validate_cultural
validate_cultural()
from validate_terrain import validate as validate_terrain
validate_terrain()
