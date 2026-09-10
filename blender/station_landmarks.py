"""Recognizable station exteriors, fitted to mapped halls and railway platforms.

One scene unit is 100 m. Architectural heights retain the city's 1.55 display
exaggeration. Roof profiles, glazing, columns and signs are photograph-based
exterior interpretations; platform footprints and rail alignments come from OSM.
"""
import json
import math
from pathlib import Path

PLAN = json.loads((Path(__file__).resolve().parents[1]/'data/stations-plan.json').read_text())
STATIONS = PLAN['stations']
MATERIAL_KEYS = ['station_stone', 'station_paving', 'station_roof', 'station_soffit',
                 'station_glass', 'station_frame', 'station_rail', 'station_ballast',
                 'station_red', 'station_line', 'station_blue']


def local_xy(identity, x, y):
    a = STATIONS[identity]['angle']
    return x*math.cos(a)+y*math.sin(a), -x*math.sin(a)+y*math.cos(a)


def inside_site(identity, x, y, margin=0):
    u, v = local_xy(identity, x, y)
    ring = STATIONS[identity]['site']
    # Plans are convex, clockwise or counterclockwise. Keep the exact oriented
    # envelope instead of clearing a large axis-aligned city rectangle.
    signs = []
    for a, b in zip(ring, ring[1:]):
        cross = (b[0]-a[0])*(v-a[1])-(b[1]-a[1])*(u-a[0])
        signs.append(cross/math.dist(a, b))
    return min(signs) >= -margin or max(signs) <= margin


SITE_BOUNDS = {identity: (min(p[0] for p in data['site']), min(p[1] for p in data['site']),
                          max(p[0] for p in data['site']), max(p[1] for p in data['site']))
               for identity, data in STATIONS.items()}


def ground_blend(identity, x, y):
    """A graded station terrace with an apron wider than a mobile DEM triangle."""
    u, v = local_xy(identity, x, y)
    u0, v0, u1, v1 = SITE_BOUNDS[identity]
    distance = max(u0-u, u-u1, v0-v, v-v1, 0)
    t = max(0, min(1, (distance-2.8)/1.0))
    return t*t*(3-2*t)


class StationMesh:
    def __init__(self, batch, identity, x, y, z):
        self.b, self.data, self.x, self.y, self.z = batch, STATIONS[identity], x, y, z
        self.angle = self.data['angle']
        self.c, self.s = math.cos(self.angle), math.sin(self.angle)

    def p(self, u, v, h):
        return self.x+u*self.c-v*self.s, self.y+u*self.s+v*self.c, self.z+h

    def face(self, points, key):
        self.b.face([self.p(*q) for q in points], key)

    def box(self, u, v, h, w, d, rise, key='station_stone', roof=None):
        self.b.box(*self.p(u, v, h), w, d, rise, key, roof, self.angle)

    def beam(self, a, b, r=.003, key='station_frame'):
        self.b.beam(self.p(*a), self.p(*b), r, key)

    def column(self, u, v, h, r, rise, key='station_frame'):
        self.b.cone(*self.p(u, v, h), r, r, rise, key, 8)

    def slab(self, mesh, base, rise, key):
        points = mesh['points']
        for tri in mesh['triangles']:
            ps = [points[i] for i in tri]
            if (ps[1][0]-ps[0][0])*(ps[2][1]-ps[0][1])-(ps[1][1]-ps[0][1])*(ps[2][0]-ps[0][0]) < 0: ps.reverse()
            self.face([(u, v, base+rise) for u, v in ps], key)
        ring = mesh.get('ring', self.data['site'])
        for a, b in zip(ring, ring[1:]):
            self.face([(*a, base), (*b, base), (*b, base+rise), (*a, base+rise)], key)

    def glazing(self, left, right, v, bottom, top, bays, rows=3):
        # Separate opaque panes avoid transparency sorting across the station.
        self.face([(left,v,bottom),(right,v,bottom),(right,v,top),(left,v,top)], 'station_glass')
        for i in range(bays+1):
            u = left+(right-left)*i/bays
            self.box(u, v, bottom, .007, .009, top-bottom, 'station_frame')
        for i in range(rows+1):
            h = bottom+(top-bottom)*i/rows
            self.box((left+right)/2, v, h, right-left, .012, .006, 'station_frame')

    def sign(self, text, u, v, h, size, reverse=False):
        # Hand-drawn stroke geometry: no font download, texture or system font
        # is required to rebuild the four Chinese station-name characters.
        glyphs = {
            '南': [[(.12,.83),(.88,.83)],[(.5,.98),(.5,.66)],[(.18,0),(.18,.67),(.82,.67),(.82,0),(.67,0)],[(.3,.56),(.4,.43)],[(.7,.56),(.6,.43)],[(.3,.4),(.7,.4)],[(.29,.21),(.71,.21)],[(.5,.4),(.5,.02)]],
            '宁': [[(.47,1),(.56,.88)],[(.15,.64),(.15,.83),(.86,.83),(.86,.65)],[(.2,.55),(.8,.55)],[(.56,.55),(.56,.02),(.4,.02)]],
            '东': [[(.12,.77),(.9,.77)],[(.42,.98),(.23,.43),(.84,.43)],[(.55,.66),(.55,.02),(.39,.02)],[(.36,.29),(.12,.05)],[(.72,.29),(.91,.05)]],
            '站': [[(.14,.96),(.24,.83)],[(.04,.74),(.42,.74)],[(.1,.62),(.17,.22)],[(.36,.63),(.28,.21)],[(.04,.14),(.43,.23)],[(.63,.98),(.63,.48)],[(.63,.72),(.95,.72)],[(.5,.02),(.5,.48),(.9,.48),(.9,.02),(.5,.02)]]}
        advance = size*1.42
        start = u-(len(text)-1)*advance/2-size/2
        for i, char in enumerate(text):
            for stroke in glyphs[char]:
                for a, b in zip(stroke, stroke[1:]):
                    aa, bb = start+i*advance+a[0]*size, start+i*advance+b[0]*size
                    if reverse: aa, bb = 2*u-aa, 2*u-bb
                    self.beam((aa,v,h+a[1]*size),(bb,v,h+b[1]*size),size*.032,'station_red')


