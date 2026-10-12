"""Coarse rectangular surroundings, sampled from the completed source terrain.

Only the area outside the calibrated urban/riverbank transition is rebuilt.
Its inner edge retains all source terrain intersections, and remaining water
shores partition the grid. No rural buildings or trees are generated.
Coordinates are glTF east/up/south, at 100 m per unit.
"""
import numpy as np
import shapely
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from urban_scope import polygons


class TerrainSampler:
    def __init__(self, triangles):
        xy = triangles[:, :, [0, 2]] * [1, -1]
        matrices = np.stack([xy[:, 1]-xy[:, 0], xy[:, 2]-xy[:, 0]], axis=2)
        good = np.abs(np.linalg.det(matrices)) > 1e-10
        self.triangles = triangles[good]
        self.xy = xy[good]
        self.inverse = np.linalg.inv(matrices[good])
        self.polygons = shapely.polygons(self.xy)
        self.tree = shapely.STRtree(self.polygons)

    def __call__(self, xy):
        # Quantized primitives can leave tiny gaps, and calibrated terrain can
        # have footprint holes. Sample the closest point on a real face there;
        # extrapolating a narrow bank/retaining triangle creates tall spikes.
        ids = self.tree.nearest(shapely.points(xy))
        weights = np.einsum('nij,nj->ni', self.inverse[ids], xy-self.xy[ids, 0])
        outside = (weights < 0).any(axis=1) | (weights.sum(axis=1) > 1)
        if outside.any():
            connection = shapely.shortest_line(self.polygons[ids[outside]], shapely.points(xy[outside]))
            closest = shapely.get_coordinates(shapely.get_point(connection, 0))
            weights[outside] = np.einsum('nij,nj->ni', self.inverse[ids[outside]],
                                         closest-self.xy[ids[outside], 0])
        weights = np.clip(weights, 0, 1)
        weights /= np.maximum(1, weights.sum(axis=1))[:, None]
        z = self.triangles[ids, :, 1]
        return z[:, 0]+weights[:, 0]*(z[:, 1]-z[:, 0])+weights[:, 1]*(z[:, 2]-z[:, 0])


    def upper_envelope(self, xy):
        """Use the highest adjoining face at float32/quantized terrain seams."""
        points = shapely.points(xy)
        pi, ti = self.tree.query(points, predicate='dwithin', distance=1e-5)
        closest = shapely.get_coordinates(shapely.get_point(
            shapely.shortest_line(self.polygons[ti], points[pi]), 0))
        w = np.einsum('nij,nj->ni', self.inverse[ti], closest-self.xy[ti, 0])
        w = np.clip(w, 0, 1)
        w /= np.maximum(1, w.sum(axis=1))[:, None]
        z = self.triangles[ti, :, 1]
        heights = z[:, 0]+w[:, 0]*(z[:, 1]-z[:, 0])+w[:, 1]*(z[:, 2]-z[:, 0])
        result = self(xy)
        np.maximum.at(result, pi, heights)
        return result


def insert_seam_vertices(poly, seam_tree):
    """Keep every original cut vertex on a polygon's shared inner edge."""
    rings = []
    for ring in [poly.exterior, *poly.interiors]:
        out = []
        coords = np.asarray(ring.coords)
        for a, b in zip(coords, coords[1:]):
            edge = LineString([a, b])
            candidates = seam_tree.query(edge.buffer(1e-5))
            delta = b-a
            length = np.dot(delta, delta)
            splits = [(0., a)]
            if length > 1e-15:
                for i in candidates:
                    q = np.asarray(seam_tree.geometries[i].coords[0])
                    t = np.dot(q-a, delta)/length
                    if 1e-8 < t < 1-1e-8:
                        splits.append((t, a+t*delta))
            out.extend(p for _, p in sorted(splits, key=lambda v: v[0]))
        rings.append(out)
    return Polygon(rings[0], rings[1:])


