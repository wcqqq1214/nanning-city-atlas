"""Build P4 site geometry against both final terrain samplers, without export."""
import json,math,sys
from pathlib import Path
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
from render_scale_baseline import SampleMesh
from terrain_height import scene_height
from forest_canopy import terrain_surface
from landmark_sites import SPECS,reservation_rings,support_points
from arts_landmark import build_arts
from zhenning_landmark import build_zhenning,terrace_level
from diwang_landmark import build_diwang
from confucius_landmark import build_confucius

geo=json.loads((ROOT/'public/data/geography.json').read_text())
dem=json.loads((ROOT/'public/data/terrain.json').read_text())
catalog={p['id']:p for p in json.loads((ROOT/'data/landmarks.json').read_text())}
w,s,e,n=geo['bounds'];cols,rows=dem['cols'],dem['rows'];heights=dem['sceneHeights']
grid=(geo['bounds'],cols,rows)
def ground(x,y):
    u=max(0,min(cols-1.000001,(x-w)/(e-w)*(cols-1)));v=max(0,min(rows-1.000001,(n-y)/(n-s)*(rows-1)))
    i,j=int(u),int(v);a,b=u-i,v-j
    h=(heights[j*cols+i]*(1-a)+heights[j*cols+i+1]*a)*(1-b)+(heights[(j+1)*cols+i]*(1-a)+heights[(j+1)*cols+i+1]*a)*b
    return scene_height(h,dem)
def bounds(x,y):
    values=[terrain_surface(x,y,ground,geo['bounds'],cols,rows,m) for m in [False,True]]
    return min(values),max(values)
report={}
out=ROOT/'work/urban-structure/p4/sites';out.mkdir(parents=True,exist_ok=True)
for identity in SPECS:
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    p=catalog[identity];x=(p['lon']-geo['center'][0])*1113.2*math.cos(math.radians(geo['center'][1]));y=(p['lat']-geo['center'][1])*1113.2
    batch=SampleMesh();result={};spec=SPECS[identity]
    if identity=='arts-center':
        z=build_arts(batch,x,y,0,display_scale=spec['displayScale'],ground_bounds=bounds,terrain_grid=grid,
                     hall_segments=spec['hallSegments'],hall_rings=spec['hallRings'])
    elif identity=='zhenning':
        z=terrace_level(x,y,lambda u,v:bounds(u,v)[1],display_scale=1)
        build_zhenning(batch,x,y,z,ground_bounds=bounds,display_scale=1,height_scale=1)
    elif identity=='diwang':z=build_diwang(batch,x,y,0,bounds)
    else:
        result=build_confucius(batch,x,y,0,bounds,grid);z=result['anchorLevel']
    material=bpy.data.materials.new('site gray');material.diffuse_color=(.65,.66,.61,1)
    obj=batch.object(identity,material);obj.data.calc_loop_triangles()
    assert all(t.area>1e-12 for t in obj.data.loop_triangles),identity+' has degenerate triangles'
    assert all(abs(v.co.x-x)<p['clearExtent'][0]/2 and abs(v.co.y-y)<p['clearExtent'][1]/2 for v in obj.data.vertices),identity+' exceeds catalog bounds'
    if identity=='confucius':
        for court in spec['courts']:
            a,b,c,d=court['rectMeters'];level=result['courtLevels'][court['id']]
            for i in range(33):
                for j in range(33):
                    assert bounds(x+(a+(c-a)*i/32)/100,y+(b+(d-b)*j/32)/100)[1]<level
    if identity=='zhenning':
        for side in [-1,1]:
            for u in [-.009,0,.009]:
                hit,*_=obj.ray_cast(Vector((x+u,y+side*.20,z+.015)),Vector((0,-side,0)),distance=.083)
                assert not hit,'blocked fort entrance'
        result['stairEntryClearanceMeters']={}
        for side,extent in [(-1,.267),(1,.2382)]:
            px,py=x,y+side*extent
            hit,point,*_=obj.ray_cast(Vector((px,py,z+1)),Vector((0,0,-1)),distance=3)
            assert hit,'missing first stair tread'
            gap=(point.z-bounds(px,py)[1])*100
            assert 0<gap<.35,f'entry step ends above the ground: {gap} m'
            result['stairEntryClearanceMeters']['south' if side==-1 else 'north']=gap
    report[identity]={'triangles':len(obj.data.loop_triangles),'datum':z,**result}
    # A 5 m sampled terrain context is for visual inspection only; numerical
    # support above uses the original final triangle samplers.
    terrain=SampleMesh();wx,wy=p['clearExtent'];nx=max(2,math.ceil((wx+.5)/.05));ny=max(2,math.ceil((wy+.5)/.05))
    for i in range(nx):
        for j in range(ny):
            ring=[(x-(wx+.5)/2+(wx+.5)*a/nx,y-(wy+.5)/2+(wy+.5)*b/ny) for a,b in [(i,j),(i+1,j),(i+1,j+1),(i,j+1)]]
            terrain.face([(*q,bounds(*q)[1]-.002) for q in ring])
    mat=bpy.data.materials.new('ground');mat.diffuse_color=(.39,.49,.40,1);terrain.object('sampled ground',mat)
    high=max(v.co.z for v in obj.data.vertices);extent=max(wx,wy,(high-z)*1.1)
    target=Vector((x,y,z+(high-z)*.35))
    bpy.ops.object.camera_add();camera=bpy.context.object;camera.data.type='ORTHO';camera.data.ortho_scale=extent*1.35
    scene=bpy.context.scene;scene.camera=camera;scene.render.engine='BLENDER_WORKBENCH'
    scene.display.shading.light='STUDIO';scene.display.shading.color_type='MATERIAL';scene.display.shading.show_shadows=True;scene.display.shading.show_cavity=True
    scene.render.resolution_x=1000;scene.render.resolution_y=800;scene.render.resolution_percentage=100
    for view,direction in [('south',(1,-2,1.25)),('north',(-1,2,1.25))]:
        camera.location=target+Vector(direction)*extent;camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
        scene.render.filepath=str(out/f'{identity}-{view}.png');bpy.ops.render.render(write_still=True)
    print('PASS',identity,report[identity],flush=True)
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
