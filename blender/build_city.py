"""Create the complete Nanning scene and editable .blend with Blender 4.5+.
Run: blender --background --python blender/build_city.py
Data preparation uses WGS84; Blender uses X east, Y north, Z up.
glTF converts to Three.js X east, Y up, Z south on export.
"""
import bpy
import hashlib
import json
import math
import random
import sys
from pathlib import Path
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'blender'))
from extra_landmarks import build_extra_landmarks
from landmark_details import build_expo, build_bridge
from expo_landmark import site_distance as expo_site_distance
from sports_landmark import SITE_PADS, MATERIAL_KEYS as SPORTS_MATERIALS, pad_distance, inside_site
from tingzi_landmark import MATERIAL_KEYS as TINGZI_MATERIALS, inside_site as inside_tingzi, terrace_level
from bridge_landmark import MATERIAL_KEYS as BRIDGE_MATERIALS
from changyou_landmark import build_changyou, MATERIAL_KEYS as CHANGYOU_MATERIALS, inside_site as inside_changyou
from nanhu_landmark import build_nanhu, MATERIAL_KEYS as NANHU_MATERIALS, inside_park as inside_nanhu
from nanhu_landmark import shore_height as nanhu_shore_height, replaces_terrain_cell, build_park_terrain
from forest_canopy import PLAN as FOREST_PLAN, REGIONS as FOREST_REGIONS, REPLACED as FOREST_REPLACED
from forest_canopy import build_canopy, build_crown_clusters, terrain_surface, CANOPY_MATERIALS
from vegetation import build_tree
from station_landmarks import PLAN as STATION_PLAN, STATIONS, MATERIAL_KEYS as STATION_MATERIALS
from station_landmarks import inside_site as inside_station, ground_blend as station_ground_blend
GEO = json.loads((ROOT / 'public/data/geography.json').read_text())
DEM = json.loads((ROOT / 'public/data/terrain.json').read_text())
CATALOG = json.loads((ROOT / 'data/landmarks.json').read_text())
PLACE_BY_ID = {place['id']: place for place in CATALOG}
assert STATION_PLAN['sceneCenter'] == GEO['center'], 'Rebuild the station plan for the scene origin'
assert STATION_PLAN['sourceHash'] == hashlib.sha256((ROOT/'data/stations-source.json').read_bytes()).hexdigest(), 'Rebuild the station plan after changing railway data'
MINX, MINY, MAXX, MAXY = GEO['bounds']
assert FOREST_PLAN['center'] == GEO['center'] and FOREST_PLAN['bbox'] == GEO['bbox'], 'Rebuild the forest plan for the current city extent'
for path, fingerprint in FOREST_PLAN['inputHashes'].items():
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == fingerprint, f'Rebuild the forest plan after changing {path}'
COLS, ROWS = DEM['cols'], DEM['rows']
HEIGHTS = DEM.get('sceneHeights', DEM['heights'])
SCALE_Z = 3.0
RNG = random.Random(771)

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for block in list(bpy.data.materials):
    bpy.data.materials.remove(block)


def srgb(v):
    return v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4


