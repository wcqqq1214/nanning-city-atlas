"""Low-poly landmark silhouettes; all dimensions are illustrative scene units."""
import math
from arts_landmark import build_arts
from sports_landmark import build_sports
from tingzi_landmark import build_tingzi
from station_landmarks import build_nanning_station, build_east_station
from landmark_sites import SPECS as CALIBRATION
from confucius_landmark import build_confucius


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


def build_extra_landmarks(landmark, ground=None, ground_bounds=None, terrain_grid=None,
                          record_support=None):
    b,x,y,z=landmark('gxu')
    b.box(x,y,z,2.4,1.9,.12,'building','roof')
    hall(b,x,y,z+.12,1.9,1.35,.65,roof='bridge')
    for side in [-1,1]:
        hall(b,x+side*.95,y-.15,z+.12,.38,1.3,.43,roof='bridge')
    for i in range(4):
        b.box(x,y-1.03-i*.1,z,1.25,.1,.12-i*.025,'roof')
    b.finish()

    b,x,y,z=landmark('east-station')
    build_east_station(b,x,y,z)
    b.finish()

    b,x,y,z=landmark('nanning-station')
    build_nanning_station(b,x,y,z)
    b.finish()

    b,x,y,z=landmark('confucius')
    result=build_confucius(b,x,y,z,ground_bounds,terrain_grid)
    if record_support:record_support('confucius',result)
    b.finish()

    b,x,y,z=landmark('arts-center')
    spec=CALIBRATION['arts-center']
    z=build_arts(b,x,y,z,ground=ground,ground_bounds=ground_bounds,terrain_grid=terrain_grid,
                 display_scale=spec['displayScale'],hall_segments=spec['hallSegments'],hall_rings=spec['hallRings'])
    if record_support:record_support('arts-center',{'anchorLevel':z})
    b.finish()

    b,x,y,z=landmark('sports-center')
    build_sports(b,x,y,z,ground=ground)
    b.finish()

    b,x,y,z=landmark('tingzi')
    build_tingzi(b,x,y,z,ground=ground)
    b.finish()
