"""Create the complete Nanning scene and editable .blend with Blender 4.5+.
Run: blender --background --python blender/build_city.py
Data preparation uses WGS84; Blender uses X east, Y north, Z up.
glTF converts to Three.js X east, Y up, Z south on export.
"""
import bpy
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
GEO = json.loads((ROOT / 'public/data/geography.json').read_text())
DEM = json.loads((ROOT / 'public/data/terrain.json').read_text())
CATALOG = json.loads((ROOT / 'data/landmarks.json').read_text())
PLACE_BY_ID = {place['id']: place for place in CATALOG}
MINX, MINY, MAXX, MAXY = GEO['bounds']
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
    'landmark': material('Landmark jade glass', '568f87', .28, .35),
    'accent': material('Brass accent', 'd3ae6b', .4, .2),
    'bridge': material('Bridge vermilion', 'b9654c', .65),
}


def height(x, y):
    i = max(0, min(COLS - 1.001, (x - MINX) / (MAXX - MINX) * (COLS - 1)))
    j = max(0, min(ROWS - 1.001, (MAXY - y) / (MAXY - MINY) * (ROWS - 1)))
    ix, jy = int(i), int(j)
    a, b = i - ix, j - jy
    h = (HEIGHTS[jy*COLS+ix]*(1-a)+HEIGHTS[jy*COLS+ix+1]*a)*(1-b) + (HEIGHTS[(jy+1)*COLS+ix]*(1-a)+HEIGHTS[(jy+1)*COLS+ix+1]*a)*b
    return max(-.08, (h - 55) / 100 * SCALE_Z)


def pos(lon,lat):
    x=(lon-GEO['center'][0])*1113.2*math.cos(math.radians(GEO['center'][1]))
    y=(lat-GEO['center'][1])*1113.2
    return x,y,height(x,y)+.1


CLEAR_AREAS = [(*pos(p['lon'], p['lat'])[:2], *p['clearExtent']) for p in CATALOG if 'clearExtent' in p]


def inside_landmark(x, y):
    return any(abs(x-cx) < width/2 and abs(y-cy) < depth/2 for cx,cy,width,depth in CLEAR_AREAS)


class Batch:
    def __init__(self, name, keys):
        self.name, self.keys, self.v, self.f, self.mi = name, keys, [], [], []
    def face(self, vertices, key):
        start = len(self.v)
        self.v.extend(vertices)
        self.f.append(tuple(range(start, start + len(vertices))))
        self.mi.append(self.keys.index(key))
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
    def finish(self):
        mesh = bpy.data.meshes.new(self.name)
        mesh.from_pydata(self.v, [], self.f)
        mesh.materials.clear()
        for key in self.keys:
            mesh.materials.append(MATS[key])
        for p, index in zip(mesh.polygons, self.mi):
            p.material_index = index
        mesh.update()
        obj = bpy.data.objects.new(self.name, mesh)
        bpy.context.collection.objects.link(obj)
        return obj


print('Building terrain...', flush=True)
ground = Batch('Terrain', ['ground','hill','hillLight','bank'])
for j in range(ROWS-1):
    for i in range(COLS-1):
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
visible_trees = [(x,y,r) for x,y,r in GEO['trees'] if not inside_landmark(x,y)]
for x,y,r in visible_trees:
    z=max(.32,height(x,y))
    trees.cone(x,y,z,.045,.03,.3,'trunk',5)
    col=RNG.choice(['leaf','leaf','leaf2','leaf3'])
    trees.cone(x,y,z+.20,r*.60,r,.28,col,7)
    trees.cone(x,y,z+.48,r,.03,.42,col,7)
trees.finish()




landmarks=[]
def landmark(id):
    place = PLACE_BY_ID[id]
    x,y,z=pos(place['lon'],place['lat'])
    batch=Batch('Landmark_'+id,['roof','landmark','accent','bridge','building'])
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
b.box(x,y,z,3.2,2.3,.44,'building','roof')
b.cone(x,y,z+.44,.63,.51,.72,'landmark',12)
for i in range(12):
    a=i/12*math.tau
    p0=(x+math.cos(a)*.15,y+math.sin(a)*.15,z+1.65)
    p1=(x+math.cos(a-.15)*.8,y+math.sin(a-.15)*.8,z+.72)
    p2=(x+math.cos(a)*1.04,y+math.sin(a)*1.04,z+.60)
    p3=(x+math.cos(a+.15)*.8,y+math.sin(a+.15)*.8,z+.72)
    b.face([p0,p1,p2,p3],'roof')
b.finish()

b,x,y,z=landmark('changyou')
for i in range(4):
    size=1.05-i*.14
    b.box(x,y,z+i*.33,size,size*.62,.3,'building')
    b.cone(x,y,z+i*.33+.3,size*.8,size*.39,.23,'accent',4)
b.finish()

b,x,y,z=landmark('bridge')
z=1.20
# Use the surveyed OSM bridge direction.
bridge_roads=[r for r in GEO['roads'] if r['name']=='南宁大桥']
if bridge_roads:
    pts=max(bridge_roads,key=lambda r:len(r['points']))['points'];a,c=pts[0],pts[-1]
else:
    a,c=(x-1,y-2),(x+1,y+2)
dx,dy=c[0]-a[0],c[1]-a[1];length=math.hypot(dx,dy);nx,ny=-dy/length,dx/length
for side in [-1,1]:
    for i in range(32):
        t=i/32;u=(i+1)/32
        p=(a[0]+dx*t+nx*.19*side,a[1]+dy*t+ny*.19*side,z+math.sin(t*math.pi)*1.65)
        q=(a[0]+dx*u+nx*.19*side,a[1]+dy*u+ny*.19*side,z+math.sin(u*math.pi)*1.65)
        b.face([(p[0]-nx*.065,p[1]-ny*.065,p[2]),(q[0]-nx*.065,q[1]-ny*.065,q[2]),(q[0]+nx*.065,q[1]+ny*.065,q[2]+.06),(p[0]+nx*.065,p[1]+ny*.065,p[2]+.06)],'bridge')
        if i%3==0:
            b.box(p[0],p[1],z,.028,.028,max(.03,p[2]-z),'roof')
b.finish()

lake = PLACE_BY_ID['nanhu']
x,y,z=pos(lake['lon'],lake['lat'])
landmarks.append({**lake,'position':[round(x,3),.3,round(-y,3)]})

# Additional cultural, campus, riverside and transport landmarks.
build_extra_landmarks(landmark)
landmarks.sort(key=lambda place: next(i for i,p in enumerate(CATALOG) if p['id']==place['id']))

(ROOT/'public/data/landmarks.json').write_text(json.dumps(landmarks,ensure_ascii=False,indent=2))
# Minimal overview data avoids downloading the geometry database at runtime.
summary={k:GEO[k] for k in ['bbox','center','bounds','metersPerUnit','osmTimestamp']}
summary['stats']={**GEO['stats'],'trees':len(visible_trees)}
summary.update({'water':GEO['water'],'minElevation':DEM['minElevation'],'maxElevation':DEM['maxElevation'],'terrainExaggeration':3,'buildingExaggeration':1.55})
(ROOT/'public/data/overview.json').write_text(json.dumps(summary,ensure_ascii=False,separators=(',',':')))

print('Saving Blender source and glTF...', flush=True)
bpy.ops.object.camera_add(location=(130,-170,165))
camera=bpy.context.object
camera.name='OverviewCamera'
direction=Vector((0,0,0))-camera.location
camera.rotation_euler=direction.to_track_quat('-Z','Y').to_euler()
camera.data.type='ORTHO';camera.data.ortho_scale=310
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
