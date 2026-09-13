"""Final mountain triangles shared by terrain, paths and dependent scene layers."""
from functools import lru_cache
import json
from pathlib import Path
import numpy as np
from terrain_height import scene_height

ROOT=Path(__file__).resolve().parents[1]
PLAN=json.loads((ROOT/'data/qingxiu-terrain-plan.json').read_text())
DEM=json.loads((ROOT/'public/data/terrain.json').read_text())
PATH_KEYS=['park_walk','park_steps','park_service','park_edge']


def contains(x,y):
    w,s,e,n=PLAN['bounds'];return w-1e-7<=x<=e+1e-7 and s-1e-7<=y<=n+1e-7


def replaces_cell(i,j):
    return PLAN['columnRange'][0]<=i<PLAN['columnRange'][1] and PLAN['rowRange'][0]<=j<PLAN['rowRange'][1]


def water_level(x,y):
    def inside(ring):
        result=False
        for (a,b),(c,d) in zip(ring,ring[1:]+ring[:1]):
            if (b>y)!=(d>y) and x<(c-a)*(y-b)/(d-b)+a:result=not result
        return result
    for lake in PLAN['waterBodies']:
        if inside(lake['rings'][0]) and not any(inside(ring) for ring in lake['rings'][1:]):
            return scene_height(lake['levelMeters'],DEM)
    return None


@lru_cache(maxsize=16)
def vertex_heights(ground,bounds,columns,rows,lightweight,coarse):
    levels=[scene_height(z,DEM)*weight+coarse(x,y,ground,bounds,columns,rows,lightweight)*(1-weight)
            for (x,y),z,weight in zip(PLAN['points'],PLAN['targetMeters'],PLAN['weights'])]
    constraints=PLAN['linearHeightConstraints'];indices={c:i for i,(c,a,b,t) in enumerate(constraints)}
    matrix=np.eye(len(constraints));rhs=np.zeros(len(constraints))
    for i,(c,a,b,t) in enumerate(constraints):
        for endpoint,weight in [(a,1-t),(b,t)]:
            if endpoint in indices:matrix[i,indices[endpoint]]-=weight
            else:rhs[i]+=levels[endpoint]*weight
    if constraints:
        resolved=np.linalg.solve(matrix,rhs)
        for c,i in indices.items():levels[c]=float(resolved[i])
    if any(abs(levels[c]-levels[a]*(1-t)-levels[b]*t)>1e-8 for c,a,b,t in PLAN['linearHeightConstraints']):
        raise ValueError('Mountain edge height constraints did not converge')
    return levels


def sample_values(x,y,levels):
    if not contains(x,y):return None
    grid=PLAN['grid'];west,south,_,_=PLAN['bounds']
    i=min(grid['columns']-1,max(0,int((x-west)/grid['dx'])))
    j=min(grid['rows']-1,max(0,int((y-south)/grid['dy'])))
    for di,dj in [(0,0),(-1,0),(0,-1),(1,0),(0,1),(-1,-1),(1,1),(-1,1),(1,-1)]:
        for face in PLAN['cells'].get(f'{i+di},{j+dj}',[]):
            ids=PLAN['triangles'][face];a,b,c=[PLAN['points'][k] for k in ids]
            denominator=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            if abs(denominator)<1e-12:continue
            u=((x-a[0])*(c[1]-a[1])-(y-a[1])*(c[0]-a[0]))/denominator
            v=((b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0]))/denominator
            if min(u,v,1-u-v)>=-1e-8:return levels[ids[0]]*(1-u-v)+levels[ids[1]]*u+levels[ids[2]]*v
    return None


def surface(x,y,ground,bounds,columns,rows,lightweight,coarse):
    if not contains(x,y):return None
    return sample_values(x,y,vertex_heights(ground,tuple(bounds),columns,rows,lightweight,coarse))


def canopy_factor(x,y):
    weight=sample_values(x,y,PLAN['weights'])
    return 1-(1-PLAN['source']['canopyRiseFactor'])*max(0,min(1,weight or 0))


def build(batch,ground,bounds,columns,rows,lightweight,coarse):
    ground=getattr(ground,'unpatched',ground)
    levels=vertex_heights(ground,tuple(bounds),columns,rows,lightweight,coarse)
    for ids,key in zip(PLAN['triangles'],PLAN['materials']):
        points=[(*PLAN['points'][i],levels[i]) for i in ids]
        a,b,c=points
        if (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])<0:points.reverse()
        batch.face(points,'hill' if key=='forest' else 'ground')


def build_paths(batch,ground,bounds,columns,rows,lightweight,coarse):
    ground=getattr(ground,'unpatched',ground)
    levels=vertex_heights(ground,tuple(bounds),columns,rows,lightweight,coarse)
    lift=PLAN['source']['pathClearanceMeters']/100;edges={};count=0
    for ids,key in zip(PLAN['triangles'],PLAN['materials']):
        if key not in ['walk','steps','service']:continue
        points=[(*PLAN['points'][i],levels[i]+lift) for i in ids]
        a,b,c=points
        if (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])<0:points.reverse()
        batch.face(points,'park_'+key);count+=1
        for a,b in zip(ids,ids[1:]+ids[:1]):
            edge=tuple(sorted((a,b)));edges[edge]=edges.get(edge,0)+1
    for (a,b),counted in edges.items():
        if counted!=1:continue
        u,v=PLAN['points'][a],PLAN['points'][b]
        batch.face([(*u,levels[a]-.003),(*v,levels[b]-.003),(*v,levels[b]+lift),(*u,levels[a]+lift)],'park_edge')
    return {'surfaceTriangles':count,'edgeSegments':sum(v==1 for v in edges.values()),'pathWays':len(PLAN['paths'])}
