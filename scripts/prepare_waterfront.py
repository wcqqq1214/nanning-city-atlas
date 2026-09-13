"""Generate a shore-clipped replacement terrain, with no change to the water map."""
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import mapbox_earcut
from shapely.geometry import Polygon, Point, LineString, box
from shapely.ops import unary_union, substring

ROOT = Path(__file__).resolve().parents[1]


def polygons(shape):
    if shape.geom_type == 'Polygon':
        yield shape
    elif hasattr(shape, 'geoms'):
        for child in shape.geoms:
            yield from polygons(child)


def prepare():
    source = json.loads((ROOT/'data/waterfront-source.json').read_text())
    geo = json.loads((ROOT/'public/data/geography.json').read_text())
    dem = json.loads((ROOT/'public/data/terrain.json').read_text())
    water = unary_union([Polygon(r[0], r[1:]) for r in geo['water']])
    river = max(polygons(water), key=lambda p:p.area)
    boundary = LineString(river.exterior.coords)
    stations = [boundary.project(Point(p)) for p in source['shoreAnchorsSceneXY']]
    shore = substring(boundary, min(stations), max(stations))
    assert 5 < shore.length < 8, 'Select the short north-bank section explicitly'
    if Point(shore.coords[0]).distance(Point(source['shoreAnchorsSceneXY'][0])) > .01:
        shore = LineString(list(shore.coords)[::-1])
    section = source['section']
    west, south, east, north = geo['bounds']
    dx, dy = (east-west)/(dem['cols']-1), (north-south)/(dem['rows']-1)
    a,b,c,d = shore.buffer(section['patchMarginMeters']/100).bounds
    ir = [math.floor((a-west)/dx/2)*2, math.ceil((c-west)/dx/2)*2]
    jr = [math.floor((north-d)/dy/2)*2, math.ceil((north-b)/dy/2)*2]
    bounds = [west+ir[0]*dx, north-jr[1]*dy, west+ir[1]*dx, north-jr[0]*dy]
    count = section['gridSubdivisions']
    cols, rows = (ir[1]-ir[0])*count, (jr[1]-jr[0])*count
    sx, sy = dx/count, dy/count
    patch = box(*bounds)
    land = patch.difference(water)
    # Insert section break-lines into each tile, rather than draping another
    # disconnected paving sheet over the old coarse surface.
    walk = shore.buffer(section['promenadeWidthMeters']/100).intersection(land)
    green = shore.buffer(section['greenBeltOuterMeters']/100).intersection(land).difference(walk)
    rest = land.difference(walk.union(green))
    buildings = unary_union([Polygon(b['rings'][0], b['rings'][1:]) for b in geo['buildings']
                             if Polygon(b['rings'][0]).intersects(patch)])
    reserved_roads = unary_union([LineString(r['points']).buffer(.16 if r['class'] in ['primary','trunk'] else .09)
                                  for r in geo['roads'] if not r['bridge'] and LineString(r['points']).intersects(patch)])
    # Keep building and carriageway reservations in the earth material. The
    # terrain still exists below roads so their shared support stays continuous.
    reserved = buildings.buffer(.015).union(reserved_roads)
    zones = [('waterfront_paving', walk.difference(reserved)),
             ('hillLight', green.difference(reserved)),
             ('ground', rest.union(walk.union(green).intersection(reserved)))]
    points, lookup, triangles, materials, cells = [], {}, [], [], {}
    def vertex(p):
        key = tuple(round(float(v), 6) for v in p)
        if key not in lookup:
            lookup[key] = len(points)
            points.append(list(key))
        return lookup[key]
    for j in range(rows):
        for i in range(cols):
            tile = box(bounds[0]+i*sx, bounds[1]+j*sy, bounds[0]+(i+1)*sx, bounds[1]+(j+1)*sy)
            cell = []
            x0,y0,x1,y1=tile.bounds
            halves=[Polygon([(x0,y0),(x1,y0),(x0,y1)]), Polygon([(x1,y0),(x1,y1),(x0,y1)])]
            for material, area in zones:
                for half in halves:
                    for p in polygons(area.intersection(half)):
                        if p.area < 1e-10: continue
                        rings = [list(r.coords)[:-1] for r in [p.exterior, *p.interiors]]
                        vertices = np.asarray([q for ring in rings for q in ring], dtype=np.float64)
                        ends = np.cumsum([len(r) for r in rings], dtype=np.uint32)
                        faces = mapbox_earcut.triangulate_float64(vertices, ends).reshape(-1, 3)
                        for face in faces:
                            ids = [vertex(vertices[k]) for k in face]
                            if Polygon([points[k] for k in ids]).area < 1e-10: continue
                            cell.append(len(triangles));triangles.append(ids);materials.append(material)
            if cell: cells[f'{i},{j}'] = cell
    def smooth(v):
        v = max(0, min(1, v)); return v*v*(3-2*v)
    weights = []
    for x,y in points:
        p = Point(x,y); distance = p.distance(shore); station = shore.project(p)
        end = smooth(min(station, shore.length-station)/(section['endBlendMeters']/100))
        inland = 1-smooth(max(0, distance-section['promenadeWidthMeters']/100)/
                         ((section['inlandBlendMeters']-section['promenadeWidthMeters'])/100))
        edge = smooth(min(x-bounds[0], bounds[2]-x, y-bounds[1], bounds[3]-y)/(section['edgeBlendMeters']/100))
        weights.append(round(end*inland*edge, 9))
    # Reuse the actual mesh's shoreline vertices to make wall/land edges coincide.
    wall_ids = [i for i,p in enumerate(points) if Point(p).distance(shore)<.000003]
    wall_ids.sort(key=lambda i:shore.project(Point(points[i])))
    inputs = ['data/waterfront-source.json','public/data/geography.json','public/data/terrain.json']
    plan = {'id':source['id'],'center':geo['center'],'bounds':bounds,'columnRange':ir,'rowRange':jr,
            'grid':{'columns':cols,'rows':rows,'dx':sx,'dy':sy},'points':points,'triangles':triangles,
            'materials':materials,'cells':cells,'weights':weights,'wallVertexIds':wall_ids,
            'shoreline':[list(p) for p in shore.coords], 'section':section,
            'inputHashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs},
            'statistics':{'lengthMeters':round(shore.length*100,2),'patchAreaM2':round(patch.area*10000,2),
                          'landAreaM2':round(land.area*10000,2),'triangles':len(triangles),
                          'promenadeAreaM2':round(walk.difference(reserved).area*10000,2)}}
    (ROOT/'data/waterfront-plan.json').write_text(json.dumps(plan,ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps(plan['statistics']), flush=True)


if __name__ == '__main__': prepare()
