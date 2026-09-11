"""Photo-interpreted mall exteriors on WGS84 footprints; 1 unit = 100 m.

Hangyang: silver ship-like podium, scalloped canopy and four mapped towers.
MixC: curved retail block, pale panel cladding and bronze-framed glass portals.
Heights and facade details are illustrative, not measured architectural plans.
See docs/MALLS.md for sources and the boundary of this reconstruction.
"""
import json
import math
from pathlib import Path

PLAN = json.loads((Path(__file__).resolve().parents[1]/'data/malls-plan.json').read_text())
SITES = PLAN['sites']
MATERIALS = {
    'mall_stone': ('Mall pale limestone panels', 'd8d3bd', .77, .04),
    'mall_silver': ('Hangyang brushed silver hull', 'cbd3cf', .39, .38),
    'mall_glass': ('Mall blue sage glazing', '527f86', .24, .27),
    'mall_glass_light': ('Mall pale reflected glazing', '799f9f', .29, .20),
    'mall_frame': ('Mall aluminium mullions', 'aebdb8', .40, .35),
    'mall_dark': ('Mall recessed shadow joints', '3e5858', .54, .17),
    'mall_bronze': ('MixC bronze entrance surrounds', 'ad8060', .47, .30),
    'mall_gold': ('Mall warm gold lettering', 'dab76b', .40, .28),
    'mall_roof': ('Mall warm grey roof', 'c1c7bb', .85, .02),
    'mall_paving': ('Mall plaza paving', 'cbd0c0', .91, .00),
    'mall_leaf': ('Mall planted terraces', '658966', .94, .00),
}
MATERIAL_KEYS = list(MATERIALS)


def contains(ring, x, y):
    inside = False
    for a, b in zip(ring, ring[1:]+ring[:1]):
        if (a[1] > y) != (b[1] > y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            inside = not inside
    return inside


def inside_site(identity, x, y):
    return contains(SITES[identity]['site'], x, y)


def intersects_site(identity, ring, x, y):
    """Remove intersecting infill, including long blocks centred off the site."""
    local = [(a-x, b-y) for a, b in ring]
    site = SITES[identity]['site']
    if any(contains(site, *p) for p in local) or any(contains(local, *p) for p in site):
        return True

    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])

    for a, b in zip(local, local[1:]+local[:1]):
        for c, d in zip(site, site[1:]+site[:1]):
            if cross(a,b,c)*cross(a,b,d) < 0 and cross(c,d,a)*cross(c,d,b) < 0:
                return True
    return False


def support_level(identity, x, y, ground_bounds):
    # Sample the interior too: a coarse DEM triangle can crest inside the site.
    ring = SITES[identity]['site']
    points = list(ring)
    for a, b in zip(ring, ring[1:]+ring[:1]):
        steps = max(1, math.ceil(math.dist(a,b)/.1))
        points.extend((a[0]+(b[0]-a[0])*i/steps, a[1]+(b[1]-a[1])*i/steps) for i in range(steps))
    for i in range(math.floor(min(p[0] for p in ring)*10), math.ceil(max(p[0] for p in ring)*10)+1):
        for j in range(math.floor(min(p[1] for p in ring)*10), math.ceil(max(p[1] for p in ring)*10)+1):
            if contains(ring,i/10,j/10): points.append((i/10,j/10))
    return max(ground_bounds(x+u,y+v)[1] for u,v in points)+.025


