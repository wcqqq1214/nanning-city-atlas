"""Zhenning Battery: sandstone fort, open courtyard and present-day ring gallery.

An independently drawn exterior interpretation of the public photographs listed
in docs/ZHENNING_MODEL.md, not a measured survey. Dimensions below are approximate
metres; the small landmark is enlarged 2.4 times for the city diorama. Vertical
proportions also follow the city's 1.55 architectural height exaggeration.
"""
import math
import json
from functools import lru_cache
from pathlib import Path

DISPLAY_SCALE = 2.4
UNIT = DISPLAY_SCALE / 100
HEIGHT_SCALE = 1.55
MATERIAL_KEYS = ['zhenning_stone', 'zhenning_stone_light', 'zhenning_stone_dark',
                 'zhenning_mortar', 'zhenning_concrete', 'zhenning_paving',
                 'zhenning_iron', 'zhenning_bronze', 'zhenning_wood', 'zhenning_red']


@lru_cache(maxsize=8)
def terrain_patch(bounds, columns, rows, center):
    """A few complete mobile cells retain the fine DEM under the small fort."""
    catalog=json.loads((Path(__file__).resolve().parents[1]/'data/landmarks.json').read_text())
    place=next(p for p in catalog if p['id']=='zhenning')
    x=(place['lon']-center[0])*1113.2*math.cos(math.radians(center[1]))
    y=(place['lat']-center[1])*1113.2
    west,south,east,north=bounds
    col=lambda u:(u-west)/(east-west)*(columns-1)
    row=lambda v:(north-v)/(north-south)*(rows-1)
    return (max(0,math.floor(col(x-.60)/2)*2),max(0,math.floor(row(y+.75)/2)*2),
            min(columns-1,math.ceil(col(x+.60)/2)*2),min(rows-1,math.ceil(row(y-.75)/2)*2))


def terrace_level(x, y, ground):
    # Include the interior, both entrances, and both displayed DEM profiles.
    # The caller supplies the upper envelope of those profiles.
    return max(ground(x+u*UNIT, y+v*UNIT)
               for u in range(-21, 22, 3) for v in range(-27, 25, 3)) + .012


class FortMesh:
    def __init__(self, batch, x, y, z):
        self.b, self.x, self.y, self.z = batch, x, y, z

    def p(self, u, v, h):
        return self.x+u*UNIT, self.y+v*UNIT, self.z+h*UNIT*HEIGHT_SCALE

    def face(self, points, key):
        self.b.face([self.p(*p) for p in points], key)

    def box(self, u, v, h, width, depth, rise, key, angle=0):
        self.b.box(*self.p(u, v, h), width*UNIT, depth*UNIT,
                   rise*UNIT*HEIGHT_SCALE, key, angle=angle)

    def beam(self, a, b, radius=.045, key='zhenning_iron'):
        # Rails terminate in other rails, columns or slabs. Omit the hidden end
        # caps while keeping four solid sides, saving thousands of triangles.
        a,b=self.p(*a),self.p(*b)
        axis=[b[i]-a[i] for i in range(3)]
        length=math.sqrt(sum(v*v for v in axis))
        if length < 1e-8: return
        axis=[v/length for v in axis]
        side=[axis[1],-axis[0],0] if abs(axis[2])<.95 else [-axis[2],0,axis[0]]
        norm=math.sqrt(sum(v*v for v in side));side=[v/norm for v in side]
        up=[axis[1]*side[2]-axis[2]*side[1],axis[2]*side[0]-axis[0]*side[2],axis[0]*side[1]-axis[1]*side[0]]
        rings=[[tuple(p[i]+radius*UNIT*(side[i]*u+up[i]*v) for i in range(3))
                for u,v in [(-1,-1),(1,-1),(1,1),(-1,1)]] for p in [a,b]]
        for i in range(4):
            j=(i+1)%4
            self.b.face([rings[0][i],rings[0][j],rings[1][j],rings[1][i]],key)

    def cylinder(self, u, v, h, radius, rise, key, top=None, segments=16):
        self.b.cone(*self.p(u, v, h), radius*UNIT,
                    (radius if top is None else top)*UNIT,
                    rise*UNIT*HEIGHT_SCALE, key, segments)

    @staticmethod
    def polar(radius, a, h):
        return radius*math.cos(a), radius*math.sin(a), h

    def sector(self, inner, outer, bottom, top, a, b, key, ends=False):
        p = self.polar
        self.face([p(outer,a,bottom),p(outer,b,bottom),p(outer,b,top),p(outer,a,top)],key)
        self.face([p(inner,b,bottom),p(inner,a,bottom),p(inner,a,top),p(inner,b,top)],key)
        self.face([p(inner,a,top),p(outer,a,top),p(outer,b,top),p(inner,b,top)],key)
        self.face([p(inner,b,bottom),p(outer,b,bottom),p(outer,a,bottom),p(inner,a,bottom)],key)
        if ends:
            self.face([p(inner,a,bottom),p(outer,a,bottom),p(outer,a,top),p(inner,a,top)],key)
            self.face([p(outer,b,bottom),p(inner,b,bottom),p(inner,b,top),p(outer,b,top)],key)

    def ring(self, inner, outer, bottom, top, key, segments=80):
        for i in range(segments):
            self.sector(inner,outer,bottom,top,i/segments*math.tau,(i+1)/segments*math.tau,key)

    def circular_rail(self, radius, bottom, height, count, key='zhenning_iron', gates=False):
        for i in range(count):
            a,b = i/count*math.tau,(i+1)/count*math.tau
            # Four clear openings line up with the radial bridges.
            if gates and min(abs(math.sin((a+b)/2)),abs(math.cos((a+b)/2)))*radius < 1.02:
                continue
            self.beam(self.polar(radius,a,bottom),self.polar(radius,a,bottom+height),.04,key)
            for h in [bottom+height*.42,bottom+height]:
                self.beam(self.polar(radius,a,h),self.polar(radius,b,h),.035,key)