def flat_geometry(triangles):
    triangles = np.asarray(triangles, dtype='<f4')
    normal = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    good = np.linalg.norm(normal, axis=1) > 1e-10
    triangles, normal = triangles[good], normal[good]
    # Terrain and road surfaces face upwards, independently of polygon winding.
    reverse = normal[:, 1] < 0
    triangles[reverse] = triangles[reverse][:, [0, 2, 1]]
    normal[reverse] *= -1
    normal /= np.linalg.norm(normal, axis=1)[:, None]
    values = np.concatenate([triangles, np.repeat(normal[:, None, :], 3, axis=1)], axis=2)
    vertices, indices = np.unique(values.reshape(-1, 6), axis=0, return_inverse=True)
    return vertices[:, :3], vertices[:, 3:], indices.reshape(-1, 3)


def canopy_ground_intersections(triangles, ground, core):
    """Partition fringe faces by actual terrain planes, including face interiors.

    A linear height difference reaches its minimum at an intersection vertex;
    these are exhaustive clearance probes, unlike canopy vertices/centroids.
    """
    xy = triangles[:, :, [0, 2]] * [1, -1]
    areas = shapely.polygons(xy)
    selected = np.flatnonzero(~shapely.covered_by(areas, core))
    fringe = shapely.difference(areas[selected], core)
    ci, gi = ground.tree.query(fringe, predicate='intersects')
    pieces = shapely.intersection(fringe[ci], ground.polygons[gi])
    # Float32 XY at this city scale resolves roughly 0.4–1.5 mm. Ignore
    # overlap strips narrower than 2 mm, where independently rounded adjacent
    # faces can intersect despite sharing an intended edge. Keep all vertices
    # of every wider intersection, including its boundary extrema.
    valid = ~shapely.is_empty(shapely.buffer(pieces, -1e-5))
    return selected[ci[valid]], gi[valid], pieces[valid]


def plane_heights(triangle, xy):
    base = triangle[:, [0, 2]] * [1, -1]
    weights = np.linalg.solve(np.column_stack([base[1]-base[0], base[2]-base[0]]), (xy-base[0]).T).T
    return triangle[0, 1] + weights @ (triangle[1:, 1]-triangle[0, 1])


def canopy_clearance(triangles, ground, core):
    ci, gi, pieces = canopy_ground_intersections(triangles, ground, core)
    minima = np.full(len(triangles), np.inf)
    for c, g, piece in zip(ci, gi, pieces):
        xy = shapely.get_coordinates(piece)
        gap = plane_heights(triangles[c], xy)-plane_heights(ground.triangles[g], xy)
        minima[c] = min(minima[c], float(gap.min()))
    return minima


def conform_canopy(points, normals, faces, scope, ground):
    """Refine only crossing faces; preserve the core and unmodified face planes."""
    from scope_city import clip_face
    triangles = points[faces]
    minima = canopy_clearance(triangles, ground, scope.core)
    distance = shapely.distance(shapely.points(points[:, [0, 2]]*[1, -1]), scope.core)
    edge = distance >= scope.source['landscapeFadeMeters']/scope.units-1e-5
    repair = (minima < -.00001) | edge[faces].any(axis=1)
    if not repair.any():
        return points, normals, faces
    values = np.concatenate([points, normals], axis=1)
    output = list(values[faces[~repair]])
    for face in faces[repair]:
        original = values[face]
        area = Polygon(original[:, [0, 2]]*[1, -1])
        if area.area <= 1e-12:
            output.append(original)
            continue
        # Keep even partially intersecting core triangles on their source plane.
        output.extend(clip_face(original, scope.core))
        fringe = area.difference(scope.core)
        ids = ground.tree.query(fringe, predicate='intersects')
        patches = []
        for i in ids:
            patch = fringe.intersection(ground.polygons[i])
            if patch.area <= 1e-12:
                continue
            patches.append(patch)
            for part in clip_face(original, patch):
                xy = part[:, [0, 2]]*[1, -1]
                heights = plane_heights(ground.triangles[i], xy)
                outside = shapely.distance(shapely.points(xy), scope.core) > 1e-7
                part[outside, 1] = np.maximum(part[outside, 1], heights[outside]+.00005)
                outer = shapely.distance(shapely.points(xy), scope.core) >= (scope.source['landscapeFadeMeters']-1)/scope.units
                part[outer, 1] = heights[outer]+.00005
                output.append(part)
        # Preserve footprint holes/slivers instead of silently dropping canopy.
        remainder = fringe.difference(unary_union(patches))
        for hole in polygons(remainder):
            # Overlay roundoff can leave long, effectively zero-width strips.
            # They retain the old face plane and would create vertical splinters.
            if not hole.buffer(-1e-6).is_empty:
                output.extend(clip_face(original, hole))
    output = np.asarray(output, dtype='<f4')
    # Float32 rounding can collapse sub-millimeter intersection slivers. Draco
    # drops these too; remove them before the bijective compression audit.
    area = np.linalg.norm(np.cross(output[:, 1, :3]-output[:, 0, :3],
                                   output[:, 2, :3]-output[:, 0, :3]), axis=1)
    output = output[area > 1e-10]
    values, indices = np.unique(output.reshape(-1, 6), axis=0, return_inverse=True)
    positions = values[:, :3]
    xy = positions[:, [0, 2]]*[1, -1]
    distance = shapely.distance(shapely.points(xy), scope.core)
    outside = distance > 1e-7
    floor = ground.upper_envelope(xy[outside])+.00005
    positions[outside, 1] = np.maximum(positions[outside, 1], floor)
    outer = distance[outside] >= (scope.source['landscapeFadeMeters']-1)/scope.units
    height = positions[outside, 1]
    height[outer] = floor[outer]
    positions[outside, 1] = height
    return positions, values[:, 3:], indices.reshape(-1, 3)


