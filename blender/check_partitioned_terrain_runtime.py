"""Exercise object identity and face/normal ownership using the production Batch."""
import ast
from collections import Counter
import json
import math
from pathlib import Path
import sys
import bpy
import numpy as np
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'blender'))
from terrain_reduction_runtime import collect,apply_existing
from terrain_partitions import collect_partitioned,partition_digest
from terrain_reduction_plan import TerrainReductionPlan,activate,suspended,mesh_digest


def main():
    tree=ast.parse((ROOT/'blender/build_city.py').read_text())
    batch=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Batch')
    env={'bpy':bpy,'math':math,'Vector':Vector,'MINX':0,'MINY':0,
         'MATS':{key:bpy.data.materials.new(key) for key in ['ground','reservoir']},
         'TERRAIN_MATERIALS':['ground','reservoir']}
    exec(compile(ast.Module(body=[batch],type_ignores=[]),'<production Batch>','exec'),env)
    group=bpy.data.objects.new('Terrain',None);bpy.context.collection.objects.link(group)
    for i,name in enumerate(['Terrain_0_0','Terrain_grading_yard_0_0','Terrain_reservoir_lake_0_0']):
        ring=[[i*2,0,1],[i*2+1,0,1],[i*2+1,1,1],[i*2,1,1]]
        build=env['Batch'](name,env['TERRAIN_MATERIALS'])
        for a,b in zip(ring,ring[1:]+ring[:1]):
            build.face([a,b,[i*2+.5,.5,1]],env['TERRAIN_MATERIALS'][i%2],[[.1,0,.995]]*3)
        if i==0:
            # Regression from a real reservoir wall: re-encoding these retained
            # corner normals changes their direction despite identical vertices.
            build.face([[109.94999694824219,-98.29283905029297,.39259660243988037],
                        [109.94999694824219,-98.29283142089844,.3925965130329132],
                        [109.94999694824219,-98.29283142089844,.4146215319633484],
                        [109.94999694824219,-98.29283905029297,.41462159156799316]],
                       'ground',[[.8087804913520813,.5881104469299316,0]]*4)
        obj=build.finish();obj.parent=group;obj['site_id']=name;obj.hide_render=(i==2)
    source=collect_partitioned(group.children_recursive,collect)
    names=source['partitionNames'];owners=source['partitionIndices']
    originals={obj.name:(obj.as_pointer(),obj.parent.as_pointer(),obj['site_id'],obj.hide_render)
               for obj in group.children_recursive}
    retained=np.arange(4,len(owners));old=source['triangles'];mats=source['materials']
    replacement=old[:2].copy();replacement[0]=old[[0,1,2],[0,0,0]];replacement[1]=old[[0,2,3],[0,0,0]]
    after=np.concatenate([old[retained],replacement]);am=np.concatenate([mats[retained],[0,0]])
    ao=np.concatenate([owners[retained],[0,0]])
    payload={'schemaVersion':1,'metersPerUnit':100,'profile':'smooth','inputHashes':{},'materialKeys':env['TERRAIN_MATERIALS'],
             'originalMeshSha256':mesh_digest(old,mats),'candidateMeshSha256':mesh_digest(after,am),
             'removedOriginalFaces':list(range(4)),'newTriangles':replacement.tolist(),'newMaterials':[0,0],
             'partitionNames':names,'originalPartitionSha256':partition_digest(names,owners),
             'candidatePartitionSha256':partition_digest(names,ao),'newPartitionIndices':[0,0]}
    legacy={k:v for k,v in payload.items() if k not in ['partitionNames','originalPartitionSha256','candidatePartitionSha256','newPartitionIndices']}
    legacy_plan=TerrainReductionPlan(legacy);legacy_plan.apply(old,mats,'smooth')
    with suspended():
        activate(legacy_plan)
        try:apply_existing(env,'smooth',group)
        except ValueError as error:assert 'ownership-aware' in str(error)
        else:raise AssertionError('Legacy plan destroyed terrain partitions')
    assert len(collect(group.children_recursive)[0])==14
    plan=TerrainReductionPlan(payload);plan.apply(old,mats,'smooth',names,owners)
    with suspended():
        activate(plan);assert apply_existing(env,'smooth',group)==group
    actual=collect_partitioned(group.children_recursive,collect)
    assert actual['partitionNames']==names and len(actual['triangles'])==12
    def face_keys(faces,materials):return Counter((tuple(f.flatten()),int(m)) for f,m in zip(faces,materials))
    for owner,name in enumerate(names):
        obj=bpy.data.objects[name]
        assert originals[name]==(obj.as_pointer(),obj.parent.as_pointer(),obj['site_id'],obj.hide_render)
        select=actual['partitionIndices']==owner;expected=ao==owner
        assert face_keys(actual['triangles'][select],actual['materials'][select])==face_keys(after[expected],am[expected])
        assert [m.name for m in obj.data.materials]==[env['MATS'][key].name for key in env['TERRAIN_MATERIALS']]
        if owner:
            np.testing.assert_allclose(actual['cornerNormals'][select],source['cornerNormals'][owners==owner],atol=1e-5,rtol=0)
        else:
            np.testing.assert_array_equal(actual['cornerNormals'][select][:2],source['cornerNormals'][4:6])
            np.testing.assert_allclose(actual['cornerNormals'][select][2:],np.broadcast_to([0,0,1],(2,3,3)),atol=1e-6,rtol=0)
    assert not any('_reduction_candidate' in o.name for o in bpy.data.objects)
    print(json.dumps({'status':'production Batch runtime fixture passed','beforeTriangles':14,'afterTriangles':12,
                      'partitions':3,'namesParentsIdentityPropertiesMaterialsPreserved':True,
                      'retainedNormalsPreserved':True,'legacyPlanRejectedBeforeMutation':True}),flush=True)


if __name__=='__main__':main()
