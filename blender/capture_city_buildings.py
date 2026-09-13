"""Reconstruct expected prepared buildings from the final source-bound city inputs."""
import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import sys
import bpy
import numpy as np


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['scene-root','support','output']:parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);root=args.scene_root.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(root/'blender'))
    from building_support_plan import BuildingSupportPlan
    from building_placement import prepared,envelope,render,validate_road_envelope
    from city_visibility import CityVisibility
    from reservoir_runtime import dedicated_dam,DAM_IDS
    from railways import REMOVED_BUILDINGS
    from road_solids import building_limits,building_envelopes
    geo=json.loads((root/'public/data/geography.json').read_text());support=BuildingSupportPlan.read(args.support,root)
    visibility=CityVisibility(geo,json.loads((root/'data/landmarks.json').read_text()));limits=building_limits();volumes=building_envelopes(geo)
    produced_path=root/'work/urban-structure/p5/city-buildings.json';produced=json.loads(produced_path.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert produced['supportPlanSha256']==sha(args.support)
    source=root/'blender/build_city.py';tree=ast.parse(source.read_text());batch_class=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Batch')
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    mats={name:bpy.data.materials.new(name) for name in ['building','roof']}
    env={'bpy':bpy,'math':math,'MATS':mats,'MINX':geo['bounds'][0],'MINY':geo['bounds'][1]}
    exec(compile(ast.Module(body=[batch_class],type_ignores=[]),str(source),'exec'),env)
    batch=env['Batch']('Expected',['building','roof']);records=[];triangles=[];normals=[];materials=[];owners=[]
    for index,b in enumerate(geo['buildings']):
        if dedicated_dam(b) or not prepared(b) or not visibility.building_visible(b,railway_hidden=index in REMOVED_BUILDINGS):continue
        placement=envelope(b,support);validate_road_envelope(index,b,placement,volumes)
        if index in limits and limits[index] is None:continue
        first=len(batch.f);result=render(batch,b,placement,'building',limits.get(index))
        if result is None:continue
        faces=batch.f[first:];used=sorted({i for face in faces for i in face});lookup={old:new for new,old in enumerate(used)}
        mesh=bpy.data.meshes.new('expected');mesh.materials.append(mats['building']);mesh.materials.append(mats['roof']);mesh.from_pydata([batch.v[i] for i in used],[],[[lookup[i] for i in f] for f in faces]);mesh.update();mesh.calc_loop_triangles()
        for polygon,key in zip(mesh.polygons,batch.mi[first:]):polygon.material_index=key
        for face in mesh.loop_triangles:
            triangles.append([tuple(mesh.vertices[i].co) for i in face.vertices]);normals.append([tuple(mesh.corner_normals[i].vector) for i in face.loops]);materials.append(mesh.polygons[face.polygon_index].material_index);owners.append(len(records))
        records.append(result);bpy.data.meshes.remove(mesh)
    actual={r['id']:r for r in produced['records']};assert len(actual)==len(produced['records']) and set(actual)=={r['id'] for r in records}
    for row in records:
        for key in ['kind','floor','bottom','top','supportRange']:assert actual[row['id']][key]==row[key],(row['id'],key)
    assert not set(actual)&DAM_IDS
    np.savez_compressed(out/'native.npz',triangles=np.asarray(triangles),cornerNormals=np.asarray(normals),materials=np.asarray(materials),buildingIndices=np.asarray(owners))
    files=[*[root/name for name in support.payload['runtimeInputs']],*[root/'blender'/name for name in ['building_placement.py','mapped_buildings.py','block_massing.py','city_visibility.py','road_solids.py']],source,args.support,produced_path,root/'public/data/geography.json',root/'data/road-solids-detail.json',root/'data/road-solids-smooth.json',Path(__file__).resolve()]
    (out/'report.json').write_text(json.dumps({'status':'expected final prepared geometry and complete production ID set; actual city exports pending audit','records':records,'buildings':len(records),'dedicatedDamsExcluded':sorted(DAM_IDS),'nativeSha256':sha(out/'native.npz'),'inputs':{str(p.resolve()):sha(p) for p in files}},indent=2)+'\n')
    print('Expected complete city prepared buildings',len(records),'triangles',len(triangles),flush=True)


if __name__=='__main__':main()
