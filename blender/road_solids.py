"""Render the common, pre-resolved road/bridge boundary in both quality tiers."""
from functools import lru_cache
import hashlib,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]

@lru_cache(maxsize=2)
def load(profile):
    filename=ROOT/f'data/road-solids-{profile}.npz'
    metadata=json.loads((ROOT/f'data/road-solids-{profile}.json').read_text())
    assert hashlib.sha256(filename.read_bytes()).hexdigest()==metadata['sha256'],'Resolved road mesh hash mismatch'
    for path,digest in metadata['inputHashes'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,f'Recapture and resolve roads after changing {path}'
    with np.load(filename) as data:arrays={name:data[name] for name in data.files}
    return arrays,metadata

def structure(batch,network):
    profile='smooth' if network.lightweight else 'detail';data,metadata=load(profile)
    assert max(abs(a-b) for first,second in zip(network.levels,metadata['levels']) for a,b in zip(first,second))<1e-5,'Resolved road levels are stale'
    materials=['viaduct_asphalt','viaduct_soffit','viaduct_concrete']
    for tri,material in zip(data['elevated'],data['elevatedMaterials']):batch.face(tri.tolist(),materials[int(material)])
    for tri in data['railings']:batch.face(tri.tolist(),'viaduct_concrete')
    for owner,s,x,y,bottom,top in data['piers']:
        owner=int(owner);path=network.paths[owner];w=network.routes[owner]['width']
        batch.box(x,y,bottom,.032,.032,top-bottom-.02,'viaduct_concrete')
        batch.beam(path.at(s,-w*.65,top-.013),path.at(s,w*.65,top-.013),.013,'viaduct_concrete')
    network.report.update({'resolvedHash':metadata['sha256'],'resolvedDeckTriangles':int(np.sum(data['elevatedMaterials']==0)),
                           'renderedPiers':len(data['piers']),'omittedPiers':metadata['omittedPiers'],'omittedRailSegments':metadata['omittedRailSegments']})

def details(batch,network,lightweight=False):
    data,metadata=load('smooth' if lightweight else 'detail')
    for tri in data['elevatedPaint']:batch.face(tri.tolist(),'viaduct_line')
    return {'markingTriangles':len(data['elevatedPaint']),'resolvedHash':metadata['sha256']}

def ground(batch,lightweight=False):
    data,metadata=load('smooth' if lightweight else 'detail')
    for tri,material in zip(data['ground'],data['groundMaterials']):batch.face(tri.tolist(),['viaduct_asphalt','road_secondary','road_local'][int(material)])
    for tri in data['groundWalls']:batch.face(tri.tolist(),'viaduct_concrete')
    for tri in data['groundPaint']:batch.face(tri.tolist(),'viaduct_line')
    return {'surfaceTriangles':len(data['ground']),'approachWallTriangles':len(data['groundWalls']),
            'markingTriangles':len(data['groundPaint']),'resolvedHash':metadata['sha256']}

@lru_cache(maxsize=1)
def building_limits():
    limits={}
    for profile in ['detail','smooth']:
        _,metadata=load(profile)
        for record in metadata['buildings']:
            index=record['index'];top=record['top']
            if index not in limits:limits[index]=top
            elif top is None or limits[index] is None:limits[index]=None
            else:limits[index]=min(limits[index],top)
    return limits