class MallMesh:
    def __init__(self, batch, x, y, z):
        self.b, self.x, self.y, self.z = batch, x, y, z

    def p(self, u, v, h):
        return self.x+u, self.y+v, self.z+h

    def face(self, points, key):
        self.b.face([self.p(*q) for q in points], key)

    def box(self, u, v, h, w, d, rise, key='mall_stone', angle=0):
        self.b.box(*self.p(u,v,h), w,d,rise,key,angle=angle)

    def beam(self, a, b, r=.003, key='mall_frame'):
        self.b.beam(self.p(*a),self.p(*b),r,key)

    def prism(self, ring, bottom, top, key, roof=None):
        # Use this for convex architectural pieces. The mapped concave MixC
        # roof is triangulated separately by the offline preparation script.
        for a, b in zip(ring,ring[1:]+ring[:1]):
            self.face([(*a,bottom),(*b,bottom),(*b,top),(*a,top)],key)
        self.face([(*p,top) for p in ring],roof or key)

    def edge(self, a, b, bottom, top, key, inset=0):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        nx,ny=dy/length,-dx/length
        aa=(a[0]+nx*inset,a[1]+ny*inset)
        bb=(b[0]+nx*inset,b[1]+ny*inset)
        self.face([(*aa,bottom),(*bb,bottom),(*bb,top),(*aa,top)],key)

    def sign(self, text, cx, cy, h, size, north=False):
        # Stroke meshes stay editable and need no font installation or textures.
        glyphs = {
            'H': [[(0,0),(0,1)],[(.7,0),(.7,1)],[(0,.5),(.7,.5)]],
            'A': [[(0,0),(.35,1),(.7,0)],[(.16,.42),(.54,.42)]],
            'N': [[(0,0),(0,1),(.7,0),(.7,1)]],
            'G': [[(.7,.83),(.52,1),(.15,1),(0,.8),(0,.2),(.15,0),(.7,0),(.7,.5),(.4,.5)]],
            'Y': [[(0,1),(.35,.5),(.7,1)],[(.35,.5),(.35,0)]],
            'M': [[(0,0),(0,1),(.35,.5),(.7,1),(.7,0)]],
            'I': [[(.35,0),(.35,1)]],
            'X': [[(0,0),(.7,1)],[(0,1),(.7,0)]],
            'C': [[(.7,.85),(.55,1),(.15,1),(0,.8),(0,.2),(.15,0),(.55,0),(.7,.15)]],
            '万': [[(0,.9),(.9,.9)],[(.42,.9),(.38,.48),(.18,.1)],[(.4,.64),(.83,.64),(.72,.07),(.54,.07)]],
            '象': [[(.4,1),(.18,.78),(.78,.78),(.88,.53),(.22,.53),(.18,.78)],[(.5,.78),(.5,.53),(.73,.28),(.69,.02),(.48,.02)],[(.51,.5),(.09,.32)],[(.64,.37),(.12,.12)],[(.71,.3),(.92,.08)],[(.74,.4),(.96,.54)]],
            '城': [[(.16,.9),(.16,.2)],[(0,.6),(.33,.6)],[(0,.13),(.35,.27)],[(.42,.03),(.45,.77),(.97,.77)],[(.45,.53),(.65,.53),(.61,.19),(.5,.18)],[(.71,1),(.76,.32),(.96,.04),(.97,.25)],[(.91,.62),(.71,.17)],[(.85,.98),(.94,.86)]],
            '航': [[(.22,1),(.12,.77),(.12,.03)],[(.12,.78),(.4,.78),(.4,.03),(.3,.03)],[(.01,.39),(.48,.49)],[(.23,.65),(.29,.53)],[(.23,.31),(.28,.19)],[(.66,1),(.73,.87)],[(.5,.79),(.99,.79)],[(.48,.04),(.57,.2),(.57,.59),(.84,.59),(.84,.1),(.93,.04),(1,.1)]],
            '洋': [[(.05,.95),(.18,.83)],[(.02,.68),(.15,.55)],[(.04,.08),(.19,.36)],[(.43,.97),(.51,.82)],[(.8,.97),(.7,.81)],[(.32,.77),(.93,.77)],[(.35,.53),(.91,.53)],[(.27,.29),(.98,.29)],[(.63,.77),(.63,.02)]],
        }
        width=len(text)*size*1.04
        for i,char in enumerate(text):
            for line in glyphs[char]:
                for a,b in zip(line,line[1:]):
                    def point(q):
                        u=-width/2+i*size*1.04+q[0]*size
                        return cx+(-u if north else u),cy,h+q[1]*size
                    self.beam(point(a),point(b),size*.034,'mall_gold')


def rounded_ring(cx,cy,w,d,r,segments=6):
    points=[]
    for xx,yy,start in [(w/2-r,d/2-r,0),(-w/2+r,d/2-r,90),
                         (-w/2+r,-d/2+r,180),(w/2-r,-d/2+r,270)]:
        for i in range(segments+1):
            a=math.radians(start+i*90/segments)
            points.append((cx+xx+r*math.cos(a),cy+yy+r*math.sin(a)))
    return points