def arch_panel(m, q, width, spring, top, depth, key):
    """Solid sides and vaulted head, leaving an actual through opening."""
    r = width/2
    for side in [-1,1]:
        a,b = sorted([side*r,side*(r+1.25)])
        for d,reverse in [(0,False),(depth,True)]:
            points=[q(a,d,0),q(b,d,0),q(b,d,top),q(a,d,top)]
            m.face(list(reversed(points)) if reverse else points,key)
        # Vertical opening reveals, not a dark rectangle on a closed wall.
        points=[q(side*r,0,0),q(side*r,depth,0),q(side*r,depth,spring),q(side*r,0,spring)]
        m.face(points if side < 0 else list(reversed(points)),key)
    for i in range(16):
        a,b = i/16*math.pi,(i+1)/16*math.pi
        ua,ub = r*math.cos(a),r*math.cos(b)
        za,zb = spring+r*math.sin(a),spring+r*math.sin(b)
        for d,reverse in [(0,False),(depth,True)]:
            points=[q(ub,d,zb),q(ua,d,za),q(ua,d,top),q(ub,d,top)]
            m.face(list(reversed(points)) if reverse else points,key)
        m.face([q(ua,0,za),q(ub,0,zb),q(ub,depth,zb),q(ua,depth,za)],key)
        # Alternating sandstone voussoirs on the entrance face.
        a,b = a+.012,b-.012
        trim=.28
        m.face([q(r*math.cos(a),-.055,spring+r*math.sin(a)),
                q((r+trim)*math.cos(a),-.055,spring+(r+trim)*math.sin(a)),
                q((r+trim)*math.cos(b),-.055,spring+(r+trim)*math.sin(b)),
                q(r*math.cos(b),-.055,spring+r*math.sin(b))],
               'zhenning_stone_light' if i%3 else 'zhenning_stone_dark')


