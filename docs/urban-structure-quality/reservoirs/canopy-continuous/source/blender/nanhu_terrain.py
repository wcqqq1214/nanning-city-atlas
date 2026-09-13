"""Sample the same explicit Nanhu triangles emitted by build_park_terrain.

The patch already replaces coarse city cells. Sampling those removed cells for
roads or vegetation gives a different surface even with an identical raw DEM.
"""
from functools import lru_cache
import math

from nanhu_landmark import PLAN
from reduced_surface import ReducedSurface


def build_surface(meshes, origin, ground):
    triangles = []
    x, y = origin
    for mesh in meshes:
        vertices = [(x+u, y+v, ground(x+u, y+v)) for u, v in mesh['points']]
        for ids in mesh['triangles']:
            a, b, c = [vertices[i] for i in ids]
            determinant = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            if abs(determinant) > 1e-12:
                triangles.append((a, b, c))
    return ReducedSurface(triangles, [0]*len(triangles), cell_size=.6)


@lru_cache(maxsize=8)
def patch_surface(ground, scene_center):
    x = (PLAN['center'][0]-scene_center[0])*1113.2*math.cos(math.radians(scene_center[1]))
    y = (PLAN['center'][1]-scene_center[1])*1113.2
    return build_surface(PLAN['terrainPatch']['meshes'], (x, y), ground)


def surface(x, y, ground, scene_center):
    ox = (PLAN['center'][0]-scene_center[0])*1113.2*math.cos(math.radians(scene_center[1]))
    oy = (PLAN['center'][1]-scene_center[1])*1113.2
    west, south, east, north = PLAN['terrainPatch']['bounds']
    if not (west+ox-1e-7 <= x <= east+ox+1e-7 and south+oy-1e-7 <= y <= north+oy+1e-7):
        return None
    return patch_surface(ground, tuple(scene_center)).sample(x, y)
