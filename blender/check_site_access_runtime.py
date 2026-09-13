"""Exercise downstream access replacement on both actual production terrain meshes."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'blender'))
from capture_native_terrain import capture
from site_access_plan import suspended
from site_access_runtime import configure,apply_active,append_roads
from terrain_reduction_runtime import collect


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--export',action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);args.output.mkdir(parents=True,exist_ok=True)
    plan=None
    report={'status':'actual terrain replacement and shared sampler audit; full city and visual acceptance pending',
            'candidateSha256':digest(args.candidate),'profiles':{},
            'tools':{str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__).resolve(),
                ROOT/'blender/site_access_plan.py',ROOT/'blender/site_access_runtime.py',
                ROOT/'blender/capture_native_terrain.py',ROOT/'blender/terrain_reduction_runtime.py',
                ROOT/'blender/build_city.py',ROOT/'blender/terrain_mesh.py',ROOT/'blender/forest_canopy.py']}}
    for profile in ['detail','smooth']:
        env=capture(profile);group=bpy.data.objects['Terrain'];state=env['RNG'].getstate()
        original={obj.name:collect([obj]) for obj in group.children_recursive if obj.type=='MESH'}
        if plan is None:
            plan=configure(env,args.candidate);report['inputs']=plan.payload['inputs']
        assert state==env['RNG'].getstate(),'Access prepass altered later palette randomness'
        replaced={'Terrain_grading_'+identity.replace('-','_')+'_0_0' for identity in plan.payload['sites']}
        assert replaced<=original.keys()
        group=apply_active(env,profile,group)
        final={obj.name:collect([obj]) for obj in group.children_recursive if obj.type=='MESH'}
        new_names={'Terrain_grading_access_'+identity.replace('-','_')+'_0_0' for identity in plan.payload['sites']}
        assert set(final)==set(original)-replaced|new_names,'Unexpected terrain partitions'
        for name in set(original)-replaced:
            assert all(np.array_equal(a,b) for a,b in zip(original[name],final[name])),name
        assert state==env['RNG'].getstate(),'Access altered later palette randomness'
        count=0;maximum=0.;change=0.
        from forest_canopy import terrain_surface
        assert env['terrain_surface'] is terrain_surface,'City and forest use different samplers'
        def query(x,y):return terrain_surface(x,y,env['height'],env['GEO']['bounds'],env['COLS'],env['ROWS'],profile=='smooth')
        for identity in plan.payload['sites']:
            name='Terrain_grading_access_'+identity.replace('-','_')+'_0_0'
            faces=final[name][0]
            expected=np.asarray(plan.payload['sites'][identity][profile]['terrainTriangles'])
            assert np.array_equal(faces,expected),'Stored replacement differs from access plan'
            for face in faces:
                for point in [*face,face.mean(axis=0)]:
                    value=query(*point[:2])
                    assert np.isfinite(value),'Access sampler missed its own surface'
                    maximum=max(maximum,abs(value-point[2])*100);count+=1
                    with suspended():previous=query(*point[:2])
                    change=max(change,abs(value-previous)*100)
        assert maximum<1e-5,maximum
        outside_points=[]
        for name in set(original)-replaced:
            centers=original[name][0].mean(axis=1)
            outside_points.extend(centers[::max(1,len(centers)//32),:2])
        with suspended():outside_before=[query(*point) for point in outside_points]
        assert outside_before==[query(*point) for point in outside_points],'Access changed external sampling'
        faces,materials,normals=collect(group.children_recursive)
        path=args.output/(profile+'.npz')
        np.savez_compressed(path,triangles=faces,materials=materials,cornerNormals=normals)
        record={'originalTriangles':sum(len(value[0]) for value in original.values()),
                'finalTriangles':len(faces),'replacedTriangles':sum(len(original[n][0]) for n in replaced),
                'replacementTriangles':sum(len(final[n][0]) for n in new_names),
                'unchangedMeshes':len(original)-len(replaced),
                'outsidePositionsMaterialsCornerNormalsIdentical':True,'paletteRngPreserved':True,
                'samplerPoints':count,'maximumSamplerErrorMeters':maximum,'sha256':digest(path),
                'maximumSamplerChangeFromBaseMeters':change,'outsideSamplerPoints':len(outside_points),
                'outsideSamplerUnchanged':True,'cityAndForestShareSampler':True}
        road_parent=bpy.data.objects.new('GroundRoads',None);bpy.context.collection.objects.link(road_parent)
        record['roads']=append_roads(env,profile,road_parent)
        if args.export:
            output=args.output/(profile+'.glb');env['export_city'](output)
            record['export']={'bytes':output.stat().st_size,'sha256':digest(output)}
        report['profiles'][profile]=record
        (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(profile,record,flush=True)


if __name__=='__main__':main()
