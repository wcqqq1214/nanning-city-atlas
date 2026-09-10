"""Minzu carriageways, frontage roads and fittings using Qingxiang materials."""
import bisect
from collections import defaultdict
import heapq
import json
import math
from pathlib import Path as FilePath
from viaduct import Path, MATERIAL_KEYS as ROAD_MATERIALS

ROOT = FilePath(__file__).resolve().parents[1]
PLAN = json.loads((ROOT / 'data/minzu-plan.json').read_text())
MATERIAL_KEYS = ROAD_MATERIALS + ['nanhu_grass']
REPLACED_ROADS = set(PLAN['replacedRoads'])
REMOVED_TREES = set(PLAN['removedTrees'])


class MinzuAvenue:
    def __init__(self, road_level, surface):
        self.base_level, self.surface = road_level, surface
        self.routes = {r['id']: r for r in PLAN['paths']}
        self.paths = {key: Path(r['points']) for key, r in self.routes.items()}
        self.keys, required, graph, widths = {}, {}, defaultdict(list), defaultdict(list)
        for key, path in self.paths.items():
            r = self.routes[key]
            source = {min(range(len(path.lengths)), key=lambda j: abs(path.lengths[j] - s)): n
                      for s, n in r['sourceNodes']}
            self.keys[key] = [source.get(i, f'{key}@{i}') for i in range(len(path.points))]
            for node in self.keys[key]: widths[node].append(r['width'] / 2)
        self.endpoint_widths = {key: (sum(widths[nodes[0]]) / len(widths[nodes[0]]),
                                     sum(widths[nodes[-1]]) / len(widths[nodes[-1]]))
                                for key, nodes in self.keys.items()}
        for key, path in self.paths.items():
            r = self.routes[key]
            for i, s in enumerate(path.lengths):
                w = self.width(key, s)
                floor = max(surface(*path.at(s, u)[:2], mobile)
                            for u in [-w-.04, 0, w+.04] for mobile in [False, True])
                value = max(road_level(*path.at(s)[:2]), floor + (.30 if r['bridge'] else .07))
                if r['bridge']: value = max(value, 1.1)
                node = self.keys[key][i]
                required[node] = max(required.get(node, -1000), value)
            for i, (a, b) in enumerate(zip(self.keys[key], self.keys[key][1:])):
                cost = .12 * (path.lengths[i+1] - path.lengths[i])
                graph[a].append((b, cost)); graph[b].append((a, cost))
        queue = [(-z, node) for node, z in required.items()]
        heapq.heapify(queue)
        while queue:
            neg, node = heapq.heappop(queue)
            if -neg < required[node] - 1e-10: continue
            for other, cost in graph[node]:
                if -neg-cost > required[other] + 1e-10:
                    required[other] = -neg-cost
                    heapq.heappush(queue, (neg+cost, other))
        self.profiles = {key: [required[n] for n in nodes] for key, nodes in self.keys.items()}
        self.sections = {key: self.reduce_sections(key) for key in self.paths}
        self.landings = []
        for key, path in self.paths.items():
            r = self.routes[key]
            for s in set([0, path.length, *r['junctions']]):
                x, y, z = self.at(key, s)
                lift = max(0, z-road_level(x, y))
                if lift > .002: self.landings.append((x, y, lift))

    def width(self, key, s):
        path, route = self.paths[key], self.routes[key]
        a, b = self.endpoint_widths[key]
        width = route['width']/2
        reach = min(.4, path.length/2)
        return width + (a-width)*max(0, 1-s/reach) + (b-width)*max(0, 1-(path.length-s)/reach)

    def level(self, key, s):
        i, t = self.paths[key].section(s)
        return self.profiles[key][i]*(1-t) + self.profiles[key][i+1]*t

    def reduce_sections(self, key):
        path = self.paths[key]
        edges = [[path.at(s, u*self.width(key, s), self.level(key, s)) for u in [-1, 1]]
                 for s in path.lengths]
        # Protect every graph junction, then simplify only between those anchors.
        keep = {0, len(path.points)-1}
        for s, _ in self.routes[key]['sourceNodes']:
            keep.add(min(range(len(path.lengths)), key=lambda i: abs(path.lengths[i]-s)))
        def reduce(a, b):
            if b-a <= 1: return
            def error(i):
                t = (path.lengths[i]-path.lengths[a])/(path.lengths[b]-path.lengths[a])
                return max(math.dist(edges[i][side], tuple(x*(1-t)+y*t for x,y in zip(edges[a][side],edges[b][side]))) for side in [0,1])
            index = max(range(a+1,b), key=error)
            if error(index) <= .004 and path.lengths[b]-path.lengths[a] <= .60: return
            if error(index) <= .004: index = (a+b)//2
            keep.add(index); reduce(a,index); reduce(index,b)
        anchors = sorted(keep)
        for a,b in zip(anchors,anchors[1:]): reduce(a,b)
        return [path.lengths[i] for i in sorted(keep)]

    def at(self, key, s, offset=0, dz=0):
        path, sections = self.paths[key], self.sections[key]
        s = max(0, min(path.length, s))
        i = max(0, min(len(sections)-2, bisect.bisect_right(sections,s)-1))
        a,b = sections[i:i+2]
        t = (s-a)/(b-a)
        pa = path.at(a, offset, self.level(key,a))
        pb = path.at(b, offset, self.level(key,b))
        return tuple(pa[j]*(1-t)+pb[j]*t+(dz if j==2 else 0) for j in range(3))

    def opening(self, key, s, margin=.20):
        return any(abs(s-j) < margin for j in self.routes[key]['junctions'])

    def road_level(self, x, y):
        # Lift retained crossing streets into the new deck at shared nodes.
        # A bounded cone dies away within the approach, retaining the DEM elsewhere.
        lift = max((max(0, z-.12*math.hypot(x-px,y-py)) for px,py,z in self.landings), default=0)
        return self.base_level(x,y)+lift

    def validate(self):
        clearance, grade = float('inf'), 0.
        for key,path in self.paths.items():
            for a,b in zip(self.sections[key],self.sections[key][1:]):
                pa,pb = self.at(key,a),self.at(key,b)
                grade = max(grade,abs(pb[2]-pa[2])/math.dist(pa[:2],pb[:2]))
                for i in range(5):
                    s = a+(b-a)*i/4
                    w = self.width(key,s)
                    for offset in [-w,0,w]:
                        x,y,z = self.at(key,s,offset)
                        clearance = min(clearance,*(z-self.surface(x,y,mobile) for mobile in [False,True]))
        assert clearance > .015, f'Minzu road intersects terrain: {clearance}'
        assert grade < .121, f'Minzu approach grade: {grade}'
        return {'minRoadClearanceMeters': round(clearance*100,3), 'maxDisplayGrade': grade,
                'renderedSections': sum(len(s)-1 for s in self.sections.values())}


