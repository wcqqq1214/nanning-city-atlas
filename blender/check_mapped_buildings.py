"""Capture the actual mapped-building consumer and city Batch in isolation.

All changed mapped footprints are included, even ones hidden in the full city.
Flat bases isolate walls/roofs; terrain support and access remain separate work.
"""
import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
from mapped_buildings import build_mapped
from gltf_export import export_city


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:]);args.output.mkdir(parents=True,exist_ok=True)
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    source=ROOT/'blender/build_city.py';tree=ast.parse(source.read_text())
    batch_class=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Batch')
    mats={}
    for key,color in [('building',(.55,.59,.62,1)),('roof',(.75,.77,.78,1))]:
        mat=bpy.data.materials.new(key);mat.diffuse_color=color;mats[key]=mat
    candidate=json.loads(args.candidate.read_text())
    env={'bpy':bpy,'MATS':mats,'math':math,'MINX':candidate['bounds'][0],'MINY':candidate['bounds'][1]}
    exec(compile(ast.Module(body=[batch_class],type_ignores=[]),str(source),'exec'),env)
    batch=env['Batch']('Buildings_quality',['building','roof'],spatial=True)
    records=[];triangles=[];materials=[];identities=[]
    for b in candidate['buildings']:
        if not b.get('qualityGeometry'):continue
        ring=b['rings'][0][:-1];x=sum(p[0] for p in ring)/len(ring);y=sum(p[1] for p in ring)/len(ring)
        batch.cell_override=(math.floor((x-env['MINX'])/80),math.floor((y-env['MINY'])/80))
        start=len(batch.f);result=build_mapped(batch,b,0,b['height']/100*1.55,'building')
        assert result is not None
        # Snapshot the exact native mesh for each record, preserving its identity
        # before the production spatial batch combines neighboring buildings.
        faces=batch.f[start:];mesh=bpy.data.meshes.new('record')
        used=sorted({i for f in faces for i in f});mapping={old:new for new,old in enumerate(used)}
        mesh.from_pydata([batch.v[i] for i in used],[],[[mapping[i] for i in f] for f in faces])
        for polygon,key in zip(mesh.polygons,batch.mi[start:]):polygon.material_index=key
        mesh.update();mesh.calc_loop_triangles()
        assert len(mesh.loop_triangles)==result['triangles'],b['id']
        for t in mesh.loop_triangles:
            triangles.append([tuple(mesh.vertices[i].co) for i in t.vertices])
            materials.append(t.material_index);identities.append(len(records))
        records.append(result);bpy.data.meshes.remove(mesh)
    batch.finish()
    np.savez_compressed(args.output/'native.npz',triangles=np.asarray(triangles),materials=np.asarray(materials),buildingIndices=np.asarray(identities))
    export_city(args.output/'buildings.glb')
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output/'buildings.blend'))
    report={'status':'isolated flat-base mapped consumer; support, visibility and full city pending',
            'buildings':len(records),'courtyards':sum(r['courtyards'] for r in records),
            'triangles':len(triangles),'records':records,
            'inputs':{str(args.candidate):hashlib.sha256(args.candidate.read_bytes()).hexdigest()},
            'toolHashes':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__).resolve(),source,ROOT/'blender/mapped_buildings.py',ROOT/'blender/gltf_export.py']},
            'files':{name:{'bytes':(args.output/name).stat().st_size,'sha256':hashlib.sha256((args.output/name).read_bytes()).hexdigest()} for name in ['native.npz','buildings.glb','buildings.blend']}}
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='records'},indent=2),flush=True)


if __name__=='__main__':main()
