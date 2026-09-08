"""Low-poly landmark silhouettes; all dimensions are illustrative scene units."""
import math
from landmark_details import build_arts


def hip_roof(b, x, y, z, width, depth, rise, key='accent'):
    eaves = [(x-width/2,y-depth/2,z),(x+width/2,y-depth/2,z),
             (x+width/2,y+depth/2,z),(x-width/2,y+depth/2,z)]
    ridge = [(x-width*.28,y,z+rise),(x+width*.28,y,z+rise)]
    for points in [(eaves[0],eaves[1],ridge[1],ridge[0]),
                   (eaves[1],eaves[2],ridge[1]),
                   (eaves[2],eaves[3],ridge[0],ridge[1]),
                   (eaves[3],eaves[0],ridge[0])]:
        b.face(points,key)


def hall(b, x, y, z, width, depth, height, roof='accent'):
    b.box(x,y,z,width,depth,height,'building')
    hip_roof(b,x,y,z+height,width*1.18,depth*1.18,height*.5,roof)
    for i in range(7):
        b.box(x-width*.45+i*width*.15,y-depth*.6,z,.045,.045,height,'bridge')


def mountain_shell(b, x, y, z, width, depth, height):
    rings=[]
    for level, scale in [(0,.7),(.26,1),(.64,.94),(.90,.62),(1,.08)]:
        ring=[]
        for i in range(24):
            a=i/24*math.tau
            cx,sy=math.cos(a),math.sin(a)
            ring.append((x+math.copysign(abs(cx)**.72,cx)*width*scale/2,
                         y+math.copysign(abs(sy)**.72,sy)*depth*scale/2,z+level*height))
        rings.append(ring)
    for lower,upper in zip(rings,rings[1:]):
        for i in range(24):
            j=(i+1)%24
            b.face([lower[i],lower[j],upper[j],upper[i]],'roof' if i%2==0 else 'building')
    b.face(rings[-1],'roof')