def fade_canopy(points, normals, faces, scope, source_ground, display_ground):
    """Extend forest relief across the city line, then merge it into the ground.

    Positions inside the core remain exact. Outside, the original canopy rise
    follows a smoothstep falloff over the same distance as the palette mask.
    This is geometric tapering, not a transparent cut through tree surfaces.
    """
    xy = points[:, [0, 2]]*[1, -1]
    distance = shapely.distance(shapely.points(xy), scope.core)
    t = np.clip(distance/(scope.source['landscapeFadeMeters']/scope.units), 0, 1)
    weight = 1-t*t*(3-2*t)
    outside = distance > 1e-7
    result = points.copy()
    original_ground = source_ground(xy[outside])
    actual_ground = display_ground(xy[outside])
    rise = np.maximum(0, points[outside, 1]-original_ground)
    # A sub-centimeter offset avoids z-fighting where the canopy meets earth.
    result[outside, 1] = actual_ground+np.maximum(.00005, rise*weight[outside])
    result, normals, faces = conform_canopy(result, normals, faces, scope, display_ground)
    # A final bounded lift compensates centimeter-scale residuals at independently
    # quantized terrain joins. Larger defects must be fixed by partitioning, not
    # hidden by raising the forest. Weld shared positions before applying it.
    gaps = canopy_clearance(result[faces], display_ground, scope.core)
    lift = np.maximum(0, .00005-gaps)
    if lift.max() > .001:
        raise ValueError('Canopy refinement left more than 10 cm of penetration')
    _, weld = np.unique(result, axis=0, return_inverse=True)
    corrections = np.zeros(weld.max()+1)
    for k in range(3):
        np.maximum.at(corrections, weld[faces[:, k]], lift)
    xy = result[:, [0, 2]]*[1, -1]
    distance = shapely.distance(shapely.points(xy), scope.core)
    if (corrections[weld][distance <= 1e-7] > .000001).any():
        raise ValueError('Canopy correction would alter the protected city core')
    result[distance > 1e-7, 1] += corrections[weld][distance > 1e-7]
    t = np.clip(distance/(scope.source['landscapeFadeMeters']/scope.units), 0, 1)
    weight = 1-t*t*(3-2*t)
    outside = distance > 1e-7
    tri = result[faces]
    face_normal = np.cross(tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0])
    _, weld = np.unique(result, axis=0, return_inverse=True)
    sums = np.zeros((weld.max()+1, 3))
    for k in range(3):
        np.add.at(sums, weld[faces[:, k]], face_normal)
    smooth = sums[weld]
    smooth /= np.maximum(np.linalg.norm(smooth, axis=1)[:, None], 1e-20)
    mixed = normals*weight[:, None]+smooth*(1-weight[:, None])
    mixed /= np.maximum(np.linalg.norm(mixed, axis=1)[:, None], 1e-20)
    mixed[~outside] = normals[~outside]
    return result, mixed.astype('<f4'), faces