def foundation(m,identity,ground_bounds):
    data=SITES[identity];ring=data['site']
    for tri in data['triangles']:
        m.face([(*ring[i],0) for i in tri],'mall_paving')
    for a,b in zip(ring,ring[1:]+ring[:1]):
        steps=max(1,math.ceil(math.dist(a,b)/.08))
        for i in range(steps):
            p=[(a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t) for t in [i/steps,(i+1)/steps]]
            levels=[ground_bounds(m.x+u,m.y+v)[0]-m.z-.018 for u,v in p]
            m.face([(*p[0],levels[0]),(*p[1],levels[1]),(*p[1],0),(*p[0],0)],'mall_paving')


def tower(m,ring,index):
    xs,ys=zip(*ring);cx,cy=(min(xs)+max(xs))/2,(min(ys)+max(ys))/2
    w,d=max(xs)-min(xs)-.012,max(ys)-min(ys)-.012
    perimeter=rounded_ring(cx,cy,w,d,min(w,d)*.28)
    bottom=.49; top=1.86 if index<2 else 1.66
    m.prism(perimeter,bottom,top,'mall_glass','mall_roof')
    for floor in range(1,29):
        h=bottom+(top-bottom)*floor/29
        for a,b in zip(perimeter,perimeter[1:]+perimeter[:1]):
            m.edge(a,b,h,h+.007,'mall_frame',.002)
    for a,b in zip(perimeter,perimeter[1:]+perimeter[:1]):
        count=max(1,math.ceil(math.dist(a,b)/.046))
        for i in range(count):
            u=a[0]+(b[0]-a[0])*i/count;v=a[1]+(b[1]-a[1])*i/count
            m.beam((u,v,bottom),(u,v,top),.0023)
    # A shallow sloping silver crown, raised on the north edge like the photos.
    inner=[(cx+(u-cx)*.88,cy+(v-cy)*.88) for u,v in perimeter]
    outer=[(u,v,top+.025+.065*(v-cy)/d) for u,v in perimeter]
    for i in range(len(perimeter)):
        j=(i+1)%len(perimeter)
        m.face([(*perimeter[i],top),(*perimeter[j],top),outer[j],outer[i]],'mall_silver')
        m.face([outer[i],outer[j],(*inner[j],top+.005),(*inner[i],top+.005)],'mall_silver')
    m.box(cx,cy,top,.12,.11,.048,'mall_dark')


def build_hangyang(m):
    # Rounded western bow, long southern hull and the eastern glass stern.
    corners=rounded_ring(-.025,.06,2.82,.96,.16,10)
    outline=[]
    for a,b in zip(corners,corners[1:]+corners[:1]):
        n=max(1,math.ceil(math.dist(a,b)/.035))
        outline.extend((a[0]+(b[0]-a[0])*i/n,a[1]+(b[1]-a[1])*i/n) for i in range(n))
    m.face([(*p,.51) for p in outline],'mall_roof')
    for a,b in zip(outline,outline[1:]+outline[:1]):
        count=max(1,math.ceil(math.dist(a,b)/.06))
        for i in range(count):
            u=a[0]+(b[0]-a[0])*i/count;v=a[1]+(b[1]-a[1])*i/count
            m.beam((u,v,.025),(u,v,.24),.0025)
        m.edge(a,b,.132,.14,'mall_frame',.004)
        # Scalloped lower edge lifts over the central entrance and west bow.
        def lower(p):
            return .225+.06*math.exp(-((p[0]+.1)/.3)**2)
        aa,bb=lower(a),lower(b)
        m.face([(*a,.012),(*b,.012),(*b,bb),(*a,aa)],'mall_glass')
        m.face([(*a,aa),(*b,bb),(*b,.51),(*a,.51)],'mall_silver')
        m.beam((*a,aa),(*b,bb),.0035)
        for h in [.255,.285,.315,.345,.375,.405,.435,.465,.505]:
            if h>max(aa,bb): m.edge(a,b,h,h+.006,'mall_frame',.005)
    # Folded blue-glass panels at the eastern tail.
    for i in range(80):
        u=-1.26+i*2.48/80;v=-.426
        uu=u+2.48/80
        if u>.78:
            m.face([(u,v-.008,.045),(uu,v-.02,.045),(uu,v-.02,.255),(u,v-.008,.255)],
                   'mall_glass_light' if i%2 else 'mall_glass')
    # A wave canopy of diamond panels over the main southern doors.
    for i in range(20):
        u=-.65+i*.06;uu=u+.06
        def roof(a,v): return .205+.055*math.cos((a+.05)*math.pi/.66)+.018*v
        a,b,c,d=(u,-.57,roof(u,0)),(uu,-.57,roof(uu,0)),(uu,-.423,roof(uu,1)),(u,-.423,roof(u,1))
        m.face([a,b,c,d],'mall_glass_light')
        m.beam(a,c,.0025);m.beam(b,d,.0025);m.beam(a,b,.003)
    for u in [-.58,-.28,.02,.32,.5]:
        m.beam((u,-.55,.01),(u,-.55,.215),.005)
    m.sign('HANGYANG',-.16,-.435,.372,.075)
    m.sign('航洋城',.78,-.439,.385,.064)
    # Atrium skylights and service roof louvres are visible from atlas cameras.
    for u in [-.48,.42]:
        m.box(u,.035,.505,.42,.20,.035,'mall_frame')
        for j in range(8):
            m.box(u-.18+j*.052,.035,.54,.043,.184,.008,'mall_glass_light')
    for index,t in enumerate(SITES['hangyang']['towers']): tower(m,t['ring'],index)
    for u in [-1.12,-.78,.77,1.08]:
        m.box(u,-.566,.004,.19,.085,.038,'mall_stone')
        m.box(u,-.566,.042,.17,.072,.022,'mall_leaf')
    for i in range(23):
        m.box(-1.35+i*.12,-.605,.002,.003,.12,.002,'mall_roof')