def build_platforms(m, east):
    track = .065 if east else .035
    # Railways owns continuous tracks through the station and both approaches.
    for platform in m.data['platforms']:
        m.slab(platform, .024, track+.020-.024, 'station_paving')
        ring = platform['ring']
        for a, b in zip(ring, ring[1:]):
            if math.dist(a, b) > .25:
                m.beam((*a,track+.022),(*b,track+.022),.003,'station_line')
        # A straight canopy follows the platform's dominant mapped direction.
        edges = [(math.dist(a,b),a,b) for a,b in zip(ring,ring[1:])]
        _, a, b = max(edges)
        dx,dy = b[0]-a[0],b[1]-a[1]
        length = math.hypot(dx,dy); dx,dy = dx/length,dy/length
        if dx < 0: dx,dy = -dx,-dy
        along = [p[0]*dx+p[1]*dy for p in ring]
        across = [-p[0]*dy+p[1]*dx for p in ring]
        lo,hi = min(along)+.045,max(along)-.045
        center,width = (min(across)+max(across))/2,max(across)-min(across)
        def q(t, w, z): return (t*dx-(center+w)*dy,t*dy+(center+w)*dx,z)
        roof = track+(.13 if east else .105)
        n = max(2,math.ceil((hi-lo)/.34))
        for j in range(n):
            ta,tb = lo+(hi-lo)*j/n,lo+(hi-lo)*(j+1)/n
            # East platform roofs stop at the elevated hall, never crossing
            # its glazing; old-station roofs remain behind the main frontage.
            mid = q((ta+tb)/2,0,0)
            if east and abs(mid[0]) < .90: continue
            for side in [-1,1]:
                a,b,c,d = q(ta,side*width*.48,roof+.015),q(tb,side*width*.48,roof+.015),q(tb,0,roof),q(ta,0,roof)
                m.face([a,b,c,d] if side<0 else [d,c,b,a],'station_roof')
                m.beam(a,b,.004,'station_frame')
            base,tip = q(ta,0,track+.02),q(ta,0,roof-.015)
            m.beam(base,tip,.007)
            for side in [-1,1]: m.beam(q(ta,0,roof-.05),q(ta,side*width*.44,roof),.004)
            m.beam(q(ta,-width*.46,roof),q(ta,width*.46,roof),.004)


