"""Capture native road heights without exporting or changing the editable city."""
import json,hashlib,math
from pathlib import Path
import numpy as np
from reservoir_runtime import dedicated_dam, input_paths as reservoir_input_paths

BUILDING_ENVELOPE_INPUTS=('blender/build_city.py','blender/road_inputs.py',
                         'blender/building_placement.py','work/road-repair/building-levels.json')


def building_envelopes(geography,levels):
    """Bind every captured volume, including unmodified roofs, to a stable ID."""
    result=[];seen=set()
    for index,bottom,top in levels:
        if type(index) is not int or not 0<=index<len(geography['buildings']) or index in seen:
            raise ValueError('Invalid or duplicate captured building index')
        if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in [bottom,top]) or top<=bottom:
            raise ValueError('Invalid captured building volume')
        seen.add(index)
        result.append({'index':index,'id':geography['buildings'][index]['id'],'bottom':bottom,'top':top})
    if len({r['id'] for r in result})!=len(result):raise ValueError('Duplicate captured building ID')
    return result


def capture_building_levels(env):
    from building_placement import prepared,envelope
    support=env.get('BUILDING_SUPPORT')
    if support is not None and any(path.startswith('data/road-solids-') for path in support.payload.get('runtimeInputs',{})):
        raise ValueError('Road capture requires upstream terrain support; access/resolved-road support creates a dependency cycle')
    buildings=[];height=env['height']
    for i,b in enumerate(env['GEO']['buildings']):
        if dedicated_dam(b):continue
        if not env['city_visibility'].building_visible(b,railway_hidden=i in env['RAILWAY_BUILDINGS']):continue
        if prepared(b):
            placement=envelope(b,env.get('BUILDING_SUPPORT'))
            buildings.append([i,placement['bottom'],placement['top']])
            continue
        ring=b['rings'][0][:-1]
        x=sum(p[0] for p in ring)/len(ring);y=sum(p[1] for p in ring)/len(ring)
        z=max(.4,height(x,y))+.07
        if env['inside_nanhu'](x-env['NANHU_X'],y-env['NANHU_Y']):z=height(x,y)+.018
        if b.get('blockId'):
            from urban_blocks import support_level
            z=support_level(b,env['displayed_ground_bounds'])
        buildings.append([i,z,z+b['height']/100*b.get('displayHeightScale',1.55)])
    building_envelopes(env['GEO'],buildings)
    return buildings


def capture_road_inputs(env):
    # Fail before writing road inputs if a visible building lacks valid support.
    buildings=capture_building_levels(env)
    root=env['ROOT'];out=root/'work/road-repair';out.mkdir(parents=True,exist_ok=True)
    height=env['height'];surface=lambda x,y,m:env['terrain_surface'](x,y,height,env['GEO']['bounds'],env['COLS'],env['ROWS'],lightweight=m)
    viaduct=env['Viaduct'](height,surface);minzu=env['MinzuAvenue'](viaduct.road_level,surface)
    from road_interfaces import capture, PaintCapture
    (out/'minzu-sections.json').write_text(json.dumps(capture(minzu)))
    bridges=[env['RiverBridge'](spec,height,minzu.road_level,lambda x,y:env['displayed_ground_bounds'](x,y)[1]) for spec in env['RIVER_BRIDGE_SPECS'].values()]
    class Capture:
        def __init__(self):self.paint=[];self.walls=[]
        def capture_vertices(self,vertices,floors):self.vertices=vertices;self.floors=floors
        def face(self,vertices,material):
            if material=='viaduct_line':self.paint.append(vertices)
            elif material=='viaduct_concrete':self.walls.append(vertices)
    for mobile,profile in [(False,'detail'),(True,'smooth')]:
        paint=PaintCapture()
        env['build_minzu_details'](paint,minzu,lightweight=mobile,native=True)
        np.save(out/f'minzu-paint-{profile}.npy',np.asarray(paint.faces))
        net=env['ElevatedRoads'](height,surface,bridges=bridges,lightweight=mobile,minzu=minzu)
        capture=Capture()
        env['build_ground_roads'](capture,height,env['GEO']['bounds'],env['COLS'],env['ROWS'],lightweight=mobile,bridges=bridges,elevated=net)
        np.savez_compressed(out/f'inputs-{profile}.npz',vertices=np.asarray(capture.vertices),floors=np.asarray(capture.floors),paint=np.asarray(capture.paint),walls=np.asarray(capture.walls))
        (out/f'levels-{profile}.json').write_text(json.dumps(net.levels,separators=(',',':')))
        piers=[]
        for i,(r,path) in enumerate(zip(net.routes,net.paths)):
            for s in r['piers']:
                x,y=path.at(s)[:2];piers.append([i,s,x,y,min(height(x,y),surface(x,y,False),surface(x,y,True))-.01])
        (out/f'piers-{profile}.json').write_text(json.dumps(piers,separators=(',',':')))
        print('Captured native road surfaces',profile,flush=True)
    from building_placement import prepared
    (out/'building-levels.json').write_text(json.dumps(buildings,separators=(',',':')))
    inputs=['data/elevated-roads-plan.json.gz','data/ground-roads-plan.json.gz','data/ground-roads-context.json','data/minzu-plan.json','data/bridges-plan.json','public/data/terrain.json','public/data/geography.json','blender/elevated_roads.py','blender/ground_roads.py']
    inputs+=['blender/minzu_avenue.py','blender/road_interfaces.py','blender/terrain_height.py']
    inputs+=['data/qingxiu-terrain-plan.json','blender/mountain_terrain.py','blender/cultural_landmarks.py']
    inputs+=['data/waterfront-plan.json','blender/local_terrain.py','blender/forest_canopy.py']
    inputs+=['data/nanhu-plan.json','blender/nanhu_terrain.py','blender/nanhu_landmark.py','blender/reduced_surface.py']
    inputs+=['blender/major_bridges.py','data/landmark-calibration-source.json','data/landmark-calibration-plan.json','blender/landmark_sites.py','blender/confucius_landmark.py','blender/arts_landmark.py','blender/diwang_landmark.py','blender/zhenning_landmark.py']
    inputs+=['blender/city_visibility.py',*BUILDING_ENVELOPE_INPUTS]
    if any(prepared(b) for b in env['GEO']['buildings']):
        support_path=env.get('BUILDING_SUPPORT_PATH')
        if support_path is None:raise ValueError('Capture prepared buildings with --building-support-plan')
        inputs.extend(['blender/building_placement.py','blender/block_massing.py','blender/mapped_buildings.py','blender/building_support_plan.py'])
        inputs.append(str(support_path.relative_to(root)))
        inputs.extend(env['BUILDING_SUPPORT'].payload['runtimeInputs'])
        inputs.extend(entry['path'] for entry in env['BUILDING_SUPPORT'].payload['inputs'].values())
    inputs+=['blender/terrain_mesh.py']
    inputs+=reservoir_input_paths()
    inputs+=['blender/site_access_plan.py']
    inputs+=['blender/site_grading.py','blender/block_grading.py']
    if env['GRADING_PLAN'] is not None:inputs+=['data/block-grading-plan.json','data/block-grading-source.json']
    inputs+=['blender/terrain_reduction_plan.py','blender/terrain_reduction_runtime.py','blender/reduced_surface.py']
    from terrain_reduction_plan import active_plan_paths
    inputs += [str(p.relative_to(root)) for p in active_plan_paths()]
    (out/'input-hashes.json').write_text(json.dumps({p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in inputs},indent=2))
