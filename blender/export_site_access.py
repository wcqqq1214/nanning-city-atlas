"""Export the staged access/soil mesh with the actual city Batch and Draco policy."""
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
from local_terrain import MATERIAL_KEYS as TERRAIN_KEYS
from site_grading import MATERIAL_KEYS as GRADING_KEYS
from terrain_reduction_runtime import collect
from site_access_runtime import emit_roads


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);args.output.mkdir(parents=True,exist_ok=True)
    payload=json.loads(args.candidate.read_text())
    for name,expected in payload['inputs'].items():
        path=(ROOT/name).resolve();path.relative_to(ROOT)
        if digest(path)!=expected:raise ValueError(f'Stale access input: {name}')
    source=ROOT/'blender/build_city.py';tree=ast.parse(source.read_text())
    keys=TERRAIN_KEYS+GRADING_KEYS+['viaduct_asphalt','viaduct_concrete']
    definitions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['srgb','material']]
    assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MATS' for t in n.targets))
    pairs=[(k,v) for k,v in zip(assignment.value.keys,assignment.value.values) if k.value in keys]
    assignment.value.keys=[k for k,v in pairs];assignment.value.values=[v for k,v in pairs]
    batch=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Batch')
    report={'status':'isolated access export; whole city and site-edge acceptance pending','profiles':{},
            'candidateSha256':digest(args.candidate),'tools':{str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),source,ROOT/'blender/gltf_export.py',ROOT/'blender/terrain_reduction_runtime.py',ROOT/'blender/site_access_runtime.py']}}
    for profile in ['detail','smooth']:
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        for material in list(bpy.data.materials):bpy.data.materials.remove(material)
        env={'bpy':bpy,'math':math,'MINX':0,'MINY':0}
        exec(compile(ast.Module(body=[*definitions,assignment,batch],type_ignores=[]),str(source),'exec'),env)
        report['materialKeys']=keys;report['materialLabels']=[env['MATS'][key].name for key in keys]
        terrain=env['Batch']('Terrain',keys,spatial=True)
        roads=env['Batch']('GroundRoads',keys,spatial=True)
        skipped=0
        for identity,profiles in payload['sites'].items():
            access=profiles[profile]
            if 'nativeStorageAudit' not in access:raise ValueError('Prepare the float32 access candidate first')
            terrain.partition_override='grading_access_'+identity.replace('-','_');terrain.cell_override=(0,0)
            roads.partition_override='access_'+identity.replace('-','_');roads.cell_override=(0,0)
            for face,key in zip(access['terrainTriangles'],access['terrainMaterials']):terrain.face(face,key)
            skipped+=emit_roads(roads,access)['omittedZeroAreaWalls']
        record={'zeroAreaBoundaryWallFacesOmitted':skipped,'files':{}}
        for name,group in [('terrain',terrain.finish()),('roads',roads.finish())]:
            triangles,materials,normals=collect(group.children_recursive)
            path=args.output/f'{profile}-{name}.npz'
            np.savez_compressed(path,triangles=triangles,materials=materials,cornerNormals=normals)
            record[name+'Triangles']=len(triangles)
            record['files'][path.name]={'bytes':path.stat().st_size,'sha256':digest(path)}
        path=args.output/(profile+'.glb');export_city(path)
        record['files'][path.name]={'bytes':path.stat().st_size,'sha256':digest(path)}
        report['profiles'][profile]=record
        print(profile,record,flush=True)
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
