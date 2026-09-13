"""Verify the isolated grading partitions inside real terrain/road GLBs."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

from check_reduced_terrain_exports import match_faces
from prepare_building_support import TerrainSurface
from validate_cultural_landmarks import glb
from decoded_surface import face_arrays

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'blender'))
from local_terrain import MATERIAL_KEYS as BASE_KEYS
from site_grading import MATERIAL_KEYS as SITE_KEYS


def decode_patch(path):
    tree=ast.parse((ROOT/'blender/build_city.py').read_text())
    value=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MATS' for t in n.targets))
    labels={k.value:v.args[0].value for k,v in zip(value.keys,value.values)}
    names=[labels[k] for k in BASE_KEYS+SITE_KEYS]
    doc,decode=glb(path);faces=[];normals=[];materials=[];nodes=[]
    for node in doc['nodes']:
        if 'mesh' not in node or not node.get('name','').startswith('Terrain_grading_'):continue
        assert not any(k in node for k in ['matrix','translation','rotation','scale'])
        nodes.append(node['name'])
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            data=decode(primitive);triangles,normal_values=face_arrays(data)
            faces.extend(triangles);normals.extend(normal_values)
            materials.extend([names.index(doc['materials'][primitive['material']]['name'])]*len(data.faces))
    assert nodes,'No separately encoded grading partition'
    return {'triangles':np.asarray(faces),'cornerNormals':np.asarray(normals),'materials':np.asarray(materials)},nodes


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['native','context','plan','output']:p.add_argument('--'+key,type=Path,required=True)
    args=p.parse_args();plan=json.loads(args.plan.read_text());report={'status':'actual grading Draco checks passed; road access and full city acceptance pending','profiles':{}}
    for profile in ['detail','smooth']:
        native=dict(np.load(args.native/(profile+'.npz')));centers=native['triangles'][:,:,:2].mean(axis=1)
        keep=np.zeros(len(centers),dtype=bool)
        for w,s,e,n in [site['bounds'] for site in plan['sites']]:
            keep|=(centers[:,0]>=w)&(centers[:,0]<=e)&(centers[:,1]>=s)&(centers[:,1]<=n)
        selected={k:v[keep] for k,v in native.items()}
        actual,nodes=decode_patch(args.context/(profile+'.glb'))
        checked=match_faces(selected,actual,position_meters=.0002,normal_degrees=.5)
        triangles=actual['triangles'];polys=[Polygon(t[:,:2]) for t in triangles]
        normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
        assert np.all(normals[:,2]>0),'Collapsed or reversed grading projection'
        cover=unary_union(polys);overlap=(sum(poly.area for poly in polys)-cover.area)*10000
        assert overlap<.00001,('Decoded grading overlap',overlap)
        surface=TerrainSurface(triangles);pads=[]
        for site in plan['sites']:
            pad=Polygon(site['pad'][0],site['pad'][1:]);support=surface.bounds(pad,.005)
            assert support['status']=='covered'
            assert (support['maximumSceneZ']-support['minimumSceneZ'])*100<.001
            pads.append({'id':site['id'],'support':support})
        report['profiles'][profile]={'geometry':checked,'nodes':nodes,'overlapSquareMeters':overlap,'pads':pads,
                                     'contextBytes':(args.context/(profile+'.glb')).stat().st_size}
    files=[args.plan,*[args.native/(p+'.npz') for p in ['detail','smooth']],*[args.context/(p+'.glb') for p in ['detail','smooth']]]
    report['inputs']={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    report['toolSha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report['dependencies']={name:hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest() for name in
                            ['check_reduced_terrain_exports.py','prepare_building_support.py','validate_cultural_landmarks.py']}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