def build_context(scope, source_triangles, water_triangles, seam_samples):
    from scope_city import crop_geometry, triangulate

    outside = scope.context.difference(scope.transition)
    sampler = TerrainSampler(source_triangles)
    step = scope.source['contextGridMeters']/scope.units
    # Exact water topology is cheap relative to the terrain and protects shores.
    water_xy = water_triangles[:, :, [0, 2]] * [1, -1]
    water = unary_union(shapely.polygons(water_xy)).intersection(scope.context)
    seam_xy = np.asarray([[p.x, p.y] for distance, _ in seam_samples
                          for p in [scope.transition.exterior.interpolate(distance)]])
    seam_tree = shapely.STRtree(shapely.points(seam_xy))
    distances, heights = np.asarray(sorted(seam_samples)).T
    # Multiple materials can share a boundary vertex. Retain the top surface.
    distances, inverse = np.unique(distances.round(6), return_inverse=True)
    seam_heights = np.full(len(distances), -np.inf)
    np.maximum.at(seam_heights, inverse, heights)
    west, south, east, north = scope.context.bounds
    xs = np.r_[np.arange(west, east, step), east]
    ys = np.r_[np.arange(south, north, step), north]
    cells = [box(x0, y0, x1, y1) for x0, x1 in zip(xs, xs[1:])
             for y0, y1 in zip(ys, ys[1:])]
    pieces = shapely.intersection(cells, outside)
    triangles = []
    for piece in pieces:
        if piece.is_empty:
            continue
        # Keep the ground under water too, for the water-layer toggle. The
        # partition ensures coarse faces have vertices on both shorelines.
        for region in [piece.difference(water), piece.intersection(water)]:
            for poly in polygons(region):
                if poly.area > 1e-10:
                    triangles.extend(triangulate(insert_seam_vertices(poly, seam_tree)))
    xy = np.asarray(triangles).reshape(-1, 2)
    xy, indices = np.unique(xy, axis=0, return_inverse=True)
    z = sampler(xy)
    # Copy the actual retained terrain edge, including its piecewise-linear
    # source heights, instead of putting a wall around the city detail mask.
    points = shapely.points(xy)
    seam = shapely.distance(points, scope.transition.boundary) < 2e-5
    at = shapely.line_locate_point(scope.transition.exterior, points[seam])
    z[seam] = np.interp(at, distances, seam_heights, period=scope.transition.length)
    ground = np.column_stack([xy[:, 0], z, -xy[:, 1]])
    terrain = flat_geometry(ground[indices.reshape(-1, 3)])
    # Schematic major roads are draped on the new surface. No lamps, barriers,
    # sleepers, minor rural streets or elevated-road detail are restored.
    widths = {'motorway': .22, 'trunk': .20, 'primary': .16, 'secondary': .12}
    roads = []
    for road in scope.geo['roads']:
        kind = road['class'].removesuffix('_link')
        if kind in widths:
            line = LineString(road['points'])
            if outside.intersects(line):
                roads.append(line.buffer(widths[kind]/2, cap_style=2, join_style=2))
    road_mask = unary_union(roads).intersection(outside)
    p, n, f, _ = crop_geometry(*terrain, road_mask)
    if p is not None:
        p[:, 1] += .015
    area = float(np.abs(np.linalg.det(np.stack([
        np.asarray(triangles)[:, 1]-np.asarray(triangles)[:, 0],
        np.asarray(triangles)[:, 2]-np.asarray(triangles)[:, 0]], axis=2))).sum()/2)
    if abs(area-outside.area) > 1e-5:
        raise ValueError('Rectangular background has missing or overlapping terrain')
    return terrain, (p, n, f), {'gridMeters': step*scope.units, 'areaKm2': outside.area/100,
                               'terrainTriangles': len(terrain[2]),
                               'roadTriangles': 0 if f is None else len(f),
                               'coverageErrorSquareMeters': abs(area-outside.area)*10000}
