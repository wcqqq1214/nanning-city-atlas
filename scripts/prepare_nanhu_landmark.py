"""Prepare a geolocated Nanhu park plan from the checked-in OSM snapshot.

Run with the geodata Python environment (Shapely 2, NumPy, mapbox-earcut).
Water and city geodata are read-only. The output is directly usable in Blender.
"""
import json
import math
import random
from pathlib import Path

import mapbox_earcut
import numpy as np
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import linemerge, unary_union

ROOT = Path(__file__).resolve().parents[1]
source = json.loads((ROOT/'data/nanhu-source.json').read_text())
geo = json.loads((ROOT/'public/data/geography.json').read_text())
dem = json.loads((ROOT/'public/data/terrain.json').read_text())
features = source['features']
by_id = {e['id']: e for e in features}
bridge = by_id[243076845]
CENTER = [sum(p[k] for p in bridge['geometry'])/2 for k in ['lon', 'lat']]
KX = 1113.2*math.cos(math.radians(geo['center'][1]))
world_origin = ((CENTER[0]-geo['center'][0])*KX, (CENTER[1]-geo['center'][1])*1113.2)


def project(p):
    return ((p['lon']-CENTER[0])*KX, (p['lat']-CENTER[1])*1113.2)


def rounded(points):
    return [[round(x, 5), round(y, 5)] for x, y in points]


outer = linemerge([LineString([project(p) for p in m['geometry']])
                   for m in source['park']['members'] if m['role'] == 'outer'])
park = Polygon(outer.coords)
water_polys = [Polygon([[(x-world_origin[0], y-world_origin[1]) for x, y in ring]
                       for ring in rings][0],
                      [[(x-world_origin[0], y-world_origin[1]) for x, y in ring] for ring in rings[1:]])
               for rings in geo['water']]
waters = [w for w in water_polys if w.intersects(park)]
water = unary_union(waters)
lake = max(waters, key=lambda w: w.area)
land = park.difference(water.buffer(.012))
buildings = unary_union([Polygon([(x-world_origin[0], y-world_origin[1]) for x, y in b['rings'][0]])
                        for b in geo['buildings']
                        if park.contains(Point(b['rings'][0][0][0]-world_origin[0], b['rings'][0][0][1]-world_origin[1]))])
roads = unary_union([LineString([(x-world_origin[0], y-world_origin[1]) for x, y in r['points']]).buffer(
                        (.13 if r['class'] in ['primary', 'trunk', 'motorway'] else
                         .085 if r['class'] == 'secondary' else .0475)+.02)
                     for r in geo['roads']
                     if LineString([(x-world_origin[0], y-world_origin[1]) for x, y in r['points']]).intersects(park)])
causeway_ids = [243076844, 243076845, 243076846]
causeways = {str(i): rounded(project(p) for p in by_id[i]['geometry']) for i in causeway_ids}
causeway_zone = unary_union([LineString(p).buffer(.14) for p in causeways.values()])
paths, source_paths, boardwalks = [], [], []
for f in features:
    tags, pts = f.get('tags', {}), f.get('geometry', [])
    if not tags.get('highway') or len(pts) < 2 or f['id'] in causeway_ids:
        continue
    line = LineString([project(p) for p in pts])
    if tags.get('bridge'):
        boardwalks.append({'id': f['id'], 'points': rounded(line.coords)})
    else:
        source_paths.append({'id': f['id'], 'points': rounded(line.coords)})
        paths.append(line.buffer(.019, cap_style='round', join_style='round'))
# Existing mapped garden paths plus a shoreline-derived promenade. Keep the
# unmodified lake boundary; do not cover water or draw paths through buildings.
shore = lake.buffer(.075).difference(lake.buffer(.030))
paving = unary_union(paths+[shore]).intersection(land).difference(buildings.buffer(.012)).difference(roads).difference(causeway_zone)


def polygon_mesh(shape, segment_length=.22):
    if shape.is_empty:
        return []
    polygons = [shape] if shape.geom_type == 'Polygon' else [p for p in shape.geoms if p.geom_type == 'Polygon']
    result = []
    for polygon in polygons:
        if polygon.area < .000015:
            continue
        if segment_length:
            polygon = polygon.segmentize(segment_length)
        rings = [list(polygon.exterior.coords)[:-1]]+[list(r.coords)[:-1] for r in polygon.interiors]
        coords = np.array([p for ring in rings for p in ring], dtype=np.float64)
        ends = np.cumsum([len(r) for r in rings], dtype=np.uint32)
        indices = mapbox_earcut.triangulate_float64(coords, ends)
        tris = [[int(i) for i in indices[k:k+3]] for k in range(0, len(indices), 3)]
        tris = [t for t in tris if Polygon([coords[i] for i in t]).area > 1e-10]
        result.append({'points': rounded(coords), 'triangles': tris})
    return result


