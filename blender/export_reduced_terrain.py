"""Export source and reduced native terrain in isolation, using city Draco settings.

Unchanged triangles retain their original polygon corner normals. The editable
output is a terrain-only integration candidate, never the formal city .blend.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
from capture_native_terrain import capture
from audit_planar_budget import triangles
from terrain_reduction_plan import TerrainReductionPlan


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:]);args.output.mkdir(parents=True,exist_ok=True)
    plan=TerrainReductionPlan.read(args.plan,ROOT);env=capture(plan.profile)
    faces=[];materials=[];corner_normals=[]
    for obj in bpy.data.objects:
        if obj.type!='MESH' or not obj.name.startswith('Terrain_'):continue
        if not np.array_equal(np.asarray(obj.matrix_world),np.eye(4)):
            raise ValueError('Expected baked native terrain positions')
        mesh=obj.data;t,m=triangles(mesh);faces.append(t);materials.append(m)
        normals=np.empty(len(mesh.corner_normals)*3);mesh.corner_normals.foreach_get('vector',normals)
        loops=np.empty(len(mesh.loop_triangles)*3,dtype=np.int32);mesh.loop_triangles.foreach_get('loops',loops)
        corner_normals.append(normals.reshape(-1,3)[loops.reshape(-1,3)])
    original=np.concatenate(faces);original_materials=np.concatenate(materials);original_normals=np.concatenate(corner_normals)
    reduced,reduced_materials=plan.apply(original,original_materials,plan.profile)
    keep=np.ones(len(original),dtype=bool);keep[plan.payload['removedOriginalFaces']]=False
    kept_normals=original_normals[keep]
    np.savez_compressed(args.output/'native-before.npz',triangles=original,materials=original_materials,cornerNormals=original_normals)
    env['export_city'](args.output/'terrain-before.glb')
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    batch=env['Batch']('Terrain',env['TERRAIN_MATERIALS'])
    for i,(face,material) in enumerate(zip(reduced,reduced_materials)):
        normals=kept_normals[i].tolist() if i<len(kept_normals) else None
        batch.face(face.tolist(),env['TERRAIN_MATERIALS'][int(material)],normals)
    batch.finish()
    final_faces=[];final_materials=[];final_normals=[]
    for obj in bpy.data.objects:
        if obj.type!='MESH' or not obj.name.startswith('Terrain_'):continue
        mesh=obj.data;t,m=triangles(mesh);final_faces.append(t);final_materials.append(m)
        n=np.empty(len(mesh.corner_normals)*3);mesh.corner_normals.foreach_get('vector',n)
        loops=np.empty(len(mesh.loop_triangles)*3,dtype=np.int32);mesh.loop_triangles.foreach_get('loops',loops)
        final_normals.append(n.reshape(-1,3)[loops.reshape(-1,3)])
    np.savez_compressed(args.output/'native-after.npz',triangles=np.concatenate(final_faces),materials=np.concatenate(final_materials),cornerNormals=np.concatenate(final_normals))
    env['export_city'](args.output/'terrain-after.glb')
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output/'reduced-terrain.blend'))
    # Exercise the exact dispatch method the integration will call. Fallback
    # uses the current source sampler, rather than a constant or a flat plane.
    fallback=lambda x,y:env['terrain_surface'](x,y,env['height'],env['GEO']['bounds'],env['COLS'],env['ROWS'],plan.profile=='smooth')
    maximum=0.;samples=0
    for triangle in plan.surface.triangles:
        points=[*triangle,tuple(sum(p[k] for p in triangle)/3 for k in range(3))]
        for point in points:
            maximum=max(maximum,abs(plan.sample(point[0],point[1],plan.profile,fallback)-point[2])*100);samples+=1
    assert maximum<1e-5
    files=['terrain-before.glb','terrain-after.glb','native-before.npz','native-after.npz','reduced-terrain.blend']
    report={'status':'isolated native/Draco candidate export; actual compressed comparison and city dependencies pending',
            'profile':plan.profile,'planSha256':hashlib.sha256(args.plan.read_bytes()).hexdigest(),
            'nativeTrianglesBefore':len(original),'nativeTrianglesAfter':len(reduced),'savedTriangles':len(original)-len(reduced),
            'preservedOriginalCornerNormalFaces':len(kept_normals),
            'dispatchSamples':samples,'maximumDispatchErrorMeters':maximum,
            'files':{name:{'sha256':hashlib.sha256((args.output/name).read_bytes()).hexdigest(),'bytes':(args.output/name).stat().st_size} for name in files},
            'toolHashes':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__).resolve(),ROOT/'blender/terrain_reduction_plan.py',ROOT/'blender/reduced_surface.py',ROOT/'blender/gltf_export.py']}}
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
