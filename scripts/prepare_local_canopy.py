"""Recut a woodland candidate along final native terrain within explicit domains.

Existing coverage, clearings, crowns and all outside faces remain unchanged.
This writes a candidate only; rebuilding the city and checking its compressed
meshes is required before accepting the candidate.
"""
import argparse
from collections import defaultdict
import copy
import hashlib
import json
from pathlib import Path

import mapbox_earcut
import numpy as np
import shapely
from shapely.geometry import Point, Polygon, box
from shapely.strtree import STRtree
from conform_canopy_edges import conform_edges

# Match the existing source-plan validator: one scene unit is 100 metres,
# so this is one square millimetre. The aggregate coverage gate below still
# rejects a patch when omitted fragments accumulate beyond 0.01 square metres.
MIN_CANOPY_AREA = 1e-10

class CoverageError(ValueError):
    def __init__(self, report):
        self.report = report
        super().__init__('Canopy coverage changed: '+json.dumps(report))


def polygons(geometry):
    if geometry.geom_type == 'Polygon':
        yield geometry
    elif hasattr(geometry, 'geoms'):
        for child in geometry.geoms:
            yield from polygons(child)


def align_partition_vertices(terrain, domain, tolerance):
    """Unify nearby float32 axis stations without rounding woodland boundaries."""
    result = terrain.copy()
    anchors = shapely.get_coordinates(domain)
    for axis in [0, 1]:
        values, inverse = np.unique(terrain[:, :, axis], return_inverse=True)
        mapped = values.copy()
        reference = np.unique(anchors[:, axis])
        start = 0
        while start < len(values):
            stop = int(np.searchsorted(values, values[start]+tolerance, side='right'))
            group = values[start:stop]
            target = float(np.median(group))
            nearby = reference[np.abs(reference-target) <= tolerance]
            if len(nearby):
                nearest = float(nearby[np.argmin(np.abs(nearby-target))])
                if np.max(np.abs(group-nearest)) <= tolerance:
                    target = nearest
            mapped[start:stop] = target
            start = stop
        result[:, :, axis] = mapped[inverse].reshape(terrain.shape[:2])
    return result


def partition_cells(partition, allowed, merge_coplanar=False):
    """Remove redundant cuts only when all grouped vertices share one plane.

    Group keys merely find candidates. The independent residual bound decides
    whether a group can merge; rounding never changes any ground coordinate.
    """
    shapes = shapely.polygons(partition[:, :, :2])
    indices = STRtree(shapes).query(allowed, predicate='intersects')
    if not merge_coplanar:
        return shapes[indices], {'sourcePartitionFaces': len(indices), 'partitionCells': len(indices)}
    faces = partition[indices]
    normal = np.cross(faces[:, 1]-faces[:, 0], faces[:, 2]-faces[:, 0])
    slopes = -normal[:, :2]/normal[:, 2, None]
    planes = np.column_stack((slopes, faces[:, 0, 2]-(slopes*faces[:, 0, :2]).sum(axis=1)))
    groups = defaultdict(list)
    for i, plane in enumerate(planes):
        groups[tuple(np.round(plane, 8))].append(i)
    cells, maximum_residual = [], 0.
    for group in groups.values():
        vertices = faces[group].reshape(-1, 3)
        plane = planes[group[0]]
        residual = float(np.max(np.abs(vertices[:, 2]-vertices[:, :2]@plane[:2]-plane[2])))
        if len(group) == 1 or residual > 1e-8:
            cells.extend(shapes[indices[group]])
            continue
        maximum_residual = max(maximum_residual, residual)
        # Zero tolerance removes collinear internal stations, not curved edges.
        cells.extend(polygons(shapely.union_all(shapes[indices[group]]).simplify(0)))
    return cells, {'sourcePartitionFaces': len(indices), 'partitionCells': len(cells),
                   'maximumMergedPlaneResidualMeters': maximum_residual*100}


