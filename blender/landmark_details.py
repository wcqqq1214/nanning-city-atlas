"""Recognizable near-view structures, deliberately simplified rather than surveyed."""
import math


def steps(b, x, y, z, width, count=6, run=.1, rise=.035):
    for i in range(count):
        b.box(x, y-i*run, z, width, run+.01, (count-i)*rise, 'roof')


def build_expo(b, x, y, z):
    b.box(x, y, z, 3.6, 3.0, .14, 'building', 'roof')
    for side in [-1, 1]:
        b.box(x+side*1.25, y+.42, z+.14, .95, 1.65, .43, 'building', 'roof')
        for j in range(9):
            b.box(x+side*1.25, y-.35+j*.18, z+.58, 1.01, .035, .045, 'roof')
    b.cone(x, y-.15, z+.14, .8, .8, .61, 'landmark', 48)
    for i in range(32):
        a=i/32*math.tau
        b.beam((x+math.cos(a)*.805,y-.15+math.sin(a)*.805,z+.2),
               (x+math.cos(a)*.805,y-.15+math.sin(a)*.805,z+.75), .014, 'roof')
    # Curved, folded petals have depth and radial ribs, rather than flat triangles.
    for i in range(12):
        angle=i/12*math.tau
        for j in range(10):
            points=[]
            for t,side in [(j/10,-1),((j+1)/10,-1),((j+1)/10,1),(j/10,1)]:
                radius=.13+t*1.04
                aa=angle+side*(.065+.13*math.sin(t*math.pi))
                zz=z+.70+1.08*(1-t)**.7+.11*math.sin(t*math.pi)
                points.append((x+math.cos(aa)*radius,y-.15+math.sin(aa)*radius,zz))
            b.face(points, 'roof')
            t,u=j/10,(j+1)/10
            def rib(v):
                r=.13+v*1.04
                return (x+math.cos(angle)*r,y-.15+math.sin(angle)*r,z+.73+1.08*(1-v)**.7+.11*math.sin(v*math.pi))
            b.beam(rib(t),rib(u),.016,'building')
    steps(b,x,y-1.52,z,2.8,8,.09,.027)
    for side in [-1,1]:
        for j in range(5):
            b.box(x+side*1.63,y-.7+j*.38,z+.15,.065,.065,.42,'roof')


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


def build_arts(b, x, y, z, shell):
    b.box(x,y,z,4.9,3.2,.16,'building','roof')
    # A broad canopy of parallel slats, with open passages and glazed entrances.
    for i in range(49):
        b.box(x-2.4+i*.1,y,z+.80,.038,3.06,.11,'roof')
    for side in [-1,1]:
        b.box(x,y+side*1.5,z+.79,4.84,.045,.14,'roof')
    for dx,dy,width,depth,hh in [(-1.48,0,1.45,2.0,1.56),(.05,.16,1.35,2.25,1.95),(1.46,-.12,1.1,1.65,1.35)]:
        b.box(x+dx,y+dy,z+.16,width*.78,depth*.78,.54,'landmark')
        shell(b,x+dx,y+dy,z+.27,width,depth,hh)
        for i in range(8):
            xx=x+dx-width*.37+i*width*.105
            b.box(xx,y+dy-depth*.40,z+.16,.015,.022,.54,'roof')
    steps(b,x,y-1.64,z,3.8,7,.09,.023)
    for side in [-1,1]:
        for j in range(8):
            b.box(x+side*2.28,y-1.15+j*.31,z+.17,.12,.065,.045,'accent')