def inscription(m, q):
    # The historic plaque is read from right to left: 鎮寧砲臺. Strokes are
    # original geometry, so rebuilding does not depend on an installed font.
    glyphs = [
        [[(.1,.9),(.9,.9)],[(.5,1),(.5,.76)],[(.23,.78),(.77,.78),(.77,.60),(.23,.60),(.23,.78)],
         [(.08,.48),(.08,.58),(.92,.58),(.92,.48)],[(.3,.48),(.19,.29),(.77,.29)],[(.67,.44),(.83,.25)],
         [(.19,.17),(.81,.17)],[(.5,.29),(.5,.02)],[(.09,.02),(.91,.02)]],
        [[(.01,.87),(.41,.87)],[(.22,.87),(.05,.45)],[(.13,.08),(.13,.51),(.37,.51),(.37,.08),(.13,.08)],
         [(.59,1),(.45,.68)],[(.55,.84),(.95,.84),(.93,.28),(.80,.22)],
         [(.58,.64),(.8,.64),(.8,.43),(.58,.43)],[(.58,.64),(.58,.10),(.95,.10),(.98,.22)]],
        [[(.47,1),(.54,.91)],[(.1,.76),(.1,.89),(.9,.89),(.9,.76)],
         [(.28,.77),(.22,.65)],[(.41,.78),(.41,.62),(.69,.62),(.74,.71)],[(.55,.79),(.61,.71)],[(.82,.76),(.87,.65)],
         [(.22,.36),(.22,.55),(.78,.55),(.78,.36),(.22,.36)],[(.4,.55),(.4,.36)],[(.6,.55),(.6,.36)],
         [(.1,.24),(.9,.24)],[(.53,.24),(.53,.02),(.38,.02)]],
        [[(.21,1),(.05,.76)],[(.21,1),(.4,.8)],[(.08,.72),(.35,.72)],[(.05,.54),(.39,.54)],
         [(.23,.72),(.23,.07)],[(.07,.39),(.12,.2)],[(.37,.4),(.30,.24)],[(.04,.06),(.4,.17)],
         [(.45,.87),(.96,.87)],[(.68,1),(.68,.71)],[(.51,.2),(.51,.72),(.89,.72),(.89,.2)],
         [(.51,.58),(.89,.58)],[(.51,.45),(.89,.45)],[(.51,.32),(.89,.32)],[(.42,.19),(.98,.19)],
         [(.60,.16),(.43,.01)],[(.80,.16),(.98,.01)]]]
    for index,strokes in enumerate(glyphs):
        start=-2.2+index*1.12
        for stroke in strokes:
            for a,b in zip(stroke,stroke[1:]):
                au,av=start+a[0]*.87,4.36+a[1]*.76
                bu,bv=start+b[0]*.87,4.36+b[1]*.76
                length=math.hypot(bu-au,bv-av)
                du,dv=-(bv-av)/length*.025,(bu-au)/length*.025
                m.face([q(au-du,-.132,av-dv),q(bu-du,-.132,bv-dv),
                        q(bu+du,-.132,bv+dv),q(au+du,-.132,av+dv)],'zhenning_red')


def build_gate(m, north=False):
    side=1 if north else -1
    def q(u,d,h): return (-side*u,side*(19.42-d),h)
    arch_panel(m,q,3.1,2.05,4.5,7.5,'zhenning_stone')
    if north:
        return
    # Raised stone name plaque and curved crest above the south gate.
    m.box(0,-19.47,4.18,5.35,.35,1.18,'zhenning_stone_light')
    m.box(0,-19.67,4.31,4.92,.045,.85,'zhenning_paving')
    m.box(0,-19.73,5.21,5.50,.22,.12,'zhenning_concrete')
    m.box(0,-19.71,4.18,5.48,.18,.12,'zhenning_concrete')
    for u in [-2.67,2.67]: m.box(u,-19.70,4.18,.13,.16,1.1,'zhenning_concrete')
    inscription(m,lambda u,d,h:(u,-19.62+d,h))
    crest=[(-2.8,5.25),(2.8,5.25),(2.8,5.65)]
    crest += [(1.35*math.cos(i/16*math.pi),5.65+.78*math.sin(i/16*math.pi)) for i in range(17)]
    crest += [(-2.8,5.65)]
    for d,reverse in [(-19.55,False),(-19.20,True)]:
        points=[(u,d,h) for u,h in crest]
        m.face(list(reversed(points)) if reverse else points,'zhenning_stone')
    for a,b in zip(crest,crest[1:]+crest[:1]):
        if a==b: continue
        m.face([(a[0],-19.55,a[1]),(a[0],-19.20,a[1]),
                (b[0],-19.20,b[1]),(b[0],-19.55,b[1])],'zhenning_stone')
    star=[]
    for i in range(10):
        a=math.pi/2+i*math.pi/5;r=.62 if i%2==0 else .27
        star.append((r*math.cos(a),-19.59,5.78+r*math.sin(a)))
    for a,b in zip(star,star[1:]+star[:1]): m.face([(0,-19.61,5.78),a,b],'zhenning_red')
    # Exhibition plaques flank the open arch; no illegible faux paragraphs.
    for u,key in [(-3.2,'zhenning_red'),(3.2,'zhenning_wood')]:
        m.box(u,-19.20,1.5,1.05,.12,.64,key)


