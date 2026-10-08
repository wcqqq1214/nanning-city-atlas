"""Sample the same explicit Nanhu triangles emitted by build_park_terrain.

The patch already replaces coarse city cells. Sampling those removed cells for
roads or vegetation gives a different surface even with an identical raw DEM.
"""
from functools import lru_cache
import math

from nanhu_landmark import PLAN, terrain_vertices
from reduced_surface import ReducedSurface


def build_surface(meshes, origin, ground, boundary_ground=None):
    triangles = []
    x, y = origin
    for mesh in meshes:
        vertices = terrain_vertices(mesh, (x, y), ground, boundary_ground)
        for ids in mesh['triangles']:
            a, b, c = [vertices[i] for i in ids]
            determinant = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            if abs(determinant) > 1e-12:
                triangles.append((a, b, c))
    return ReducedSurface(triangles, [0]*len(triangles), cell_size=.6)


@lru_cache(maxsize=8)
def patch_surface(ground, scene_center, bounds, columns, rows, lightweight, coarse):
    x = (PLAN['center'][0]-scene_center[0])*1113.2*math.cos(math.radians(scene_center[1]))
    y = (PLAN['center'][1]-scene_center[1])*1113.2
    boundary_ground = lambda u, v: coarse(u,v,ground,bounds,columns,rows,lightweight)
    return build_surface(PLAN['terrainPatch']['meshes'], (x, y), ground, boundary_ground)


def surface(x, y, ground, scene_center, bounds, columns, rows, lightweight, coarse):
    ox = (PLAN['center'][0]-scene_center[0])*1113.2*math.cos(math.radians(scene_center[1]))
    oy = (PLAN['center'][1]-scene_center[1])*1113.2
    west, south, east, north = PLAN['terrainPatch']['bounds']
    if not (west+ox-1e-7 <= x <= east+ox+1e-7 and south+oy-1e-7 <= y <= north+oy+1e-7):
        return None
    return patch_surface(ground, tuple(scene_center), tuple(bounds), columns, rows,
                         lightweight, coarse).sample(x, y)
