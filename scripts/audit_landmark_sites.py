"""Intersect P4 candidate footprints with frozen P3 exported terrain.

Coverage is evaluated from actual decoded triangles, including their clipped
interior vertices. This exposes site grading needs before a flat reference
candidate can be mistaken for a correctly grounded city landmark.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon, box, Point
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
from arts_landmark import outline, SITE_ANGLE
from validate_cultural_landmarks import glb


def main():
    baseline = ROOT/'work/urban-structure/baseline-p3'
    plan = json.loads((ROOT/'data/landmark-calibration-plan.json').read_text())
    catalog = {p['id']:p for p in json.loads((ROOT/'data/landmarks.json').read_text())}
    geo = json.loads((baseline/'public/data/geography.json').read_text())
    kx = 1113.2*math.cos(math.radians(geo['center'][1]))
    sites = {}
    for identity in ['arts-center','zhenning','diwang','confucius']:
        p = catalog[identity]
        x,y = (p['lon']-geo['center'][0])*kx,(p['lat']-geo['center'][1])*1113.2
        if identity=='arts-center':
            c,s=math.cos(SITE_ANGLE),math.sin(SITE_ANGLE)
            shape=Polygon([(x+1.12*(u*c-v*s),y+1.12*(u*s+v*c)) for u,v in outline()])
        elif identity=='zhenning':
            shape=unary_union([Point(x,y).buffer(.205,resolution=40),
                               box(x-.032,y-.2673,x+.032,y-.19),
                               box(x-.021,y+.19,x+.021,y+.239)])
        elif identity=='diwang':
            shape=unary_union([Polygon([(x+u,y+v) for u,v in plan['sites'][identity][key]])
                               for key in ['outlineSceneXY','podiumOutlineSceneXY']])
        else: shape=box(x-1.35,y-1.7,x+1.35,y+1.7)
        sites[identity]=(shape, x,y)
    water=unary_union([Polygon(r[0],r[1:]) for r in geo['water']])
    report={'baseline':'baseline-p3','note':'Decoded P3 terrain, candidate footprints; Confucius uses the existing platform extent, not a proposed replacement.',
            'planSha256':hashlib.sha256((ROOT/'data/landmark-calibration-plan.json').read_bytes()).hexdigest(),
            'sites':{identity:{'footprintAreaSquareMeters':shape.area*10_000,
                              'mappedWaterOverlapSquareMeters':shape.intersection(water).area*10_000,
                              'profiles':{}} for identity,(shape,_,_) in sites.items()}}
    for profile,suffix in [('detail',''),('smooth','-mobile')]:
        path=baseline/f'public/models/nanning-city{suffix}.glb'
        doc,decode=glb(path)
        candidates={name:[] for name in sites}
        for node in doc['nodes']:
            if not node.get('name','').startswith('Terrain_'):continue
            for primitive in doc['meshes'][node['mesh']]['primitives']:
                mesh=decode(primitive)
                triangles=np.asarray(mesh.points)[mesh.faces][:,:,[0,2,1]].copy()
                triangles[:,:,1]*=-1
                lower=triangles[:,:,:2].min(axis=1);upper=triangles[:,:,:2].max(axis=1)
                for name,(shape,_,_) in sites.items():
                    w,s,e,n=shape.bounds
                    mask=(lower[:,0]<=e)&(upper[:,0]>=w)&(lower[:,1]<=n)&(upper[:,1]>=s)
                    candidates[name].extend(triangles[mask])
        for name,(shape,_,_) in sites.items():
            pieces=[];heights=[]
            for triangle in candidates[name]:
                polygon=Polygon(triangle[:,:2])
                if polygon.area<1e-12:continue
                clipped=polygon.intersection(shape)
                if clipped.area<1e-12:continue
                affine=np.linalg.solve(np.column_stack((triangle[:,:2],np.ones(3))),triangle[:,2])
                geoms=[clipped] if clipped.geom_type=='Polygon' else getattr(clipped,'geoms',[])
                for part in geoms:
                    if part.geom_type!='Polygon':continue
                    pieces.append(part)
                    heights.extend(float(np.dot([u,v,1],affine)) for u,v in part.exterior.coords)
            covered=unary_union(pieces)
            assert heights,name
            report['sites'][name]['profiles'][profile]={
                'minimumSceneHeightMeters':min(heights)*100,
                'maximumSceneHeightMeters':max(heights)*100,
                'reliefMeters':(max(heights)-min(heights))*100,
                'uncoveredSquareMeters':shape.difference(covered).area*10_000,
                'terrainPieces':len(pieces)}
        report.setdefault('assets',{})[profile]=hashlib.sha256(path.read_bytes()).hexdigest()
    output=ROOT/'work/urban-structure/p4/site-audit.json'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report['sites'],ensure_ascii=False,indent=2))


if __name__=='__main__': main()