def build_nanning_station(batch, x, y, z):
    m = StationMesh(batch,'nanning-station',x,y,z)
    m.slab(m.data['siteMesh'], -.012, .036, 'station_paving')
    build_platforms(m,False)
    m.box(0,0,.025,1.10,.55,.255,'station_stone')
    m.box(0,-.055,.065,1.07,.44,.255,'station_glass')
    for side in [-1,1]:
        m.box(side*.513,-.01,.04,.085,.54,.29)
        # Twin shallow barrel roofs visible behind the long entrance fascia.
        center=side*.282
        for j in range(16):
            a,b=-1+j/8,-1+(j+1)/8
            za,zb=.32+.055*math.sqrt(max(0,1-a*a)),.32+.055*math.sqrt(max(0,1-b*b))
            ua,ub=center+a*.255,center+b*.255
            m.face([(ua,-.278,za),(ub,-.278,zb),(ub,.286,zb),(ua,.286,za)],'station_roof')
            m.beam((ua,-.278,za+.001),(ua,.286,za+.001),.0016,'station_frame')
        for v in [-.28,-.14,0,.14,.285]:
            for j in range(12):
                a,b=-1+j/6,-1+(j+1)/6
                m.beam((center+a*.255,v,.322+.055*math.sqrt(max(0,1-a*a))),
                       (center+b*.255,v,.322+.055*math.sqrt(max(0,1-b*b))),.0025)
    for left,right in [(-.49,-.074),(.074,.49)]:
        m.glazing(left,right,-.286,.075,.315,10,4)
        for i in range(4):
            u=left+(right-left)*(i+.5)/4
            m.box(u,-.300,.025,.010,.025,.065)
            m.box(u,-.316,.028,.05,.006,.045,'station_glass')
    m.box(0,-.286,.108,.146,.035,.218)
    m.box(0,-.306,.121,.33,.038,.022,'station_roof')
    m.box(0,-.340,.118,.43,.105,.016,'station_roof')
    m.box(0,-.387,.137,.40,.012,.022,'station_red')
    for u in [-.19,-.095,.095,.19]: m.column(u,-.37,.040,.009,.079,'station_stone')
    for i in range(7): m.box(0,-.425+i*.011,.024,.40,.012,.004*(i+1),'station_paving')
    # Square clock: recessed dial, minute marks, and fixed illustrative hands.
    m.box(0,-.308,.239,.066,.008,.066,'station_frame')
    m.box(0,-.314,.243,.058,.004,.058,'station_line')
    for i in range(12):
        a=i/12*math.tau
        m.beam((math.sin(a)*.021,-.318,.272+math.cos(a)*.021),
               (math.sin(a)*.026,-.318,.272+math.cos(a)*.026),.0013,'station_rail')
    m.beam((0,-.319,.272),(-.012,-.319,.287),.0018,'station_rail')
    m.beam((0,-.319,.272),(.017,-.319,.281),.0012,'station_rail')
    m.sign('南宁站',0,-.279,.349,.070)
    # Small forecourt shelter, with repeated ribs and open sides.
    for j in range(12):
        a,b=-.40+j*.8/12,-.40+(j+1)*.8/12
        za,zb=.10+.018*(1-(a/.4)**2),.10+.018*(1-(b/.4)**2)
        m.face([(a,-.68,za),(b,-.68,zb),(b,-.51,zb),(a,-.51,za)],'station_blue')
        m.beam((a,-.68,za),(a,-.51,za),.0018)
    for u in [-.38,-.19,0,.19,.38]:
        for v in [-.66,-.53]: m.column(u,v,.025,.0035,.075)
    # Glazed rear footbridge ties the seven platforms to the historic hall.
    m.box(0,.88,.166,.11,1.14,.055,'station_glass','station_roof')
    for v in [.4,.65,.9,1.15,1.4]:
        m.box(0,v,.047,.016,.025,.119,'station_frame')
        m.box(0,v,.167,.12,.007,.055,'station_frame')


