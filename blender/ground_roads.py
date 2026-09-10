"""Disjoint ground-road surfaces fitted to the actual terrain triangles."""
import bisect
import gzip
import hashlib
import json
import math
from pathlib import Path
from forest_canopy import refined_terrain_height, terrain_surface
from nanhu_landmark import PLAN as NANHU_PLAN

ROOT=Path(__file__).resolve().parents[1]
PLAN_BYTES=gzip.decompress((ROOT/'data/ground-roads-plan.json.gz').read_bytes())
PLAN_HASH=hashlib.sha256(PLAN_BYTES).hexdigest()
PLAN=json.loads(PLAN_BYTES)
del PLAN_BYTES
CONTEXT=json.loads((ROOT/'data/ground-roads-context.json').read_text())
MATERIAL_KEYS=['viaduct_asphalt','road_secondary','road_local','viaduct_line','viaduct_concrete']
REPLACED_ROADS=set(PLAN['roadIndices'])
REMOVED_TREES=set(PLAN['removedTrees'])


def plane_height(vertices,x,y):
    a,b,c=vertices
    denominator=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
    if abs(denominator)<1e-14: return sum(p[2] for p in vertices)/3
    u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/denominator
    v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/denominator
    return u*a[2]+v*b[2]+(1-u-v)*c[2]


