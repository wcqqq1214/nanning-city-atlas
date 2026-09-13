"""Decode reservoir GLBs and compare actual geometry, materials and winding."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon,shape
from check_reservoir_terrain import compare,shared_shoreline
from check_reduced_terrain_exports import match_faces
from validate_cultural_landmarks import glb
from decoded_surface import face_arrays


def geometric_normals(triangles):
    normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    length=np.linalg.norm(normals,axis=1)
    if np.any(length==0):raise ValueError('Degenerate source triangle')
    return np.repeat((normals/length[:,None])[:,None,:],3,axis=1)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['plan','directory','output']:parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();plan=json.loads(args.plan.read_text());result={'status':'independent reservoir GLB checked; full city integration remains pending','profiles':{}}
    dem=json.loads(Path(plan['inputs']['terrain']['path']).read_text())
    names=['reservoir_ground','dam_slope','dam_crest','reservoir_water']
    for profile in ['detail','smooth']:
        source=np.load(args.directory/(profile+'.npz'));original=np.concatenate([source['triangles'],source['bankTriangles'],source['waterTriangles']])
        materials=np.concatenate([source['materials'],np.full(len(source['bankTriangles']),1),np.full(len(source['waterTriangles']),3)])
        native={'triangles':original,'materials':materials,'cornerNormals':np.concatenate([source['cornerNormals'],source['bankCornerNormals'],source['waterCornerNormals']])}
        doc,decode=glb(args.directory/(profile+'.glb'));triangles=[];normal_values=[];material_values=[];water_ids=[];terrain_flags=[]
        for node in doc['nodes']:
            if 'mesh' not in node:continue
            if any(k in node for k in ['matrix','translation','rotation','scale']):raise ValueError('Unbaked reservoir transform')
            water_index=int(node['name'].split('_')[-1]) if node['name'].startswith('Reservoir_water_') else -1
            for primitive in doc['meshes'][node['mesh']]['primitives']:
                mesh=decode(primitive);faces,face_normals=face_arrays(mesh)
                triangles.extend(faces);normal_values.extend(face_normals)
                material_values.extend([names.index(doc['materials'][primitive['material']]['name'])]*len(mesh.faces));water_ids.extend([water_index]*len(mesh.faces))
                terrain_flags.extend([node['name'].startswith('Reservoir_terrain')]*len(mesh.faces))
        actual={'triangles':np.asarray(triangles),'materials':np.asarray(material_values),'cornerNormals':np.asarray(normal_values)}
        # Reservoir nodes disable position quantization. Require the exact
        # float32 geometry, including tiny neighboring faces which a tolerant
        # bipartite match could otherwise pair with each other.
        record={'geometry':match_faces(native,actual,position_meters=0,normal_degrees=.5),'water':{}}
        # Scope by the actual terrain node, never by dropping failed faces.
        triangles=actual['triangles']
        land=triangles[np.asarray(terrain_flags)];water_ids=np.asarray(water_ids)
        record['terrain']=compare(land,shape(plan['landGeometry']))
        for entry in plan['waterBodies']:
            rings=entry['rings'];index=entry['geographyWaterIndex']
            faces=triangles[water_ids==index]
            record['water'][index]=compare(faces,Polygon(rings[0],rings[1:]))
            if entry.get('waterMesh'):
                connected=triangles[np.isin(water_ids,entry.get('connectedWaterIndices',[]))]
                record['water'][index]['sharedShoreline']=shared_shoreline(
                    land,faces,plan['source']['mesh']['bankAboveWaterMeters']*dem['verticalExaggeration'],plan['bounds'],connected)
        result['profiles'][profile]=record
    paths=[args.plan,args.directory/'report.json',*[args.directory/(p+'.'+ext) for p in ['detail','smooth'] for ext in ['npz','glb']]]
    result['inputs']={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    result['toolSha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result['decoderSha256']=hashlib.sha256(Path(__file__).with_name('decoded_surface.py').read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['profiles']))


if __name__=='__main__':main()
