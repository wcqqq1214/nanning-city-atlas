"""Distinct river bridges, fitted to paired OSM carriageways; units are 100 m.

Primary span lengths are retained. Vertical dimensions and fittings are display
approximations. Both quality profiles retain complete load-bearing structures.
"""
import bisect
import json
import math
from pathlib import Path

PLAN = json.loads((Path(__file__).resolve().parents[1]/'data/bridges-plan.json').read_text())
SPECS = {b['id']: b for b in PLAN['bridges']}
REPLACED_ROADS = {i for b in SPECS.values() for i in b['roadIndices']}
MATERIALS = {
    'rb_road':('River bridge asphalt','697b78',.92,0),
    'rb_stone':('River bridge warm concrete','d4d9ca',.83,0),
    'rb_white':('River bridge ivory towers','e9e9da',.66,.12),
    'rb_red':('River bridge vermilion steel','b8513d',.49,.3),
    'rb_gold':('River bridge pale gold steel','c5a56b',.5,.32),
    'rb_cable':('River bridge silver cables','b4c5bf',.42,.5),
    'rb_dark':('River bridge dark metal','526d69',.53,.4),
    'rb_line':('River bridge road markings','eee8ce',.85,0),
}
MATERIAL_KEYS = list(MATERIALS)


class Path:
    def __init__(self, points):
        self.points = points
        self.lengths = [0.]
        for a,c in zip(points,points[1:]): self.lengths.append(self.lengths[-1]+math.dist(a,c))
        self.total = self.lengths[-1]

    def at(self, s, offset=0, z=0):
        s=max(0,min(self.total,s))
        i=max(0,min(len(self.points)-2,bisect.bisect_right(self.lengths,s)-1))
        a,c=self.points[i:i+2]
        d=self.lengths[i+1]-self.lengths[i]
        t=(s-self.lengths[i])/d
        return (a[0]+(c[0]-a[0])*t-(c[1]-a[1])/d*offset,
                a[1]+(c[1]-a[1])*t+(c[0]-a[0])/d*offset,z)


class Bridge:
    def __init__(self, spec, ground, road_level, surface):
        self.spec, self.ground = spec, ground
        self.path=Path(spec['points'])
        self.start,self.end=spec['mainStart'],spec['mainEnd']
        self.width=spec['widthMeters']/200
        self.rise=spec['displayRise']
        self.kind=spec['kind']
        self.stations=[self.path.total*i/math.ceil(self.path.total/.06)
                       for i in range(math.ceil(self.path.total/.06)+1)]
        # A terrain-clearing longitudinal envelope avoids dips over the river and
        # keeps both rendered terrain profiles below the underside near the banks.
        main=max(1.18,max(surface(*self.path.at(s)[:2])+.15 for s in self.stations
                          if self.start <= s <= self.end))
        ends=[max(1.1,road_level(*self.path.at(s)[:2])) for s in [0,self.path.total]]
        self.levels=[]
        for s in self.stations:
            t=max(0,min(1,s/self.start)) if s<self.start else max(0,min(1,(self.path.total-s)/(self.path.total-self.end)))
            edge=ends[0 if s<self.start else 1]
            nominal=main if self.start<=s<=self.end else edge+(main-edge)*t*t*(3-2*t)
            self.levels.append(max(nominal,surface(*self.path.at(s)[:2])+.12))
        # Bound display grade in both directions, including high embankments.
        for indices in [range(1,len(self.levels)),range(len(self.levels)-2,-1,-1)]:
            for i in indices:
                j=i-1 if isinstance(indices,range) and indices.step>0 else i+1
                self.levels[i]=max(self.levels[i],self.levels[j]-.20*abs(self.stations[i]-self.stations[j]))
        self.supports=[self.start]
        for span in spec['spansMeters']: self.supports.append(self.supports[-1]+span/100)
        for a,c in [(0,self.start),(self.end,self.path.total)]:
            n=max(1,math.ceil((c-a)/.48))
            self.supports.extend(a+(c-a)*i/n for i in range(n+1))
        self.supports=sorted(set(round(s,7) for s in self.supports))

    def level(self,s):
        s=max(0,min(self.path.total,s))
        i=max(0,min(len(self.stations)-2,bisect.bisect_right(self.stations,s)-1))
        t=(s-self.stations[i])/(self.stations[i+1]-self.stations[i])
        return self.levels[i]*(1-t)+self.levels[i+1]*t

    def at(self,s,o=0,dz=0): return self.path.at(s,o,self.level(s)+dz)

    def depth(self,s):
        if self.kind!='girder' or not self.start<s<self.end: return .055
        supports=[self.start]
        for span in self.spec['spansMeters']: supports.append(supports[-1]+span/100)
        i=max(0,min(len(supports)-2,bisect.bisect_right(supports,s)-1))
        t=(s-supports[i])/(supports[i+1]-supports[i])
        return .055+.13*(abs(2*t-1)**2)

    def prism(self,b,s,o,w,d,z,h,key):
        corners=[self.path.at(s+ds,o+do,z+dz) for dz in [0,h]
                 for ds,do in [(-d/2,-w/2),(d/2,-w/2),(d/2,w/2),(-d/2,w/2)]]
        for ids in [(0,3,2,1),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(4,5,6,7)]:
            b.face([corners[i] for i in ids],key)

    def strip(self,b,s,t,a,c,dz,key):
        a,c=sorted((a,c))
        b.face([self.at(s,a,dz),self.at(t,a,dz),self.at(t,c,dz),self.at(s,c,dz)],key)