def build_ground_roads(batch,ground,bounds,columns,rows,lightweight=False, bridges=()):
    mesh=PLAN['meshes']['smooth' if lightweight else 'detail']
    supports=[]
    for support in mesh['supports']:
        vertices=[]
        for x,y,col,row in support['vertices']:
            z=(refined_terrain_height(col,row,ground,bounds,columns,rows)
               if support['refined'] else ground(x,y))
            vertices.append((x,y,z))
        supports.append(vertices)
    # Nanhu's retained fine terrain meets a coarser mobile tile at its edge.
    # Match the higher of both actual edge profiles locally, so a quantized
    # boundary cannot move a low road triangle into the neighbouring high tile.
    geo=PLAN['sceneCenter'];kx=1113.2*math.cos(math.radians(geo[1]))
    nx=(NANHU_PLAN['center'][0]-geo[0])*kx;ny=(NANHU_PLAN['center'][1]-geo[1])*1113.2
    pw,ps,pe,pn=NANHU_PLAN['terrainPatch']['bounds']
    edges=[]
    for axis,value,lo,hi,normal in [(0,nx+pw,ny+ps,ny+pn,-1),(0,nx+pe,ny+ps,ny+pn,1),
                                     (1,ny+ps,nx+pw,nx+pe,-1),(1,ny+pn,nx+pw,nx+pe,1)]:
        samples={}
        for part in NANHU_PLAN['terrainPatch']['meshes']:
            for u,v in part['points']:
                x,y=nx+u,ny+v
                if abs((x,y)[axis]-value)<.00002:
                    samples[(y,x)[axis]]=ground(x,y)
        edges.append((axis,value,lo,hi,normal,sorted(samples),samples))
    ports=[]
    for bridge in bridges:
        for end,inside in [(0,.02),(bridge.path.total,bridge.path.total-.02)]:
            a,b=bridge.at(end,-bridge.width),bridge.at(end,bridge.width)
            center,inner=bridge.at(end),bridge.at(inside)
            ux,uy=center[0]-inner[0],center[1]-inner[1];length=math.hypot(ux,uy)
            ports.append((a,b,center[0],center[1],ux/length,uy/length))
    vertices=[];floors=[];min_lift=float('inf');max_lift=0
    for i,(x,y) in enumerate(mesh['points']):
        floor=plane_height(supports[mesh['pointSupports'][i]],x,y)
        z=floor+.008
        for axis,value,lo,hi,normal,stations,samples in edges:
            along=(y,x)[axis];gap=abs((x,y)[axis]-value)
            if gap>.35 or not lo<=along<=hi or len(stations)<2:continue
            j=max(0,min(len(stations)-2,bisect.bisect_right(stations,along)-1))
            a,b=stations[j:j+2];t=max(0,min(1,(along-a)/(b-a)))
            fine=samples[a]*(1-t)+samples[b]*t
            q=[x,y];q[axis]=value+normal*.00003
            coarse=terrain_surface(*q,ground,bounds,columns,rows,lightweight)
            blend=1-gap/.35;blend=blend*blend*(3-2*blend)
            z=max(z,floor+.008+max(0,max(fine,coarse)-floor)*blend)
        join=mesh['joins'].get(str(i))
        if join:
            index,px,py,distance=join
            face=CONTEXT['roadFaces'][index] if index>=0 else CONTEXT['bridgePorts'][-index-1]['face']
            target=plane_height(face,px,py)
            t=max(0,1-distance/.65);blend=t*t*(3-2*t)
            # Old generic elevated strips use a 110 m minimum display datum.
            # They are outside this ground-road pass: do not turn a local street
            # into a cliff merely to reach a suspended legacy bridge endpoint.
            if index<0 and target-floor>.35:
                blend=0
            z=max(z,floor+.008+max(0,target-floor-.008)*blend)
        for a,b,cx,cy,ux,uy in ports:
            if abs(x-cx)>.9 or abs(y-cy)>.9 or (x-cx)*ux+(y-cy)*uy<-.002:continue
            dx,dy=b[0]-a[0],b[1]-a[1]
            t=max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy)))
            gap=math.hypot(x-a[0]-t*dx,y-a[1]-t*dy)
            if gap>.65:continue
            blend=max(0,1-gap/.65);blend=blend*blend*(3-2*blend)
            z=max(z,floor+.008+max(0,a[2]*(1-t)+b[2]*t-floor-.008)*blend)
        floors.append(floor)
        min_lift=min(min_lift,z-floor);max_lift=max(max_lift,z-floor)
        vertices.append((x,y,z))
    for tri,material in zip(mesh['triangles'],mesh['materials']):
        batch.face([vertices[i] for i in tri],MATERIAL_KEYS[material])
    # Close only raised approach boundaries; ordinary street surfaces stay flat.
    edges={}
    for tri in mesh['triangles']:
        for a,b in zip(tri,tri[1:]+tri[:1]):
            edge=tuple(sorted((a,b)));edges[edge]=edges.get(edge,0)+1
    walls=0
    for (a,b),uses in edges.items():
        if uses!=1 or max(vertices[a][2]-floors[a],vertices[b][2]-floors[b])<.03:continue
        batch.face([vertices[a],vertices[b],(*vertices[b][:2],floors[b]+.004),(*vertices[a][:2],floors[a]+.004)],'viaduct_concrete')
        walls+=2
    paint=[]
    for x,y,parent in mesh['paintPoints']:
        z=plane_height([vertices[i] for i in mesh['triangles'][parent]],x,y)
        paint.append((x,y,z+.0020))
    painted=0
    for tri in mesh['paintTriangles']:
        parent=mesh['paintPoints'][tri[0]][2]
        a,b,c=[vertices[i] for i in mesh['triangles'][parent]]
        u=[b[k]-a[k] for k in range(3)];v=[c[k]-a[k] for k in range(3)]
        normal=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
        # Do not put narrow paint on near-vertical legacy connection slivers.
        if math.hypot(*normal[:2])>abs(normal[2]):continue
        batch.face([paint[i] for i in tri],'viaduct_line');painted+=1
    assert all(math.isfinite(v) for point in vertices for v in point)
    assert min_lift>=.007999
    return {'surfaceTriangles':len(mesh['triangles']),'approachWallTriangles':walls,'markingTriangles':painted,'omittedSteepMarkingTriangles':len(mesh['paintTriangles'])-painted,
            'minTerrainLiftMeters':round(min_lift*100,4),'maxConnectionLiftMeters':round(max_lift*100,3)}