def build_mixc(m):
    data=SITES['mixc'];ring=data['site'];top=.635
    # Exact mapped concave plan; cap via earcut avoids filling the inner curve.
    for tri in data['triangles']:
        m.face([(*ring[i],top) for i in tri],'mall_roof')
    for index,(a,b) in enumerate(zip(ring,ring[1:]+ring[:1])):
        # The mapped NW projection is the main entrance, including its returns.
        if index in {1,2,3}:
            continue
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        count=max(1,math.ceil(length/.055))
        m.edge(a,b,.012,top,'mall_stone')
        m.edge(a,b,.026,.145,'mall_glass',.002)
        m.edge(a,b,.23,.285,'mall_glass_light',.002)
        m.edge(a,b,.43,.478,'mall_glass',.002)
        for h in [.15,.215,.295,.365,.425,.488,.55,.618]:
            m.edge(a,b,h,h+.008,'mall_frame',.005)
        for i in range(count):
            u=a[0]+dx*i/count;v=a[1]+dy*i/count
            nx,ny=dy/length,-dx/length
            m.beam((u+nx*.004,v+ny*.004,.018),(u+nx*.004,v+ny*.004,top),.0018,'mall_frame')
        m.beam((*a,top+.008),(*b,top+.008),.008,'mall_stone')
    # Main entrance occupies the diagonal NW corner, not the long north wall.
    # Local +u follows the front edge and +v points into the mapped footprint.
    a,b=ring[2],ring[3]
    width=math.dist(a,b)
    tx,ty=(b[0]-a[0])/width,(b[1]-a[1])/width
    ox,oy=(a[0]+b[0])/2,(a[1]+b[1])/2
    class CornerMesh(MallMesh):
        def p(self,u,v,h):
            return m.p(ox+tx*u-ty*v,oy+ty*u+tx*v,h)
        def box(self,u,v,h,w,d,rise,key='mall_stone',angle=0):
            self.b.box(*self.p(u,v,h),w,d,rise,key,angle=math.atan2(ty,tx)+angle)
    entry=CornerMesh(m.b,0,0,0)
    half=width/2
    # Glass returns connect the recessed entrance to both adjoining elevations.
    for start,end in [(ring[1],ring[2]),(ring[3],ring[4])]:
        m.edge(start,end,.015,top,'mall_glass',-.002)
        for h in [.145,.285,.425,.56]:
            m.edge(start,end,h,h+.006,'mall_frame',-.001)
    entry.box(0,.051,.015,width-.024,.018,.594,'mall_glass')
    for u in [-half+.011,half-.011]:
        entry.box(u,.040,.012,.022,.066,.641,'mall_bronze')
    entry.box(0,.040,.625,width,.066,.033,'mall_bronze')
    # Continuous glazing and a paired bank of actual ground-level doors.
    for i in range(7):
        entry.box(-half+.030+i*(width-.060)/6,.037,.022,.003,.006,.58,'mall_frame')
    for h in [.145,.285,.425,.558,.607]:
        entry.box(0,.037,h,width-.042,.006,.004,'mall_frame')
    for u in [-.075,-.025,.025,.075]:
        entry.box(u,.028,.015,.046,.012,.115,'mall_glass_light')
        entry.box(u+.014,.019,.063,.002,.006,.025,'mall_gold')
    entry.box(0,.066,.152,width-.018,.139,.012,'mall_bronze')
    for i in range(7):
        entry.box(-half+.028+i*(width-.056)/6,.061,.165,.036,.124,.004,'mall_glass_light')
    entry.sign('万象城',0,.004,.558,.060)
    entry.sign('MIXC',0,-.006,.184,.048)
    # Subtle secondary doors on the west elevation retain the continuous facade.
    for v in [-.53,-.47,-.41]:
        m.box(-1.009,v,.022,.012,.051,.106,'mall_glass_light')
    # North-side shop panels remain restrained and texture-free.
    for i,u in enumerate([-.22,.94,1.34]):
        m.box(u,.801,.315,.30,.018,.255,'mall_bronze' if i==0 else 'mall_dark')
        for j in range(9): m.box(u-.135+j*.034,.814,.323,.006,.006,.236,'mall_gold')
    # Long glazed roof lanterns follow the two arms of the commercial plan.
    for cx,cy,w,d in [(.78,.52,1.22,.19),(-.60,-.25,.22,1.38)]:
        m.box(cx,cy,top+.012,w,d,.025,'mall_frame')
        n=max(5,math.ceil(max(w,d)/.07))
        for i in range(n):
            for side in [-1,1]:
                if w>d:
                    a=cx-w/2+i*w/n;b=a+w/n
                    ps=[(a,cy,top+.092),(b,cy,top+.092),(b,cy+side*d/2,top+.037),(a,cy+side*d/2,top+.037)]
                else:
                    a=cy-d/2+i*d/n;b=a+d/n
                    ps=[(cx,a,top+.092),(cx,b,top+.092),(cx+side*w/2,b,top+.037),(cx+side*w/2,a,top+.037)]
                # Wind the north/east facets outward as well as the south/west.
                normal=(ps[1][0]-ps[0][0])*(ps[2][1]-ps[0][1])-(ps[1][1]-ps[0][1])*(ps[2][0]-ps[0][0])
                m.face(ps if normal>0 else ps[::-1],'mall_glass_light')
                m.beam(ps[0],ps[3],.0025)
        for end in [-1,1]:
            if w>d:
                cap=[(cx+end*w/2,cy-d/2,top+.037),(cx+end*w/2,cy+d/2,top+.037),(cx+end*w/2,cy,top+.092)]
            else:
                cap=[(cx-w/2,cy+end*d/2,top+.037),(cx+w/2,cy+end*d/2,top+.037),(cx,cy+end*d/2,top+.092)]
            m.face(cap if (end>0)==(w>d) else cap[::-1],'mall_glass')
    for u,v in [(-.80,.43),(-.38,.37),(1.30,.59),(-.73,-1.02)]:
        m.box(u,v,top+.012,.14,.13,.055,'mall_frame')
        for j in range(5): m.box(u-.055+j*.027,v,top+.067,.01,.11,.007,'mall_dark')
    for u,v in [(-.35,.03),(-.25,.3),(1.54,.62)]:
        if contains(ring,u,v):
            m.box(u,v,top+.01,.12,.09,.018,'mall_stone')
            m.box(u,v,top+.028,.10,.072,.012,'mall_leaf')


def build_mall(batch,identity,x,y,z,ground_bounds):
    m=MallMesh(batch,x,y,z)
    foundation(m,identity,ground_bounds)
    (build_hangyang if identity=='hangyang' else build_mixc)(m)