def build_structure(b, r):
    w,kind=r.width,r.kind
    # Chamfered box section, with separate footways and a central reservation.
    for s,t in zip(r.stations,r.stations[1:]):
        d,e=r.depth(s),r.depth(t)
        sections=[[(off,dz) for off,dz in [(-w,0),(w,0),(w,-.025),(w*.72,-dep),(-w*.72,-dep),(-w,-.025)]] for dep in [d,e]]
        for j in range(6):
            k=(j+1)%6
            b.face([r.at(s,*sections[0][j]),r.at(t,*sections[1][j]),r.at(t,*sections[1][k]),r.at(s,*sections[0][k])], 'rb_road' if j==0 else 'rb_stone')
        for side in [-1,1]:
            r.strip(b,s,t,side*w*.81,side*w*.99,.012,'rb_stone')
            b.beam(r.at(s,side*w,.025),r.at(t,side*w,.025),.008,'rb_stone')
        r.strip(b,s,t,-.009,.009,.009,'rb_stone')
    for s in [0,r.path.total]:
        r.prism(b,s,0,w*1.98,.018,r.level(s)-.06,.06,'rb_stone')
    # Navigation spans have only their specified structural supports; no generic
    # regularly spaced columns are placed inside suspended spans.
    for s in r.supports:
        bottom=min(r.ground(*r.path.at(s)[:2])-.025,.27)
        top=r.level(s)-r.depth(s)
        if top<bottom+.03: continue
        main=abs(s-r.start)<.001 or abs(s-r.end)<.001
        for side in [-1,1]:
            off=side*w*.57
            r.prism(b,s,off,.075 if main else .05,.095 if main else .065,bottom,top-bottom,'rb_stone')
            r.prism(b,s,off,.115,.14,bottom,.07,'rb_stone')
        r.prism(b,s,0,w*1.7,.10,top-.025,.032,'rb_stone')
    if kind in ['through-arch','twin-arch','deck-arch']:
        spans=r.spec['spansMeters']
        start=r.start
        for length in spans:
            end=start+length/100
            arch(b,r,start,end)
            start=end
    elif kind in ['stayed','harp','single-stayed']:
        stayed(b,r)
    elif kind in ['suspension','single-suspension']:
        suspension(b,r)


