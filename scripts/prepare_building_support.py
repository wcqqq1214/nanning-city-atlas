"""Measure complete building support on two actual exported terrain surfaces.

This preparation is independent of Blender's unrendered bilinear height field.
It accepts frozen/candidate terrain contexts and records their exact hashes;
support must be regenerated whenever the final terrain or footprints change.
"""
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

import DracoPy
import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import Polygon
from shapely.ops import unary_union


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind_runtime(result, paths, manifest, root):
    root=root.resolve();metadata=json.loads(manifest.read_text());hashes=metadata['inputHashes']
    if not all(name in hashes for name in ['public/data/geography.json','public/data/terrain.json']):
        raise ValueError('Context has no geography/terrain source bindings')
    for name,expected in hashes.items():
        source=(root/name).resolve();source.relative_to(root)
        if not source.is_file() or digest(source)!=expected:raise ValueError(f'Stale terrain context source: {name}')
    if digest(paths['geography'])!=hashes['public/data/geography.json']:
        raise ValueError('Building footprints and terrain context use different geography')
    result['runtimeInputs']=dict(hashes)
    result['inputs']={name:{'path':str(path.resolve().relative_to(root)),'sha256':digest(path)} for name,path in paths.items()}
    result['contextManifest']={'path':str(manifest.resolve().relative_to(root)),'sha256':digest(manifest)}
    return result


def terrain_faces(path):
    raw = path.read_bytes()
    if raw[:4] != b'glTF': raise ValueError(f'Not a GLB: {path}')
    size = struct.unpack_from('<I', raw, 12)[0]
    doc = json.loads(raw[20:20+size]); binary = 28+size
    # The city exporter bakes world transforms. Reject a different contract
    # explicitly rather than silently treating local vertices as world points.
    if any(any(k in node for k in ['matrix', 'translation', 'rotation', 'scale']) for node in doc['nodes']):
        raise ValueError('Terrain support requires the city exporter’s baked world transforms')
    result = []
    for node in doc['nodes']:
        if 'mesh' not in node or not node.get('name', '').startswith('Terrain_'): continue
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            view = doc['bufferViews'][primitive['extensions']['KHR_draco_mesh_compression']['bufferView']]
            start = binary+view.get('byteOffset', 0)
            mesh = DracoPy.decode(raw[start:start+view['byteLength']])
            # glTF east/up/south -> scene east/north/up, in 100 m units.
            faces = np.asarray(mesh.points[mesh.faces], dtype=np.float64)[:, :, [0, 2, 1]]
            faces[:, :, 1] *= -1
            result.append(faces)
    if not result: raise ValueError(f'No actual terrain mesh in {path}')
    return np.concatenate(result)


def geometry_points(geometry):
    if geometry.is_empty: return []
    if geometry.geom_type == 'Polygon':
        return list(geometry.exterior.coords)+[p for ring in geometry.interiors for p in ring.coords]
    if hasattr(geometry, 'geoms'):
        return [p for piece in geometry.geoms for p in geometry_points(piece)]
    return list(geometry.coords)


class TerrainSurface:
    def __init__(self, triangles):
        triangles = np.asarray(triangles, dtype=np.float64)
        if triangles.ndim != 3 or triangles.shape[1:] != (3, 3) or not np.isfinite(triangles).all():
            raise ValueError('Expected finite east/north/up triangles')
        a = triangles[:, 1]-triangles[:, 0]; b = triangles[:, 2]-triangles[:, 0]
        determinant = a[:, 0]*b[:, 1]-a[:, 1]*b[:, 0]
        keep = np.abs(determinant) > 1e-12
        self.ignoredVerticalOrDegenerateFaces = int((~keep).sum())
        self.triangles = triangles[keep]
        if not len(self.triangles): raise ValueError('No horizontal terrain coverage')
        a, b, determinant = a[keep], b[keep], determinant[keep]
        ax = (a[:, 2]*b[:, 1]-a[:, 1]*b[:, 2])/determinant
        ay = (a[:, 0]*b[:, 2]-a[:, 2]*b[:, 0])/determinant
        intercept = self.triangles[:, 0, 2]-ax*self.triangles[:, 0, 0]-ay*self.triangles[:, 0, 1]
        self.planes = np.column_stack((ax, ay, intercept))
        xy = self.triangles[:, :, :2]
        self.centers = xy.mean(axis=1)
        self.radius = float(np.linalg.norm(xy-self.centers[:, None, :], axis=2).max())
        self.low, self.high = xy.min(axis=1), xy.max(axis=1)
        self.tree = cKDTree(self.centers)

    def bounds(self, footprint, coverage_tolerance_meters=.05):
        if not footprint.is_valid or footprint.is_empty or footprint.area <= 0:
            raise ValueError('Invalid building footprint')
        west, south, east, north = footprint.bounds
        center = ((west+east)/2, (south+north)/2)
        radius = math.hypot(east-west, north-south)/2+self.radius
        nearby = sorted(self.tree.query_ball_point(center, radius+1e-9))
        clipped_shapes = []; witnesses = []
        for i in nearby:
            lo, hi = self.low[i], self.high[i]
            if lo[0] > east or hi[0] < west or lo[1] > north or hi[1] < south: continue
            clipped = Polygon(self.triangles[i, :, :2]).intersection(footprint)
            points = geometry_points(clipped)
            if not points: continue
            points = np.asarray(points)
            z = np.column_stack((points, np.ones(len(points))))@self.planes[i]
            for index in [int(z.argmin()), int(z.argmax())]:
                witnesses.append([float(points[index, 0]), float(points[index, 1]), float(z[index])])
            if clipped.area > 0: clipped_shapes.append(clipped)
        if not clipped_shapes:
            return {'status': 'missing-terrain', 'coveredFraction': 0.0, 'uncoveredAreaSquareMeters': footprint.area*10000}
        coverage = unary_union(clipped_shapes)
        missing = footprint.difference(coverage)
        unsupported = footprint.difference(coverage.buffer(coverage_tolerance_meters/100))
        low = min(witnesses, key=lambda p: (p[2], p[0], p[1]))
        high = max(witnesses, key=lambda p: (p[2], p[0], p[1]))
        return {'status': 'covered' if unsupported.area < 1e-10 else 'incomplete-terrain',
                'minimumSceneZ': low[2], 'maximumSceneZ': high[2],
                'minimumWitnessSceneXYZ': low, 'maximumWitnessSceneXYZ': high,
                'coveredFraction': min(1.0, coverage.area/footprint.area),
                'uncoveredAreaSquareMeters': missing.area*10000,
                'uncoveredBeyondToleranceSquareMeters': unsupported.area*10000,
                'coverageToleranceMeters': coverage_tolerance_meters,
                'intersectingFaces': len(clipped_shapes)}


