"""Shared, bounded geometry for broadleaf trees and forest crown clusters."""
import math

PHI = (1+math.sqrt(5))/2
CROWN_NORM = math.sqrt(1+PHI*PHI)
CROWN_POINTS = [(-1,PHI,0),(1,PHI,0),(-1,-PHI,0),(1,-PHI,0),
                (0,-1,PHI),(0,1,PHI),(0,-1,-PHI),(0,1,-PHI),
                (PHI,0,-1),(PHI,0,1),(-PHI,0,-1),(-PHI,0,1)]
CROWN_POINTS = [tuple(c/CROWN_NORM for c in point) for point in CROWN_POINTS]
CROWN_FACES = [(0,11,5),(0,5,1),(0,1,7),(0,7,10),(0,10,11),(1,5,9),
               (5,11,4),(11,10,2),(10,7,6),(7,1,8),(3,9,4),(3,4,2),
               (3,2,6),(3,6,8),(3,8,9),(4,9,5),(2,4,11),(6,2,10),
               (8,6,7),(9,8,1)]
COARSE_POINTS = [(1,0,0),(0,1,0),(-1,0,0),(0,-1,0),(0,0,.850651),(0,0,-.850651)]
COARSE_FACES = [(i,(i+1)%4,4) for i in range(4)]+[((i+1)%4,i,5) for i in range(4)]


def build_tree(batch, x, y, z, radius, color, lightweight=False, *,
               crown_height=.43, crown_rise=.33, trunk_radius=.028,
               trunk_height=.30, trunk_color='trunk'):
    """30 triangles in detail, 8 in smooth; retain the original trunk position."""
    angle = (x*17+y*23)%math.tau
    c, s = math.cos(angle), math.sin(angle)
    points = COARSE_POINTS if lightweight else CROWN_POINTS
    faces = COARSE_FACES if lightweight else CROWN_FACES
    vertices = [(x+radius*1.06*(a*c-b*s), y+radius*.91*(a*s+b*c),
                 z+crown_height+d*crown_rise) for a,b,d in points]
    for face in faces:
        batch.face([vertices[i] for i in face],color)
    if not lightweight:
        batch.cone(x,y,z,trunk_radius,trunk_radius*.714,trunk_height,trunk_color,4)
