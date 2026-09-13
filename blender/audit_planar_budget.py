"""Measure terrain planar-dissolve candidates; never modifies public assets.

Outputs original and candidate triangle arrays for an independent vertical-error
audit. A Blender reduction count alone is not permission to use the candidate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
import bmesh
import numpy as np


def triangles(mesh):
    mesh.calc_loop_triangles()
    vertices=np.empty(len(mesh.vertices)*3,dtype=np.float64);mesh.vertices.foreach_get('co',vertices)
    indices=np.empty(len(mesh.loop_triangles)*3,dtype=np.int32);mesh.loop_triangles.foreach_get('vertices',indices)
    materials=np.empty(len(mesh.loop_triangles),dtype=np.int32);mesh.loop_triangles.foreach_get('material_index',materials)
    return vertices.reshape(-1,3)[indices.reshape(-1,3)],materials


def main():
    p=argparse.ArgumentParser(description=__doc__)
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument('--input',type=Path)
    source.add_argument('--native-profile',choices=['detail','smooth'])
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--preserve-boundary-vertices',action='store_true')
    p.add_argument('--capture-only',action='store_true',help='Capture native source arrays without dissolve candidates')
    p.add_argument('--angles',type=float,nargs='+',default=[.0001,.0005,.001])
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:]);args.output.mkdir(parents=True,exist_ok=True)
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    if args.native_profile:
        sys.path.insert(0,str(Path(__file__).resolve().parent))
        from capture_native_terrain import capture
        capture(args.native_profile)
    else:
        bpy.ops.import_scene.gltf(filepath=str(args.input))
    terrain=[o for o in bpy.data.objects if o.type=='MESH' and o.name.startswith('Terrain_')]
    assert terrain,'No terrain meshes in input'
    report={'status':'terrain reduction candidates; exact height/coverage and city dependency checks pending',
            'input':str(args.input) if args.input else 'native '+args.native_profile,
            'preserveBoundaryVertices':args.preserve_boundary_vertices,
            'scriptSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'nodes':[],'angles':{}}
    if args.input:report['inputSha256']=hashlib.sha256(args.input.read_bytes()).hexdigest()
    else:
        root=Path(__file__).resolve().parents[1]
        from terrain_mesh import NATIVE_DATA_INPUTS
        sources=list((root/'blender').glob('*.py'))+[root/name for name in NATIVE_DATA_INPUTS]
        report['inputHashes']={str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(sources)}
    original=[];original_materials=[];copies=[]
    for obj in terrain:
        mesh=obj.data.copy();mesh.transform(obj.matrix_world)
        faces,materials=triangles(mesh);original.append(faces);original_materials.append(materials)
        # Importer returns Blender east/north/up coordinates. Duplicate vertices
        # from glTF normal splits are welded only at effectively identical XYZ.
        bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-7)
        bm.to_mesh(mesh);bm.free();mesh.update();copies.append((obj.name,mesh))
        report['nodes'].append({'name':obj.name,'triangles':len(faces),'weldedVertices':len(mesh.vertices)})
    np.savez_compressed(args.output/'original.npz',triangles=np.concatenate(original),materials=np.concatenate(original_materials))
    report['originalTriangles']=sum(len(f) for f in original)
    for angle in ([] if args.capture_only else args.angles):
        all_faces=[];all_materials=[];counts={}
        for name,source in copies:
            mesh=source.copy();bm=bmesh.new();bm.from_mesh(mesh)
            bmesh.ops.dissolve_limit(bm,angle_limit=angle,use_dissolve_boundaries=False,
                                    verts=[] if args.preserve_boundary_vertices else list(bm.verts),
                                    edges=list(bm.edges),delimit={'MATERIAL'})
            bm.to_mesh(mesh);bm.free();mesh.update()
            faces,materials=triangles(mesh);all_faces.append(faces);all_materials.append(materials);counts[name]=len(faces)
            bpy.data.meshes.remove(mesh)
        filename=f'angle-{angle:g}.npz';path=args.output/filename
        np.savez_compressed(path,triangles=np.concatenate(all_faces),materials=np.concatenate(all_materials))
        count=sum(counts.values());report['angles'][str(angle)]={'triangles':count,'saved':report['originalTriangles']-count,
            'nodes':counts,'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        print('Planar budget:',angle,count,'saved',report['originalTriangles']-count,flush=True)
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