tree_land = land.difference(buildings.buffer(.13)).difference(roads.buffer(.08)).difference(paving.buffer(.10)).difference(causeway_zone)
trees = []
for x, y, radius in geo['trees']:
    u, v = x-world_origin[0], y-world_origin[1]
    if tree_land.contains(Point(u, v)):
        trees.append([round(u, 4), round(v, 4), round(min(.18, radius*.45), 3)])
# Add a restrained row of trees landward of the promenade, with deterministic
# spacing and separation from both existing trunks and mapped buildings.
tree_line = lake.buffer(.22).exterior
for i in range(math.ceil(tree_line.length/.55)):
    point = tree_line.interpolate(i*.55)
    if tree_land.contains(point) and all(math.dist(point.coords[0], t[:2]) > .34 for t in trees):
        trees.append([round(point.x, 4), round(point.y, 4), .135+(i%4)*.009])

# The city-wide canopy is sparse here. Fill garden land with a reproducible,
# loose broadleaf planting pattern, away from water, buildings and paths.
rng = random.Random(12477526)
planting = tree_land.buffer(-.09)
west, south, east, north = park.bounds
for i in range(math.ceil((east-west)/.48)):
    for j in range(math.ceil((north-south)/.48)):
        u, v = west+(i+.5)*.48+rng.uniform(-.10, .10), south+(j+.5)*.48+rng.uniform(-.10, .10)
        if planting.contains(Point(u, v)) and all(math.dist((u, v), t[:2]) > .30 for t in trees):
            trees.append([round(u, 4), round(v, 4), round(rng.uniform(.105, .15), 3)])

square = by_id[652143042]
square_poly = Polygon([project(p) for p in square['geometry']]).intersection(land).difference(buildings)

# Replace only the coarse terrain cells surrounding Nanhu with a shore-clipped
# display mesh. Water coordinates and the original DEM remain unchanged. The
# outer rectangle aligns with both original and half-resolution terrain grids.
minx, miny, maxx, maxy = geo['bounds']
dx, dy = (maxx-minx)/(dem['cols']-1), (maxy-miny)/(dem['rows']-1)
west, south, east, north = park.bounds
cols = [math.floor((west+world_origin[0]-minx)/dx/2)*2-2,
        math.ceil((east+world_origin[0]-minx)/dx/2)*2+2]
rows = [math.floor((maxy-north-world_origin[1])/dy/2)*2-2,
        math.ceil((maxy-south-world_origin[1])/dy/2)*2+2]
xs = [minx+(cols[0]+i/3)*dx-world_origin[0] for i in range((cols[1]-cols[0])*3+1)]
ys = [maxy-(rows[1]-j/3)*dy-world_origin[1] for j in range((rows[1]-rows[0])*3+1)]
patch_box = box(xs[0], ys[0], xs[-1], ys[-1])
patch_water = unary_union([p for p in water_polys if p.intersects(patch_box)])
terrain_meshes = []
for aa, cc in zip(xs, xs[1:]):
    for bb, dd in zip(ys, ys[1:]):
        cell = box(aa, bb, cc, dd).difference(patch_water)
        terrain_meshes.extend(polygon_mesh(cell, segment_length=None))
distance_grid = [[round(Point(u, v).distance(water), 5) for u in xs] for v in ys]
terrain_patch = {'columnRange': cols, 'rowRange': rows,
                 'bounds': [xs[0], ys[0], xs[-1], ys[-1]],
                 'columns': len(xs), 'rows': len(ys), 'shoreDistance': distance_grid,
                 'meshes': terrain_meshes}
plan = {
    'center': CENTER,
    'osmTimestamp': source['osmTimestamp'],
    'sources': {'park': 12477526, 'bridge': 243076845, 'causeways': [243076844, 243076846], 'square': 652143042},
    'park': rounded(park.exterior.coords),
    'water': [[rounded(p.exterior.coords)]+[rounded(r.coords) for r in p.interiors] for p in waters],
    'lake': [rounded(lake.exterior.coords)]+[rounded(r.coords) for r in lake.interiors],
    'causeways': causeways,
    'paths': polygon_mesh(paving),
    'mappedPaths': source_paths,
    'boardwalks': boardwalks,
    'square': polygon_mesh(square_poly),
    'trees': trees,
    'terrainPatch': terrain_patch,
}
(ROOT/'data/nanhu-plan.json').write_text(json.dumps(plan, ensure_ascii=False, separators=(',', ':'))+'\n')
print(f'Nanhu: {len(trees)} broadleaf trees, {len(source_paths)} mapped garden paths, {len(boardwalks)} boardwalks; '
      f'{sum(len(p["triangles"]) for p in plan["paths"])} paving triangles. Lake boundaries unchanged.')
print(f'Shore-clipped terrain: {sum(len(p["triangles"]) for p in terrain_meshes)} triangles, '
      f'{len(xs)} × {len(ys)} display samples.')
