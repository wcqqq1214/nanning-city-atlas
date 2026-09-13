"""Check actual water compression and preserved source shoreline/island coverage."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union
from check_reduced_terrain_exports import match_faces
from validate_cultural_landmarks import glb


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['directory','geography','output']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    report=json.loads((args.directory/'report.json').read_text())
    for name,entry in report['files'].items():
        if digest(args.directory/name)!=entry['sha256']:raise ValueError('Water export changed')
    if digest(args.geography)!=report['inputs']['public/data/geography.json']:raise ValueError('Wrong shoreline geography')
    geo=json.loads(args.geography.read_text());native=dict(np.load(args.directory/'native.npz'))
    document,load=glb(args.directory/'water.glb');triangles=[];normals=[]
    for node in document['nodes']:
        if 'mesh' not in node:continue
        if any(k in node for k in ['translation','rotation','scale','matrix']):raise ValueError('Unbaked water transform')
        for primitive in document['meshes'][node['mesh']]['primitives']:
            mesh=load(primitive);xyz=np.asarray(mesh.points,dtype=float)[:,[0,2,1]];xyz[:,1]*=-1
            n=np.asarray(mesh.normals,dtype=float)[:,[0,2,1]];n[:,1]*=-1
            triangles.extend(xyz[mesh.faces]);normals.extend(n[mesh.faces])
    actual={'triangles':np.asarray(triangles),'cornerNormals':np.asarray(normals),'materials':np.zeros(len(triangles),dtype=int)}
    geometry=match_faces(native,actual,position_meters=.02,normal_degrees=.5)
    normals=np.cross(actual['triangles'][:,1]-actual['triangles'][:,0],actual['triangles'][:,2]-actual['triangles'][:,0])
    if np.any(normals[:,2]<=0):raise ValueError('Reversed or collapsed water triangle')
    shapes=[Polygon(t[:,:2]) for t in actual['triangles']];coverage=unary_union(shapes)
    overlap=(sum(p.area for p in shapes)-coverage.area)*10000
    if abs(overlap)>1e-4:raise ValueError('Compressed water triangles overlap')
    lakes=[]
    for record in geo['shorelineRestoration']['water']:
        index=record['index'];rings=geo['water'][index];expected=Polygon(rings[0],rings[1:])
        local=coverage.intersection(expected.buffer(.001))
        missing=expected.difference(local.buffer(.0002)).area*10000
        extra=local.difference(expected.buffer(.0002)).area*10000
        if missing>1e-5 or extra>1e-5:raise ValueError('Compressed shoreline exceeds 2 cm tolerance')
        for ring in rings[1:]:
            if coverage.intersection(Polygon(ring).buffer(-.0002)).area*10000>1e-5:raise ValueError('Water island filled')
        lakes.append({'index':index,'islands':len(rings)-1,'missingBeyondToleranceSquareMeters':missing,'extraBeyondToleranceSquareMeters':extra})
    result={'status':'actual Water mesh and compression checked; terrain/building interfaces and final city separate',
            'geometry':geometry,'positionToleranceMeters':.02,'waterOverlapSquareMeters':overlap,'restoredLakes':lakes,
            'inputs':{str(p):digest(p) for p in [args.directory/'report.json',args.directory/'water.glb',args.geography]},
            'toolSha256':digest(Path(__file__))}
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(result)
