"""Check continuous canopy clearance against actual native terrain triangles.

Height differences are affine on each projected triangle intersection. Their
minimum occurs at an intersection vertex, so checking every such vertex covers
the whole overlap rather than only the canopy centroid and edge midpoints.
Inputs use east/north/up coordinates, one scene unit = 100 metres.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

from prepare_building_support import TerrainSurface


def check(canopy, terrain, minimum_clearance_meters=9.5, coverage_tolerance_meters=0):
    if not np.isfinite(coverage_tolerance_meters) or coverage_tolerance_meters < 0:
        raise ValueError('Invalid coverage tolerance')
    roof = TerrainSurface(canopy)
    canopy_normals = np.cross(canopy[:, 1]-canopy[:, 0], canopy[:, 2]-canopy[:, 0])
    source_ids = np.flatnonzero(np.abs(canopy_normals[:, 2]) > 1e-12)
    ground = TerrainSurface(terrain)
    ground_shapes = shapely.polygons(ground.triangles[:, :, :2])
    roof_shapes = shapely.polygons(roof.triangles[:, :, :2])
    tree = STRtree(ground_shapes)
    minimum = float('inf')
    failed, missing_faces, pairs_checked = 0, 0, 0
    total_missing, maximum_missing = 0., 0.
    examples, failed_ids = [], []
    for start in range(0, len(roof_shapes), 512):
        shapes = roof_shapes[start:start+512]
        a, b = tree.query(shapes, predicate='intersects')
        intersections = shapely.intersection(shapes[a], ground_shapes[b])
        keep = shapely.area(intersections) > 1e-14
        a, b, intersections = a[keep], b[keep], intersections[keep]
        pairs_checked += len(a)
        points, owners = shapely.get_coordinates(intersections, return_index=True)
        if len(points):
            delta = roof.planes[start+a[owners]]-ground.planes[b[owners]]
            clearance = ((delta[:, :2]*points).sum(axis=1)+delta[:, 2])*100
            minimum = min(minimum, float(clearance.min()))
            minima = np.full(len(shapes), float('inf'))
            np.minimum.at(minima, a[owners], clearance)
            bad = np.flatnonzero(minima <= minimum_clearance_meters)
            failed += len(bad)
            failed_ids.extend(source_ids[start+bad].tolist())
            for i in bad[:max(0, 30-len(examples))]:
                examples.append({'face': int(source_ids[start+i]), 'minimumClearanceMeters': float(minima[i]),
                                 'triangle': roof.triangles[start+i].tolist()})
        # Union, not summed areas: overlaps cannot conceal a coverage hole.
        order = np.argsort(a, kind='stable')
        sorted_ids = a[order]
        groups = np.split(order, np.flatnonzero(np.diff(sorted_ids))+1) if len(order) else []
        missing = shapely.area(shapes).copy()
        for group in groups:
            i = int(a[group[0]])
            missing[i] = shapes[i].difference(shapely.union_all(intersections[group])).area
        missing *= 10000
        total_missing += float(missing.sum())
        maximum_missing = max(maximum_missing, float(missing.max()))
        missing_faces += int((missing > .01).sum())
    ground_union = shapely.union_all(ground_shapes)
    canopy_union = shapely.union_all(roof_shapes)
    raw_missing = canopy_union.difference(ground_union).area*10000
    envelope = ground_union.buffer(coverage_tolerance_meters/100) if coverage_tolerance_meters else ground_union
    bounded_missing = canopy_union.difference(envelope).area*10000
    # A triangle may become vertical at native float32 precision without losing
    # its visible area. The lower boundary consists of its three edges; test
    # each edge across every ground intersection, including interior ridge cuts.
    vertical_ids = np.flatnonzero((np.abs(canopy_normals[:, 2]) <= 1e-12) &
                                 (np.linalg.norm(canopy_normals, axis=1) > 0))
    vertical_failed, vertical_uncovered = [], []
    for index in vertical_ids:
        face = canopy[index]
        face_minimum = float('inf')
        for a3, b3 in zip(face, np.roll(face, -1, axis=0)):
            edge = b3[:2]-a3[:2]
            length2 = float(edge@edge)
            line = LineString([a3[:2], b3[:2]]) if length2 else Point(a3[:2])
            if not envelope.covers(line):
                vertical_uncovered.append(int(index))
            hits = tree.query(line, predicate='intersects')
            if not len(hits):
                vertical_uncovered.append(int(index))
                continue
            clipped = shapely.intersection(line, ground_shapes[hits])
            coordinates, owners = shapely.get_coordinates(clipped, return_index=True)
            if not len(coordinates):
                vertical_uncovered.append(int(index))
                continue
            parameter = np.clip((coordinates-a3[:2])@edge/length2, 0, 1) if length2 else np.zeros(len(coordinates))
            z = a3[2]+parameter*(b3[2]-a3[2]) if length2 else np.full(len(coordinates), min(a3[2], b3[2]))
            planes = ground.planes[hits[owners]]
            clearance = (z-(planes[:, :2]*coordinates).sum(axis=1)-planes[:, 2])*100
            face_minimum = min(face_minimum, float(clearance.min()))
        minimum = min(minimum, face_minimum)
        if face_minimum <= minimum_clearance_meters:
            vertical_failed.append(int(index))
    # Compute actual whole-region coverage once. Summing independent clipped
    # slivers can accumulate numerical overlay error even when the union covers
    # the complete canopy, so retain that sum as a diagnostic only.
    passed = failed == 0 and not vertical_failed and not vertical_uncovered and bounded_missing <= .01
    return {'passed': passed, 'scope': 'continuous native mesh overlap; compressed export and visual QA are separate',
            'canopyFaces': len(canopy), 'terrainFaces': len(terrain), 'overlapPairsChecked': pairs_checked,
            'minimumRequiredClearanceMeters': minimum_clearance_meters,
            'minimumClearanceMeters': minimum if np.isfinite(minimum) else None,
            'failedClearanceFaces': failed, 'failureExamples': examples,
            'failedClearanceFaceIndices': failed_ids,
            'verticalCanopyFacesChecked': len(vertical_ids), 'failedVerticalCanopyFaces': vertical_failed,
            'verticalFacesWithUncoveredEdges': sorted(set(vertical_uncovered)),
            'zeroAreaCanopyFaces': int((np.linalg.norm(canopy_normals, axis=1) == 0).sum()),
            'missingCoverageSquareMeters': raw_missing, 'sumOfPerFaceMissingCoverageSquareMeters': total_missing,
            'coverageToleranceMeters': coverage_tolerance_meters, 'coverageOutsideToleranceSquareMeters': bounded_missing,
            'maximumFaceMissingCoverageSquareMeters': maximum_missing,
            'facesMissingMoreThan0_01SquareMeters': missing_faces,
            'ignoredCanopyVerticalOrDegenerateFaces': roof.ignoredVerticalOrDegenerateFaces,
            'ignoredGroundVerticalOrDegenerateFaces': ground.ignoredVerticalOrDegenerateFaces}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--canopy', type=Path, required=True)
    parser.add_argument('--terrain', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--minimum-clearance-meters', type=float, default=9.5)
    parser.add_argument('--coverage-tolerance-meters', type=float, default=0)
    args = parser.parse_args()
    result = check(np.load(args.canopy)['triangles'], np.load(args.terrain)['triangles'], args.minimum_clearance_meters, args.coverage_tolerance_meters)
    result['inputs'] = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in [args.canopy, args.terrain, Path(__file__), Path(__file__).with_name('prepare_building_support.py')]}
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ['failureExamples', 'inputs']}, indent=2), flush=True)
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
