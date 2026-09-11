"""Inspect the saved fort mesh and its local mobile terrain transition.

Run: blender --background blender/nanning-city.blend --python-exit-code 1
             --python scripts/validate_zhenning.py
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
from zhenning_landmark import UNIT, HEIGHT_SCALE, MATERIAL_KEYS, terrain_patch
from forest_canopy import terrain_surface, refined_terrain_height

catalog=json.loads((ROOT/'data/landmarks.json').read_text())
place=next(p for p in catalog if p['id']=='zhenning')
public=next(p for p in json.loads((ROOT/'public/data/landmarks.json').read_text()) if p['id']=='zhenning')
geo=json.loads((ROOT/'public/data/geography.json').read_text())
dem=json.loads((ROOT/'public/data/terrain.json').read_text())
x=(place['lon']-geo['center'][0])*1113.2*math.cos(math.radians(geo['center'][1]))
y=(place['lat']-geo['center'][1])*1113.2
# Published positions have millimetre scene rounding. Obtain the precise floor
# from the apron vertex at x + 20.5 m, rather than rounding ray heights.
obj=bpy.data.objects['Landmark_zhenning']
mesh=obj.data
mesh.calc_loop_triangles()
assert not mesh.validate(), 'Invalid fort mesh'
assert all(t.area>1e-12 for t in mesh.loop_triangles), 'Degenerate fort triangles'
assert 17_000<len(mesh.loop_triangles)<21_000, 'Fort detail is missing or excessive'
assert len({p.material_index for p in mesh.polygons})==len(MATERIAL_KEYS)
z=max(v.co.z for v in mesh.vertices if abs(v.co.x-(x+20.5*UNIT))<1e-5 and abs(v.co.y-y)<1e-5)
assert abs(z-public['position'][1])<=.00051
assert all(abs(v.co.x-x)<place['clearExtent'][0]/2 and abs(v.co.y-y)<place['clearExtent'][1]/2 for v in mesh.vertices)

def ray(u,v,h,direction,distance):
    return obj.ray_cast(Vector((x+u*UNIT,y+v*UNIT,z+h*UNIT*HEIGHT_SCALE)),Vector(direction),distance=distance)

for side in [-1,1]:
    for u in [-.9,0,.9]:
        hit,*_=ray(u,side*20,1.5,(0,-side,0),8.3*UNIT)
        assert not hit, 'A wall blocks the gate passage'
for a in [0,math.pi/2,math.pi,3*math.pi/2]:
    hit,point,*_=ray(8*math.cos(a),8*math.sin(a),6.2,(0,0,-1),2*UNIT*HEIGHT_SCALE)
    assert hit and 4.7<(point.z-z)/(UNIT*HEIGHT_SCALE)<5.1, 'A radial bridge is missing'
for a in [math.pi/4,3*math.pi/4,5*math.pi/4,7*math.pi/4]:
    hit,point,*_=ray(8.0*math.cos(a),8.0*math.sin(a),10,(0,0,-1),11*UNIT*HEIGHT_SCALE)
    assert hit and abs(point.z-z)<.002, 'The open courtyard is covered by a solid cap'

west,south,east,north=geo['bounds'];cols,rows=dem['cols'],dem['rows']
heights=dem.get('sceneHeights',dem['heights'])
def ground(xx,yy):
    u=max(0,min(cols-1.001,(xx-west)/(east-west)*(cols-1)))
    v=max(0,min(rows-1.001,(north-yy)/(north-south)*(rows-1)))
    i,j=int(u),int(v);a,b=u-i,v-j
    h=(heights[j*cols+i]*(1-a)+heights[j*cols+i+1]*a)*(1-b)+(heights[(j+1)*cols+i]*(1-a)+heights[(j+1)*cols+i+1]*a)*b
    from terrain_height import scene_height
    return scene_height(h,dem)

i0,j0,i1,j1=terrain_patch(tuple(geo['bounds']),cols,rows,tuple(geo['center']))
assert all(i%2==0 for i in [i0,j0,i1,j1])
assert (i1-i0)*(j1-j0)<=24, 'The local patch changed too much city terrain'
def at(i,j): return west+i/(cols-1)*(east-west),north-j/(rows-1)*(north-south)
for i,j in [(i,j) for i in [i0,i1] for j in range(j0+1,j1,2)]+[(i,j) for j in [j0,j1] for i in range(i0+1,i1,2)]:
    xx,yy=at(i,j)
    expected=(ground(*at(i,j-1))+ground(*at(i,j+1)))/2 if i in [i0,i1] else (ground(*at(i-1,j))+ground(*at(i+1,j)))/2
    assert abs(refined_terrain_height(i,j,ground,geo['bounds'],cols,rows)-expected)<1e-9
    # Probe both sides of the seam; no visible discontinuity at the transition.
    dx=1e-6 if i in [i0,i1] else 0;dy=1e-6 if j in [j0,j1] else 0
    a=terrain_surface(xx-dx,yy-dy,ground,geo['bounds'],cols,rows,True)
    b=terrain_surface(xx+dx,yy+dy,ground,geo['bounds'],cols,rows,True)
    assert abs(a-b)<1e-5, 'Crack between detailed and coarse terrain'
for u in [-.46,0,.46]:
    for v in [-.62,0,.55]:
        for lightweight in [False,True]:
            assert terrain_surface(x+u,y+v,ground,geo['bounds'],cols,rows,lightweight)<z, 'Terrain protrudes through the fort floor'

print(f'PASS: Zhenning {len(mesh.loop_triangles):,} triangles; two open gates, four bridges, open courtyard; {((i1-i0)*(j1-j0)//4)} mobile terrain cells refined with continuous borders.',flush=True)
