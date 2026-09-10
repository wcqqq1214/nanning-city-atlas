"""Continuous mapped railways, graded embankments, bridges and sparse fittings.

Horizontal positions are OSM data. Heights and small structural fittings are
terrain-aware display approximations, not an engineering reconstruction.
"""
import bisect
import heapq
import json
import math
from pathlib import Path
from functools import lru_cache
from station_landmarks import ground_blend

ROOT = Path(__file__).resolve().parents[1]
PLAN = json.loads((ROOT/'data/railways-plan.json').read_text())
MATERIAL_KEYS = ['rail_ballast','rail_steel','rail_sleeper','rail_concrete','rail_metal','rail_earth']
REMOVED_TREES = set(PLAN['removedTrees'])
REMOVED_BUILDINGS = set(PLAN['removedBuildings'])
GAUGE = .01435


class TerrainCut:
    def __init__(self,cuts):
        self.cells={}
        for cut in cuts:
            x,y,_=cut
            for gx in range(math.floor((x-3.5)/4),math.floor((x+3.5)/4)+1):
                for gy in range(math.floor((y-3.5)/4),math.floor((y+3.5)/4)+1):
                    self.cells.setdefault((gx,gy),[]).append(cut)

    def height(self,x,y,level):
        # Cover a mobile DEM cell diagonal, then blend into unchanged terrain.
        for cx,cy,z in self.cells.get((math.floor(x/4),math.floor(y/4)),[]):
            distance=math.hypot(x-cx,y-cy)
            if distance>=3.5: continue
            t=max(0,min(1,(distance-2.8)/.7))
            blend=t*t*(3-2*t)
            level=min(level,z*(1-blend)+level*blend)
        return level


class RailPath:
    def __init__(self, points, levels):
        self.points, self.levels = points, levels
        self.distances = [0.]
        for a,b in zip(points,points[1:]):
            self.distances.append(self.distances[-1]+math.dist(a,b))
        self.length = self.distances[-1]
        self.normals = []
        for i in range(len(points)):
            a,b = points[max(0,i-1)], points[min(len(points)-1,i+1)]
            d = math.dist(a,b)
            self.normals.append((-(b[1]-a[1])/d,(b[0]-a[0])/d))

    def at(self, distance, offset=0, rise=0):
        distance = max(0,min(self.length,distance))
        i = max(0,min(len(self.points)-2,bisect.bisect_right(self.distances,distance)-1))
        t = (distance-self.distances[i])/(self.distances[i+1]-self.distances[i])
        a,b = self.points[i:i+2]
        na,nb = self.normals[i:i+2]
        nx,ny = na[0]*(1-t)+nb[0]*t,na[1]*(1-t)+nb[1]*t
        d = math.hypot(nx,ny)
        return (a[0]*(1-t)+b[0]*t+nx/d*offset,
                a[1]*(1-t)+b[1]*t+ny/d*offset,
                self.levels[i]*(1-t)+self.levels[i+1]*t+rise)