def prepare(geography, surfaces):
    if geography['metersPerUnit'] != 100: raise ValueError('Expected 100 m scene units')
    buildings = [b for b in geography['buildings'] if b.get('qualityGeometry') or b.get('massing')]
    records = []
    for building in buildings:
        shape = Polygon(building['rings'][0], building['rings'][1:])
        profiles = {name: surface.bounds(shape) for name, surface in surfaces.items()}
        complete = all(p['status'] == 'covered' for p in profiles.values())
        record = {'id': building['id'], 'sourceRef': building.get('sourceRef'), 'blockId': building.get('blockId'),
                  'footprintHash': hashlib.sha256(json.dumps(building['rings'], separators=(',', ':')).encode()).hexdigest(),
                  'profiles': profiles, 'status': 'supported' if complete else 'review-required'}
        if all('minimumSceneZ' in p for p in profiles.values()):
            low = min(p['minimumSceneZ'] for p in profiles.values())
            high = max(p['maximumSceneZ'] for p in profiles.values())
            record['groundRangeSceneZ'] = [low, high]
            record['reliefMeters'] = (high-low)*100
        records.append(record)
    relief = [r['reliefMeters'] for r in records if 'reliefMeters' in r]
    return {'status': 'candidate support; final terrain/context consistency and city export pending',
            'method': 'Exact affine extrema over actual terrain triangles clipped by complete building footprints, including holes',
            'metersPerUnit': 100, 'records': records,
            'statistics': {'buildings': len(records), 'supported': sum(r['status'] == 'supported' for r in records),
                           'reviewRequired': sum(r['status'] != 'supported' for r in records),
                           'reliefMetersP50': float(np.percentile(relief, 50)) if relief else None,
                           'reliefMetersP95': float(np.percentile(relief, 95)) if relief else None,
                           'reliefMetersMaximum': max(relief, default=None)},
            'limitations': ['Ground under each footprint is measured; this does not certify entrance access or platform design',
                            'Large relief needs site review; a tall foundation skirt is not itself a terrain solution',
                            'Buildings hidden by city landmarks, railways or roads are included until visibility is resolved']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geography', type=Path, required=True)
    parser.add_argument('--detail', type=Path, required=True)
    parser.add_argument('--smooth', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--context-sources', type=Path, help='Bind a city support plan to current terrain context sources')
    args = parser.parse_args()
    surfaces = {}
    for name in ['detail', 'smooth']:
        print(f'Decoding {name} terrain...', flush=True)
        surfaces[name] = TerrainSurface(terrain_faces(getattr(args, name)))
    result = prepare(json.loads(args.geography.read_text()), surfaces)
    result['inputs'] = {name: {'path': str(path), 'sha256': digest(path)} for name, path in
                       [('geography', args.geography), ('detail', args.detail), ('smooth', args.smooth)]}
    result['tools'] = {str(Path(__file__).name): digest(Path(__file__))}
    if args.context_sources:
        bind_runtime(result,{name:getattr(args,name) for name in ['geography','detail','smooth']},args.context_sources,Path(__file__).resolve().parents[1])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result['statistics'], indent=2))
