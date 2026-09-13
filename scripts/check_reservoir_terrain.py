"""Independent native geometry coverage checks for a reservoir export."""
import argparse
import hashlib
import json
from pathlib import Path
import math
from collections import Counter
import numpy as np
from shapely.geometry import Polygon, shape
from shapely.ops import unary_union


def compare(actual,expected,tolerance=.00005):
    faces=[Polygon(t[:,:2]) for t in actual]
    if any(not p.is_valid or p.area<=0 for p in faces):raise ValueError('Invalid projected native triangle')
    union=unary_union(faces);overlap=(math.fsum(p.area for p in faces)-union.area)*10000
    if abs(overlap)>1e-4:raise ValueError(f'Overlapping native faces: {overlap} m²')
    uncovered=expected.difference(union.buffer(tolerance)).area*10000
    excess=union.difference(expected.buffer(tolerance)).area*10000
    if max(uncovered,excess)>1e-5:raise ValueError(f'Native coverage outside 5 mm boundary tolerance: {uncovered}, {excess}')
    return {'triangles':len(faces),'overlapSquareMeters':overlap,'uncoveredBeyond5mmSquareMeters':uncovered,'excessBeyond5mmSquareMeters':excess}


def shared_shoreline(land,water,expected_gap,bounds,connected_water=None):
    def boundary(faces):
        counts=Counter();values={}
        for face in faces:
            for a,b in zip(face,np.roll(face,-1,axis=0)):
                key=tuple(sorted((tuple(a[:2]),tuple(b[:2]))));counts[key]+=1;values[key]=(a,b)
        return {k:values[k] for k,v in counts.items() if v==1}
    land_edges=boundary(land);water_edges=boundary(water);maximum=0.;matched=0;city_edge=0
    connected_edges=boundary(connected_water) if connected_water is not None else {}
    water_join_error=0.;water_joins=0
    for key,edge in water_edges.items():
        if key in connected_edges:
            if key in land_edges:raise ValueError('Connected water edge is also covered by land')
            heights={tuple(p[:2]):p[2] for p in connected_edges[key]}
            for p in edge:water_join_error=max(water_join_error,abs(heights[tuple(p[:2])]-p[2])*100)
            water_joins+=1;continue
        if key not in land_edges:
            if any(all(abs(p[k]-limit)<1.5e-5 for p in edge) for k,limit in [(0,bounds[0]),(0,bounds[2]),(1,bounds[1]),(1,bounds[3])]):
                city_edge+=1;continue
            raise ValueError('Land and variable water do not share an exact shoreline edge')
        heights={tuple(p[:2]):p[2] for p in land_edges[key]}
        for p in edge:maximum=max(maximum,abs((heights[tuple(p[:2])]-p[2])*100-expected_gap))
        matched+=1
    if not (matched or water_joins) or maximum>.001:raise ValueError(f'Variable water shore clearance differs by {maximum} m')
    if water_join_error>.001:raise ValueError(f'Connected water height differs by {water_join_error} m')
    return {'sharedNativeEdges':matched,'cityBoundaryEdges':city_edge,'maximumBankClearanceErrorMeters':maximum,
            'expectedBankClearanceMeters':expected_gap,'connectedWaterEdges':water_joins,'maximumWaterJoinErrorMeters':water_join_error}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['plan','exports','output']:parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();plan=json.loads(args.plan.read_text());result={'status':'native coverage only; compressed and full-city checks remain pending','profiles':{}}
    dem=json.loads(Path(plan['inputs']['terrain']['path']).read_text())
    for profile in ['detail','smooth']:
        data=np.load(args.exports/(profile+'.npz'));triangles=data['triangles']
        record={'terrain':compare(triangles,shape(plan['landGeometry'])),'water':{}}
        for entry in plan['waterBodies']:
            index=entry['geographyWaterIndex'];faces=data['waterTriangles'][data['waterIndices']==index]
            geometry=Polygon(entry['rings'][0],entry['rings'][1:]);water=compare(faces,geometry)
            if entry.get('waterMesh'):
                mesh=entry['waterMesh']
                points=np.asarray([[x,y,max(-.08,dem['verticalOffset']+(z-dem['verticalDatumMeters'])/100*dem['verticalExaggeration'])]
                                   for (x,y),z in zip(mesh['points'],mesh['targetMeters'])],dtype=np.float32).astype(float)
                expected=points[np.asarray(mesh['triangles'])]
                key=lambda f:tuple(sorted(tuple(p) for p in f))
                if Counter(key(f) for f in expected)!=Counter(key(f) for f in faces):raise ValueError('Native regional water differs from its prepared mesh')
                error=0.;water['heightMode']='continuous source-region display mesh'
                water['displaySourceMeterRange']=[min(mesh['targetMeters']),max(mesh['targetMeters'])]
                connected=data['waterTriangles'][np.isin(data['waterIndices'],entry.get('connectedWaterIndices',[]))]
                water['sharedShoreline']=shared_shoreline(triangles,faces,plan['source']['mesh']['bankAboveWaterMeters']*dem['verticalExaggeration'],plan['bounds'],connected)
            else:
                expected=max(-.08,dem['verticalOffset']+(entry['levelMeters']-dem['verticalDatumMeters'])/100*dem['verticalExaggeration'])
                error=float(np.max(np.abs(faces[:,:,2]-expected))*100)
            if error>.001:raise ValueError('Native water height differs from source-bound display level')
            water['maximumHeightErrorMeters']=error;water['islands']=len(geometry.interiors);record['water'][index]=water
        if np.any(np.cross(triangles[:,1,:2]-triangles[:,0,:2],triangles[:,2,:2]-triangles[:,0,:2])<=0):
            raise ValueError('Reversed terrain winding')
        result['profiles'][profile]=record
    result['inputs']={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.plan,args.exports/'detail.npz',args.exports/'smooth.npz']}
    result['toolSha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['profiles']))


if __name__=='__main__':main()