class Railways:
    def __init__(self, ground, surface, station_sites):
        surface=lru_cache(maxsize=300000)(surface)
        self.ground, self.surface = ground,surface
        nodes = PLAN['nodes']
        required = [-1000.]*len(nodes)
        self.floors = [None]*len(nodes)
        graph = [[] for _ in nodes]
        for route in PLAN['paths']:
            tunnel = route['tags'].get('tunnel','no')!='no'
            bridge = route['tags'].get('bridge','no')!='no'
            layer = max(1,int(route['tags'].get('layer','1')))
            flat_path=RailPath([nodes[i]['xy'] for i in route['nodes']],[0.]*len(route['nodes']))
            for i in route['nodes']:
                x,y = nodes[i]['xy']
                if self.floors[i] is None:
                    self.floors[i] = max(ground(x,y),surface(x,y,False),surface(x,y,True))
                if not tunnel:
                    clearance = .24*layer if bridge else .035
                    # Existing station aprons are deliberately flattened. Ease
                    # bridge approaches into their rail datum over that apron.
                    for name,(sx,sy,level) in station_sites.items():
                        if abs(x-sx)<10 and abs(y-sy)<10:
                            blend = ground_blend(name,x-sx,y-sy)
                            station_clearance = .065 if name=='east-station' else .035
                            clearance = station_clearance*(1-blend)+clearance*blend
                    required[i] = max(required[i],max(self.floors[i],.26 if bridge else -1000)+clearance)
            if not tunnel:
                for j,(a,b) in enumerate(zip(route['nodes'],route['nodes'][1:])):
                    lo,hi=flat_path.distances[j:j+2]
                    floor=max(surface(*flat_path.at(lo+(hi-lo)*t,offset)[:2],mobile)
                              for t in [0,.5,1] for offset in [-.028,.028] for mobile in [False,True])
                    # A DEM triangle boundary can peak between OSM vertices.
                    # Both ends support the sampled segment, including shoulders.
                    for i in [a,b]: required[i]=max(required[i],floor+.035)
            for a,b in zip(route['nodes'],route['nodes'][1:]):
                cost = .12*math.dist(nodes[a]['xy'],nodes[b]['xy'])
                graph[a].append((b,cost)); graph[b].append((a,cost))
        fixed = {}
        for i,node in enumerate(nodes):
            if node['station']:
                name = node['station']
                fixed[i] = station_sites[name][2]+(.065 if name=='east-station' else .035)
                required[i] = fixed[i]
        queue = [(-v,i) for i,v in enumerate(required) if v>-999]
        self.minimum_levels = required.copy()
        heapq.heapify(queue)
        while queue:
            negative,i = heapq.heappop(queue)
            if -negative < required[i]-1e-10: continue
            for j,cost in graph[i]:
                candidate = -negative-cost
                if candidate > required[j]+1e-10:
                    required[j] = candidate
                    heapq.heappush(queue,(-candidate,j))
        # The station platform datum is a hard constraint. A shortest-path upper
        # envelope gives the connected approach a bounded grade; locally cut
        # the display DEM where its coarse hill would otherwise bury that track.
        upper = [float('inf')]*len(nodes)
        queue = [(v,i) for i,v in fixed.items()]
        heapq.heapify(queue)
        for i,v in fixed.items(): upper[i]=v
        while queue:
            value,i=heapq.heappop(queue)
            if value>upper[i]+1e-10: continue
            for j,cost in graph[i]:
                if value+cost<upper[j]-1e-10:
                    upper[j]=value+cost
                    heapq.heappush(queue,(upper[j],j))
        required = [min(a,b) for a,b in zip(required,upper)]
        self.cuts = [(nodes[i]['xy'][0],nodes[i]['xy'][1],value-.035)
                     for i,value in enumerate(required)
                     if nodes[i]['station'] is None and self.minimum_levels[i]>value+.001]
        self.terrain_cut=TerrainCut(self.cuts)
        self.levels = required
        self.paths = {}
        for route in PLAN['paths']:
            kept=[]
            for i in route['nodes']:
                kept.append(i)
                while len(kept)>=3 and nodes[kept[-2]]['osmNode'] is None:
                    a,b,c=kept[-3:]
                    pa,pb,pc=[nodes[j]['xy'] for j in [a,b,c]]
                    dx,dy=pc[0]-pa[0],pc[1]-pa[1]
                    if dx*dx+dy*dy<1e-12: break
                    t=((pb[0]-pa[0])*dx+(pb[1]-pa[1])*dy)/(dx*dx+dy*dy)
                    if math.dist(pb,(pa[0]+t*dx,pa[1]+t*dy))>1e-6 or abs(required[b]-(required[a]*(1-t)+required[c]*t))>1e-6:
                        break
                    kept.pop(-2)
            self.paths[route['id']]=RailPath([nodes[i]['xy'] for i in kept],[required[i] for i in kept])
        self.routes = {r['id']:r for r in PLAN['paths']}
        self.track_cells={}
        for route in PLAN['paths']:
            if route['tags'].get('tunnel','no')!='no': continue
            for a,b in zip(route['nodes'],route['nodes'][1:]):
                pa,pb=nodes[a]['xy'],nodes[b]['xy']
                for gx in range(math.floor(min(pa[0],pb[0])/2),math.floor(max(pa[0],pb[0])/2)+1):
                    for gy in range(math.floor(min(pa[1],pb[1])/2),math.floor(max(pa[1],pb[1])/2)+1):
                        self.track_cells.setdefault((gx,gy),[]).append((route['id'],a,b))

    def cut_ground(self,x,y,level):
        return self.terrain_cut.height(x,y,level)

    def adjacent_track(self,route_id,point,radius=.026):
        x,y,z=point;gx,gy=math.floor(x/2),math.floor(y/2)
        for u in range(gx-1,gx+2):
            for v in range(gy-1,gy+2):
                for identity,a,b in self.track_cells.get((u,v),[]):
                    if identity==route_id: continue
                    pa,pb=PLAN['nodes'][a]['xy'],PLAN['nodes'][b]['xy']
                    dx,dy=pb[0]-pa[0],pb[1]-pa[1]
                    t=max(0,min(1,((x-pa[0])*dx+(y-pa[1])*dy)/(dx*dx+dy*dy)))
                    if math.hypot(x-pa[0]-t*dx,y-pa[1]-t*dy)<radius and abs(z-(self.levels[a]*(1-t)+self.levels[b]*t))<.06:
                        return True
        return False

    def validate(self,station_sites):
        max_grade,penetration,station_error=0.,0.,0.
        worst=None
        for route in PLAN['paths']:
            path=self.paths[route['id']]
            for a,b,za,zb in zip(path.points,path.points[1:],path.levels,path.levels[1:]):
                max_grade=max(max_grade,abs(zb-za)/math.dist(a,b))
            if route['tags'].get('tunnel','no')!='no': continue
            for a,b in zip(path.distances,path.distances[1:]):
                for t in [0,.25,.5,.75,1]:
                    for offset in [-.019,0,.019]:
                        x,y,z=path.at(a+(b-a)*t,offset,-.009)
                        floor=max(self.surface(x,y,False),self.surface(x,y,True))
                        if floor-z>penetration:
                            penetration=floor-z
                            worst={'way':route['osmId'],'position':[x,y,z],'ground':floor}
        for i,node in enumerate(PLAN['nodes']):
            if node['station']:
                name=node['station']
                expected=station_sites[name][2]+(.065 if name=='east-station' else .035)
                station_error=max(station_error,abs(self.levels[i]-expected))
        return {'maxDisplayGrade':max_grade,'maxBallastPenetration':penetration,
                'maxStationDatumError':station_error,'terrainCutSamples':len(self.cuts),'worst':worst}