def build_barracks(m):
    for half in range(2):
        for i in range(10):
            a=-math.pi/2+.22+(i+.5)*(math.pi-.44)/10+half*math.pi
            nx,ny=-math.cos(a),-math.sin(a)
            tx,ty=-ny,nx
            def q(u,h,depth=0):
                return 12*math.cos(a)+tx*u+nx*depth,12*math.sin(a)+ty*u+ny*depth,h
            radius,spring=.58,2.2
            points=[q(-radius,.08,.03),q(radius,.08,.03)]
            points += [q(radius*math.cos(j/12*math.pi),spring+radius*math.sin(j/12*math.pi),.03) for j in range(13)]
            m.face(points,'zhenning_wood')
            for j in range(12):
                aa,bb=j/12*math.pi,(j+1)/12*math.pi
                m.face([q(radius*math.cos(aa),spring+radius*math.sin(aa),.055),
                        q((radius+.10)*math.cos(aa),spring+(radius+.10)*math.sin(aa),.055),
                        q((radius+.10)*math.cos(bb),spring+(radius+.10)*math.sin(bb),.055),
                        q(radius*math.cos(bb),spring+radius*math.sin(bb),.055)],'zhenning_concrete')
            for u in [-.63,0,.63]: m.beam(q(u,.08,.07),q(u,2.2,.07),.033,'zhenning_stone_light')
            for h in [.35,1.5,2.2]: m.beam(q(-.55,h,.07),q(.55,h,.07),.028,'zhenning_stone_light')


def build_cannon(m):
    """Static museum exterior only: silhouette, carriage, rail and access steps."""
    angle=math.radians(-28)
    c,s=math.cos(angle),math.sin(angle)
    def q(u,v,h): return u*c-v*s,u*s+v*c,5.12+h
    def box(u,v,h,w,d,rise,key='zhenning_iron'):
        m.box(*q(u,v,h),w,d,rise,key,angle)
    def beam(a,b,r=.04,key='zhenning_iron'): m.beam(q(*a),q(*b),r,key)
    def tube(start,end,r0,r1,key='zhenning_iron',segments=16,cap=True):
        # Local cannon axis is in the u/h plane; circular cross-sections remain
        # perpendicular to the sloping barrel instead of becoming boxes.
        du,dh=end[0]-start[0],end[2]-start[2]
        length=math.hypot(du,dh)
        rings=[]
        for point,r in [(start,r0),(end,r1)]:
            rings.append([q(point[0]-dh/length*r*math.sin(i/segments*math.tau),
                            point[1]+r*math.cos(i/segments*math.tau),
                            point[2]+du/length*r*math.sin(i/segments*math.tau)) for i in range(segments)])
        for i in range(segments):
            j=(i+1)%segments
            m.face([rings[0][i],rings[0][j],rings[1][j],rings[1][i]],key)
        if cap: m.face(list(reversed(rings[0])),key);m.face(rings[1],key)
    m.ring(2.24,2.34,5.10,5.16,'zhenning_iron',64)
    m.cylinder(*q(-.72,0,0),.60,.13,'zhenning_iron',segments=20)
    m.cylinder(*q(-.72,0,.13),.49,.83,'zhenning_iron',top=.33,segments=20)
    m.cylinder(*q(-.72,0,.96),.50,.12,'zhenning_iron',segments=20)
    box(.25,0,1.02,3.15,1.04,.53)
    box(.28,0,.92,3.3,1.15,.12,'zhenning_bronze')
    for side in [-1,1]:
        profile=[(-1.25,.52,1.56),(.95,.52,1.56),(.75,.52,1.98),(-.63,.52,2.30),(-1.25,.52,1.84)]
        points=[q(u,v*side,h) for u,v,h in profile]
        m.face(points if side>0 else list(reversed(points)),'zhenning_iron')
        beam((-1.21,side*.55,1.58),(.90,side*.55,1.58),.035,'zhenning_bronze')
        for i in range(10):
            # Flat octagonal rivet heads, kept below the mesh budget.
            u=-1.14+i*.30
            for h in [1.14,1.48]:
                points=[q(u+.035*math.cos(j/8*math.tau),side*.531,h+.035*math.sin(j/8*math.tau)) for j in range(8)]
                m.face(points if side<0 else list(reversed(points)),'zhenning_bronze')
    # Recognizable stepped taper; the muzzle is a shallow dark inset.
    sections=[((.68,0,1.90),(-.45,0,2.07),.29,.28),
              ((-.45,0,2.07),(-1.23,0,2.19),.255,.225),
              ((-1.23,0,2.19),(-2.45,0,2.38),.205,.145)]
    for a,b,r0,r1 in sections: tube(a,b,r0,r1)
    tube((-2.45,0,2.38),(-2.52,0,2.39),.165,.165,'zhenning_bronze')
    tube((-2.526,0,2.391),(-2.529,0,2.392),.104,.104,'zhenning_mortar',cap=True)
    box(1.80,0,1.0,1.2,1.7,.12)
    for side in [-1,1]:
        for u in [1.22,2.34]: beam((u,side*.80,1.08),(u,side*.80,2.03))
        beam((1.22,side*.80,2.03),(2.34,side*.80,2.03))
        beam((1.9,side*.6,0),(1.9,side*.6,.99),.08)
    # Slotted rear guard plate: separated strips leave three visible openings.
    box(2.15,0,1.10,.12,1.02,.70)
    box(2.15,0,2.20,.12,1.02,.12)
    for v in [-.46,-.15,.15,.46]: box(2.15,v,1.80,.12,.10,.40)
    for i in range(4): box(.95,-1.6+i*.24,.2+i*.2,.63,.27,.10)
    beam((.67,-1.6,.15),(.67,-.84,.9),.045)
    beam((1.24,-1.6,.15),(1.24,-.84,.9),.045)


