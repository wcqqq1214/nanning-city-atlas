"""Source-region display levels with a continuous transition across mapped joins.

The transition is an explicit visualization estimate, never a hydraulic model.
Runtime height queries use the prepared native water mesh, not this field.
"""
import math
import numpy as np


def inside_ring(x,y,ring):
    inside=False
    for (a,b),(c,d) in zip(ring,ring[1:]+ring[:1]):
        if (b>y)!=(d>y) and x<(c-a)*(y-b)/(d-b)+a:inside=not inside
    return inside


def inside_polygon(x,y,rings):
    return inside_ring(x,y,rings[0]) and not any(inside_ring(x,y,r) for r in rings[1:])


class WaterLevelField:
    def __init__(self,entry):
        self.constant=entry['levelMeters'];self.regions=[]
        if not math.isfinite(self.constant):raise ValueError('Invalid water display level')
        if not entry.get('levelRegions'):return
        width=entry.get('transitionWidthMeters',0)
        if not math.isfinite(width) or width<=0:raise ValueError('A positive water transition width is required')
        self.width=width/100
        for r in entry.get('levelInfluenceRegions',entry['levelRegions']):
            if not math.isfinite(r['levelMeters']):raise ValueError('Invalid source region display level')
            segments=[(a,b) for ring in r['rings'] for a,b in zip(ring,ring[1:]) if a!=b]
            if not segments:raise ValueError('Missing water region boundary')
            starts=np.asarray([a for a,b in segments]);direction=np.asarray([b for a,b in segments])-starts
            self.regions.append((r['rings'],r['levelMeters'],starts,direction,np.sum(direction*direction,axis=1)))

    def meters(self,x,y):
        if not self.regions:return self.constant
        distances=[]
        for rings,level,starts,direction,length2 in self.regions:
            if inside_polygon(x,y,rings):distance=0.
            else:
                delta=np.asarray([x,y])-starts
                t=np.clip(np.sum(delta*direction,axis=1)/length2,0,1)
                distance=float(np.min(np.linalg.norm(delta-t[:,None]*direction,axis=1)))
            distances.append(distance)
        t=np.clip(np.asarray(distances)/self.width,0,1);weights=1-t*t*(3-2*t)
        if weights.sum()==0:return self.regions[int(np.argmin(distances))][1]
        return float(np.dot(weights,[r[1] for r in self.regions])/weights.sum())