def ribbon(batch, path, distances, left, right, rise, material):
    for a,b in zip(distances,distances[1:]):
        batch.face([path.at(a,left,rise),path.at(b,left,rise),
                    path.at(b,right,rise),path.at(a,right,rise)],material)


def build_structure(batch, railways):
    """The same linework and support geometry survives both quality profiles."""
    for route in PLAN['paths']:
        if route['tags'].get('tunnel','no')!='no': continue
        path = railways.paths[route['id']]
        distances = path.distances
        bridge = route['tags'].get('bridge','no')!='no'
        # Flat ballast top and sloped shoulders, with continuous rail heads.
        ribbon(batch,path,distances,-.019,.019,-.009,'rail_ballast')
        for side in [-1,1]:
            for a,b in zip(distances,distances[1:]):
                batch.face([path.at(a,side*.019,-.009),path.at(b,side*.019,-.009),
                            path.at(b,side*.028,-.020),path.at(a,side*.028,-.020)],'rail_ballast')
            offset = side*GAUGE/2
            ribbon(batch,path,distances,offset-.0009,offset+.0009,.003,'rail_steel')
            for edge in [-.0009,.0009]:
                for a,b in zip(distances,distances[1:]):
                    batch.face([path.at(a,offset+edge,-.005),path.at(b,offset+edge,-.005),
                                path.at(b,offset+edge,.003),path.at(a,offset+edge,.003)],'rail_steel')
        if bridge:
            ribbon(batch,path,distances,-.039,.039,-.022,'rail_concrete')
            for side in [-1,1]:
                for a,b in zip(distances,distances[1:]):
                    for low,high,offset in [(-.062,-.022,.039),(-.022,.004,.037)]:
                        if low==-.022 and railways.adjacent_track(route['id'],path.at((a+b)/2,side*offset)):
                            continue
                        batch.face([path.at(a,side*offset,low),path.at(b,side*offset,low),
                                    path.at(b,side*offset,high),path.at(a,side*offset,high)],'rail_concrete')
            for s in route['piers']:
                x,y,top = path.at(s,0,-.062)
                bottom = min(railways.surface(x,y,False),railways.surface(x,y,True))-.025
                if top-bottom > .09:
                    batch.box(x,y,bottom,.024,.034,top-bottom,'rail_concrete')
                    batch.box(x,y,top-.012,.065,.045,.012,'rail_concrete')
            if route['tags'].get('bridge:structure')=='truss':
                # OSM explicitly identifies the San'an steel-truss crossing.
                # Retain its open structural silhouette in both profiles.
                count=max(2,math.ceil(path.length/.24))
                for j in range(count):
                    a,b=path.length*j/count,path.length*(j+1)/count
                    for side in [-1,1]:
                        if railways.adjacent_track(route['id'],path.at((a+b)/2,side*.042)):
                            continue
                        batch.beam(path.at(a,side*.042,.015),path.at(b,side*.042,.015),.0035,'rail_metal')
                        batch.beam(path.at(a,side*.042,.14),path.at(b,side*.042,.14),.0035,'rail_metal')
                        batch.beam(path.at(a,side*.042,.015),path.at(a,side*.042,.14),.003,'rail_metal')
                        batch.beam(path.at(a,side*.042,.015 if j%2==0 else .14),
                                   path.at(b,side*.042,.14 if j%2==0 else .015),.003,'rail_metal')
                    batch.beam(path.at(a,-.042,.14),path.at(a,.042,.14),.003,'rail_metal')
        else:
            # Fill the space down to BOTH displayed terrains; no floating strips
            # when the grade envelope crosses a low-resolution DEM valley.
            for a,b in zip(distances,distances[1:]):
                for side in [-1,1]:
                    topa,topb = path.at(a,side*.028,-.020),path.at(b,side*.028,-.020)
                    lows=[]
                    for s,top in [(a,topa),(b,topb)]:
                        floor = min(railways.surface(*top[:2],False),railways.surface(*top[:2],True))
                        width = .029+min(.14,max(0,top[2]-floor)*.4)
                        x,y,_=path.at(s,side*width)
                        lows.append((x,y,min(railways.surface(x,y,False),railways.surface(x,y,True))-.005))
                    batch.face([topa,topb,lows[1],lows[0]],'rail_earth')


