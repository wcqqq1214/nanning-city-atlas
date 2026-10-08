"""Check canopy clearance against a piecewise affine mountain requirement.

The requirement is 9.5 m times the source mountain canopy factor. Splitting
each actual canopy/ground intersection at factor boundaries makes its residual
affine on every piece; all piece vertices are checked, including vertical edges.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

from check_canopy_clearance import check as check_coverage
from prepare_building_support import TerrainSurface


class Requirement:
    def __init__(self, triangles, default_meters):
        values = np.asarray(triangles, dtype=float)
        if not np.isfinite(values).all() or not np.isfinite(default_meters) or default_meters <= 0:
            raise ValueError('Invalid clearance requirement')
        self.surface = TerrainSurface(values)
        if len(self.surface.triangles) != len(values) or np.any(values[:, :, 2] <= 0):
            raise ValueError('Requirement must contain positive, nonvertical triangles')
        self.shapes = shapely.polygons(values[:, :, :2])
        self.tree = STRtree(self.shapes)
        self.domain = shapely.union_all(self.shapes)
        self.default = default_meters / 100
        self.minimum_meters = min(default_meters, float(values[:, :, 2].min())*100)

    def margin(self, geometry, clearance_plane):
        hits = self.tree.query(geometry, predicate='intersects')
        pieces = shapely.intersection(geometry, self.shapes[hits])
        coordinates, owners = shapely.get_coordinates(pieces, return_index=True)
        margins, points = [], []
        if len(coordinates):
            delta = clearance_plane-self.surface.planes[hits[owners]]
            margins.extend(((delta[:, :2]*coordinates).sum(axis=1)+delta[:, 2])*100)
            points.extend(coordinates)
        # Areas outside the mountain source retain the ordinary 9.5 m rule.
        coordinates = shapely.get_coordinates(geometry.difference(self.domain))
        if len(coordinates):
            margins.extend((coordinates@clearance_plane[:2]+clearance_plane[2]-self.default)*100)
            points.extend(coordinates)
        if not margins:
            raise ValueError('No requirement evaluated over a nonempty intersection')
        index = int(np.argmin(margins))
        return float(margins[index]), np.asarray(points[index]).tolist()


def check(canopy, terrain, requirement_triangles, default_meters=9.5, coverage_tolerance_meters=.002):
    requirement = Requirement(requirement_triangles, default_meters)
    coverage = check_coverage(canopy, terrain, requirement.minimum_meters, coverage_tolerance_meters)
    roof, ground = TerrainSurface(canopy), TerrainSurface(terrain)
    normals = np.cross(canopy[:, 1]-canopy[:, 0], canopy[:, 2]-canopy[:, 0])
    horizontal = np.flatnonzero(abs(normals[:, 2]) > 1e-12)
    shapes = shapely.polygons(ground.triangles[:, :, :2])
    tree = STRtree(shapes)
    minimum, worst = float('inf'), None
    failed, pairs = set(), 0

    def evaluate(face, geometry, plane):
        nonlocal minimum, worst, pairs
        margin, xy = requirement.margin(geometry, plane)
        pairs += 1
        if margin < minimum:
            minimum, worst = margin, {'canopyFace': int(face), 'xy': xy, 'marginMeters': margin}
        if margin <= 0:
            failed.add(int(face))

    for index, triangle in enumerate(roof.triangles):
        polygon = shapely.Polygon(triangle[:, :2])
        hits = tree.query(polygon, predicate='intersects')
        pieces = shapely.intersection(polygon, shapes[hits])
        for other, piece in zip(hits, pieces):
            if piece.area > 1e-14:
                evaluate(horizontal[index], piece, roof.planes[index]-ground.planes[other])
    vertical = np.flatnonzero((abs(normals[:, 2]) <= 1e-12) & (np.linalg.norm(normals, axis=1) > 0))
    for index in vertical:
        triangle = canopy[index]
        for a, b in zip(triangle, np.roll(triangle, -1, axis=0)):
            edge = b[:2]-a[:2]
            length2 = float(edge@edge)
            line = LineString([a[:2], b[:2]]) if length2 else Point(a[:2])
            slope = edge*(b[2]-a[2])/length2 if length2 else np.zeros(2)
            height_plane = np.r_[slope, a[2]-slope@a[:2] if length2 else min(a[2], b[2])]
            for other in tree.query(line, predicate='intersects'):
                piece = line.intersection(shapes[other])
                if not piece.is_empty:
                    evaluate(index, piece, height_plane-ground.planes[other])
    return {'passed': bool(coverage['passed'] and not failed and np.isfinite(minimum)),
            'scope': 'actual canopy/terrain intersections split by source requirement boundaries',
            'coverageAndMinimumFloor': coverage,
            'minimumRequiredClearanceMeters': requirement.minimum_meters,
            'outsideMountainRequiredClearanceMeters': default_meters,
            'minimumMarginMeters': minimum if np.isfinite(minimum) else None,
            'worstLocation': worst, 'intersectionsChecked': pairs,
            'failedFaceIndices': sorted(failed), 'verticalFacesChecked': len(vertical)}


def from_plan(plan):
    weights = np.asarray(plan['weights'], dtype=float)
    factor = plan['source']['canopyRiseFactor']
    if not np.isfinite(weights).all() or np.any((weights < 0) | (weights > 1)) or not 0 < factor <= 1:
        raise ValueError('Invalid mountain canopy weights or factor')
    values = .095*(1-(1-factor)*weights)
    return np.column_stack([plan['points'], values])[plan['triangles']]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='NPZ with actual canopy and terrain arrays')
    parser.add_argument('--mountain-plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = np.load(args.input)
    report = check(data['canopy'], data['terrain'], from_plan(json.loads(args.mountain_plan.read_text())))
    report['inputs'] = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in [args.input, args.mountain_plan, Path(__file__),
                                  Path(__file__).with_name('check_canopy_clearance.py')]}
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['inputs','coverageAndMinimumFloor']}, indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
