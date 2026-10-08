"""Explicit Blender integration after native railway cuts have been established."""
from pathlib import Path
import bpy
import bmesh
import numpy as np
from terrain_mesh import build as build_terrain_mesh
from terrain_reduction_plan import TerrainReductionPlan,activate,active_plan,suspended
from terrain_partitions import collect_partitioned


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
    state=env['RNG'].getstate();group=None;existing=bpy.data.objects.get('Terrain')
    try:
        with suspended():
            # Reuse a captured native group when present. Rebuilding beside it
            # would let Blender suffix every object name and lose provenance.
            group=existing if existing is not None else build_terrain_mesh(env,lightweight=plan.profile=='smooth').finish()
            source=collect_partitioned(group.children_recursive,collect)
            plan.apply(source['triangles'],source['materials'],plan.profile,
                       source['partitionNames'],source['partitionIndices'])
    finally:
        if group is not None and group is not existing:remove_group(group)
        env['RNG'].setstate(state)
    activate(plan)
    print('Validated terrain reduction:',plan.profile,plan.payload['savedTriangles'],'triangles',flush=True)
    return plan


def apply_existing(env,profile,group):
    plan=active_plan(profile)
    if plan is None:return group
    source=collect_partitioned(group.children_recursive,collect)
    faces,materials,normals=[source[k] for k in ['triangles','materials','cornerNormals']]
    after,after_materials=plan.apply(faces,materials,profile,source['partitionNames'],source['partitionIndices'])
    keep=np.ones(len(faces),dtype=bool);keep[plan.payload['removedOriginalFaces']]=False
    old_normals=normals[keep]
    if 'partitionNames' in plan.payload:
        # Replace mesh data on the existing objects: access and reservoir
        # consumers retain names, parents, custom properties and node identity.
        objects={obj.name:obj for obj in group.children_recursive if obj.type=='MESH'}
        replacements=[]
        try:
            for index,name in enumerate(source['partitionNames']):
                selected=np.flatnonzero(plan.result_partitions==index)
                if not len(selected):raise ValueError('Reduction removed an entire terrain partition')
                if len(selected)==int(np.count_nonzero(source['partitionIndices']==index)) and np.all(selected<len(old_normals)):
                    # Leave an unchanged partition's mesh and encoded custom
                    # normals intact; a Blender normal roundtrip is not exact.
                    continue
                obj=objects[name];source_ids=np.flatnonzero(source['partitionIndices']==index)
                obj.data.calc_loop_triangles()
                polygon_ids=np.asarray([t.polygon_index for t in obj.data.loop_triangles])
                kept_counts=np.bincount(polygon_ids,weights=keep[source_ids],minlength=len(obj.data.polygons))
                polygon_counts=np.bincount(polygon_ids,minlength=len(obj.data.polygons))
                if np.any((kept_counts!=0)&(kept_counts!=polygon_counts)):
                    raise ValueError('Reduction partially replaces an original terrain polygon')
                polygon_keep=kept_counts!=0
                if len(obj.data.vertices)!=len(obj.data.loops):
                    raise ValueError('Partition replacement requires unwelded native terrain')
                mesh=obj.data.copy();bm=bmesh.new()
                try:
                    bm.from_mesh(mesh);bm.faces.ensure_lookup_table()
                    # Preserve retained loop data in its original normal space.
                    # Reading and re-encoding a custom normal can rotate it on
                    # extremely thin sidewalls even with unchanged positions.
                    # Retaining walls can be quads. Keep their original polygon
                    # and normal space when both captured triangles are retained.
                    removed=[bm.faces[j] for j in range(len(polygon_keep)) if not polygon_keep[j]]
                    ordered=[bm.faces[j] for j in range(len(polygon_keep)) if polygon_keep[j]]
                    bmesh.ops.delete(bm,geom=removed,context='FACES')
                    for i in selected[selected>=len(old_normals)]:
                        face=bm.faces.new([bm.verts.new(p) for p in after[i]])
                        face.material_index=int(after_materials[i])
                        ordered.append(face)
                    order={face:i for i,face in enumerate(ordered)}
                    bm.faces.sort(key=lambda face:order[face])
                    bm.to_mesh(mesh);mesh.update()
                except Exception:
                    bpy.data.meshes.remove(mesh);raise
                finally:bm.free()
                replacements.append((obj,mesh))
            for obj,mesh in replacements:
                old_mesh=obj.data;obj.data=mesh
                if old_mesh.users==0:bpy.data.meshes.remove(old_mesh)
        finally:
            for _,mesh in replacements:
                if mesh.users==0:bpy.data.meshes.remove(mesh)
        return group
    if any(name.startswith(('Terrain_grading_','Terrain_reservoir_')) for name in source['partitionNames']):
        raise ValueError('Partitioned terrain requires an ownership-aware reduction plan')
    remove_group(group)
    batch=env['Batch']('Terrain',env['TERRAIN_MATERIALS'])
    for i,(face,key) in enumerate(zip(after,after_materials)):
        batch.face(face.tolist(),env['TERRAIN_MATERIALS'][int(key)],old_normals[i].tolist() if i<len(old_normals) else None)
    return batch.finish()
