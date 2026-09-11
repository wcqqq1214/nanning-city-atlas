"""Shared Qingxiang construction for the remaining elevated city road network."""
from collections import defaultdict
import gzip
import hashlib
import heapq
import json
import math
from pathlib import Path
from viaduct import Path as RoadPath, MATERIAL_KEYS
from road_interfaces import LANDING_WAYS

ROOT=Path(__file__).resolve().parents[1]
PAYLOAD=gzip.decompress((ROOT/'data/elevated-roads-plan.json.gz').read_bytes())
PLAN=json.loads(PAYLOAD);PLAN_HASH=hashlib.sha256(PAYLOAD).hexdigest();del PAYLOAD
REPLACED_ROADS={r['roadIndex'] for r in PLAN['routes']}
MAX_GRADE=.18


def plane(tri):
    a,b,c=tri;dx,dy=b[0]-a[0],b[1]-a[1];ex,ey=c[0]-a[0],c[1]-a[1]
    d=dx*ey-dy*ex
    if abs(d)<2e-8:return None
    u=((b[2]-a[2])*ey-(c[2]-a[2])*dy)/d
    v=(dx*(c[2]-a[2])-ex*(b[2]-a[2]))/d
    return u,v,a[2]-u*a[0]-v*a[1]


class ElevatedRoads:
    def __init__(self,ground,surface,bridges=(),lightweight=False,minzu=None):
        profile='smooth' if lightweight else 'detail'
        self.ground=ground;self.surface=surface;self.lightweight=lightweight
        self.routes=[{**r,'terrainFloor':r['terrainFloors'][profile],'roadFloor':r['roadFloors'][profile]} for r in PLAN['routes']]
        self.paths=[RoadPath(r['points']) for r in self.routes]
        from ground_roads import REPLACED_ROADS as ground_indices
        geo=json.loads((ROOT/'public/data/geography.json').read_text())
        from road_terrain import deck_floors
        terrain=json.loads((ROOT/'public/data/terrain.json').read_text())
        external_nodes={tuple(p) for i,r in enumerate(geo['roads']) if i not in REPLACED_ROADS and i not in ground_indices for p in r['points']}
        bridge_ends=[bridge.at(s) for bridge in bridges for s in [0,bridge.path.total]]
        self.anchors={}
        for i,(r,path) in enumerate(zip(self.routes,self.paths)):
            for j in [0,len(path.points)-1]:
                x,y=path.points[j]
                if tuple(round(v,3) for v in (x,y)) not in external_nodes:continue
                target=r['roadFloor'][j]
                close=[p for p in bridge_ends if math.hypot(x-p[0],y-p[1])<.35]
                if close:target=min(close,key=lambda p:math.hypot(x-p[0],y-p[1]))[2]
                if target>-500:self.anchors[i,j]=target
            if r['osmId'] in LANDING_WAYS:
                j=0 if LANDING_WAYS[r['osmId']]==0 else len(path.points)-1
                x,y=path.points[j];target=r['roadFloor'][j]
                if minzu is not None:
                    key=min(minzu.paths,key=lambda key:minzu.paths[key].nearest(x,y)[0])
                    distance,s=minzu.paths[key].nearest(x,y)
                    assert distance<.1,'Minzu landing moved outside its carriageway'
                    target=minzu.at(key,s)[2]
                assert target>-500,'Missing fixed Minzu landing height'
                self.anchors[i,j]=target
        for i,(r,path) in enumerate(zip(self.routes,self.paths)):
            fixed={j:z-.005 for (owner,j),z in self.anchors.items() if owner==i}
            r['terrainFloor']=deck_floors(path,r['width'],r['terrainFloor'],lambda x,y:surface(x,y,lightweight),geo['bounds'],terrain['cols'],terrain['rows'],fixed)
        graph=defaultdict(list);lookup={};keys=[];levels=[];minimums=[]
        for i,(r,path) in enumerate(zip(self.routes,self.paths)):
            ids=[]
            for j,(x,y) in enumerate(path.points):
                key=(round(x,6),round(y,6))
                if key not in lookup:lookup[key]=len(levels);levels.append(-1000.);minimums.append(-1000.)
                node=lookup[key];ids.append(node)
                floor=max(r['terrainFloor'][j],surface(x,y,lightweight))
                minimums[node]=max(minimums[node],floor+.005)
                # Old 110 m generic bridge datum is deliberately discarded.
                required=max(floor+.23,r['roadFloor'][j]+.20)
                for end in [0,len(path.points)-1]:
                    if (i,end) not in self.anchors:continue
                    distance=abs(path.lengths[j]-path.lengths[end])
                    if distance<1.5:
                        # Existing detailed decks are fixed landing constraints.
                        # Taper the clearance requirement through their approach.
                        required=min(required,max(floor+.005,self.anchors[i,end]+MAX_GRADE*distance))
                levels[node]=max(levels[node],required)
            for j,(a,b,s,t) in enumerate(zip(ids,ids[1:],path.lengths,path.lengths[1:])):
                # Steep exaggerated mountain terrain is retained. Do not lift
                # an entire bridge/landing merely to flatten an existing ridge.
                cost=max(MAX_GRADE*(t-s),min(.75*(t-s),abs(r['terrainFloor'][j+1]-r['terrainFloor'][j])))
                if any((s if end==0 else path.length-t)<1.5 for end in r['groundEnds']):cost=max(cost,.75*(t-s))
                end=LANDING_WAYS.get(r['osmId'])
                if end is not None and (s if end==0 else path.length-t)<.8:
                    # These OSM ground-end flags actually meet a fixed Minzu
                    # deck. Keep an ordinary approach grade, not a 75% landing.
                    cost=MAX_GRADE*(t-s)
                graph[a].append((b,cost));graph[b].append((a,cost))
            keys.append(ids)
        for (i,j),target in self.anchors.items():levels[keys[i][j]]=target
        for a,r in enumerate(self.routes):
            for b,stations in r['mergeStations']:
                if not stations:continue
                for j in stations:
                    x,y=self.paths[a].points[j];s=self.paths[b].nearest(x,y)[1]
                    k=min(range(len(keys[b])),key=lambda k:abs(self.paths[b].lengths[k]-s))
                    anchor,node=keys[a][j],keys[b][k]
                    if node!=anchor:graph[anchor].append((node,0));graph[node].append((anchor,0))
        for cross in PLAN['crossings']:
            a,b=cross['upper'],cross['lower'];x,y=cross['point'];ends=[]
            for i in (a,b):
                s=self.paths[i].nearest(x,y)[1];j=self.paths[i].section(s)[0]
                ends.append(keys[i][j:j+2])
            for lower in ends[1]:
                for upper in ends[0]:graph[lower].append((upper,-.16))
        # Propagate fixed detailed-deck landing limits backwards through the
        # same graph; this avoids raising an otherwise connected existing bridge.
        reverse=defaultdict(list)
        for a,edges in graph.items():
            for b,cost in edges:reverse[b].append((a,cost))
        # Ground landings use the lowest feasible network profile. A uniform
        # elevated clearance at endpoints used to lift streets into tall walls.
        landing_floor=minimums.copy()
        for (i,j),target in self.anchors.items():landing_floor[keys[i][j]]=max(landing_floor[keys[i][j]],target)
        pending_floor=[(-value,node) for node,value in enumerate(landing_floor)];heapq.heapify(pending_floor)
        while pending_floor:
            negative,node=heapq.heappop(pending_floor);value=-negative
            if value<landing_floor[node]-1e-9:continue
            for other,cost in graph[node]:
                if value-cost>landing_floor[other]+1e-9:
                    landing_floor[other]=value-cost;heapq.heappush(pending_floor,(-landing_floor[other],other))
        upper=[float('inf')]*len(levels);pending=[];upper_updates=defaultdict(int)
        for (i,j),target in self.anchors.items():
            node=keys[i][j];upper[node]=min(upper[node],target);heapq.heappush(pending,(target,node))
        for i,r in enumerate(self.routes):
            for end in r['groundEnds']:
                j=0 if end==0 else len(keys[i])-1
                if (i,j) in self.anchors:continue
                target=max(landing_floor[keys[i][j]]+.01,r['roadFloor'][j])
                node=keys[i][j];upper[node]=min(upper[node],target);heapq.heappush(pending,(upper[node],node))
        while pending:
            value,node=heapq.heappop(pending)
            if value>upper[node]+1e-9:continue
            for other,cost in reverse[node]:
                candidate=value+cost
                if candidate<upper[other]-1e-9:
                    upper[other]=candidate;upper_updates[other]+=1
                    if upper_updates[other]>200:raise ValueError(f'Contradictory crossing order near {[p for p,k in lookup.items() if k==other]}')
                    heapq.heappush(pending,(candidate,other))
        incompatible=[(p,minimums[node],upper[node]) for p,node in lookup.items() if minimums[node]>upper[node]+.002]
        if incompatible:raise ValueError(f'Existing deck landing below terrain constraints: {incompatible[:8]}')
        levels=[min(value,upper[i]) for i,value in enumerate(levels)]
        queue=[(-v,i) for i,v in enumerate(levels)];heapq.heapify(queue);updates=defaultdict(int)
        while queue:
            negative,node=heapq.heappop(queue);value=-negative
            if value<levels[node]-1e-9:continue
            for other,cost in graph[node]:
                candidate=value-cost
                if candidate>levels[other]+1e-9:
                    levels[other]=candidate;updates[other]+=1
                    if updates[other]>200:raise ValueError(f'Inconsistent elevated crossing constraints near node {other}: {[p for p,k in lookup.items() if k==other]}')
                    heapq.heappush(queue,(-candidate,other))
        self.levels=[[levels[k] for k in ids] for ids in keys]
        self.ports=defaultdict(list)
        for i,(r,path) in enumerate(zip(self.routes,self.paths)):
            for end in r['groundEnds']:
                s=0 if end==0 else path.length;inside=min(.05,path.length) if end==0 else max(0,path.length-.05)
                x,y=path.at(s)[:2];u,v=path.at(inside)[:2];length=math.hypot(x-u,y-v)
                port=(x,y,(x-u)/length,(y-v)/length,r['width'],self.level(i,s))
                for gx in range(math.floor(x-.9),math.floor(x+.9)+1):
                    for gy in range(math.floor(y-.9),math.floor(y+.9)+1):self.ports[gx,gy].append(port)
        slopes=[abs(a-b)/(t-s) for path,z in zip(self.paths,self.levels) for a,b,s,t in zip(z,z[1:],path.lengths,path.lengths[1:]) if t-s>1e-8]
        gaps=[]
        for cross in PLAN['crossings']:
            x,y=cross['point'];a,b=cross['upper'],cross['lower']
            gaps.append(self.level(a,self.paths[a].nearest(x,y)[1])-self.level(b,self.paths[b].nearest(x,y)[1])-.035)
        seam=max((abs(self.levels[i][j]-target) for (i,j),target in self.anchors.items()),default=0)
        self.report={**PLAN['stats'],'maxDisplayGrade':round(max(slopes),6),'minCrossingClearanceMeters':round(min(gaps,default=0)*100,4),'maxExternalSeamMeters':round(seam*100,4),'planHash':PLAN_HASH}

    def level(self,i,s):
        j,t=self.paths[i].section(s);return self.levels[i][j]*(1-t)+self.levels[i][j+1]*t

    def connection_height(self,x,y,z):
        for cx,cy,ux,uy,w,target in self.ports.get((math.floor(x),math.floor(y)),[]):
            forward=(x-cx)*ux+(y-cy)*uy
            side=abs((x-cx)*uy-(y-cy)*ux);gap=math.hypot(forward,max(0,side-w))
            if gap>.65:continue
            t=1-gap/.65;blend=t*t*(3-2*t);z=max(z,z+max(0,target-z)*blend)
        return z


def build_structure(batch,network):
    from road_solids import structure
    return structure(batch,network)


def build_details(batch,network,lightweight=False):
    from road_solids import details
    return details(batch,network,lightweight)