def ribbon(batch, road, key, a, b, lo, hi, material, dz=0):
    batch.face([road.at(key,a,lo,dz),road.at(key,b,lo,dz),
                road.at(key,b,hi,dz),road.at(key,a,hi,dz)], material)


def build_structure(batch, road):
    for key,path in road.paths.items():
        r = road.routes[key]
        for a,b in zip(road.sections[key],road.sections[key][1:]):
            wa,wb = road.width(key,a),road.width(key,b)
            batch.face([road.at(key,a,-wa),road.at(key,b,-wb),road.at(key,b,wb),road.at(key,a,wa)],'viaduct_asphalt')
            for side in [-1,1]:
                top = [road.at(key,a,side*wa),road.at(key,b,side*wb)]
                bottom = [(x,y,z-.035 if r['bridge'] else min(road.surface(x,y,False),road.surface(x,y,True))-.003) for x,y,z in top]
                batch.face([top[0],top[1],bottom[1],bottom[0]],'viaduct_soffit' if r['bridge'] else 'viaduct_concrete')
                if road.opening(key,(a+b)/2, .25+(b-a)/2): continue
                # Concrete edge strips frame the road; short side walls add a
                # readable kerb without repeatedly modelling individual stones.
                edge = .006
                za = .012 if r['bridge'] else .004
                q = [road.at(key,a,side*(wa-edge),za),road.at(key,b,side*(wb-edge),za),
                     road.at(key,b,side*wb,za),road.at(key,a,side*wa,za)]
                batch.face(q,'viaduct_concrete')
                batch.face([road.at(key,a,side*(wa-edge)),road.at(key,b,side*(wb-edge)),q[1],q[0]],'viaduct_concrete')
            if r['bridge']:
                batch.face([road.at(key,a,-wa,-.035),road.at(key,a,wa,-.035),road.at(key,b,wb,-.035),road.at(key,b,-wb,-.035)],'viaduct_soffit')
            elif not road.opening(key,(a+b)/2,.25+(b-a)/2):
                # A narrow planted verge sits inside the left shoulder. No
                # invented median crosses an OSM junction or neighbouring road.
                if not r['frontage']:
                    batch.face([road.at(key,a,wa-.018,.0045),road.at(key,b,wb-.018,.0045),
                                road.at(key,b,wb-.007,.0045),road.at(key,a,wa-.007,.0045)],'nanhu_grass')
        # Source-tagged short bridges get a soffit and end abutments. Avoid
        # guessed piers in the lower carriageway at grade-separated crossings.
        if r['bridge']:
            for s in [0,path.length]:
                w = road.width(key,s)
                x,y,z = road.at(key,s)
                floor = min(road.surface(x,y,False),road.surface(x,y,True))
                a,b = road.at(key,max(0,s-.03)),road.at(key,min(path.length,s+.03))
                batch.box(x,y,floor,w*2,.024,max(.01,z-.035-floor),'viaduct_concrete',angle=math.atan2(b[1]-a[1],b[0]-a[0])-math.pi/2)