def recut(mesh, terrain, domain, partition_tolerance_meters=0, merge_coplanar=False):
    if partition_tolerance_meters < 0:
        raise ValueError('Negative partition precision')
    original = np.asarray(mesh['points'], dtype=float)[mesh['triangles']]
    shapes = shapely.polygons(original[:, :, :2])
    old_tree = STRtree(shapes)
    touched = np.asarray(shapely.intersects(shapes, domain))
    if not touched.any():
        return copy.deepcopy(mesh), {'changed': False}
    allowed = shapely.union_all(shapes[touched]).intersection(domain)
    normal = np.cross(terrain[:, 1]-terrain[:, 0], terrain[:, 2]-terrain[:, 0])
    terrain = terrain[np.abs(normal[:, 2]) > 1e-12]
    # Optional candidate experiment: unify nearby float32 cut coordinates.
    # This affects canopy partition lines only, never the ground or coverage.
    # Runtime clearance and actual export checks remain mandatory.
    partition = align_partition_vertices(terrain, domain, partition_tolerance_meters/100) if partition_tolerance_meters else terrain
    cells, partition_report = partition_cells(partition, allowed, merge_coplanar)
    points, triangles, colors, lookup = [], [], [], {}
    coefficients = {}

    def rise(x, y):
        point = Point(x, y)
        hits = old_tree.query(point, predicate='intersects')
        index = int(hits[0]) if len(hits) else int(old_tree.nearest(point))
        if shapes[index].distance(point) > 1e-7:
            raise ValueError('New canopy vertex lies outside original woodland')
        if index not in coefficients:
            vertices = original[index]
            coefficients[index] = np.linalg.solve(np.column_stack((vertices[:, :2], np.ones(3))), vertices[:, 2])
        return float(coefficients[index] @ [x, y, 1])

    def vertex(value):
        key = tuple(value)
        if key not in lookup:
            lookup[key] = len(points)
            points.append(list(value))
        return lookup[key]

    def add(geometry, color):
        for polygon in polygons(geometry):
            if polygon.area <= 1e-12:
                continue
            rings = [list(r.coords)[:-1] for r in [polygon.exterior, *polygon.interiors]]
            coords = np.asarray([p for ring in rings for p in ring], dtype=float)
            faces = mapbox_earcut.triangulate_float64(coords, np.cumsum([len(r) for r in rings], dtype=np.uint32)).reshape(-1, 3)
            ids = [vertex([float(x), float(y), rise(x, y)]) for x, y in coords]
            for face in faces:
                indices = [ids[int(i)] for i in face]
                a, b, c = np.asarray([points[i] for i in indices])
                cross = np.cross(b-a, c-a)[2]
                if abs(cross)/2 <= MIN_CANOPY_AREA:
                    continue
                triangles.append(indices if cross > 0 else indices[::-1])
                colors.append(color)

    outside = 0
    for i, shape in enumerate(shapes):
        if not touched[i]:
            triangles.append([vertex(p) for p in original[i].tolist()])
            colors.append(mesh['colors'][i])
            outside += 1
        else:
            add(shape.difference(domain), mesh['colors'][i])
    for cell in cells:
        part = cell.intersection(allowed)
        if part.area <= 1e-12:
            continue
        source = int(old_tree.nearest(part.representative_point()))
        add(part, mesh['colors'][source])
    result = {'points': points, 'triangles': triangles, 'colors': colors}
    # Recutting only one side of a boundary leaves a T-junction. Once the
    # vertices sample non-planar ground, its long neighbour edge opens a crack.
    result, edge_report = conform_edges(result, domain, minimum_area=MIN_CANOPY_AREA)
    before = shapely.union_all(shapes)
    after_shapes = shapely.polygons(np.asarray(result['points'])[result['triangles']][:, :, :2])
    after = shapely.union_all(after_shapes)
    difference = before.symmetric_difference(after).area * 10000
    overlap = (shapely.area(after_shapes).sum()-after.area) * 10000
    original_overlap = (shapely.area(shapes).sum()-before.area) * 10000
    # Preserve pre-existing millimetre rounding slivers outside this patch;
    # reject additional overlap instead of claiming the source was perfect.
    if difference > .01 or overlap-original_overlap > .01:
        missing = before.difference(after)
        added = after.difference(before)
        raise CoverageError({'differenceSquareMeters': difference, 'overlapSquareMeters': float(overlap),
                             'originalOverlapSquareMeters': float(original_overlap),
                             'missingSquareMeters': missing.area*10000, 'addedSquareMeters': added.area*10000,
                             'largestMissingPieces': [dict(areaSquareMeters=p.area*10000, bounds=list(p.bounds))
                                                      for p in sorted(polygons(missing), key=lambda p: -p.area)[:10]]})
    return result, {'changed': True, 'originalTriangles': len(original), 'candidateTriangles': len(result['triangles']),
                    'conformingEdges': edge_report,
                    'partitionToleranceMeters': partition_tolerance_meters,
                    'maximumPartitionAxisShiftMeters': float(np.max(np.abs(partition[:, :, :2]-terrain[:, :, :2]))*100),
                    'outsideTrianglesCopiedExactly': outside, 'coverageDifferenceSquareMeters': difference,
                    'overlapSquareMeters': overlap, 'originalOverlapSquareMeters': original_overlap,
                    'additionalOverlapSquareMeters': overlap-original_overlap,
                    'mergeCoplanarPartitions': merge_coplanar, **partition_report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forest', type=Path, required=True)
    parser.add_argument('--terrain-directory', type=Path, required=True)
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--partition-tolerance-meters', type=float, default=0)
    parser.add_argument('--merge-coplanar', action='store_true')
    args = parser.parse_args()
    registry = json.loads(args.registry.read_text())
    sources = [args.forest, args.registry, Path(__file__).resolve(), Path(__file__).with_name('conform_canopy_edges.py').resolve()]
    domains = []
    for entry in registry['plans']:
        path = args.root/entry['path']
        payload = json.loads(path.read_text())
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Stale reservoir registry')
        domains.append(box(*payload['bounds']))
        sources.append(path)
    domain = shapely.union_all(domains)
    plan = json.loads(args.forest.read_text())
    report = {'status': 'candidate only; runtime, compressed mesh and visual checks pending', 'regions': {}}
    for profile in ['detail', 'smooth']:
        source = args.terrain_directory/(profile+'.npz')
        sources.append(source)
        terrain = np.load(source)['triangles']
        for region in plan['regions']:
            try:
                region[profile], record = recut(region[profile], terrain, domain, args.partition_tolerance_meters, args.merge_coplanar)
            except CoverageError as error:
                report['status'] = 'rejected: canopy coverage regression; candidate not written'
                report['failure'] = {'region': region['id'], 'profile': profile, **error.report}
                report['inputs'] = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
                args.output.with_suffix('.report.json').write_text(json.dumps(report, indent=2)+'\n')
                raise
            report['regions'][region['id']+'/'+profile] = record
            print(region['id'], profile, record, flush=True)
    report['inputs'] = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    plan['localTerrainCanopy'] = report
    args.output.write_text(json.dumps(plan, ensure_ascii=False, separators=(',', ':'))+'\n')
    args.output.with_suffix('.report.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
