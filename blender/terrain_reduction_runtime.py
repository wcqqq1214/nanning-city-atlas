"""Explicit Blender integration after native railway cuts have been established."""
from pathlib import Path
import bpy
import numpy as np
from terrain_mesh import build as build_terrain_mesh
from terrain_reduction_plan import TerrainReductionPlan,activate,active_plan,suspended


def collect(objects):
    triangles=[];materials=[];normals=[]
    for obj in sorted(objects,key=lambda o:o.name):
        if obj.type!='MESH':continue
        if not np.array_equal(np.asarray(obj.matrix_world),np.eye(4)):
            raise ValueError('Native terrain positions must be baked')
        mesh=obj.data;mesh.calc_loop_triangles()
        vertices=np.empty(len(mesh.vertices)*3);mesh.vertices.foreach_get('co',vertices)
        faces=np.empty(len(mesh.loop_triangles)*3,dtype=np.int32);mesh.loop_triangles.foreach_get('vertices',faces)
        keys=np.empty(len(mesh.loop_triangles),dtype=np.int32);mesh.loop_triangles.foreach_get('material_index',keys)
        n=np.empty(len(mesh.corner_normals)*3);mesh.corner_normals.foreach_get('vector',n)
        loops=np.empty(len(mesh.loop_triangles)*3,dtype=np.int32);mesh.loop_triangles.foreach_get('loops',loops)
        triangles.append(vertices.reshape(-1,3)[faces.reshape(-1,3)]);materials.append(keys)
        normals.append(n.reshape(-1,3)[loops.reshape(-1,3)])
    if not triangles:raise ValueError('No native terrain to validate')
    return np.concatenate(triangles),np.concatenate(materials),np.concatenate(normals)


def remove_group(group):
    for obj in list(group.children_recursive):
        mesh=obj.data if obj.type=='MESH' else None;bpy.data.objects.remove(obj,do_unlink=True)
        if mesh is not None and mesh.users==0:bpy.data.meshes.remove(mesh)
    bpy.data.objects.remove(group,do_unlink=True)


def configure(env,path):
    path=Path(path).resolve();path.relative_to(env['ROOT'])
    plan=TerrainReductionPlan.read(path,env['ROOT'])
    state=env['RNG'].getstate();group=None
    try:
        with suspended():
            group=build_terrain_mesh(env,lightweight=plan.profile=='smooth').finish()
            faces,materials,_=collect(group.children_recursive)
            plan.apply(faces,materials,plan.profile)
    finally:
        if group is not None:remove_group(group)
        env['RNG'].setstate(state)
    activate(plan)
    print('Validated terrain reduction:',plan.profile,plan.payload['savedTriangles'],'triangles',flush=True)
    return plan


def apply_existing(env,profile,group):
    plan=active_plan(profile)
    if plan is None:return group
    faces,materials,normals=collect(group.children_recursive)
    after,after_materials=plan.apply(faces,materials,profile)
    keep=np.ones(len(faces),dtype=bool);keep[plan.payload['removedOriginalFaces']]=False
    old_normals=normals[keep];remove_group(group)
    batch=env['Batch']('Terrain',env['TERRAIN_MATERIALS'])
    for i,(face,key) in enumerate(zip(after,after_materials)):
        batch.face(face.tolist(),env['TERRAIN_MATERIALS'][int(key)],old_normals[i].tolist() if i<len(old_normals) else None)
    return batch.finish()
