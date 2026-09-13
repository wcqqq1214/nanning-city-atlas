"""Export prepared buildings at measured elevations, retaining unresolved IDs."""
import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'blender'))
from building_placement import prepared,envelope,render
from building_support_plan import BuildingSupportPlan
from gltf_export import export_city


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['geography','support','output']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);args.output.mkdir(parents=True,exist_ok=True)
    geo=json.loads(args.geography.read_text());support=BuildingSupportPlan.read(args.support,ROOT)
    if digest(args.geography)!=support.payload['inputs']['geography']['sha256']:raise ValueError('Wrong support geography')
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    source=ROOT/'blender/build_city.py';tree=ast.parse(source.read_text())
    batch_class=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Batch')
    mats={}
    for key,color in [('building',(.55,.59,.62,1)),('roof',(.75,.77,.78,1))]:
        mat=bpy.data.materials.new(key);mat.diffuse_color=color;mats[key]=mat
    env={'bpy':bpy,'MATS':mats,'math':math,'MINX':geo['bounds'][0],'MINY':geo['bounds'][1]}
    exec(compile(ast.Module(body=[batch_class],type_ignores=[]),str(source),'exec'),env)
    batch=env['Batch']('Buildings_quality',['building','roof'],spatial=True)
    records=[];unresolved=[];triangles=[];materials=[];normals=[];identities=[]
    for b in geo['buildings']:
        if not prepared(b):continue
        try:placement=envelope(b,support)
        except ValueError as error:
            if b.get('use')!='dam' and support.records[b['id']]['status']=='supported':raise
            unresolved.append({'id':b['id'],'sourceRef':b.get('sourceRef'),'reason':str(error)});continue
        ring=b['rings'][0][:-1];x=sum(p[0] for p in ring)/len(ring);y=sum(p[1] for p in ring)/len(ring)
        batch.cell_override=(math.floor((x-env['MINX'])/80),math.floor((y-env['MINY'])/80))
        start=len(batch.f);result=render(batch,b,placement,'building')
        assert result is not None,b['id']
        faces=batch.f[start:];mesh=bpy.data.meshes.new('record')
        used=sorted({i for f in faces for i in f});mapping={old:new for new,old in enumerate(used)}
        mesh.from_pydata([batch.v[i] for i in used],[],[[mapping[i] for i in f] for f in faces])
        for polygon,key in zip(mesh.polygons,batch.mi[start:]):polygon.material_index=key
        mesh.update();mesh.calc_loop_triangles()
        heights=[v.co.z for v in mesh.vertices]
        assert abs(min(heights)-placement['bottom'])*100<.001,b['id']
        assert abs(max(heights)-placement['top'])*100<.001,b['id']
        for face in mesh.loop_triangles:
            assert face.area>0,b['id']
            triangles.append([tuple(mesh.vertices[i].co) for i in face.vertices])
            normals.append([tuple(mesh.corner_normals[i].vector) for i in face.loops])
            materials.append(face.material_index);identities.append(len(records))
        records.append(result);bpy.data.meshes.remove(mesh)
    batch.finish()
    np.savez_compressed(args.output/'native.npz',triangles=np.asarray(triangles),materials=np.asarray(materials),cornerNormals=np.asarray(normals),buildingIndices=np.asarray(identities))
    export_city(args.output/'buildings.glb')
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output/'buildings.blend'))
    report={'status':'measured-elevation consumer candidate; unresolved structures, site access, visibility and full city pending',
            'records':records,'unresolved':unresolved,'buildings':len(records),'triangles':len(triangles),
            'compoundBuildings':sum(r['kind']=='compound' for r in records),
            'largeReliefSiteReviews':sum(r['siteReviewRequired'] for r in records),
            'inputs':{str(p):digest(p) for p in [args.geography,args.support]},
            'toolHashes':{str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__).resolve(),source,ROOT/'blender/building_placement.py',ROOT/'blender/block_massing.py',ROOT/'blender/mapped_buildings.py',ROOT/'blender/gltf_export.py']},
            'files':{name:{'sha256':digest(args.output/name),'bytes':(args.output/name).stat().st_size} for name in ['native.npz','buildings.glb','buildings.blend']}}
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print({k:v for k,v in report.items() if k not in ['records','inputs','toolHashes','files']},flush=True)


if __name__=='__main__':main()
