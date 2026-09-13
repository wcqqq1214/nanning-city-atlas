"""Recut only the Qingxiu patch against its final terrain and park clearings."""
import hashlib
import json
import sys
from functools import lru_cache
from pathlib import Path

import mapbox_earcut
import numpy as np
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'blender'))
from mountain_terrain import PLAN, canopy_factor


def polygons(shape):
    if shape.geom_type == 'Polygon':
        yield shape
    elif hasattr(shape, 'geoms'):
        for child in shape.geoms:
            yield from polygons(child)


def geometry(rings):
    return unary_union([Polygon(p[0], p[1:]) for p in rings])


def apply(plan, geo, restoration):
    patch = box(*PLAN['bounds'])
    paths = unary_union([geometry(p) for p in PLAN['pathFootprints'].values()])
    tower = Point(PLAN['towerCenterSceneXY'])
    clearing = paths.buffer(.04, join_style=2).union(
        tower.buffer(PLAN['source']['tower']['platformRadiusMeters']/100+.03)).intersection(patch)
    terrain = [Polygon([PLAN['points'][i] for i in tri]) for tri in PLAN['triangles']]
    terrain_index = STRtree(terrain)
    removed = {i for i, (x, y, r) in enumerate(geo['trees'])
               if patch.intersects(Point(x, y)) and clearing.intersects(Point(x, y).buffer(r))}
    stats = []
    for region in plan['regions']:
        old_area = geometry(region['coverage'])
        woodland = geometry(region['woodland'])
        if not woodland.intersects(patch):
            continue
        restored = woodland.intersection(tower.buffer(.85)).intersection(restoration)
        allowed = old_area.union(restored).difference(clearing)
        region['coverage'] = [[[[float(x), float(y)] for x, y in ring.coords]
                              for ring in [p.exterior, *p.interiors]] for p in polygons(allowed)]
        region['areaKm2'] = round(allowed.area/100, 4)
        # Trees previously hidden by the canopy may now sit on a new footway.
        removed.update(i for i in region['replacedTreeIndices']
                       if not allowed.contains(Point(geo['trees'][i][:2])))
        region['replacedTreeIndices'] = [i for i in region['replacedTreeIndices'] if i not in removed]
        region['smoothCrownClusters'] = [c for c in region.get('smoothCrownClusters',region['crownClusters'][::2])
                                        if allowed.buffer(.00002).contains(Point(c[:2]).buffer(c[2]))]
        region['crownClusters'] = [c for c in region['crownClusters']
                                  if allowed.buffer(.00002).contains(Point(c[:2]).buffer(c[2]))]
        for profile in ['detail', 'smooth']:
            old = region[profile]
            old_faces = [Polygon([old['points'][i][:2] for i in tri]) for tri in old['triangles']]
            old_index = STRtree(old_faces)
            points, triangles, colors, lookup = [], [], [], {}
            coefficients = {}

            @lru_cache(maxsize=None)
            def original_rise(x, y):
                point = Point(x, y)
                candidates = old_index.query(point, predicate='intersects')
                index = int(candidates[0]) if len(candidates) else int(old_index.nearest(point))
                if old_faces[index].distance(point) > 1e-7:
                    return .10
                if index not in coefficients:
                    vertices = np.array([old['points'][i] for i in old['triangles'][index]])
                    coefficients[index] = np.linalg.solve(np.column_stack((vertices[:, :2], np.ones(3))), vertices[:, 2])
                a, b, c = coefficients[index]
                return max(.10, float(a*x+b*y+c))

            def add(shape, rise_at, color, reduce):
                for polygon in polygons(shape):
                    if polygon.area < 1e-10:
                        continue
                    rings = [list(r.coords)[:-1] for r in [polygon.exterior, *polygon.interiors]]
                    coords = np.array([p for r in rings for p in r], dtype=np.float64)
                    indices = mapbox_earcut.triangulate_float64(
                        coords, np.cumsum([len(r) for r in rings], dtype=np.uint32)).reshape(-1, 3)
                    local = []
                    for x, y in coords:
                        rise = rise_at(x, y)
                        if reduce:
                            factor = canopy_factor(x, y)
                            influence = (1-factor)/(1-PLAN['source']['canopyRiseFactor'])
                            blend = influence*max(0, 1-Point(x, y).distance(clearing)/.4)
                            rise = (rise*(1-blend)+.10*blend)*factor
                        key = (round(float(x), 8), round(float(y), 8), round(float(rise), 8))
                        if key not in lookup:
                            lookup[key] = len(points)
                            points.append(list(key))
                        local.append(lookup[key])
                    for tri in indices:
                        ids = [local[int(i)] for i in tri]
                        a, b, c = [points[i] for i in ids]
                        cross = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
                        if abs(cross) <= 2e-10:
                            continue
                        triangles.append(ids if cross > 0 else ids[::-1])
                        colors.append(color)

            for face_id, footprint in enumerate(old_faces):
                vertices = np.array([old['points'][i] for i in old['triangles'][face_id]])
                if not footprint.intersects(patch):
                    # Copy these faces and values exactly; no scope-wide resampling.
                    ids = []
                    for vertex in vertices.tolist():
                        key = tuple(vertex)
                        if key not in lookup:
                            lookup[key] = len(points); points.append(vertex)
                        ids.append(lookup[key])
                    triangles.append(ids); colors.append(old['colors'][face_id])
                    continue
                affine = np.linalg.solve(np.column_stack((vertices[:, :2], np.ones(3))), vertices[:, 2])
                def rise_at(x, y):
                    return affine[0]*x+affine[1]*y+affine[2]
                add(footprint.difference(patch), rise_at, old['colors'][face_id], False)
            # Each canopy face needs only the final terrain edges. Retaining the
            # obsolete coarse canopy edges as well needlessly multiplies faces.
            local_area = allowed.intersection(patch)
            for index in terrain_index.query(local_area, predicate='intersects'):
                shape = local_area.intersection(terrain[int(index)])
                if shape.area <= 1e-10:
                    continue
                color = old['colors'][int(old_index.nearest(shape.representative_point()))]
                add(shape, original_rise, color, True)
            region[profile] = {'points': points, 'triangles': triangles, 'colors': colors}
        stats.append({'region': region['id'], 'areaKm2': region['areaKm2'],
                      'detailTriangles': len(region['detail']['triangles']),
                      'smoothTriangles': len(region['smooth']['triangles'])})
    plan['mountainRemovedTreeIndices'] = sorted(removed)
    plan['mountainCanopy'] = {'regions': stats, 'pathBufferMeters': 4,
                             'platformBufferMeters': 3, 'restoredRiseMeters': 10,
                             'clearingTransitionMeters': 40,
                             'riseFactor': PLAN['source']['canopyRiseFactor']}
    plan['areaKm2'] = round(sum(r['areaKm2'] for r in plan['regions']), 4)
    for path in ['data/qingxiu-terrain-plan.json', 'scripts/prepare_mountain_canopy.py', 'blender/mountain_terrain.py']:
        plan['inputHashes'][path] = hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
    print('Mountain canopy:', json.dumps(plan['mountainCanopy']), flush=True)