def build_zhenning(batch, x, y, z, ground_bounds=None):
    m=FortMesh(batch,x,y,z)
    # A narrow stone apron ties the model to the hillside in both quality modes.
    m.cylinder(0,0,-.18,20.5,.18,'zhenning_paving',segments=80)
    for i in range(80):
        a,b=i/80*math.tau,(i+1)/80*math.tau
        ps=[m.p(*m.polar(20.5,t,0)) for t in [a,b]]
        lower=[(px,py,min(z-.006,(ground_bounds(px,py)[0] if ground_bounds else z)-.03)) for px,py,_ in ps]
        batch.face([lower[0],lower[1],ps[1],ps[0]],'zhenning_stone_dark')
    # South stairway and smaller north exit: broad landings, shallow treads.
    for north,count in [(False,14),(True,8)]:
        side=1 if north else -1
        width=6.2 if not north else 4.0
        tops=[]
        for i in range(count):
            v=side*(20.0+(count-i-.5)*.48)
            bounds=[ground_bounds(*m.p(u,v+dv,0)[:2]) if ground_bounds else (z-.08,z-.08)
                    for u in [-width/2,0,width/2] for dv in [-.25,0,.25]]
            bottom=(min(p[0] for p in bounds)-z-.01)/(UNIT*HEIGHT_SCALE)
            floor=(max(p[1] for p in bounds)-z)/(UNIT*HEIGHT_SCALE)
            top=max(.025-(count-1-i)*.11,floor+.04,(tops[-1][1]+.015) if tops else -100)
            m.box(0,v,bottom,width,.50,top-bottom,'zhenning_paving')
            tops.append((v,top))
        for u in [-width/2-.10,width/2+.10]:
            for a,b in zip(tops,tops[1:]):
                m.beam((u,a[0],a[1]+.20),(u,b[0],b[1]+.20),.12,'zhenning_stone_light')

    # Solid ring walls with paired openings aligned precisely to the tunnels.
    for inner,outer,key in [(18.65,19.5,'zhenning_stone'),(12,12.48,'zhenning_concrete')]:
        gap=math.asin(1.55/inner)
        for half in range(2):
            start=-math.pi/2+gap+half*math.pi
            span=math.pi-2*gap
            for i in range(40):
                m.sector(inner,outer,0,4.45,start+span*i/40,start+span*(i+1)/40,key,ends=i in [0,39])
    m.ring(12,19.5,4.45,4.65,'zhenning_paving')
    # Shallow staggered stone courses add joints without individual solid bricks.
    for row in range(7):
        for i in range(96):
            a=(i+(row%2)*.5)/96*math.tau+.002
            b=(i+1+(row%2)*.5)/96*math.tau-.002
            if abs(math.cos((a+b)/2))*19.5 < 2.85: continue
            h0,h1=row*.62+.025,(row+1)*.62-.025
            key=['zhenning_stone','zhenning_stone_light','zhenning_stone_dark'][(i*13+row*7)%7//3]
            m.face([m.polar(19.512,a,h0),m.polar(19.512,b,h0),m.polar(19.512,b,h1),m.polar(19.512,a,h1)],key)
    # The parapet has small rectangular embrasures, not invented battlements.
    m.ring(18.7,19.5,4.65,4.94,'zhenning_stone',80)
    for i in range(40):
        a=i/40*math.tau
        if abs(math.cos(a))*19.5 < 3: continue
        m.box(19.516*math.cos(a),19.516*math.sin(a),3.72,.12,.55,.36,'zhenning_mortar',a)
    build_gate(m)
    build_gate(m,True)
    build_barracks(m)

    # Open central platform, with four raised radial walkways and safety rails.
    m.cylinder(0,0,0,7.15,4.84,'zhenning_stone_dark',top=6.8,segments=64)
    m.cylinder(0,0,4.84,6.94,.20,'zhenning_paving',segments=64)
    for row in range(7):
        for i in range(48):
            a=(i+(row%2)*.5)/48*math.tau+.003
            b=(i+1+(row%2)*.5)/48*math.tau-.003
            lo,hi=row*.69+.03,(row+1)*.69-.03
            r0,r1=7.16-lo/4.84*.35,7.16-hi/4.84*.35
            m.face([m.polar(r0,a,lo),m.polar(r0,b,lo),m.polar(r1,b,hi),m.polar(r1,a,hi)],
                   'zhenning_stone' if (row+i)%4 else 'zhenning_stone_light')
    for angle in [0,math.pi/2,math.pi,math.pi*1.5]:
        c,s=math.cos(angle),math.sin(angle)
        def q(u,v,h): return u*c-v*s,u*s+v*c,h
        points=[q(6.6,-.88,5.04),q(12.55,-.88,4.65),q(12.55,.88,4.65),q(6.6,.88,5.04)]
        m.face(points,'zhenning_paving')
        for a,b in zip(points,points[1:]+points[:1]):
            m.face([(a[0],a[1],a[2]-.24),(b[0],b[1],b[2]-.24),b,a],'zhenning_concrete')
        for side in [-1,1]:
            m.beam(q(6.7,side*.86,6.02),q(12.4,side*.86,5.65),.035)
            for j in range(6):
                u=6.7+j*1.14;h=5.04-(u-6.6)/5.95*.39
                m.beam(q(u,side*.86,h),q(u,side*.86,h+.98),.035)
    m.circular_rail(6.68,5.04,1.0,64,gates=True)

    # The later gallery sits inside the rampart, set back from the outer wall.
    # Its narrow annular roof leaves the cannon visible from above.
    m.ring(9.8,12.0,4.45,4.65,'zhenning_paving',64)
    for i in range(20):
        a=(i+.5)/20*math.tau
        for radius in [10.15,12.6]:
            u,v,_=m.polar(radius,a,4.65)
            base=0 if radius<12 else 4.65
            m.cylinder(u,v,base,.22,7.35-base,'zhenning_concrete',segments=8)
    m.ring(9.8,13.1,7.35,7.57,'zhenning_concrete',64)
    m.circular_rail(9.92,7.57,.96,60)
    m.circular_rail(12.95,7.57,.96,60)
    # Three-stroke repeating rectangular lattice under the inner roof edge.
    for i in range(80):
        a,b=i/80*math.tau,(i+1)/80*math.tau
        m.beam(m.polar(9.92,a,6.66),m.polar(9.92,b,6.66),.045,'zhenning_concrete')
        m.beam(m.polar(9.92,a,6.66),m.polar(9.92,a,7.34),.045,'zhenning_concrete')
        mid=(a+b)/2
        m.beam(m.polar(9.92,mid,6.66),m.polar(9.92,mid,7.05),.04,'zhenning_concrete')
        m.beam(m.polar(9.92,mid,7.05),m.polar(9.92,b,7.05),.04,'zhenning_concrete')

    # Bell and two stele silhouettes sit at the base of the central platform.
    m.cylinder(-2,-8.4,0,.9,.25,'zhenning_paving',segments=16)
    m.cylinder(-2,-8.4,.25,.68,1.42,'zhenning_bronze',top=.47,segments=16)
    m.cylinder(-2,-8.4,1.67,.47,.28,'zhenning_bronze',top=.15,segments=16)
    for h,r in [(.31,.70),(.45,.67),(1.2,.56),(1.6,.49)]:
        # Exterior casting bands, deliberately omitting fine inscription text.
        m.cylinder(-2,-8.4,h,r,.055,'zhenning_bronze',segments=16)
    for u in [-3.4,1.0]:
        m.box(u,-7.6,0,1.1,.65,.28,'zhenning_stone_light')
        m.box(u,-7.6,.28,.86,.28,2.1,'zhenning_paving')
        m.box(u,-7.6,2.38,1.1,.50,.16,'zhenning_stone_dark')
    build_cannon(m)
