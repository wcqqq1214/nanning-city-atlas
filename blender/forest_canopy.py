"""Terrain-following woodland surfaces and sparse low-poly crown clusters."""
import json
import math
from pathlib import Path

from vegetation import CROWN_POINTS, CROWN_FACES
from zhenning_landmark import terrain_patch as zhenning_terrain_patch

PLAN = json.loads((Path(__file__).resolve().parents[1]/'data/forest-plan.json').read_text())
REGIONS = PLAN['regions']
REPLACED = {i for region in REGIONS for i in region['replacedTreeIndices']}
CANOPY_MATERIALS = ['forest_deep', 'forest_jade', 'forest_light']


def refined_terrain_height(col, row, ground, bounds, columns, rows):
    """Keep the fine patch's edge on the neighbouring coarse triangle edge."""
    west,south,east,north=bounds
    def at(i,j):
        return ground(west+i/(columns-1)*(east-west),north-j/(rows-1)*(north-south))
    i0,j0,i1,j1=zhenning_terrain_patch(tuple(bounds),columns,rows,tuple(PLAN['center']))
    if col in [i0,i1] and row%2 and j0<row<j1:
        return (at(col,row-1)+at(col,row+1))/2
    if row in [j0,j1] and col%2 and i0<col<i1:
        return (at(col-1,row)+at(col+1,row))/2
    return at(col,row)


def terrain_surface(x, y, ground, bounds, columns, rows, lightweight=False):
    """Interpolate the displayed triangle, not a bilinear DEM height."""
    west, south, east, north = bounds
    u = max(0, min(columns-1.000001, (x-west)/(east-west)*(columns-1)))
    v = max(0, min(rows-1.000001, (north-y)/(north-south)*(rows-1)))
    step = 2 if lightweight else 1
    if lightweight:
        i0,j0,i1,j1=zhenning_terrain_patch(tuple(bounds),columns,rows,tuple(PLAN['center']))
        if i0<=u<i1 and j0<=v<j1:
            step=1
    i, j = int(u)//step*step, int(v)//step*step
    ii, jj = min(i+step, columns-1), min(j+step, rows-1)
    a, b = (u-i)/(ii-i), (v-j)/(jj-j)
    z = [refined_terrain_height(col,row,ground,bounds,columns,rows) if lightweight and step==1 else
         ground(west+col/(columns-1)*(east-west), north-row/(rows-1)*(north-south))
         for col, row in [(i,j), (ii,j), (ii,jj), (i,jj)]]
    return (z[0]*(1-a)+z[1]*(a-b)+z[2]*b if a >= b else
            z[0]*(1-b)+z[2]*a+z[3]*(b-a))


def build_canopy(batch, region, ground, bounds, columns, rows, lightweight=False):
    mesh = region['smooth' if lightweight else 'detail']
    vertices = [(x, y, terrain_surface(x,y,ground,bounds,columns,rows,lightweight)+rise)
                for x, y, rise in mesh['points']]
    # Shared normals soften the forest surface into foliage, while the original
    # faceted earth remains visible at clearings and when vegetation is hidden.
    normals = [[0.,0.,0.] for _ in vertices]
    for tri in mesh['triangles']:
        a,b,c = [vertices[i] for i in tri]
        u = [b[k]-a[k] for k in range(3)]
        v = [c[k]-a[k] for k in range(3)]
        normal = [u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        for i in tri:
            normals[i] = [normals[i][k]+normal[k] for k in range(3)]
    normals = [tuple(c/max(1e-12,math.sqrt(sum(v*v for v in n))) for c in n) for n in normals]
    for tri, color in zip(mesh['triangles'], mesh['colors']):
        # Smooth suburban coverage shares one material; lighting supplies its
        # relief, avoiding repeated boundary vertices across three primitives.
        if lightweight and region['id'] != 'qingxiu':
            color = 1
        batch.face([vertices[i] for i in tri], CANOPY_MATERIALS[color], [normals[i] for i in tri])


def build_crown_clusters(batch, region, ground, bounds, columns, rows, lightweight=False):
    clusters = region['crownClusters'][::2 if lightweight else 1]
    for x,y,r,aspect,angle,color in clusters:
        floor = terrain_surface(x,y,ground,bounds,columns,rows,lightweight)
        c,s = math.cos(angle),math.sin(angle)
        vertices = []
        for a,b,d in CROWN_POINTS:
            u = x+r*(a*c-b*s)
            v = y+r*aspect*(a*s+b*c)
            # Low rounded lobes merge into the canopy beneath them. Fitting the
            # uphill side locally avoids tall, level-topped blocks on slopes.
            h = max(floor+.48+d*.42,
                    terrain_surface(u,v,ground,bounds,columns,rows,lightweight)+.12)
            vertices.append((u,v,h))
        for face in CROWN_FACES:
            batch.face([vertices[i] for i in face],CANOPY_MATERIALS[color])
