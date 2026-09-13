"""P4 reservations and shared support samples, in east/north scene units.

Reservations describe the rendered site, not surveyed property boundaries.
Terrain extrema include edge intersections with both coarse grids and the
Qingxiu replacement mesh, so low roofs cannot conceal missed interior peaks.
"""
import json
import math
from functools import lru_cache
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=json.loads((ROOT/'data/landmark-calibration-source.json').read_text())
SPECS=SOURCE['sites']


def rect_ring(rect):
    w,s,e,n=rect
    return [(w,s),(e,s),(e,n),(w,n)]


def reservation_rings(identity):
    if identity=='arts-center':
        from arts_landmark import outline,SITE_ANGLE,entrance_flights
        c,s=math.cos(SITE_ANGLE),math.sin(SITE_ANGLE)
        rings=[[(u*c*1.12-v*s*1.12,u*s*1.12+v*c*1.12) for u,v in outline()]]
        for a,b,width in entrance_flights():
            length=math.dist(a,b);dx=(b[0]-a[0])/length;dy=(b[1]-a[1])/length
            rings.append([(p[0]-dy*t,p[1]+dx*t) for p,t in [(a,-width/2),(b,-width/2),(b,width/2),(a,width/2)]])
        return rings
    if identity=='zhenning':
        return [[(.21*math.cos(i*math.tau/80),.21*math.sin(i*math.tau/80)) for i in range(80)],
                rect_ring([-.035,-.28,.035,-.19]),rect_ring([-.025,.19,.025,.25])]
    if identity=='confucius':
        courts=[rect_ring([v/100 for v in item['rectMeters']]) for item in SPECS[identity]['courts']]
        courts += [rect_ring([-.11,-.50,.11,-.43]),rect_ring([-.11,.09,.11,.18]),
                   rect_ring([-.09,.58,.09,.66]),rect_ring([-.09,.90,.09,1.02])]
        return courts
    if identity=='diwang':
        plan=json.loads((ROOT/'data/landmark-calibration-plan.json').read_text())['sites'][identity]
        return [plan['podiumOutlineSceneXY'][:-1],plan['outlineSceneXY'][:-1]]
    return []


def inside(point,ring):
    x,y=point;hit=False
    for a,b in zip(ring,ring[1:]+ring[:1]):
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:hit=not hit
    return hit


@lru_cache(maxsize=4)
def rings_for(identity):
    return reservation_rings(identity)


def inside_site(identity,u,v):
    return any(inside((u,v),ring) for ring in rings_for(identity))


def cross(a,b):return a[0]*b[1]-a[1]*b[0]


def support_points(ring,terrain_grid):
    from mountain_terrain import PLAN as mountain
    bounds,cols,rows=terrain_grid
    west,south,east,north=bounds
    w=min(p[0] for p in ring);e=max(p[0] for p in ring)
    s=min(p[1] for p in ring);n=max(p[1] for p in ring)
    points=list(ring);edges=[]
    dx=(east-west)/(cols-1);dy=(north-south)/(rows-1)
    for step in [1,2]:
        for i in range(max(0,math.floor((w-west)/dx/step)*step),min(cols-1,math.ceil((e-west)/dx)),step):
            for j in range(max(0,math.floor((north-n)/dy/step)*step),min(rows-1,math.ceil((north-s)/dy)),step):
                p=[(west+a*dx,north-b*dy) for a,b in [(i,j),(min(i+step,cols-1),j),(min(i+step,cols-1),min(j+step,rows-1)),(i,min(j+step,rows-1))]]
                edges.extend([(p[0],p[1]),(p[1],p[2]),(p[2],p[3]),(p[3],p[0]),(p[0],p[2])])
    mw,ms,me,mn=mountain['bounds']
    if w<me and e>mw and s<mn and n>ms:
        for tri in mountain['triangles']:
            p=[mountain['points'][i] for i in tri]
            if max(a[0] for a in p)<w or min(a[0] for a in p)>e or max(a[1] for a in p)<s or min(a[1] for a in p)>n:continue
            edges.extend(zip(p,p[1:]+p[:1]))
    for a,b in edges:
        points.extend(p for p in [a,b] if inside(p,ring))
        r=(b[0]-a[0],b[1]-a[1])
        for c,d in zip(ring,ring[1:]+ring[:1]):
            q=(d[0]-c[0],d[1]-c[1]);den=cross(r,q)
            if abs(den)<1e-14:continue
            ca=(c[0]-a[0],c[1]-a[1]);t=cross(ca,q)/den;u=cross(ca,r)/den
            if -1e-9<=t<=1+1e-9 and -1e-9<=u<=1+1e-9:points.append((a[0]+t*r[0],a[1]+t*r[1]))
    # Fine samples cover native smooth callbacks in addition to the final mesh.
    nx=max(1,math.ceil((e-w)/.03));ny=max(1,math.ceil((n-s)/.03))
    points.extend((w+(e-w)*i/nx,s+(n-s)*j/ny) for i in range(nx+1) for j in range(ny+1)
                  if inside((w+(e-w)*i/nx,s+(n-s)*j/ny),ring))
    return list({(round(p[0],10),round(p[1],10)) for p in points})


def support_level(ring,ground_bounds,terrain_grid,clearance=.012):
    return max(ground_bounds(*p)[1] for p in support_points(ring,terrain_grid))+clearance
