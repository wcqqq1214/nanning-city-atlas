"""Node canopy triangle edges before sampling the final non-planar ground.

An inserted point on only one side of an edge becomes a visible 3D crack after
terrain sampling. Split incident triangles around an interior centroid so all
boundary stations survive triangulation, including collinear stations.
"""
import copy
import numpy as np
import shapely
from shapely.geometry import LineString, Polygon
from shapely.strtree import STRtree


def conform_edges(mesh, domain=None, tolerance=1e-9, minimum_area=1e-10):
    if tolerance <= 0 or minimum_area < 0:
        raise ValueError('Invalid precision or minimum area')
    points = np.asarray(mesh['points'], dtype=float)
    used = np.unique(mesh['triangles'])
    # Ignore unused vertices left by removal of microscopic fragments.
    xy, unique_indices = np.unique(points[used, :2], axis=0, return_index=True)
    ids = used[unique_indices]
    tree = STRtree(shapely.points(xy))
    output = copy.deepcopy(mesh)
    output['triangles'], output['colors'] = [], []
    split = added = 0
    omitted_area = maximum_rise_difference = 0.
    scope = domain.buffer(tolerance) if domain is not None else None
    for face, color in zip(mesh['triangles'], mesh['colors']):
        vertices = points[face]
        if scope is not None and not Polygon(vertices[:, :2]).intersects(scope):
            output['triangles'].append(face); output['colors'].append(color)
            continue
        ring = []
        for ai, bi in zip(face, face[1:]+face[:1]):
            a, b = points[ai], points[bi]
            d = b[:2]-a[:2]; length2 = float(d@d)
            ring.append(ai)
            if length2 <= tolerance*tolerance:
                continue
            line = LineString([a[:2], b[:2]])
            candidates = tree.query(line.buffer(tolerance, cap_style='square'))
            candidates = candidates[np.argsort((xy[candidates]-a[:2])@d)]
            for candidate in candidates:
                index = int(ids[candidate]); p = points[index]
                t = float((p[:2]-a[:2])@d/length2)
                # Endpoint exclusion is in distance units, not an edge fraction.
                if t*np.sqrt(length2) <= tolerance or (1-t)*np.sqrt(length2) <= tolerance:
                    continue
                if np.linalg.norm(p[:2]-a[:2]-t*d) > tolerance:
                    continue
                maximum_rise_difference = max(maximum_rise_difference, abs(float(p[2]-a[2]-t*(b[2]-a[2]))))
                ring.append(index)
        if len(ring) == 3:
            output['triangles'].append(face); output['colors'].append(color)
            continue
        split += 1
        center = vertices.mean(axis=0)
        center_id = len(output['points']); output['points'].append(center.tolist())
        for ai, bi in zip(ring, ring[1:]+ring[:1]):
            a, b = points[ai], points[bi]
            u, v = b[:2]-a[:2], center[:2]-a[:2]
            cross = float(u[0]*v[1]-u[1]*v[0])
            area = abs(cross)/2
            if area <= minimum_area:
                omitted_area += area
                continue
            output['triangles'].append([ai, bi, center_id] if cross > 0 else [bi, ai, center_id])
            output['colors'].append(color); added += 1
    if omitted_area*10000 > .01:
        raise ValueError('Conforming edges would omit more than 0.01 square metres')
    return output, {'trianglesSplit': split, 'trianglesAdded': added-split,
                    'omittedSquareMeters': omitted_area*10000,
                    'maximumRiseDifferenceMeters': maximum_rise_difference*100,
                    'toleranceMeters': tolerance*100}