def arch(b,r,start,end):
    kind=r.kind
    key='rb_red' if kind=='through-arch' else ('rb_white' if kind=='twin-arch' else 'rb_stone')
    rise=r.rise if kind!='deck-arch' else .24
    foot=-.30 if kind=='through-arch' else (-.36 if kind=='deck-arch' else .025)
    # Arch ribs follow a straight support chord, independent of approach curves.
    def point(t,side,dz=0,do=0):
        a,c=r.at(start,side*r.width*.87),r.at(end,side*r.width*.87)
        off=r.path.at(start,do)
        center=r.path.at(start)
        return (a[0]+(c[0]-a[0])*t+off[0]-center[0],a[1]+(c[1]-a[1])*t+off[1]-center[1],a[2]+(c[2]-a[2])*t+foot+rise*4*t*(1-t)+dz)
    n=64 if kind=='through-arch' else 40
    for side in [-1,1]:
        if kind=='through-arch':
            # The arch springings sit below and outside the deck crosshead.
            # Inclined concrete seats connect them to the main pier columns.
            for s,t in [(start,0),(end,1)]:
                b.beam(r.at(s,side*r.width*.57,-.48),point(t,side),.045,'rb_stone')
        # Four chord members and diagonal lacing distinguish the steel tube truss.
        chords=[(-.022,-.027),(-.022,.027),(.022,-.027),(.022,.027)] if kind=='through-arch' else [(0,0)]
        for dz,do in chords:
            for i in range(n): b.beam(point(i/n,side,dz,do),point((i+1)/n,side,dz,do),.009 if len(chords)>1 else .024,key)
        for i in range(1,n):
            t=i/n
            if i%2==0:
                upper=point(t,side)
                lower=r.at(start+(end-start)*t,side*r.width*.80,-.005)
                if upper[2]>lower[2]+.025:
                    b.beam(lower,upper,.0035,'rb_cable')
                elif upper[2]<lower[2]-.025:
                    b.beam(upper,lower,.014,'rb_stone')
            if len(chords)>1:
                for do in [-.027,.027]:
                    b.beam(point((i-1)/n,side,-.022,do),point(i/n,side,.022,do),.0045,key)
                    b.beam(point(i/n,side,-.022,do),point(i/n,side,.022,do),.0045,key)
    if kind!='deck-arch':
        for i in range(5,n-4,6):
            t=i/n
            if point(t,1)[2]>r.level(start+(end-start)*t)+.20:
                b.beam(point(t,-1),point(t,1),.014,key)
                if kind=='through-arch': b.beam(point(t,-1),point((i+3)/n,1),.009,key)


def tower(b,r,s,kind):
    rise=r.rise
    key='rb_red' if kind=='suspension' else 'rb_white'
    if kind=='harp':
        # Solid tapered energy tower on the centre reservation.
        rings=[]
        for t in [0,.18,.48,.8,1.]:
            width=.055+.055*(1-t)
            rings.append([r.at(s+ds,do,rise*t-.10) for ds,do in [(-width,-width*.6),(width,-width*.6),(width,width*.6),(-width,width*.6)]])
        for a,c in zip(rings,rings[1:]):
            for j in range(4): b.face([a[j],c[j],c[(j+1)%4],a[(j+1)%4]],key)
        b.face(rings[-1],key)
        for side in [-1,1]: b.beam(r.at(s,side*.012,rise*.12),r.at(s,side*.012,rise*.91),.008,'rb_gold')
        return
    if kind in ['stayed','single-suspension']:
        # Curved transverse legs; Qingshan closes above an oval opening, while
        # Yinghua splits into two outward horns above the central cable saddle.
        for side in [-1,1]:
            for i in range(48):
                def p(t):
                    if kind=='stayed': offset=side*(r.width*.82*(1-t)+.18*math.sin(math.pi*t))
                    else: offset=side*(r.width*.94*(1-t)+.11*math.sin(math.pi*t))
                    return r.at(s,offset,rise*t-.13)
                b.beam(p(i/48),p((i+1)/48),.033 if kind=='stayed' else .037,key)
        if kind=='stayed':
            b.beam(r.at(s,0,rise-.13),r.at(s+.06,.10,rise+.08),.034,key)
            b.beam(r.at(s,0,rise-.13),r.at(s-.035,-.045,rise+.015),.029,key)
        else:
            for side in [-1,1]:
                b.beam(r.at(s,0,rise-.13),r.at(s,side*.095,rise+.12),.035,'rb_white')
    else:
        for side in [-1,1]:
            b.beam(r.at(s,side*r.width*.86,-.20),r.at(s,side*r.width*.77,rise),.035,key)
        for z in [.12,rise*.76,rise*.95]:
            b.beam(r.at(s,-r.width*.82,z),r.at(s,r.width*.82,z),.026,key)