def material(name, color, roughness=.85, metallic=0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    c = tuple(srgb(int(color[i:i+2], 16) / 255) for i in (0, 2, 4)) + (1,)
    m.diffuse_color = c
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = c
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    return m

MATS = {
    'ground': material('Porcelain earth', 'ced8c8'),
    'hill': material('Green hills', '719784'),
    'hillLight': material('Hill facets light', '86a08a'),
    'bank': material('Riverbank', 'b3cbb5'),
    'base': material('Cut earth', '607e74'),
    'water': material('Jade water', '3ca49b', .27, .22),
    'road': material('Road white', 'eeeee1'),
    'highway': material('Main avenue', 'f4e4b9'),
    'building': material('Warm porcelain', 'e8e9df'),
    'building2': material('Cool porcelain', 'cededb'),
    'building3': material('Sandstone porcelain', 'd9ddce'),
    'roof': material('Roof', 'f7f3e8'),
    'leaf': material('Canopy deep', '387b63'),
    'leaf2': material('Canopy jade', '529176'),
    'leaf3': material('Canopy lime', '83a077'),
    'trunk': material('Tree trunk', '637667'),
    'forest_deep': material('Forest shaded foliage', '537f68'),
    'forest_jade': material('Forest jade foliage', '608b71'),
    'forest_light': material('Forest sunlit foliage', '70967b'),
    'landmark': material('Landmark jade glass', '568f87', .28, .35),
    'accent': material('Brass accent', 'd3ae6b', .4, .2),
    'bridge': material('Bridge vermilion', 'b9654c', .65),
    'expo_membrane': material('Expo ivory membrane', 'f8f7ef', .64),
    'expo_glass': material('Expo silver sage glazing', '91b0aa', .24, .18),
    'expo_frame': material('Expo aluminium frames', 'b5bfb9', .42, .3),
    'expo_stone': material('Expo limestone terraces', 'd2d5ca'),
    'arts_white': material('Arts folded white aluminium', 'f4f5ee', .48, .08),
    'arts_shell': material('Arts recessed silver roof', 'b9c4be', .57, .10),
    'arts_soffit': material('Arts pearl canopy soffit', 'dfe4dc', .72),
    'arts_glass': material('Arts grey green foyer glazing', '68857f', .22, .23),
    'arts_frame': material('Arts brushed aluminium frames', 'a9b8b0', .36, .35),
    'arts_stone': material('Arts pale stone podium', 'd8dacc', .9),
    'sports_roof': material('Sports silver leaf roof', 'e0e7e3', .42, .28),
    'sports_soffit': material('Sports roof underside', 'a2afa9', .72, .12),
    'sports_frame': material('Sports steel structure', '98a8a1', .42, .32),
    'sports_glass': material('Sports sage glazing', '52766e', .25, .24),
    'sports_stone': material('Sports concrete terraces', 'd6d9cd', .85),
    'sports_track': material('Sports terracotta track', 'ae6453', .90),
    'sports_turf': material('Sports pitch deep green', '418367', .95),
    'sports_turf_light': material('Sports pitch mown green', '559573', .95),
    'sports_line': material('Sports field markings', 'f4f2e3', .90),
    'sports_seat_red': material('Sports terracotta seating', 'b76c51', .70),
    'sports_seat_gold': material('Sports amber seating', 'd3af68', .70),
    'sports_screen': material('Sports scoreboard', '233f3c', .40),
    'tingzi_wall': material('Tingzi warm ivory facade', 'e6decb', .82),
    'tingzi_trim': material('Tingzi white limestone mouldings', 'f8f2e5', .73),
    'tingzi_glass': material('Tingzi recessed arched glazing', '526563', .28, .12),
    'tingzi_roof': material('Tingzi terracotta spires', 'a65b42', .70),
    'tingzi_dome': material('Tingzi blue grey dome', '64848b', .46, .18),
    'tingzi_paving': material('Tingzi terrace stone', 'c9c9b9', .88),
    'tingzi_deck': material('Tingzi passenger pier decking', '918672', .85),
    'nbridge_steel': material('Nanning Bridge vermilion steel box ribs', 'b95139', .47, .28),
    'nbridge_edge': material('Nanning Bridge pale edge beams', 'd4d8cf', .75),
    'nbridge_road': material('Nanning Bridge asphalt deck', '727e78', .92),
    'nbridge_concrete': material('Nanning Bridge concrete supports', 'c3c8bc', .86),
    'nbridge_cable': material('Nanning Bridge steel cables and rails', '7b8981', .45, .42),
    'nbridge_line': material('Nanning Bridge road markings', 'eee9cf', .80),
    'changyou_tile': material('Changyou grey curved roof tiles', '69716a', .82),
    'changyou_tile_rib': material('Changyou raised tile ridges', '899187', .80),
    'changyou_eave': material('Changyou ochre eave trim', 'bc9f6d', .78),
    'changyou_wood': material('Changyou vermilion timber', '8c493a', .77),
    'changyou_dark': material('Changyou recessed timber walls', '514b3d', .83),
    'changyou_stone': material('Changyou pale stone colonnade', 'dfdccb', .86),
    'changyou_window': material('Changyou shaded glazing', '4c6960', .32, .12),
    'nanhu_stone': material('Nanhu white concrete arches', 'd9dcd2', .86),
    'nanhu_cap': material('Nanhu pale balustrade', 'f0eee1', .80),
    'nanhu_paving': material('Nanhu warm stone paths', 'cbbfaa', .88),
    'nanhu_edge': material('Nanhu grey stone edging', 'a4afa1', .90),
    'nanhu_grass': material('Nanhu causeway grass', '8ba674', .95),
    'nanhu_wood': material('Nanhu boardwalk timber', '927c59', .89),
    'nanhu_trunk': material('Nanhu tree trunks', '7c7158', .92),
    'nanhu_palm': material('Nanhu palm fronds', '507c47', .88),
    'nanhu_leaf': material('Nanhu broadleaf canopy', '62895a', .90),
    'nanhu_leaf_light': material('Nanhu sunlit foliage', '91aa6e', .92),
    'nanhu_leaf_dark': material('Nanhu shaded foliage', '477958', .91),
    'nanhu_metal': material('Nanhu garden fittings', '52675c', .62, .18),
    'station_stone': material('Station pale limestone', 'e2ddcb', .76),
    'station_paving': material('Station platform paving', 'c7cdc4', .86),
    'station_roof': material('Station silver roof panels', 'e9eeea', .43, .24),
    'station_soffit': material('Station shaded steel soffits', '9eafa6', .68, .16),
    'station_glass': material('Station sage curtain wall', '5a8d85', .26, .26),
    'station_frame': material('Station aluminium mullions', 'a3b5ae', .40, .35),
    'station_rail': material('Station rails and clock hands', '526461', .43, .36),
    'station_ballast': material('Station track ballast', '89938a', .96),
    'station_red': material('Station vermilion lettering', 'b7473b', .65),
    'station_line': material('Station clock face and safety lines', 'e7dcb0', .77),
    'station_blue': material('Nanning entrance shelter', '4d96a4', .53, .16),
}


def terrain_height(x, y):
    i = max(0, min(COLS - 1.001, (x - MINX) / (MAXX - MINX) * (COLS - 1)))
    j = max(0, min(ROWS - 1.001, (MAXY - y) / (MAXY - MINY) * (ROWS - 1)))
    ix, jy = int(i), int(j)
    a, b = i - ix, j - jy
    h = (HEIGHTS[jy*COLS+ix]*(1-a)+HEIGHTS[jy*COLS+ix+1]*a)*(1-b) + (HEIGHTS[(jy+1)*COLS+ix]*(1-a)+HEIGHTS[(jy+1)*COLS+ix+1]*a)*b
    return max(-.08, (h - 55) / 100 * SCALE_Z)


EXPO = PLACE_BY_ID['expo']
EXPO_X = (EXPO['lon']-GEO['center'][0])*1113.2*math.cos(math.radians(GEO['center'][1]))
EXPO_Y = (EXPO['lat']-GEO['center'][1])*1113.2
EXPO_GROUND = terrain_height(EXPO_X, EXPO_Y)
SPORTS = PLACE_BY_ID['sports-center']
SPORTS_X = (SPORTS['lon']-GEO['center'][0])*1113.2*math.cos(math.radians(GEO['center'][1]))
SPORTS_Y = (SPORTS['lat']-GEO['center'][1])*1113.2
SPORTS_LEVELS = [terrain_height(SPORTS_X+pad[0], SPORTS_Y+pad[1]) for pad in SITE_PADS]
NANHU_X = (PLACE_BY_ID['nanhu']['lon']-GEO['center'][0])*1113.2*math.cos(math.radians(GEO['center'][1]))
NANHU_Y = (PLACE_BY_ID['nanhu']['lat']-GEO['center'][1])*1113.2
STATION_SITES = {}
for identity, station in STATIONS.items():
    assert [PLACE_BY_ID[identity]['lon'], PLACE_BY_ID[identity]['lat']] == station['center']
    sx = (station['center'][0]-GEO['center'][0])*1113.2*math.cos(math.radians(GEO['center'][1]))
    sy = (station['center'][1]-GEO['center'][1])*1113.2
    STATION_SITES[identity] = (sx, sy, terrain_height(sx, sy))


def height(x, y):
    h = terrain_height(x, y)
    h = nanhu_shore_height(x-NANHU_X, y-NANHU_Y, h)
    # The ~95 m display DEM cannot resolve the building's graded terrace. Level
    # its visual support, with a soft apron, so coarse hillside triangles do not
    # pass through the lobby or stairs. Raw DEM data remains unchanged.
    distance = expo_site_distance(x-EXPO_X, y-EXPO_Y)
    if distance < 1.3:
        t = max(0, min(1, (distance - .45) / .85))
        blend = t*t*(3-2*t)
        h = EXPO_GROUND*(1-blend) + h*blend
    # The low-resolution DEM cannot resolve the three graded sports terraces.
    # All scene layers use the same local correction, including roads and trees.
    for pad, level in zip(SITE_PADS, SPORTS_LEVELS):
        distance = pad_distance(x-SPORTS_X, y-SPORTS_Y, pad)
        if distance < .65:
            t = max(0, distance/.65)
            blend = t*t*(3-2*t)
            h = level*(1-blend) + h*blend
    for identity, (sx, sy, level) in STATION_SITES.items():
        if abs(x-sx) < 10 and abs(y-sy) < 10:
            blend = station_ground_blend(identity, x-sx, y-sy)
            h = level*(1-blend) + h*blend
    return h


def pos(lon,lat):
    x=(lon-GEO['center'][0])*1113.2*math.cos(math.radians(GEO['center'][1]))
    y=(lat-GEO['center'][1])*1113.2
    return x,y,height(x,y)+.1


CLEAR_AREAS = [(*pos(p['lon'], p['lat'])[:2], *p['clearExtent']) for p in CATALOG if 'clearExtent' in p]
TINGZI_X, TINGZI_Y, _ = pos(PLACE_BY_ID['tingzi']['lon'], PLACE_BY_ID['tingzi']['lat'])
CHANGYOU_X, CHANGYOU_Y, _ = pos(PLACE_BY_ID['changyou']['lon'], PLACE_BY_ID['changyou']['lat'])


def inside_landmark(x, y):
    return (inside_site(x-SPORTS_X, y-SPORTS_Y) or
            inside_tingzi(x-TINGZI_X, y-TINGZI_Y) or
            inside_changyou(x-CHANGYOU_X, y-CHANGYOU_Y) or
            any(abs(x-sx)<7 and abs(y-sy)<7 and inside_station(identity,x-sx,y-sy)
                for identity,(sx,sy,_) in STATION_SITES.items()) or
            any(abs(x-cx) < width/2 and abs(y-cy) < depth/2 for cx,cy,width,depth in CLEAR_AREAS))


class Batch:
    def __init__(self, name, keys, spatial=False, weld=False):
        self.name, self.keys, self.v, self.f, self.mi = name, keys, [], [], []
        self.spatial = spatial
        self.weld = weld
        self.normals = []
    def face(self, vertices, key, normals=None):
        start = len(self.v)
        self.v.extend(vertices)
        self.f.append(tuple(range(start, start + len(vertices))))
        self.mi.append(self.keys.index(key))
        self.normals.append(normals)
    def box(self, x, y, z, w, d, h, key, roof=None, angle=0):
        verts = []
        for zz in [z, z+h]:
            for xx, yy in [(-w/2,-d/2),(w/2,-d/2),(w/2,d/2),(-w/2,d/2)]:
                verts.append((x+xx*math.cos(angle)-yy*math.sin(angle), y+xx*math.sin(angle)+yy*math.cos(angle), zz))
        for ids in [(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(4,5,6,7)]:
            self.face([verts[k] for k in ids], roof if ids == (4,5,6,7) and roof else key)
    def cone(self, x, y, z, radius, top_radius, h, key, segments=7):
        lower, upper = [], []
        for i in range(segments):
            a = i/segments*math.tau
            lower.append((x+math.cos(a)*radius,y+math.sin(a)*radius,z))
            upper.append((x+math.cos(a)*top_radius,y+math.sin(a)*top_radius,z+h))
        for i in range(segments):
            k = (i+1)%segments
            self.face([lower[i],lower[k],upper[k],upper[i]],key)
        self.face(upper,key)
    def beam(self, a, b, radius, key):
        axis=Vector(b)-Vector(a)
        if axis.length < .00001: return
        axis.normalize()
        side=axis.cross(Vector((0,0,1)) if abs(axis.z)<.95 else Vector((0,1,0))).normalized()*radius
        up=axis.cross(side).normalized()*radius
        rings=[[tuple(Vector(p)+side*u+up*v) for u,v in [(-1,-1),(1,-1),(1,1),(-1,1)]] for p in [a,b]]
        for i in range(4):
            j=(i+1)%4
            self.face([rings[0][i],rings[0][j],rings[1][j],rings[1][i]],key)
        self.face(rings[0],key);self.face(rings[1],key)
    def finish(self):
        def make_object(name, vertices, faces, materials, parent=None, normals=None):
            mesh=bpy.data.meshes.new(name)
            mesh.from_pydata(vertices, [], faces)
            for key in self.keys: mesh.materials.append(MATS[key])
            for polygon,index in zip(mesh.polygons,materials):
                polygon.material_index=index
                if self.weld:
                    polygon.use_smooth=True
            mesh.update()
            if normals and any(n is not None for n in normals):
                # Smooth along a membrane panel while keeping its fold creases.
                # Zero vectors retain Blender's geometric normals on other faces.
                mesh.normals_split_custom_set([
                    normal for face, custom in zip(faces, normals)
                    for normal in (custom if custom is not None else [(0, 0, 0)] * len(face))
                ])
            obj=bpy.data.objects.new(name,mesh)
            bpy.context.collection.objects.link(obj)
            obj.parent=parent
            return obj
        # Spatial batches permit Three.js frustum culling in close views.
        if not self.spatial and self.name not in ['Terrain','Buildings','Vegetation','Roads','Bridges']:
            return make_object(self.name,self.v,self.f,self.mi,normals=self.normals)
        parent=bpy.data.objects.new(self.name,None)
        bpy.context.collection.objects.link(parent)
        groups={}
        for face,index,normal in zip(self.f,self.mi,self.normals):
            verts=[self.v[i] for i in face]
            cx=sum(v[0] for v in verts)/len(verts);cy=sum(v[1] for v in verts)/len(verts)
            cell=(math.floor((cx-MINX)/80),math.floor((cy-MINY)/80))
            vertices,faces,materials,normals,lookup=groups.setdefault(cell,([],[],[],[],{}))
            if self.weld:
                # Shared canopy vertices must also share Blender's normal
                # space, otherwise tiny custom-normal differences defeat glTF
                # deduplication and encode each triangle corner separately.
                ids=[]
                for vertex in verts:
                    key=tuple(vertex)
                    if key not in lookup:
                        lookup[key]=len(vertices)
                        vertices.append(vertex)
                    ids.append(lookup[key])
                faces.append(tuple(ids))
            else:
                offset=len(vertices);vertices.extend(verts)
                faces.append(tuple(range(offset,offset+len(verts))))
            materials.append(index);normals.append(normal)
        for (i,j),(vertices,faces,materials,normals,lookup) in sorted(groups.items()):
            make_object(f'{self.name}_{i}_{j}',vertices,faces,materials,parent,normals)
        return parent


def build_forests(parent, lightweight=False):
    for region in FOREST_REGIONS:
        prefix = f'Vegetation_{region["id"]}'
        canopy = Batch(prefix+'_canopy',CANOPY_MATERIALS,spatial=True,weld=True)
        build_canopy(canopy,region,height,GEO['bounds'],COLS,ROWS,lightweight)
        canopy_group = canopy.finish()
        canopy_group.parent = parent
        for obj in canopy_group.children:
            for polygon in obj.data.polygons:
                polygon.use_smooth = True
        crowns = Batch(prefix+'_crowns',CANOPY_MATERIALS,spatial=True)
        build_crown_clusters(crowns,region,height,GEO['bounds'],COLS,ROWS,lightweight)
        crowns.finish().parent = parent


print('Building terrain...', flush=True)
ground = Batch('Terrain', ['ground','hill','hillLight','bank'])
for j in range(ROWS-1):
    for i in range(COLS-1):
        if replaces_terrain_cell(i, j):
            continue
        verts = []
        for ii, jj in [(i,j),(i+1,j),(i+1,j+1),(i,j+1)]:
            x=MINX+(MAXX-MINX)*ii/(COLS-1)
            y=MAXY-(MAXY-MINY)*jj/(ROWS-1)
            verts.append((x,y,height(x,y)))
        lc = DEM.get('landcover', [0]*(COLS*ROWS))[j*COLS+i]
        avg = sum(p[2] for p in verts)/4
        key = ('hill' if RNG.random() > .22 else 'hillLight') if lc == 1 or avg > 2.6 else ('bank' if lc == 2 else 'ground')
        ground.face([verts[0],verts[2],verts[1]],key)
        ground.face([verts[0],verts[3],verts[2]],key)
build_park_terrain(ground, NANHU_X, NANHU_Y, height)
ground.finish()
base = Batch('Plinth', ['base'])
base.box(0,0,-2.6,MAXX-MINX,MAXY-MINY,2.45,'base')
for axis in ['north','south','east','west']:
    count = COLS if axis in ['north','south'] else ROWS
    for i in range(count-1):
        if axis in ['north','south']:
            a=(MINX+(MAXX-MINX)*i/(count-1),MAXY if axis=='north' else MINY)
            b=(MINX+(MAXX-MINX)*(i+1)/(count-1),a[1])
        else:
            a=(MAXX if axis=='east' else MINX,MINY+(MAXY-MINY)*i/(count-1))
            b=(a[0],MINY+(MAXY-MINY)*(i+1)/(count-1))
        base.face([(a[0],a[1],-.15),(b[0],b[1],-.15),(b[0],b[1],height(*b)),(a[0],a[1],height(*a))],'base')
base.finish()
water = Batch('Water',['water'])
for tri in GEO['waterTriangles']:
    water.face([(x,y,.26) for x,y in tri],'water')
water.finish()

print('Building road network...', flush=True)
roadbatch=Batch('Roads',['road','highway'])
bridgebatch=Batch('Bridges',['road','bridge'])
for road in GEO['roads']:
    if road['name'] == '南宁大桥' and road['bridge']:
        # The detailed deck replaces both generic carriageway strips.
        continue
    major = road['class'] in ['trunk','primary','motorway']
    width = .26 if major else (.17 if road['class']=='secondary' else .095)
    target = bridgebatch if road['bridge'] else roadbatch
    points = road['points']
    for a,b in zip(points,points[1:]):
        dx,dy=b[0]-a[0],b[1]-a[1]
        length=math.hypot(dx,dy)
        if length < .001: continue
        # Resample to let roads follow DEM ridges rather than cut through hills.
        steps=max(1,math.ceil(length/.55))
        for k in range(steps):
            x1,y1=a[0]+dx*k/steps,a[1]+dy*k/steps
            x2,y2=a[0]+dx*(k+1)/steps,a[1]+dy*(k+1)/steps
            ox,oy=-dy/length*width/2,dx/length*width/2
            h1,h2=height(x1,y1)+.065,height(x2,y2)+.065
            if road['bridge']: h1,h2=max(1.1,h1),max(1.1,h2)
            target.face([(x1-ox,y1-oy,h1),(x2-ox,y2-oy,h2),(x2+ox,y2+oy,h2),(x1+ox,y1+oy,h1)],'road' if road['bridge'] or not major else 'highway')
roadbatch.finish(); bridgebatch.finish()

print('Building simplified city blocks...', flush=True)
buildings=Batch('Buildings',['building','building2','building3','roof'])
for b in GEO['buildings']:
    if any(n in b.get('name','') for n in ['龙象塔','华润大厦A','地王国际商会中心']): continue
    ring=b['rings'][0][:-1]
    if len(ring)<3: continue
    x=sum(p[0] for p in ring)/len(ring); y=sum(p[1] for p in ring)/len(ring)
    if inside_landmark(x,y): continue
    z=max(.4,height(x,y))+.07
    if inside_nanhu(x-NANHU_X, y-NANHU_Y):
        z=height(x,y)+.018
    hh=b['height']/100*1.55
    key=RNG.choice(['building','building','building','building2','building3'])
    for a,c in zip(ring,ring[1:]+ring[:1]):
        buildings.face([(a[0],a[1],z),(c[0],c[1],z),(c[0],c[1],z+hh),(a[0],a[1],z+hh)],key)
    roof_vertices = [Vector((a,b,z+hh)) for a,b in ring]
    for tri in tessellate_polygon([roof_vertices]):
        # Blender 5.2 returns indices; older supported releases return Vectors.
        buildings.face([tuple(roof_vertices[p] if isinstance(p, int) else p) for p in tri],'roof')
buildings.finish()

print('Building tree canopy...', flush=True)
trees=Batch('Vegetation',['leaf','leaf2','leaf3','trunk'])
original_trees = [(i,x,y,r) for i,(x,y,r) in enumerate(GEO['trees']) if not inside_landmark(x,y)
                 and not any(abs(x-sx)<7 and abs(y-sy)<7 and inside_station(identity,x-sx,y-sy,margin=r+.03)
                             for identity,(sx,sy,_) in STATION_SITES.items())
                 and not inside_tingzi(x-TINGZI_X, y-TINGZI_Y, margin=r+.04)
                 and not inside_changyou(x-CHANGYOU_X, y-CHANGYOU_Y, margin=r*.6+.02)
                 and not inside_nanhu(x-NANHU_X, y-NANHU_Y)]
visible_trees = [(i,x,y,r) for i,x,y,r in original_trees if i not in FOREST_REPLACED]
for i,x,y,r in original_trees:
    # Keep the original deterministic color sequence when interiors are removed.
    col=RNG.choice(['leaf','leaf','leaf2','leaf3'])
    if i in FOREST_REPLACED:
        continue
    z=max(.32,terrain_surface(x,y,height,GEO['bounds'],COLS,ROWS))
    build_tree(trees,x,y,z,r,col)
tree_group=trees.finish()
build_forests(tree_group)




landmarks=[]
def landmark(id):
    place = PLACE_BY_ID[id]
    x,y,z=pos(place['lon'],place['lat'])
    if id in ['sports-center', 'changyou', *STATIONS]:
        # Open fields and colonnade feet start at their local ground level.
        z = height(x, y)
    if id == 'tingzi': z = terrace_level(x, y, z, height)
    keys=['roof','landmark','accent','bridge','building']
    if id == 'expo': keys += ['expo_membrane','expo_glass','expo_frame','expo_stone']
    if id == 'arts-center': keys += ['arts_white','arts_shell','arts_soffit','arts_glass','arts_frame','arts_stone']
    if id == 'sports-center': keys += SPORTS_MATERIALS
    if id == 'tingzi': keys += TINGZI_MATERIALS
    if id == 'bridge': keys += BRIDGE_MATERIALS
    if id == 'changyou': keys += CHANGYOU_MATERIALS
    if id == 'nanhu': keys += NANHU_MATERIALS
    if id in STATIONS: keys += STATION_MATERIALS
    batch=Batch('Landmark_'+id,keys)
    landmarks.append({k:v for k,v in place.items() if k != 'clearExtent'})
    landmarks[-1]['position']=[round(x,3),round(z,3),round(-y,3)]
    return batch,x,y,z

b,x,y,z=landmark('qingxiu')
for i in range(9):
    r=.37-i*.026
    b.cone(x,y,z+i*.26,r,r*.96,.24,'roof',8)
    b.cone(x,y,z+i*.26+.21,r*1.35,r*.68,.095,'accent',8)
b.cone(x,y,z+2.5,.15,0,.52,'accent',8)
b.finish()

b,x,y,z=landmark('cr')
for i in range(8):
    size=.77-i*.055
    b.box(x,y,z+i*.78,size,size,.8,'landmark','roof')
    b.box(x,y,z+i*.78,size+.018,size+.018,.034,'accent')
b.cone(x,y,z+6.3,.23,.08,.6,'landmark',4)
b.finish()

b,x,y,z=landmark('diwang')
b.box(x,y,z,.64,.64,4.25,'landmark','roof')
b.box(x,y,z+3.8,.42,.42,.8,'landmark','roof')
b.cone(x,y,z+4.6,.28,0,.46,'accent',4)
b.finish()

b,x,y,z=landmark('expo')
build_expo(b,x,y,z)
b.finish()

b,x,y,z=landmark('changyou')
build_changyou(b,x,y,z,height)
b.finish()

b,x,y,z=landmark('nanhu')
nanhu_trees=Batch('Vegetation_nanhu',['nanhu_trunk','nanhu_palm','nanhu_leaf','nanhu_leaf_light','nanhu_leaf_dark'])
landmarks[-1]['position'][1]=round(build_nanhu(b,x,y,height,nanhu_trees),3)
nanhu_trees.finish().parent=tree_group
b.finish()

b,x,y,z=landmark('bridge')
bridge_center=build_bridge(b,GEO['roads'],height)
# Keep the geographic catalog point, and anchor the label at deck height.
landmarks[-1]['position'][1]=round(bridge_center[2],3)
b.finish()

for place in CATALOG:
    if not place['modelled']:
        x,y,z=pos(place['lon'],place['lat'])
        landmarks.append({**place,'position':[round(x,3),round(max(.3,z),3),round(-y,3)]})

# Additional cultural, campus, riverside and transport landmarks.
build_extra_landmarks(landmark, height)
landmarks.sort(key=lambda place: next(i for i,p in enumerate(CATALOG) if p['id']==place['id']))

(ROOT/'public/data/landmarks.json').write_text(json.dumps(landmarks,ensure_ascii=False,indent=2))
# Minimal overview data avoids downloading the geometry database at runtime.
summary={k:GEO[k] for k in ['bbox','center','bounds','metersPerUnit','osmTimestamp']}
summary['stats']={**GEO['stats'],'trees':len(visible_trees)}
summary['forestCanopy']={'areaKm2':FOREST_PLAN['areaKm2'],'stage':FOREST_PLAN['stage'],
    'source':'OSM natural=wood / landuse=forest','sourceCount':len(FOREST_PLAN['sources']),
    'regions':[{'id':r['id'],'areaKm2':r['areaKm2']} for r in FOREST_REGIONS],
    'replacedTrees':len(original_trees)-len(visible_trees)}
summary['previousBbox']=json.loads((ROOT/'data/region.json').read_text())['previousBbox']
summary.update({'water':GEO['water'],'minElevation':DEM['minElevation'],'maxElevation':DEM['maxElevation'],'terrainExaggeration':3,'buildingExaggeration':1.55})
(ROOT/'public/data/overview.json').write_text(json.dumps(summary,ensure_ascii=False,separators=(',',':')))

print('Saving Blender source and glTF...', flush=True)
bpy.ops.object.camera_add(location=(220,-290,280))
camera=bpy.context.object
camera.name='OverviewCamera'
direction=Vector((0,0,0))-camera.location
camera.rotation_euler=direction.to_track_quat('-Z','Y').to_euler()
camera.data.type='ORTHO';camera.data.ortho_scale=max(MAXX-MINX,MAXY-MINY)*1.42
bpy.context.scene.camera=camera
bpy.ops.object.light_add(type='AREA',location=(-60,-30,160))
bpy.context.object.data.energy=80000
bpy.context.object.data.shape='DISK';bpy.context.object.data.size=110
bpy.context.scene.world.use_nodes=True
world_background=bpy.context.scene.world.node_tree.nodes.get('Background')
world_background.inputs['Color'].default_value=(.68,.76,.70,1)
world_background.inputs['Strength'].default_value=.65
bpy.context.scene.view_settings.view_transform='AgX'
bpy.context.scene.render.engine='CYCLES'
bpy.context.scene.cycles.samples=24
bpy.context.scene.render.resolution_x=1600
bpy.context.scene.render.resolution_y=1100
bpy.context.scene.render.resolution_percentage=100
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/nanning-city.blend'))
bpy.ops.export_scene.gltf(filepath=str(ROOT/'public/models/nanning-city.glb'),export_format='GLB',export_cameras=False,export_lights=False,export_yup=True,export_apply=True,export_animations=False,export_extras=True,export_draco_mesh_compression_enable=True,export_draco_mesh_compression_level=6)
print('City complete:',len(GEO['buildings']),'buildings,',len(visible_trees),'trees,',len(landmarks),'landmarks.',flush=True)

# Keep the editable .blend at full detail; export a separate lightweight model.
# Mapped buildings, roads, water and every landmark retain their full geometry.
for name in ['Terrain','Vegetation']:
    obj=bpy.data.objects.get(name)
    for child in list(obj.children_recursive): bpy.data.objects.remove(child,do_unlink=True)
    bpy.data.objects.remove(obj,do_unlink=True)
mobile_ground=Batch('Terrain',['ground','hill','hillLight','bank'])
ix=sorted(set(range(0,COLS,2))|{COLS-1});jy=sorted(set(range(0,ROWS,2))|{ROWS-1})
for j,jj in zip(jy,jy[1:]):
    for i,ii in zip(ix,ix[1:]):
        if replaces_terrain_cell(i, j):
            continue
        verts=[]
        for col,row in [(i,j),(ii,j),(ii,jj),(i,jj)]:
            x=MINX+(MAXX-MINX)*col/(COLS-1);y=MAXY-(MAXY-MINY)*row/(ROWS-1)
            verts.append((x,y,height(x,y)))
        lc=DEM['landcover'][j*COLS+i]
        key='hill' if lc==1 or sum(v[2] for v in verts)/4>2.6 else ('bank' if lc==2 else 'ground')
        mobile_ground.face([verts[0],verts[2],verts[1]],key)
        mobile_ground.face([verts[0],verts[3],verts[2]],key)
build_park_terrain(mobile_ground, NANHU_X, NANHU_Y, height)
mobile_ground.finish()
mobile_trees=Batch('Vegetation',['leaf','leaf2','leaf3','trunk'])
mobile_tree_count=0
# Subsample the original positions before removing covered forest interiors.
for order,(i,x,y,r) in enumerate(original_trees[::4]):
    if i in FOREST_REPLACED:
        continue
    mobile_tree_count+=1
    col=['leaf','leaf2','leaf3'][order%3]
    z=max(.32,terrain_surface(x,y,height,GEO['bounds'],COLS,ROWS,lightweight=True))
    build_tree(mobile_trees,x,y,z,r,col,lightweight=True)
mobile_tree_group=mobile_trees.finish()
build_forests(mobile_tree_group,lightweight=True)
nanhu_trees.finish().parent=mobile_tree_group
bpy.ops.export_scene.gltf(filepath=str(ROOT/'public/models/nanning-city-mobile.glb'),export_format='GLB',export_cameras=False,export_lights=False,export_yup=True,export_apply=True,export_animations=False,export_extras=True,export_draco_mesh_compression_enable=True,export_draco_mesh_compression_level=6)
summary['mobileTrees']=mobile_tree_count
summary['models']={}
for key,filename in [('detail','nanning-city.glb'),('smooth','nanning-city-mobile.glb')]:
    summary['models'][key]={'file':filename,'bytes':(ROOT/'public/models'/filename).stat().st_size}
(ROOT/'public/data/overview.json').write_text(json.dumps(summary,ensure_ascii=False,separators=(',',':')))
print('Desktop and mobile model variants complete.',flush=True)
