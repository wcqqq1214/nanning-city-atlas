"""Fresh terrain and native road context for rebuilding after a DEM change.

Never reads resolved road heights. Writes only work/terrain-resample/context/.
"""
import hashlib
import json
from pathlib import Path
import bpy
from minzu_avenue import build_structure as native_minzu
from bridge_landmark import MATERIAL_KEYS as NBRIDGE_KEYS


def capture(env,include_ground=False):
    root=env['ROOT'];out=root/'work/terrain-resample/context';out.mkdir(parents=True,exist_ok=True)
    Batch=env['Batch'];ground=env['height'];geo=env['GEO'];dem=env['DEM'];cols,rows=env['COLS'],env['ROWS']
    west,south,east,north=geo['bounds']
    surface=lambda x,y,m:env['terrain_surface'](x,y,ground,geo['bounds'],cols,rows,m)
    viaduct=env['Viaduct'](ground,surface);minzu=env['MinzuAvenue'](viaduct.road_level,surface)
    bridges={i:env['RiverBridge'](s,ground,minzu.road_level,lambda x,y:max(surface(x,y,False),surface(x,y,True))) for i,s in env['RIVER_BRIDGE_SPECS'].items()}
    for mobile,profile in [(False,'detail'),(True,'smooth')]:
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        terrain=Batch('Terrain',['ground','hill','hillLight','bank'])
        step=2 if mobile else 1
        ix=sorted(set(range(0,cols,step))|{cols-1});jy=sorted(set(range(0,rows,step))|{rows-1})
        zi0,zj0,zi1,zj1=env['zhenning_terrain_patch'](tuple(geo['bounds']),cols,rows,tuple(geo['center']))
        for j,jj in zip(jy,jy[1:]):
            for i,ii in zip(ix,ix[1:]):
                if env['replaces_terrain_cell'](i,j):continue
                refined=mobile and zi0<=i<zi1 and zj0<=j<zj1
                cc=list(range(i,ii+1)) if refined else [i,ii];rr=list(range(j,jj+1)) if refined else [j,jj]
                for r0,r1 in zip(rr,rr[1:]):
                    for c0,c1 in zip(cc,cc[1:]):
                        points=[]
                        for col,row in [(c0,r0),(c1,r0),(c1,r1),(c0,r1)]:
                            x=west+(east-west)*col/(cols-1);y=north-(north-south)*row/(rows-1)
                            z=env['refined_terrain_height'](col,row,ground,geo['bounds'],cols,rows) if refined else ground(x,y)
                            points.append((x,y,z))
                        lc=dem['landcover'][r0*cols+c0];key='hill' if lc==1 else 'bank' if lc==2 else 'ground'
                        terrain.face([points[0],points[2],points[1]],key);terrain.face([points[0],points[3],points[2]],key)
        env['build_park_terrain'](terrain,env['NANHU_X'],env['NANHU_Y'],ground);terrain.finish()
        b=Batch('MinzuAvenue',env['MINZU_MATERIALS'],spatial=True);native_minzu(b,minzu);b.finish()
        b=Batch('Landmark_qingxiang-viaduct',env['VIADUCT_MATERIALS']);env['build_viaduct_structure'](b,viaduct);b.finish()
        for identity,bridge in bridges.items():
            b=Batch('Landmark_'+identity,env['RIVER_BRIDGE_KEYS']);env['build_river_bridge'](b,bridge);b.finish()
        b=Batch('Landmark_bridge',NBRIDGE_KEYS);env['build_bridge'](b,geo['roads'],ground);b.finish()
        b=Batch('Railways',env['RAILWAY_MATERIALS'],spatial=True);env['build_railway_structure'](b,env['railways']);b.finish()
        if include_ground:
            b=Batch('GroundRoads',env['GROUND_ROAD_MATERIALS'],spatial=True,weld=True)
            env['build_ground_roads'](b,ground,geo['bounds'],cols,rows,lightweight=mobile,bridges=bridges.values());b.finish()
        env['export_city'](out/f'{profile}.glb')
        print('Fresh terrain context',profile,'with ground streets' if include_ground else 'native roads only',flush=True)
    inputs=['public/data/terrain.json','public/data/geography.json','data/minzu-plan.json','data/viaduct-plan.json','data/railways-plan.json','data/nanhu-plan.json']
    (out/'sources.json').write_text(json.dumps({'inputHashes':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in inputs},'includesGround':include_ground},indent=2))