def build_east_station(batch, x, y, z):
    m = StationMesh(batch,'east-station',x,y,z)
    m.slab(m.data['siteMesh'], -.012, .04, 'station_paving')
    build_platforms(m,True)
    # The elevated concourse runs north/south across the east/west tracks.
    m.box(0,0,.198,1.72,4.06,.026,'station_stone')
    m.box(0,0,.228,1.66,3.92,.258,'station_glass','station_soffit')
    for side in [-1,1]:
        m.box(side*.848,0,.226,.027,3.93,.263,'station_frame')
        for i in range(35):
            v=-1.92+i*3.84/34
            m.box(side*.839,v,.233,.011,.012,.25,'station_frame')
        for h in [.235,.318,.402,.482]: m.box(side*.843,0,h,.014,3.9,.007,'station_frame')
    for side in [-1,1]:
        v=side*2.04
        m.box(0,v,.027,2.03,.31,.137,'station_stone')
        m.glazing(-.96,.96,side*2.202,.062,.158,32,2)
        # Raised drop-off deck, parapets and paired descending stair flights.
        m.box(0,side*2.32,.164,2.23,.29,.03,'station_stone','station_paving')
        m.box(0,side*2.449,.199,2.20,.011,.024,'station_frame')
        for u in [-.78,.78]:
            for i in range(13): m.box(u,side*(2.46+i*.012),.028,.13,.013,.164*(13-i)/13,'station_paving')
        m.glazing(-.91,.91,side*1.963,.225,.497,30,4)
        # The two gate piers and twelve branched side columns frame the hall.
        for u in [-.33,.33]:
            m.box(u,side*2.091,.194,.10,.09,.305)
            m.box(u,side*2.091,.48,.15,.13,.025,'station_roof')
        m.box(0,side*2.073,.492,.75,.13,.040,'station_roof')
        for sign in [-1,1]:
            for i in range(6):
                u=sign*(.455+i*.104)
                m.column(u,side*2.069,.198,.013,.205,'station_stone')
                for branch in [-1,1]:
                    m.beam((u,side*2.069,.385),(u+branch*.037,side*2.069,.51),.008,'station_stone')
        m.sign('南宁东站',0,side*2.265,.558,.076,reverse=side>0)
        # Diagonal steel soffit grid is visible through the open colonnade.
        for i in range(19):
            u=-.99+i*.11
            m.beam((u,side*1.97,.506),(u+.105,side*2.23,.526),.0022)
            m.beam((u+.105,side*1.97,.506),(u,side*2.23,.526),.0022)
    # Three nested, shallow roofs with raised eaves and narrow clerestories.
    # They replace the old six-wave silhouette; the centre is the tallest tier.
    for tier,(width,depth,base,rise) in enumerate([(2.20,4.51,.518,.07),(1.48,4.12,.615,.05),(.88,3.77,.695,.052)]):
        ridge=width*.31
        def roof_point(u,v):
            edge=max(0,(abs(u)-ridge)/(width/2-ridge))
            return base+rise*(1-edge)+.016*(abs(v)/(depth/2))**10+.008*(abs(u)/(width/2))**8
        us=[-width/2+(width*i/32) for i in range(33)]
        vs=[-depth/2+depth*i/8 for i in range(9)]
        for ua,ub in zip(us,us[1:]):
            for va,vb in zip(vs,vs[1:]):
                m.face([(ua,va,roof_point(ua,va)),(ub,va,roof_point(ub,va)),
                        (ub,vb,roof_point(ub,vb)),(ua,vb,roof_point(ua,vb))],'station_roof')
        for u in us[::2]:
            for va,vb in zip(vs,vs[1:]): m.beam((u,va,roof_point(u,va)+.002),(u,vb,roof_point(u,vb)+.002),.0015,'station_frame')
        for side in [-1,1]:
            v=side*depth/2
            for ua,ub in zip(us,us[1:]):
                ha,hb=roof_point(ua,v),roof_point(ub,v)
                m.face([(ua,v,ha-.013),(ub,v,hb-.013),(ub,v,hb),(ua,v,ha)],'station_soffit')
            u=side*width/2
            for va,vb in zip(vs,vs[1:]):
                ha,hb=roof_point(u,va),roof_point(u,vb)
                m.face([(u,va,base-.033),(u,vb,base-.033),(u,vb,hb),(u,va,ha)],'station_glass' if tier else 'station_soffit')
                m.beam((u,va,ha),(u,vb,hb),.004,'station_roof')
                if tier: m.box(u,va,base-.034,.006,.007,.04,'station_frame')