def stayed(b,r):
    positions=[(r.start+r.end)/2] if r.kind=='single-stayed' else [r.start,r.end]
    for s in positions: tower(b,r,s,r.kind)
    for ti,s in enumerate(positions):
        for direction in [-1,1]:
            if len(positions)==1: reach=(r.end-r.start)/2
            elif (ti==0 and direction==1) or (ti==1 and direction==-1): reach=(r.end-r.start)/2-.045
            else: reach=min(1.7,s-.08 if direction<0 else r.path.total-s-.08)
            n=22 if r.kind=='single-stayed' else 20
            for i in range(1,n+1):
                f=i/n
                z=(r.rise-.16)*f if r.kind=='harp' else r.rise*(.52+.40*f)
                for side in [-1,1]:
                    o=side*.055 if r.kind=='harp' else side*r.width*.8
                    top=r.at(s,o if r.kind!='stayed' else side*.06,z)
                    low=r.at(s+direction*reach*f,o,.015)
                    b.beam(low,top,.0034,'rb_gold' if r.kind=='harp' else 'rb_cable')
                    b.beam(low,tuple(low[k]+(top[k]-low[k])*.025 for k in range(3)),.006,'rb_dark')


def suspension(b,r):
    single=r.kind=='single-suspension'
    for s in [r.start,r.end]: tower(b,r,s,r.kind)
    offsets=[0] if single else [-r.width*.79,r.width*.79]
    def cable(t,o):
        s=r.start+(r.end-r.start)*t
        a,c=r.at(r.start,o,r.rise-.13),r.at(r.end,o,r.rise-.13)
        return (a[0]+(c[0]-a[0])*t,a[1]+(c[1]-a[1])*t,a[2]+(c[2]-a[2])*t-r.rise*.66*4*t*(1-t))
    for o in offsets:
        for i in range(96): b.beam(cable(i/96,o),cable((i+1)/96,o),.013,'rb_red' if not single else 'rb_dark')
        for i in range(1,40):
            t=i/40;s=r.start+(r.end-r.start)*t
            for off in [-r.width*.79,r.width*.79] if single else [o]:
                b.beam(r.at(s,off,.01),cable(t,o),.0032,'rb_cable')
        for s,anchor,t in [(r.start,max(.08,r.start-1.25),0),(r.end,min(r.path.total-.08,r.end+1.25),1)]:
            top=cable(t,o)
            low=r.at(anchor,o,.045)
            b.beam(low,top,.013,'rb_dark' if single else 'rb_red')
            r.prism(b,anchor,o,.13,.24,r.level(anchor)-.13,.21,'rb_stone')


def build_details(b,r,lightweight=False):
    w=r.width
    n=math.ceil(r.path.total/(.14 if lightweight else .08))
    for i in range(n):
        s,t=r.path.total*i/n,r.path.total*(i+1)/n
        for side in [-1,1]:
            b.beam(r.at(s,side*w,.050),r.at(t,side*w,.050),.0027,'rb_dark')
            b.beam(r.at(s,side*w,.016),r.at(s,side*w,.055),.003,'rb_stone')
            if not lightweight: b.beam(r.at(s,side*w,.034),r.at(t,side*w,.034),.002,'rb_cable')
            r.strip(b,s,t,side*w*.78,side*w*.795,.004,'rb_line')
        if i%2==0:
            for o in [-w*.52,-w*.27,w*.27,w*.52]: r.strip(b,s,min(t,s+.04),o-.0016,o+.0016,.004,'rb_line')
    for s in r.supports:
        r.strip(b,max(0,s-.003),min(r.path.total,s+.003),-w,w,.016,'rb_dark')
    if not lightweight:
        count=max(1,math.floor(r.path.total/.38))
        for i in range(1,count):
            s=r.path.total*i/count
            for side in [-1,1]:
                b.beam(r.at(s,side*w*.92,.025),r.at(s,side*w*.92,.14),.0025,'rb_dark')
                b.beam(r.at(s,side*w*.92,.14),r.at(s,side*w*.68,.16),.0025,'rb_dark')
                b.beam(r.at(s,side*w*.68,.16),r.at(s+.017,side*w*.68,.16),.005,'rb_line')
