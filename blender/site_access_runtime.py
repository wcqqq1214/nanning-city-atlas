"""Apply verified access soil to a finished terrain group without changing other meshes."""
import bpy
import numpy as np

from terrain_reduction_runtime import collect,remove_group
from site_access_plan import SiteAccessPlan,activate,active_plan,suspended


def configure(env,path):
    from terrain_mesh import build
    plan=SiteAccessPlan.read(path,env['ROOT']);state=env['RNG'].getstate()
    try:
        for profile in ['detail','smooth']:
            group=None
            try:
                with suspended():group=build(env,lightweight=profile=='smooth').finish()
                for identity in plan.payload['sites']:
                    prefix='Terrain_grading_'+identity.replace('-','_')+'_0_0'
                    objects=[o for o in group.children_recursive if o.type=='MESH' and o.name.split('.')[0]==prefix]
                    if len(objects)!=1:raise ValueError('Missing native grading partition: '+prefix)
                    faces,materials,_=collect(objects);plan.validate_base(identity,profile,faces,materials)
            finally:
                if group is not None:remove_group(group)
    finally:env['RNG'].setstate(state)
    activate(plan)
    return plan


def apply_active(env,profile,group):
    plan=active_plan()
    return group if plan is None else apply_existing(env,plan,profile,group)


def emit_roads(batch,access):
    edges={};skipped=0
    for ids in access['triangles']:
        batch.face([access['topPoints'][i] for i in ids],'viaduct_asphalt')
        for a,b in zip(ids,ids[1:]+ids[:1]):
            key=tuple(sorted((a,b)));uses,_=edges.get(key,(0,(a,b)));edges[key]=(uses+1,(a,b))
    walls=0
    for uses,(a,b) in edges.values():
        if uses!=1:continue
        top=[access['topPoints'][i] for i in [a,b]];bottom=[access['soilPoints'][i] for i in [a,b]]
        for face in [[top[0],bottom[0],top[1]],[top[1],bottom[0],bottom[1]]]:
            va,vb,vc=np.asarray(face)
            if np.linalg.norm(np.cross(vb-va,vc-va))==0:skipped+=1;continue
            batch.face(face,'viaduct_concrete');walls+=1
    return {'pavingTriangles':len(access['triangles']),'wallTriangles':walls,'omittedZeroAreaWalls':skipped}


def append_roads(env,profile,parent):
    plan=active_plan()
    if plan is None:return {}
    batch=env['Batch']('GroundRoads',['viaduct_asphalt','viaduct_concrete'],spatial=True);counts={}
    for identity,profiles in plan.payload['sites'].items():
        batch.partition_override='access_'+identity.replace('-','_');batch.cell_override=(0,0)
        counts[identity]=emit_roads(batch,profiles[profile])
    temporary=batch.finish()
    for obj in list(temporary.children):obj.parent=parent
    bpy.data.objects.remove(temporary,do_unlink=True)
    return counts


def apply_existing(env,plan,profile,group):
    selected=[]
    for identity in plan.payload['sites']:
        name='Terrain_grading_'+identity.replace('-','_')+'_0_0'
        matches=[obj for obj in group.children_recursive if obj.name==name and obj.type=='MESH']
        if len(matches)!=1:raise ValueError(f'Missing original grading partition: {name}')
        obj=matches[0];triangles,materials,_=collect([obj])
        plan.validate_base(identity,profile,triangles,materials)
        selected.append((identity,obj))
    # Validate all sites before mutating any scene objects.
    batch=env['Batch']('Terrain',env['TERRAIN_MATERIALS'],spatial=True)
    for identity,obj in selected:plan.emit_terrain(batch,identity,profile)
    temporary=batch.finish()
    for obj in list(temporary.children):obj.parent=group
    bpy.data.objects.remove(temporary,do_unlink=True)
    for _,obj in selected:
        mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)
    return group
