"""Source-sized Diwang massing: mapped podium, glass shaft and offset crown.

Total height is corroborated at 276 m. Intermediate heights, corner treatment,
facade divisions and helipad radius are photo-based estimates in the source
record. The builder is used by the isolated P4 preview before city integration.
"""
import json
import math
from pathlib import Path

from mathutils import Vector
from mathutils.geometry import tessellate_polygon

PLAN = json.loads((Path(__file__).resolve().parents[1] /
                   'data/landmark-calibration-plan.json').read_text())['sites']['diwang']


def build_diwang(batch, x, y, z, ground_bounds=None):
    ring = PLAN['podiumOutlineSceneXY'][:-1]
    axes = PLAN['fittedAxes']
    angle = axes['angleRadians']
    c, s = math.cos(angle), math.sin(angle)
    u0, v0 = axes['centerUV']
    width, depth = axes['extentUV']

    if ground_bounds:
        # Sample the edges as well as their endpoints. The full acceptance also
        # intersects the actual terrain triangles with the podium footprint.
        samples = [(a[0]+(b[0]-a[0])*t/8, a[1]+(b[1]-a[1])*t/8)
                   for a,b in zip(ring,ring[1:]+ring[:1]) for t in range(9)]
        z = max(ground_bounds(x+u,y+v)[1] for u,v in samples) + .005

    def point(u, v, h):
        u, v = u+u0, v+v0
        return x+u*c-v*s, y+u*s+v*c, z+h/100

    def cap(points, key):
        vectors = [Vector(p) for p in points]
        for triangle in tessellate_polygon([vectors]):
            batch.face([points[p] if isinstance(p,int) else tuple(p)
                        for p in triangle], key)

    def extrude(points, low, high, key, roof='roof', local=True):
        convert = point if local else lambda u,v,h:(x+u,y+v,z+h/100)
        lower = [convert(u,v,low) for u,v in points]
        upper = [convert(u,v,high) for u,v in points]
        for i in range(len(points)):
            j = (i+1)%len(points)
            batch.face([lower[i],lower[j],upper[j],upper[i]],key)
        cap(upper,roof)

    extrude(ring, 0, PLAN['podiumHeightMeters'], 'building', local=False)
    for a,b in zip(ring,ring[1:]+ring[:1]):
        bottom = [(x+u,y+v,min(z-.02,ground_bounds(x+u,y+v)[0]-.02))
                  if ground_bounds else (x+u,y+v,z-.02) for u,v in (a,b)]
        batch.face([bottom[0],bottom[1],(x+b[0],y+b[1],z),(x+a[0],y+a[1],z)],'roof')

    # Chamfered glass shaft, with independently raised corner piers. No invented
    # pyramid: the contractor photograph shows a flat, circular roof platform.
    hw, hd, cut = width/2, depth/2, .028
    body = [(-hw+cut,-hd),(hw-cut,-hd),(hw,-hd+cut),(hw,hd-cut),
            (hw-cut,hd),(-hw+cut,hd),(-hw,hd-cut),(-hw,-hd+cut)]
    extrude(body, PLAN['podiumHeightMeters'], PLAN['bodyHeightMeters'], 'landmark')
    post = .045
    for su,sv,top in [(-1,-1,232),(1,-1,236),(-1,1,244),(1,1,PLAN['highCornerHeightMeters'])]:
        u,v = su*(hw-post/2),sv*(hd-post/2)
        outline = [(u-post/2,v-post/2),(u+post/2,v-post/2),
                   (u+post/2,v+post/2),(u-post/2,v+post/2)]
        extrude(outline,PLAN['podiumHeightMeters'],top,'bridge')
    # Sparse real recessed-looking facade bands keep the tall face readable;
    # their count is visual subdivision, not an asserted count of floors.
    for h in [55,90,125,160,195,225]:
        for a,b in zip(body,body[1:]+body[:1]):
            aa,bb = (a[0]*1.002,a[1]*1.002),(b[0]*1.002,b[1]*1.002)
            batch.face([point(*aa,h),point(*bb,h),point(*bb,h+.45),point(*aa,h+.45)],'roof')
    for su in [-1,1]:
        for fraction in [-.5,0,.5]:
            u = su*hw*1.002
            v = fraction*depth*.75
            batch.face([point(u,v-.001,PLAN['podiumHeightMeters']),point(u,v+.001,PLAN['podiumHeightMeters']),
                        point(u,v+.001,PLAN['bodyHeightMeters']),point(u,v-.001,PLAN['bodyHeightMeters'])],'bridge')
    deck = [(-.025+PLAN['roofDeckRadiusMeters']/100*math.cos(i*math.tau/24),
             .015+PLAN['roofDeckRadiusMeters']/100*math.sin(i*math.tau/24)) for i in range(24)]
    extrude(deck,PLAN['roofDeckHeightMeters']-1.2,PLAN['roofDeckHeightMeters'],'accent')
    # Two slender supports hold the platform over the main tower roof.
    for u in [-.095,.065]:
        extrude([(u-.02,-.02),(u+.02,-.02),(u+.02,.05),(u-.02,.05)],
                PLAN['bodyHeightMeters'],PLAN['roofDeckHeightMeters']-1.2,'bridge')
    u,v = hw-post/2,hd-post/2
    extrude([(u-.003,v-.003),(u+.003,v-.003),(u+.003,v+.003),(u-.003,v+.003)],
            PLAN['highCornerHeightMeters'],PLAN['heightMeters'],'accent')
    return z
