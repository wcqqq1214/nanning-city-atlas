"""Native Minzu sections participating in the two Zhuxi ramp landings."""
import math

# OSM landing nodes, in the retained city coordinate system.
LANDINGS = ((74.014, -10.268), (77.513, -10.266))
LANDING_WAYS = {959178351: 1, 392546680: 0}


def selected(road, key, a, b):
    if not road.routes[key]['bridge']:
        return False
    # Include complete rendered sections so no artificial cut wall is exposed.
    x, y, _ = road.at(key, (a+b)/2)
    return any(math.hypot(x-u, y-v) < .35+(b-a)/2 for u, v in LANDINGS)


def capture(road):
    sections=[]
    for key, path in road.paths.items():
        for a,b in zip(road.sections[key],road.sections[key][1:]):
            if not selected(road,key,a,b):continue
            wa,wb=road.width(key,a),road.width(key,b)
            sections.append({'key':key,'a':a,'b':b,'points':[road.at(key,a,-wa),road.at(key,b,-wb),road.at(key,b,wb),road.at(key,a,wa)]})
    return sections


class PaintCapture:
    def __init__(self):self.faces=[]
    def face(self, vertices, material):
        if material=='viaduct_line':
            self.faces.extend([[vertices[0],vertices[j],vertices[j+1]] for j in range(1,len(vertices)-1)])
    def beam(self,*args,**kwargs):pass


class ResolvedPaint:
    """Keep native lamps; replace markings with the exposed-surface result."""
    def __init__(self,batch):self.batch=batch
    def face(self,vertices,material):
        if material!='viaduct_line':self.batch.face(vertices,material)
    def beam(self,*args,**kwargs):self.batch.beam(*args,**kwargs)


class NativeStructure:
    """Omit only native faces wholly owned by a replaced bridge section."""
    def __init__(self,batch,sections):
        self.batch=batch;self.sections=[]
        for section in sections:
            q=section['points']
            self.sections.append((q, min(p[0] for p in q),max(p[0] for p in q),
                                  min(p[1] for p in q),max(p[1] for p in q),
                                  min(p[2] for p in q)-.035,max(p[2] for p in q)+.012))
    def face(self,vertices,material):
        eps=1e-8
        for q,x0,x1,y0,y1,z0,z1 in self.sections:
            if any(not(x0-eps<=x<=x1+eps and y0-eps<=y<=y1+eps and z0-eps<=z<=z1+eps) for x,y,z in vertices):continue
            # The native road section is a convex quad; include shared edges.
            signs=[(b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0])
                   for a,b in zip(q,q[1:]+q[:1]) for x,y,z in vertices]
            if min(signs)>=-eps or max(signs)<=eps:return
        self.batch.face(vertices,material)
    def box(self,*args,**kwargs):
        # Native abutments remain, including their buried lower portions.
        self.batch.box(*args,**kwargs)


def build_structure(batch,road,lightweight=False):
    from minzu_avenue import build_structure as native_structure
    native_structure(NativeStructure(batch,capture(road)),road)
    from road_solids import minzu_structure
    minzu_structure(batch,lightweight)


def build_details(batch,road,lightweight=False,native=False):
    from minzu_avenue import build_details as native_details
    if native:return native_details(batch,road,lightweight)
    counts=native_details(ResolvedPaint(batch),road,lightweight)
    from road_solids import load
    data,_=load('smooth' if lightweight else 'detail')
    for tri in data['minzuPaint']:batch.face(tri.tolist(),'viaduct_line')
    return counts
