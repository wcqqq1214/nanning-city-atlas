"""Low-poly landmark silhouettes; all dimensions are illustrative scene units."""
import math
from arts_landmark import build_arts
from sports_landmark import build_sports
from tingzi_landmark import build_tingzi
from station_landmarks import build_nanning_station, build_east_station


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


def build_extra_landmarks(landmark, ground=None):
    b,x,y,z=landmark('gxu')
    b.box(x,y,z,2.4,1.9,.12,'building','roof')
    hall(b,x,y,z+.12,1.9,1.35,.65,roof='bridge')
    for side in [-1,1]:
        hall(b,x+side*.95,y-.15,z+.12,.38,1.3,.43,roof='bridge')
    for i in range(4):
        b.box(x,y-1.03-i*.1,z,1.25,.1,.12-i*.025,'roof')
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
    build_east_station(b,x,y,z)
    b.finish()

    b,x,y,z=landmark('nanning-station')
    build_nanning_station(b,x,y,z)
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
    build_arts(b,x,y,z,ground=ground)
    b.finish()

    b,x,y,z=landmark('sports-center')
    build_sports(b,x,y,z,ground=ground)
    b.finish()

    b,x,y,z=landmark('tingzi')
    build_tingzi(b,x,y,z,ground=ground)
    b.finish()