def build_extra_landmarks(landmark):
    b,x,y,z=landmark('gxu')
    b.box(x,y,z,2.4,1.9,.12,'building','roof')
    hall(b,x,y,z+.12,1.9,1.35,.65,roof='bridge')
    for side in [-1,1]:
        hall(b,x+side*.95,y-.15,z+.12,.38,1.3,.43,roof='bridge')
    for i in range(4):
        b.box(x,y-1.03-i*.1,z,1.25,.1,.12-i*.025,'roof')
    b.finish()

    b,x,y,z=landmark('zhenning')
    for i in range(20):
        a,c=i/20*math.tau,(i+1)/20*math.tau
        outer=[(x+math.cos(t)*.7,y+math.sin(t)*.7) for t in [a,c]]
        inner=[(x+math.cos(t)*.49,y+math.sin(t)*.49) for t in [a,c]]
        b.face([(px,py,z) for px,py in outer]+[(px,py,z+.43) for px,py in reversed(outer)],'building')
        b.face([(px,py,z+.43) for px,py in [outer[0],outer[1],inner[1],inner[0]]],'roof')
        b.face([(px,py,z+.43) for px,py in inner]+[(px,py,z) for px,py in reversed(inner)],'building')
        if i%2==0:
            b.box(x+math.cos(a)*.61,y+math.sin(a)*.61,z+.43,.13,.13,.13,'roof')
    b.cone(x,y,z,.21,.17,.27,'landmark',12)
    b.box(x+.24,y,z+.28,.78,.11,.12,'landmark')
    b.box(x-.13,y,z+.12,.23,.27,.25,'landmark')
    b.finish()

    b,x,y,z=landmark('gx-museum')
    b.box(x,y,z,2.35,1.8,.15,'roof')
    b.box(x,y+.1,z+.15,2.15,1.3,.63,'building','roof')
    b.box(x,y+.1,z+.78,1.7,1.15,.22,'building','roof')
    b.box(x,y-.62,z+.65,2.3,.25,.08,'roof')
    for i in range(12):
        b.box(x-1+i*2/11,y-.65,z+.15,.055,.055,.5,'landmark')
    b.box(x,y-.7,z+.24,1.45,.02,.24,'landmark')
    for i in range(3):
        b.box(x,y-.91-i*.07,z,1.4,.07,.14-i*.04,'roof')
    b.finish()

    b,x,y,z=landmark('east-station')
    b.box(x,y,z,5.8,2.8,.16,'building','roof')
    b.box(x,y,z+.16,5.3,2.4,.53,'landmark')
    for i in range(6):
        sx=x-2.5+i
        for j in range(10):
            a,c=j/10,(j+1)/10
            za=z+.68+.25*math.sin(a*math.pi)
            zc=z+.68+.25*math.sin(c*math.pi)
            b.face([(sx+a-.5,y-1.37,za),(sx+c-.5,y-1.37,zc),
                    (sx+c-.5,y+1.37,zc),(sx+a-.5,y+1.37,za)],'roof')
    for i in range(9):
        py=y-1.25+i*.31
        b.box(x,py,z+.16,7,.10,.08,'building','roof')
        b.box(x,py-.08,z+.17,7,.018,.025,'landmark')
    b.box(x,y-1.42,z+.29,4.8,.08,.32,'landmark')
    b.finish()

    b,x,y,z=landmark('ethnic-museum')
    b.box(x,y,z,3.5,2.4,.15,'roof')
    for side in [-1,1]:
        b.box(x+side*1.12,y+.15,z+.15,1.15,1.5,.63,'building','roof',angle=-side*.16)
        b.box(x+side*1.34,y-.48,z+.75,.95,.6,.12,'roof',angle=side*.28)
    b.cone(x,y,z+.15,.77,.66,.64,'landmark',24)
    b.cone(x,y,z+.79,.66,.82,.23,'accent',24)
    b.cone(x,y,z+1.02,.83,.83,.10,'accent',24)
    b.cone(x,y,z+1.12,.17,.17,.03,'roof',12)
    for i in range(12):
        a=i/12*math.tau
        b.face([(x+math.cos(a)*.21,y+math.sin(a)*.21,z+1.135),
                (x+math.cos(a-.055)*.7,y+math.sin(a-.055)*.7,z+1.135),
                (x+math.cos(a+.055)*.7,y+math.sin(a+.055)*.7,z+1.135)],'roof')
    b.finish()

    b,x,y,z=landmark('confucius')
    b.box(x,y,z,2.7,3.4,.10,'roof')
    hall(b,x,y+.8,z+.10,1.9,.8,.65)
    hall(b,x,y-.8,z+.10,1.2,.5,.40)
    for side in [-1,1]:
        hall(b,x+side*1.07,y,z+.10,.35,2.65,.34)
    hall(b,x,y+1.4,z+.10,1.3,.4,.40)
    for side in [-1,1]:
        b.box(x+side*.44,y-1.4,z+.1,.07,.07,.66,'bridge')
    b.box(x,y-1.4,z+.64,1.2,.09,.09,'accent')
    b.finish()

    b,x,y,z=landmark('arts-center')
    build_arts(b,x,y,z,mountain_shell)
    b.finish()

    b,x,y,z=landmark('tingzi')
    b.box(x,y,z,3.1,1.6,.15,'building','roof')
    for level in range(3):
        size=1.25-level*.18
        hall(b,x,y,z+.15+level*.39,size,size*.7,.34,roof='bridge')
    for side in [-1,1]:
        hall(b,x+side*1.10,y,z+.15,.6,.7,.4,roof='bridge')
    b.box(x,y-.95,z+.08,2.5,.2,.12,'accent')
    for i in range(13):
        b.box(x-1.2+i*.2,y-1.03,z+.2,.025,.025,.17,'roof')
    b.finish()
