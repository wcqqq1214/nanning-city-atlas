"""Capture the production reservoir partition and city water loop in both profiles."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys

import bpy
import numpy as np


def replacement_edges(triangles,payload):
    """Actual open edges on the outer boundary or an excluded base cell."""
    bounds=payload['bounds'];segments=payload.get('replacementBoundarySegments')
    if segments is None:
        w,s,e,n=bounds;corners=[(w,s),(e,s),(e,n),(w,n),(w,s)]
        segments=list(zip(corners,corners[1:]))
    segments=np.asarray(segments);starts=segments[:,0];direction=segments[:,1]-starts
    lengths=np.sum(direction*direction,axis=1);edges={}
    for triangle in triangles:
        for a,b in zip(triangle,np.roll(triangle,-1,axis=0)):
            key=tuple(sorted((tuple(a),tuple(b))));edges[key]=edges.get(key,0)+1
    for (a,b),count in edges.items():
        if count!=1:continue
        if any(side in payload.get('restoredCityBoundarySides',[]) and abs(a[k%2]-bounds[k])<1.5e-5 and abs(b[k%2]-bounds[k])<1.5e-5
               for k,side in enumerate(['west','south','east','north'])):continue
        def on(q):
            delta=np.asarray(q[:2])-starts
            t=np.clip(np.sum(delta*direction,axis=1)/np.maximum(lengths,1e-20),0,1)
            return np.linalg.norm(delta-t[:,None]*direction,axis=1)<1.5e-5
        if np.any(on(a)&on(b)):yield np.asarray(a),np.asarray(b)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--save-blend',action='store_true',help='Keep the captured terrain and water for fixed-view inspection')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);root=args.scene_root.resolve()
    sys.path.insert(0,str(root/'blender'))
    from capture_native_terrain import capture
    from terrain_reduction_runtime import collect
    from reservoir_runtime import PLAN,PLANS,DAM_IDS
    if PLAN is None:raise ValueError('Activate the reservoir in the selected city first')
    source=root/'blender/build_city.py';tree=ast.parse(source.read_text())
    start=next(i for i,n in enumerate(tree.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='water' for t in n.targets))
    end=next(i for i,n in enumerate(tree.body[start:],start) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)
             and isinstance(n.value.func,ast.Attribute) and isinstance(n.value.func.value,ast.Name)
             and n.value.func.value.id=='custom_water' and n.value.func.attr=='finish')
    water_code=compile(ast.Module(body=tree.body[start:end+1],type_ignores=[]),str(source),'exec')
    args.output.mkdir(parents=True,exist_ok=True)
    result={'status':'production native terrain/water audit; full city and downstream roads remain pending',
            'damIds':sorted(DAM_IDS),'profiles':{},'inputs':{}}
    for profile in ['detail','smooth']:
        env=capture(profile)
        nodes=[o for o in bpy.data.objects if o.name.startswith('Terrain_reservoir_') and o.type=='MESH']
        triangles,materials,normals=collect(nodes)
        u=triangles[:,1,:2]-triangles[:,0,:2];v=triangles[:,2,:2]-triangles[:,0,:2]
        determinant=u[:,0]*v[:,1]-u[:,1]*v[:,0]
        land=determinant!=0
        if np.any(determinant[land]<=1e-12):raise ValueError('Invalid production reservoir land face')
        records={};all_triangles=triangles;all_land=land
        for plan in PLANS:
            prefix='Terrain_reservoir_'+plan.payload['id'].replace('-','_')
            patch_nodes=[o for o in nodes if o.name==prefix+'_0_0']
            triangles,_,_=collect(patch_nodes)
            u=triangles[:,1,:2]-triangles[:,0,:2];v=triangles[:,2,:2]-triangles[:,0,:2]
            land=u[:,0]*v[:,1]-u[:,1]*v[:,0]!=0
            surface,collapsed=plan.surface(env['unpatched_height'],env['GEO']['bounds'],env['COLS'],env['ROWS'],profile=='smooth',env['coarse_terrain_surface'])
            if collapsed or np.count_nonzero(land)!=len(surface.triangles) or np.count_nonzero(~land)!=2*len(plan.bank_faces(surface)):
                raise ValueError('Production reservoir partition does not contain exactly its land and banks')
            maximum=0.;samples=0
            for triangle in triangles[land]:
                for q in [*triangle,triangle.mean(axis=0)]:
                    z=env['terrain_surface'](float(q[0]),float(q[1]),env['height'],env['GEO']['bounds'],env['COLS'],env['ROWS'],profile=='smooth')
                    maximum=max(maximum,abs(z-q[2])*100);samples+=1
            if maximum>.005:raise ValueError(f'Production shared sampler differs by {maximum} m')
            seam_error=0.;seam_samples=0;bounds=plan.payload['bounds']
            for a,b in replacement_edges(triangles[land],plan.payload):
                for q in [a,b,(a+b)/2]:
                    expected=env['coarse_terrain_surface'](q[0],q[1],env['unpatched_height'],env['GEO']['bounds'],env['COLS'],env['ROWS'],profile=='smooth')
                    seam_error=max(seam_error,abs(expected-q[2])*100);seam_samples+=1
            if not seam_samples or seam_error>.005:raise ValueError(f'Production reservoir outer seam differs by {seam_error} m')
            records[plan.payload['id']]={'landTriangles':int(land.sum()),'bankTriangles':int((~land).sum()),
                'samplerSamples':samples,'maximumSamplerErrorMeters':maximum,'boundarySamples':seam_samples,
                'maximumBoundaryErrorMeters':seam_error,'nodes':[o.name for o in patch_nodes]}
        triangles=all_triangles;land=all_land
        samples=sum(r['samplerSamples'] for r in records.values());maximum=max(r['maximumSamplerErrorMeters'] for r in records.values())
        seam_samples=sum(r['boundarySamples'] for r in records.values());seam_error=max(r['maximumBoundaryErrorMeters'] for r in records.values())
        exec(water_code,env)
        water,_,_=collect([obj for obj in bpy.data.objects if obj.type=='MESH' and obj.name in ['Water','Reservoir_water_custom']])
        output=args.output/(profile+'.npz')
        np.savez_compressed(output,triangles=triangles,materials=materials,cornerNormals=normals,landMask=land,waterTriangles=water)
        result['profiles'][profile]={'terrainTriangles':len(triangles),'landTriangles':int(land.sum()),'bankTriangles':int((~land).sum()),
                                     'patches':records,'cityWaterTriangles':len(water),'samplerSamples':samples,'maximumSamplerErrorMeters':maximum,
                                     'boundarySamples':seam_samples,'maximumBoundaryErrorMeters':seam_error,
                                     'materialNames':[env['MATS'][key].name for key in env['TERRAIN_MATERIALS']],
                                     'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'nodes':[o.name for o in nodes]}
        if args.save_blend:
            blend=args.output/(profile+'.blend');bpy.ops.wm.save_as_mainfile(filepath=str(blend))
            result['profiles'][profile]['blendSha256']=hashlib.sha256(blend.read_bytes()).hexdigest()
        print(profile,result['profiles'][profile],flush=True)
    from terrain_mesh import NATIVE_DATA_INPUTS
    result['nativeDataInputs']=list(dict.fromkeys(NATIVE_DATA_INPUTS))
    paths=[*NATIVE_DATA_INPUTS,'blender/build_city.py','blender/terrain_mesh.py','blender/forest_canopy.py','blender/road_inputs.py','blender/gltf_export.py']
    result['inputs']={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in paths}
    result['toolSha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (args.output/'report.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
