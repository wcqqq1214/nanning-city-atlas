"""Check supported building exports without treating site-review flags as passed."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

from check_reduced_terrain_exports import match_faces
from validate_cultural_landmarks import glb


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['directory','geography','output']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    report=json.loads((args.directory/'report.json').read_text())
    for name,entry in report['files'].items():
        if digest(args.directory/name)!=entry['sha256']:raise ValueError('Export changed: '+name)
    if digest(args.geography) not in report['inputs'].values():raise ValueError('Wrong building geography')
    geo=json.loads(args.geography.read_text());byid={b['id']:b for b in geo['buildings']}
    native=dict(np.load(args.directory/'native.npz'));doc,load=glb(args.directory/'buildings.glb')
    triangles=[];normals=[];materials=[]
    for node in doc['nodes']:
        if 'mesh' not in node:continue
        if any(k in node for k in ['matrix','translation','rotation','scale']):raise ValueError('Unbaked building transform')
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            data=load(primitive);points=np.asarray(data.points,dtype=float)[:,[0,2,1]];points[:,1]*=-1
            ns=np.asarray(data.normals,dtype=float)[:,[0,2,1]];ns[:,1]*=-1
            triangles.extend(points[data.faces]);normals.extend(ns[data.faces])
            materials.extend([['building','roof'].index(doc['materials'][primitive['material']]['name'])]*len(data.faces))
    actual={'triangles':np.asarray(triangles),'materials':np.asarray(materials),'cornerNormals':np.asarray(normals)}
    matched=match_faces(native,actual,position_meters=.05,normal_degrees=.5,include_mapping=True)
    owners=native['buildingIndices'][matched.pop('nativeIndexByActualFace')];checked=[]
    for index,record in enumerate(report['records']):
        b=byid[record['id']];faces=actual['triangles'][owners==index]
        if abs(faces[:,:,2].min()-record['bottom'])*100>.05:raise ValueError('Building bottom changed: '+b['id'])
        if abs(faces[:,:,2].max()-record['top'])*100>.05:raise ValueError('Building top changed: '+b['id'])
        roofs=actual['triangles'][(owners==index)&(actual['materials']==1)]
        cross=np.cross(roofs[:,1]-roofs[:,0],roofs[:,2]-roofs[:,0])
        if np.any(cross[:,2]<=0):raise ValueError('Collapsed or reversed roof: '+b['id'])
        shapes=[Polygon(t[:,:2]) for t in roofs];cover=unary_union(shapes);expected=Polygon(b['rings'][0],b['rings'][1:])
        missing=expected.difference(cover.buffer(.0005)).area*10000
        outside=cover.difference(expected.buffer(.0005)).area*10000
        overlap=(sum(p.area for p in shapes)-cover.area)*10000
        if missing>1e-5 or outside>1e-5 or abs(overlap)>1e-5:raise ValueError(f'Roof coverage failed for {b["id"]}: {missing}, {outside}, {overlap}')
        checked.append({'id':b['id'],'kind':record['kind'],'roofTriangles':len(roofs),'courtyards':len(b['rings'])-1,
                        'roofOverlapSquareMeters':overlap,'siteReviewRequired':record['siteReviewRequired']})
    output={'status':'measured-elevation geometry checked; special structures, site review, visibility and full city pending',
            'geometry':matched,'buildings':len(checked),'compoundBuildings':sum(r['kind']=='compound' for r in checked),
            'courtyards':sum(r['courtyards'] for r in checked),'unresolved':report['unresolved'],
            'largeReliefSiteReviews':report['largeReliefSiteReviews'],'records':checked,
            'inputs':{str(p):digest(p) for p in [args.directory/'report.json',args.directory/'buildings.glb',args.directory/'native.npz',args.geography]},
            'toolSha256':digest(Path(__file__))}
    args.output.write_text(json.dumps(output,indent=2)+'\n')
    print({k:v for k,v in output.items() if k not in ['records','inputs']})


if __name__=='__main__':main()