def arrow(batch, road, key, s, offset, turn):
    def line(a,b,lo,hi): ribbon(batch,road,key,s+a,s+b,offset+lo,offset+hi,'viaduct_line',.0018)
    line(-.027,.012,-.0015,.0015)
    if 'through' in turn:
        batch.face([road.at(key,s+.035,offset,.0018),road.at(key,s+.01,offset-.008,.0018),road.at(key,s+.01,offset+.008,.0018)],'viaduct_line')
    if 'left' in turn or 'reverse' in turn:
        line(.007,.011,0,.016)
        batch.face([road.at(key,s+.009,offset+.026,.0018),road.at(key,s+.019,offset+.012,.0018),road.at(key,s-.001,offset+.012,.0018)],'viaduct_line')
    if 'right' in turn:
        line(.007,.011,-.016,0)
        batch.face([road.at(key,s+.009,offset-.026,.0018),road.at(key,s-.001,offset-.012,.0018),road.at(key,s+.019,offset-.012,.0018)],'viaduct_line')


def build_details(batch, road, lightweight=False):
    counts = {'laneDashes':0,'lamps':0,'turnArrows':0}
    for key,path in road.paths.items():
        r = road.routes[key]
        spacing = .30 if lightweight else .20
        for j in range(math.ceil(path.length/spacing)):
            a,b = j*spacing+.025,min(path.length-.025,j*spacing+.10)
            if b <= a or road.opening(key,(a+b)/2,.22): continue
            w = min(road.width(key,a),road.width(key,b))-.014
            for lane in range(1,r['lanes']):
                offset = -w+2*w*lane/r['lanes']
                ribbon(batch,road,key,a,b,offset-.0012,offset+.0012,'viaduct_line',.0018)
                counts['laneDashes'] += 1
        # Edge lines survive both profiles and keep the surface readable at distance.
        for a,b in zip(road.sections[key],road.sections[key][1:]):
            if road.opening(key,(a+b)/2,.22+(b-a)/2): continue
            for side in [-1,1]:
                margin = .023 if side==1 and not r['frontage'] and not r['bridge'] else .010
                wa,wb = road.width(key,a)-margin,road.width(key,b)-margin
                batch.face([road.at(key,a,side*wa-.0012,.0018),road.at(key,b,side*wb-.0012,.0018),
                            road.at(key,b,side*wb+.0012,.0018),road.at(key,a,side*wa+.0012,.0018)],'viaduct_line')
        if lightweight: continue
        turns = r['tags'].get('turn:lanes','').split('|')
        if len(turns) == r['lanes'] and path.length > .5:
            s = path.length-.30
            w = road.width(key,s)-.014
            for lane,turn in enumerate(turns):
                arrow(batch,road,key,s,w-(lane+.5)*2*w/r['lanes'],turn)
                counts['turnArrows'] += 1
        if r['frontage']: continue
        for j in range(1,math.ceil(path.length/.9)):
            s = j*.9
            if s > path.length-.12 or road.opening(key,s,.30): continue
            offset = road.width(key,s)-.004
            a = road.at(key,s,offset,.014)
            b = road.at(key,s,offset,.114)
            c = road.at(key,s,offset-.04,.12)
            batch.beam(a,b,.0018,'viaduct_metal')
            batch.beam(b,c,.0016,'viaduct_metal')
            batch.beam(c,road.at(key,s,offset-.058,.12),.003,'viaduct_metal')
            counts['lamps'] += 1
    return counts
