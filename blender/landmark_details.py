"""Recognizable near-view structures, deliberately simplified rather than surveyed."""
import math
from expo_landmark import build_expo


def build_bridge(b, roads, height):
    candidates=[r for r in roads if r['name']=='南宁大桥' and r['bridge']]
    assert candidates, 'Nanning Bridge requires its mapped centerline'
    pts=max(candidates,key=lambda r:sum(math.dist(a,c) for a,c in zip(r['points'],r['points'][1:])))['points']
    # Follow the mapped horizontal curve. The artistic arch spans the central 300 m.
    lengths=[0]
    for a,c in zip(pts,pts[1:]): lengths.append(lengths[-1]+math.dist(a,c))
    total=lengths[-1]
    deck=1.23
    def at(t, offset=0, level=deck):
        distance=max(0,min(1,t))*total
        index=next((i for i in range(len(lengths)-1) if lengths[i+1]>=distance),len(pts)-2)
        a,c=pts[index],pts[index+1]
        ll=lengths[index+1]-lengths[index]
        u=(distance-lengths[index])/max(ll,.001)
        dx,dy=(c[0]-a[0])/max(ll,.001),(c[1]-a[1])/max(ll,.001)
        return (a[0]+(c[0]-a[0])*u-dy*offset,a[1]+(c[1]-a[1])*u+dx*offset,level)
    for i in range(72):
        t,u=i/72,(i+1)/72
        b.face([at(t,-.25),at(u,-.25),at(u,.25),at(t,.25)],'building')
        for side in [-1,1]:
            b.beam(at(t,side*.28,deck+.13),at(u,side*.28,deck+.13),.017,'roof')
            b.beam(at(t,side*.25,deck-.04),at(u,side*.25,deck-.04),.065,'building')
        if i%2==0:
            b.beam(at(t,0,deck+.015),at(t+.006,0,deck+.015),.012,'accent')
    start=max(.08,.5-1.5/total); end=min(.92,.5+1.5/total)
    def arch(t,side):
        h=math.sin(t*math.pi)*1.60
        return at(start+(end-start)*t,side*(.27+h*.25),deck+h)
    for side in [-1,1]:
        for i in range(48):
            t,u=i/48,(i+1)/48
            b.beam(arch(t,side),arch(u,side),.067,'bridge')
            if i%3==0 and i:
                b.beam(at(start+(end-start)*t,side*.23,deck),arch(t,side),.011,'roof')
    for t in [0,.08,start,end,.92,1]:
        x,y,_=at(t)
        lower=min(deck-.12,max(.26,height(x,y)))
        b.box(x,y,lower,.18,.30,max(.08,deck-lower),'building')
    return at(.5)
