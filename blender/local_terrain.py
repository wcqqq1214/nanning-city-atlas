"""Shared triangulated waterfront replacement, queried by every dependent layer.

Vertex heights blend to each quality tier's original triangle at the outer edge.
The plan stores horizontal geometry only; original DEM samples are never edited.
"""
from functools import lru_cache
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = json.loads((ROOT/'data/waterfront-plan.json').read_text())
MATERIAL_KEYS = ['ground', 'hill', 'hillLight', 'bank', 'waterfront_paving', 'waterfront_wall']


def contains(x,y):
    w,s,e,n = PLAN['bounds']
    return w-1e-7 <= x <= e+1e-7 and s-1e-7 <= y <= n+1e-7


def replaces_cell(i,j):
    return (PLAN['columnRange'][0] <= i < PLAN['columnRange'][1] and
            PLAN['rowRange'][0] <= j < PLAN['rowRange'][1])


@lru_cache(maxsize=16)
def vertex_heights(ground, bounds, columns, rows, lightweight, coarse):
    return [PLAN['section']['bankTopSceneZ']*weight+
            coarse(x,y,ground,bounds,columns,rows,lightweight)*(1-weight)
            for (x,y),weight in zip(PLAN['points'], PLAN['weights'])]


def surface(x,y,ground,bounds,columns,rows,lightweight,coarse):
    if not contains(x,y): return None
    grid = PLAN['grid'];west,south,_,_ = PLAN['bounds']
    i = min(grid['columns']-1,max(0,int((x-west)/grid['dx'])))
    j = min(grid['rows']-1,max(0,int((y-south)/grid['dy'])))
    levels = vertex_heights(ground,tuple(bounds),columns,rows,lightweight,coarse)
    # Neighbour cells handle rounded tile-edge points without opening seams.
    for di,dj in [(0,0),(-1,0),(0,-1),(1,0),(0,1),(-1,-1),(1,1),(-1,1),(1,-1)]:
        for face in PLAN['cells'].get(f'{i+di},{j+dj}',[]):
            ids = PLAN['triangles'][face]
            a,b,c = [PLAN['points'][k] for k in ids]
            denominator = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            if abs(denominator)<1e-12: continue
            u = ((x-a[0])*(c[1]-a[1])-(y-a[1])*(c[0]-a[0]))/denominator
            v = ((b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0]))/denominator
            if min(u,v,1-u-v)>=-1e-5:
                return levels[ids[0]]*(1-u-v)+levels[ids[1]]*u+levels[ids[2]]*v
    return None  # Water remains a real hole in the terrain.


def build(batch,ground,bounds,columns,rows,lightweight,coarse,include_wall=True):
    ground = getattr(ground,'unpatched',ground)
    levels = vertex_heights(ground,tuple(bounds),columns,rows,lightweight,coarse)
    points = [(*point,z) for point,z in zip(PLAN['points'],levels)]
    for face,key in zip(PLAN['triangles'],PLAN['materials']):
        vertices = [points[i] for i in face]
        a,b,c = vertices
        if (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])<0:
            vertices.reverse()
        batch.face(vertices,key)
    if include_wall:
        bottom = PLAN['section']['waterSceneZ']-.025
        for ia,ib in zip(PLAN['wallVertexIds'],PLAN['wallVertexIds'][1:]):
            a,b = points[ia],points[ib]
            if math.dist(a[:2],b[:2])>.5:
                raise ValueError('Unexpected gap in the waterfront wall')
            # River-facing wall meets the very same vertices as the land surface.
            batch.face([(*a[:2],bottom),(*b[:2],bottom),b,a],'waterfront_wall')