def build_details(batch, railways, lightweight=False):
    counts = {'sleepers':0,'masts':0,'portals':0}
    tunnel_nodes = set()
    surface_nodes = set()
    for route in PLAN['paths']:
        if route['tags'].get('tunnel','no')!='no':
            tunnel_nodes.update(route['nodes'][1:-1])
        else:
            surface_nodes.update(route['nodes'])
    tunnel_ends = {}
    for route in PLAN['paths']:
        path = railways.paths[route['id']]
        if route['tags'].get('tunnel','no')!='no':
            for i,s in [(route['nodes'][0],0),(route['nodes'][-1],path.length)]:
                tunnel_ends.setdefault(i,[]).append((path,s))
            continue
        spacing = .08 if lightweight else .025
        count = max(1,math.floor(path.length/spacing))
        for i in range(count):
            s = (i+.5)*path.length/count
            batch.face([path.at(s-.0018,-.0135,-.004),path.at(s+.0018,-.0135,-.004),
                        path.at(s+.0018,.0135,-.004),path.at(s-.0018,.0135,-.004)],'rail_sleeper')
            counts['sleepers']+=1
        if route['tags'].get('electrified')!='contact_line': continue
        # The map locates electrified tracks, not individual masts. These are
        # regularly spaced schematic fittings, with reduced density on mobile.
        for s in route['masts'][::2 if lightweight else 1]:
            batch.beam(path.at(s,.041,-.030),path.at(s,.041,.100),.002,'rail_metal')
            batch.beam(path.at(s,.041,.090),path.at(s,0,.075),.0016,'rail_metal')
            counts['masts']+=1
        if not lightweight:
            ribbon(batch,path,path.distances,-.0006,.0006,.071,'rail_metal')
    # A boundary between two tunnel OSM ways is not a second portal.
    for i,ends in tunnel_ends.items():
        if len(ends)!=1 or i in tunnel_nodes or i not in surface_nodes: continue
        path,s=ends[0]
        for side in [-1,1]:
            batch.beam(path.at(s,side*.034,-.025),path.at(s,side*.034,.085),.008,'rail_concrete')
        batch.beam(path.at(s,-.034,.085),path.at(s,.034,.085),.008,'rail_concrete')
        counts['portals']+=1
    return counts
