"""Validate declared access paving against its source and actual city mesh."""
import sys
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union


def read_access(path, root, report):
    declared = set().union(*(set(report[p].get('siteAccess', {})) for p in ['detail', 'smooth']))
    if path is None:
        if declared:
            raise ValueError('Declared site access requires --site-access-plan')
        return None
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'blender'))
    from site_access_plan import SiteAccessPlan
    plan = SiteAccessPlan.read(path, root)
    for profile in ['detail', 'smooth']:
        if set(plan.payload['sites']) != set(report[profile].get('siteAccess', {})):
            raise ValueError('Access plan and city summary declare different sites')
    return plan.payload


def footprint(triangles):
    return unary_union([Polygon(t[:, :2]) for t in np.asarray(triangles)])


def check_support(paving, terrain):
    """Require complete support, rather than an aggregate overlap-pair count."""
    t = np.asarray(terrain)
    w,s,e,n = paving.bounds
    xy = t[:, :, :2]
    lo, hi = xy.min(axis=1), xy.max(axis=1)
    selected = (hi[:,0]>=w)&(lo[:,0]<=e)&(hi[:,1]>=s)&(lo[:,1]<=n)
    ground = footprint(t[selected])
    missing = paving.difference(ground.buffer(.002/100)).area*10000
    if missing > .01:
        raise ValueError('Access pavement has missing terrain support')
    return {'coverageToleranceMeters':.002,'unsupportedSquareMeters':missing}


def check_contact(minimum_scene_clearance):
    # Access intentionally touches its prepared soil at the yard edge. Bound
    # export/plane arithmetic by the existing 0.2 mm access position gate.
    # Ordinary streets retain their separate strict positive-clearance check.
    minimum_meters = minimum_scene_clearance*100
    if minimum_meters < -.0002:
        raise ValueError('Access pavement penetrates its soil beyond export precision')
    return {'minimumClearanceMeters':minimum_meters,'contactToleranceMeters':.0002}


def source_walls(source):
    edges = {}
    for face in source['triangles']:
        for a, b in zip(face, face[1:]+face[:1]):
            edges.setdefault(tuple(sorted((a, b))), []).append((a, b))
    walls = []
    top, soil = np.asarray(source['topPoints']), np.asarray(source['soilPoints'])
    for uses in edges.values():
        if len(uses) == 2:
            continue
        if len(uses) != 1:
            raise ValueError('Non-manifold access boundary')
        a, b = uses[0]
        for triangle in [[top[a], soil[a], top[b]], [top[b], soil[a], soil[b]]]:
            t = np.asarray(triangle)
            if np.linalg.norm(np.cross(t[1]-t[0], t[2]-t[0])) > 0:
                walls.append(t)
    return np.asarray(walls).reshape(-1, 3, 3)


def check_access(payload, reported, profile, actual):
    sites = payload['sites'] if payload is not None else {}
    expected_names = {'GroundRoads_access_'+identity.replace('-', '_')+'_0_0': identity for identity in sites}
    if set(actual) != set(expected_names):
        raise ValueError('Actual access nodes differ from the declared sites')
    result = []
    # Use the same strict native/decoded gate as the isolated access audit.
    from check_reduced_terrain_exports import match_faces
    for name, identity in expected_names.items():
        source = sites[identity][profile]
        native = np.asarray(source['topPoints'], dtype=float)[source['triangles']]
        paving, walls = actual[name]['road'], actual[name]['walls']
        counts = reported[identity]
        if counts['pavingTriangles'] != len(native) or counts['wallTriangles'] != len(walls):
            raise ValueError('Access summary disagrees with source or actual mesh counts')
        def geometry(faces, upward=False):
            normals = np.cross(faces[:, 1]-faces[:, 0], faces[:, 2]-faces[:, 0])
            lengths = np.linalg.norm(normals, axis=1)
            if np.any(lengths == 0) or (upward and np.any(normals[:, 2] <= 0)):
                raise ValueError('Collapsed or reversed access pavement')
            return {'triangles': faces, 'materials': np.zeros(len(faces), dtype=int),
                    'cornerNormals': np.repeat((normals/lengths[:, None])[:, None, :], 3, axis=1)}
        correspondence = match_faces(geometry(native, True), geometry(paving, True),
                                     position_meters=.0002, normal_degrees=.5)
        expected_walls = source_walls(source)
        if len(expected_walls) != len(walls):
            raise ValueError('Actual access walls differ from the source boundary')
        wall_check = (match_faces(geometry(expected_walls), geometry(walls),
                                 position_meters=.0002, normal_degrees=.5)
                      if len(walls) else {'triangles': 0})
        result.append({'id': identity, 'sourceFootprint': footprint(native),
                       'actualFootprint': footprint(paving), 'geometry': correspondence,
                       'wallGeometry': wall_check,
                       'pavingTriangles': len(paving), 'wallTriangles': len(walls)})
    return result
