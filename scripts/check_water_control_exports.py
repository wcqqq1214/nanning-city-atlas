"""Check actual sluice GLB geometry, source scope and unobstructed gate apertures."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union
from check_reduced_terrain_exports import match_faces
from validate_cultural_landmarks import glb


def vertical_hits(triangles,x,y):
    a=triangles[:,0];u=triangles[:,1]-a;v=triangles[:,2]-a
    det=u[:,0]*v[:,1]-u[:,1]*v[:,0];valid=abs(det)>1e-15
    a,u,v,det=a[valid],u[valid],v[valid],det[valid];dx=x-a[:,0];dy=y-a[:,1]
    s=(dx*v[:,1]-dy*v[:,0])/det;t=(dy*u[:,0]-dx*u[:,1])/det
    hit=(s>=-1e-8)&(t>=-1e-8)&(s+t<=1+1e-8)
    return np.unique(np.round((a[:,2]+s*u[:,2]+t*v[:,2])[hit],12))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['directory','geography','source','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--node',default='Reservoir_control_linglong')
    p.add_argument('--expected-parent')
    args=p.parse_args();root=args.directory;report=json.loads((root/'report.json').read_text());geo=json.loads(args.geography.read_text());spec=json.loads(args.source.read_text())
    for file,h in report['inputs'].items():
        if hashlib.sha256(Path(file).read_bytes()).hexdigest()!=h:raise ValueError('Reexport after changing '+file)
    planned=json.loads((root/'geometry.json').read_text());original=np.load(root/'structure.npz')
    doc,decode=glb(root/'structure.glb');xyz=[];normals=[];materials=[]
    if args.expected_parent:
        ids=[i for i,n in enumerate(doc['nodes']) if n.get('name')==args.node]
        parents=[n for n in doc['nodes'] if ids and ids[0] in n.get('children',[])]
        if len(ids)!=1 or len(parents)!=1 or parents[0].get('name')!=args.expected_parent:
            raise ValueError('Sluice GLB does not retain its layer parent')
        if any(k in parents[0] for k in ['matrix','scale','translation','rotation']):
            raise ValueError('Unexpected transformed sluice layer parent')
    for node in doc['nodes']:
        if 'mesh' not in node:continue
        if node['name']!=args.node or any(k in node for k in ['matrix','scale','translation','rotation']):raise ValueError('Unexpected sluice node/transform')
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            mesh=decode(primitive);v=np.asarray(mesh.points,dtype=float)[:,[0,2,1]];v[:,1]*=-1
            n=np.asarray(mesh.normals,dtype=float)[:,[0,2,1]];n[:,1]*=-1
            xyz.extend(v[mesh.faces]);normals.extend(n[mesh.faces]);materials.extend([report['materialNames'].index(doc['materials'][primitive['material']]['name'])]*len(mesh.faces))
    actual={'triangles':np.asarray(xyz),'cornerNormals':np.asarray(normals),'materials':np.asarray(materials)}
    result={'status':'independent actual sluice export verified; full-city activation pending','geometry':match_faces(original,actual,position_meters=0,normal_degrees=.5)}
    expected={tuple(np.asarray(q,dtype=np.float32).astype(float)) for part in planned['parts'] for face in part['faces'] for q in face}
    if expected!={tuple(q) for face in original['triangles'] for q in face}:raise ValueError('Native structure differs from declared members')
    if len(original['triangles'])!=12*len(planned['parts']):raise ValueError('Structural member face count differs')
    footprint=Polygon(next(b for b in geo['buildings'] if b['id']==spec['buildingId'])['rings'][0]);water=unary_union([Polygon(r[0],r[1:]) for r in geo['water']])
    out=wet=0
    for part in planned['parts']:
        poly=Polygon(part['footprint'])
        if part['name'].startswith('approach-'):wet+=poly.intersection(water.buffer(-.00005)).area*10000
        else:out+=poly.difference(footprint.buffer(.00005)).area*10000
    if max(out,wet)>1e-5:raise ValueError('Sluice exceeds mapped footprint or land approaches cover water')
    result.update(outsideFootprintBeyond5mmSquareMeters=out,approachWaterOverlapBeyond5mmSquareMeters=wet,gateApertures=[])
    for entry in planned['gateOpenings']:
        # Several rays through each aperture catch either a filled weir or an
        # accidental retained ordinary-building box in the exported structure.
        probes=[]
        for x,y in entry['probeXY']:
            hits=vertical_hits(actual['triangles'],x,y);level=planned['waterHeight']
            below=hits[hits<level];above=hits[hits>level]
            if not len(below) or not len(above):raise ValueError('No sill/deck bounding a gate aperture')
            lo,hi=float(below.max()),float(above.min())
            if abs(hi-planned['gateBottom'])*100>.001 or hi<=level+.001:raise ValueError('Actual gate opening is obstructed')
            probes.append({'xy':[x,y],'belowWaterClearanceMeters':(level-lo)*100,'aboveWaterClearanceMeters':(hi-level)*100})
        result['gateApertures'].append({'centerXY':entry['centerXY'],'probes':probes})
    files=[args.geography,args.source,root/'report.json',root/'geometry.json',root/'structure.npz',root/'structure.glb',Path(__file__)]
    result['inputs']={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':main()
