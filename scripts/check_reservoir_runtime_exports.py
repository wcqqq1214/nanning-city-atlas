"""Verify actual production land/water and its partition in full terrain contexts."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon,shape
from shapely.ops import unary_union
from check_reservoir_terrain import compare
from check_reduced_terrain_exports import match_faces
from validate_cultural_landmarks import glb
from decoded_surface import face_arrays


def face_key(face):
    return tuple(sorted(tuple(p) for p in np.asarray(face,dtype=np.float32)))


def prepared_water_faces(native,geography,plan,index,claimed):
    """Claim exact native faces, including tiny faces at rounded shorelines."""
    from reservoir_water import inside_polygon
    lake=plan.payload['waterBodies'][index]
    if lake.get('waterMesh'):
        expected=plan.water_surface(index).triangles
    else:
        expected=[]
        for face in geography['waterTriangles']:
            x,y=np.mean(face,axis=0)
            if inside_polygon(x,y,lake['rings']):
                z=plan.water_height(index,x,y)
                expected.append([(*p,z) for p in face])
    lookup={}
    for i,face in enumerate(native):lookup.setdefault(face_key(face),[]).append(i)
    indices=[]
    for face in expected:
        available=[i for i in lookup.get(face_key(face),[]) if i not in claimed]
        if len(available)!=1:raise ValueError('Missing, duplicate or multiply owned production water face')
        claimed.add(available[0]);indices.append(available[0])
    if not indices:raise ValueError('Prepared reservoir water has no production faces')
    return native[indices]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['scene-root','native','context','output']:parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();root=args.scene_root.resolve()
    sys.path.insert(0,str(root/'blender'))
    from reservoir_runtime import load_registry
    group,plan_inputs=load_registry(root/'data/reservoir-terrain-registry.json',root)
    if group is None:raise ValueError('No active reservoir plans')
    metadata=json.loads((args.native/'report.json').read_text())
    geography=json.loads((root/'public/data/geography.json').read_text())
    context=json.loads((args.context/'sources.json').read_text())
    required=metadata.get('nativeDataInputs')
    if not required or not set(required)<=set(context['inputHashes']):
        raise ValueError('Rebuild context with every active native terrain dependency')
    for bindings in [metadata['inputs'],context['inputHashes']]:
        for name,digest in bindings.items():
            if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('Stale reservoir context: '+name)
    result={'status':'production reservoir and water native checks plus compressed terrain context; complete city pending','profiles':{}}
    for profile in ['detail','smooth']:
        native=dict(np.load(args.native/(profile+'.npz')));names=metadata['profiles'][profile]['materialNames']
        doc,decode=glb(args.context/(profile+'.glb'));triangles=[];materials=[];normals=[]
        for node in doc['nodes']:
            if 'mesh' not in node or not node.get('name','').startswith('Terrain_reservoir_'):continue
            if any(k in node for k in ['matrix','translation','rotation','scale']):raise ValueError('Unbaked runtime reservoir')
            for primitive in doc['meshes'][node['mesh']]['primitives']:
                mesh=decode(primitive);faces,face_normals=face_arrays(mesh)
                triangles.extend(faces);normals.extend(face_normals)
                materials.extend([names.index(doc['materials'][primitive['material']]['name'])]*len(mesh.faces))
        actual={'triangles':np.asarray(triangles),'materials':np.asarray(materials),'cornerNormals':np.asarray(normals)}
        record={'compressedTerrain':match_faces(native,actual,position_meters=0,normal_degrees=.5),
                'nativeLand':compare(native['triangles'][native['landMask']],unary_union([shape(p.payload['landGeometry']) for p in group.plans])),'nativeWater':{}}
        claimed=set()
        for plan in group.plans:
            for index,lake in enumerate(plan.payload['waterBodies']):
                polygon=Polygon(lake['rings'][0],lake['rings'][1:])
                faces=prepared_water_faces(native['waterTriangles'],geography,plan,index,claimed)
                water=compare(faces,polygon)
                # Prepared connected lakes may vary in elevation. Compare the
                # actual prepared water mesh, not the single fallback level.
                vertices=np.unique(faces.reshape(-1,3),axis=0)
                error=max(abs(plan.water_height(index,*q[:2])-q[2])*100 for q in vertices)
                water['maximumHeightErrorMeters']=float(error)
                if error>.001:raise ValueError('Production water height differs from prepared reservoir surface')
                water['islands']=len(polygon.interiors);record['nativeWater'][lake['geographyWaterIndex']]=water
        result['profiles'][profile]=record
    paths=[*[root/name for name in plan_inputs],args.native/'report.json',args.context/'sources.json',*[p/(s+ext) for p,ext in [(args.native,'.npz'),(args.context,'.glb')] for s in ['detail','smooth']]]
    result['inputs']={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    result['toolSha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result['decoderSha256']=hashlib.sha256(Path(__file__).with_name('decoded_surface.py').read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['profiles']))


if __name__=='__main__':main()
