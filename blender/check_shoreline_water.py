"""Export the actual city Water statements independently of downstream roads."""
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
from gltf_export import export_city
from mountain_terrain import water_level


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);args.output.mkdir(parents=True,exist_ok=True)
    geo=json.loads((ROOT/'public/data/geography.json').read_text())
    plan=json.loads((ROOT/'data/qingxiu-terrain-plan.json').read_text())
    for name,expected in plan['inputHashes'].items():
        if digest(ROOT/name)!=expected:raise ValueError('Stale mountain water source: '+name)
    source=ROOT/'blender/build_city.py';tree=ast.parse(source.read_text())
    batch=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Batch')
    start=next(i for i,n in enumerate(tree.body) if isinstance(n,ast.Assign)
               and any(isinstance(t,ast.Name) and t.id=='water' for t in n.targets))
    statements=tree.body[start:start+3]
    if not isinstance(statements[1],ast.For) or ast.unparse(statements[2])!='water.finish()':
        raise ValueError('Review changed city water statements before this capture')
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    material=bpy.data.materials.new('water');material.diffuse_color=(.3,.6,.7,1)
    env={'bpy':bpy,'math':math,'MATS':{'water':material},'GEO':geo,
         'MINX':geo['bounds'][0],'MINY':geo['bounds'][1],'mountain_water_level':water_level}
    exec(compile(ast.Module(body=[batch,*statements],type_ignores=[]),str(source),'exec'),env)
    triangles=[];normals=[]
    for obj in bpy.context.scene.objects:
        if obj.type!='MESH':continue
        mesh=obj.data;mesh.calc_loop_triangles()
        for triangle in mesh.loop_triangles:
            if triangle.area<=0:raise ValueError('Native water triangle collapsed')
            triangles.append([tuple(mesh.vertices[i].co) for i in triangle.vertices])
            normals.append([tuple(mesh.corner_normals[i].vector) for i in triangle.loops])
    np.savez_compressed(args.output/'native.npz',triangles=np.asarray(triangles),
                        cornerNormals=np.asarray(normals),materials=np.zeros(len(triangles),dtype=int))
    export_city(args.output/'water.glb')
    names=['public/data/geography.json','public/data/terrain.json','data/qingxiu-terrain-plan.json',
           'blender/build_city.py','blender/mountain_terrain.py','blender/gltf_export.py','blender/check_shoreline_water.py']
    report={'status':'actual Water consumer and compression candidate; complete city and site design pending',
            'triangles':len(triangles),'inputs':{n:digest(ROOT/n) for n in names},
            'files':{n:{'sha256':digest(args.output/n),'bytes':(args.output/n).stat().st_size} for n in ['native.npz','water.glb']}}
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(report,flush=True)
