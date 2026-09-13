"""Fresh terrain and native road context for rebuilding after a DEM change.

Never reads resolved road heights. Writes only work/terrain-resample/context/.
"""
import hashlib
import json
from pathlib import Path
import bpy
from minzu_avenue import build_structure as native_minzu
from bridge_landmark import MATERIAL_KEYS as NBRIDGE_KEYS
from terrain_mesh import build as build_terrain_mesh, NATIVE_DATA_INPUTS
from terrain_reduction_runtime import apply_existing as apply_terrain_reduction
from terrain_reduction_plan import active_plan_paths
from reservoir_runtime import input_paths as reservoir_input_paths


def capture(env,include_ground=False):
    root=env['ROOT'];out=root/'work/terrain-resample/context';out.mkdir(parents=True,exist_ok=True)
    Batch=env['Batch'];ground=env['height'];geo=env['GEO'];dem=env['DEM'];cols,rows=env['COLS'],env['ROWS']
    west,south,east,north=geo['bounds']
    surface=lambda x,y,m:env['terrain_surface'](x,y,ground,geo['bounds'],cols,rows,m)
    viaduct=env['Viaduct'](ground,surface);minzu=env['MinzuAvenue'](viaduct.road_level,surface)
    bridges={i:env['RiverBridge'](s,ground,minzu.road_level,lambda x,y:max(surface(x,y,False),surface(x,y,True))) for i,s in env['RIVER_BRIDGE_SPECS'].items()}
    for mobile,profile in [(False,'detail'),(True,'smooth')]:
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        rng_state=env['RNG'].getstate()
        terrain=build_terrain_mesh(env,lightweight=mobile)
        env['RNG'].setstate(rng_state)
        apply_terrain_reduction(env,profile,terrain.finish())
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
    inputs+=['data/qingxiu-terrain-plan.json','blender/mountain_terrain.py']
    inputs+=['data/waterfront-plan.json','blender/local_terrain.py','data/bridges-plan.json','blender/major_bridges.py']
    inputs+=['blender/terrain_mesh.py']
    inputs+=reservoir_input_paths()
    inputs+=['blender/site_access_plan.py']
    inputs+=['blender/site_grading.py','blender/block_grading.py']
    if env['GRADING_PLAN'] is not None:inputs+=['data/block-grading-plan.json','data/block-grading-source.json']
    inputs+=['blender/terrain_reduction_plan.py','blender/terrain_reduction_runtime.py','blender/reduced_surface.py','blender/forest_canopy.py']
    inputs+=['blender/nanhu_terrain.py','blender/nanhu_landmark.py']
    inputs+=['blender/build_city.py','blender/gltf_export.py']
    inputs+=NATIVE_DATA_INPUTS
    if include_ground:
        inputs+=['data/ground-roads-plan.json.gz','data/ground-roads-context.json','blender/ground_roads.py']
    inputs += [str(p.relative_to(root)) for p in active_plan_paths()]
    (out/'sources.json').write_text(json.dumps({'inputHashes':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in inputs},'includesGround':include_ground},indent=2))
