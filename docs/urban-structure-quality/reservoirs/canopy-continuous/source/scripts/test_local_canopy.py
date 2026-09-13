"""Regression: a ridge between old canopy vertices must not pierce foliage."""
import unittest
import numpy as np
from shapely.geometry import Polygon, box
from prepare_local_canopy import CoverageError, partition_cells, recut


class LocalCanopyTests(unittest.TestCase):
    def test_coplanar_merge_removes_internal_cuts_but_preserves_ridge(self):
        terrain = []
        for x0, x1 in [(0, .5), (.5, 1), (1, 1.5), (1.5, 2)]:
            quad = [[x, y, 1-abs(x-1)] for x, y in [(x0, 0), (x1, 0), (x1, 2), (x0, 2)]]
            terrain.extend([[quad[i] for i in face] for face in [(0, 1, 2), (0, 2, 3)]])
        mesh = {'points': [[0, 0, .1], [2, 0, .1], [2, 2, .1], [0, 2, .1]],
                'triangles': [[0, 1, 2], [0, 2, 3]], 'colors': [1, 1]}
        candidate, record = recut(mesh, np.asarray(terrain), box(0, 0, 2, 2), merge_coplanar=True)
        self.assertEqual(record['candidateTriangles'], 4)
        self.assertEqual(record['partitionCells'], 2)
        for triangle in np.asarray(candidate['points'])[candidate['triangles']]:
            self.assertFalse(triangle[:, 0].min() < 1 < triangle[:, 0].max())
        self.assertLess(record['coverageDifferenceSquareMeters'], 1e-8)

    def test_plane_group_rounding_does_not_authorize_merge(self):
        # Equal rounded slopes over a long footprint still have a real seam.
        terrain = np.asarray([[[0, 0, 0], [100, 0, 0], [0, 1, 0]],
                              [[0, 1, 0], [100, 0, 4e-7], [100, 1, 4e-7]]])
        cells, report = partition_cells(terrain, box(-1, -1, 101, 2), True)
        self.assertEqual(len(cells), 2)
        self.assertEqual(report['maximumMergedPlaneResidualMeters'], 0)

    def test_ridge_recut_keeps_clearings_and_outside_faces(self):
        # Four strips surround an open courtyard, plus an unrelated triangle.
        polygons = [box(0, 0, 2, .5), box(0, 1.5, 2, 2),
                    box(0, .5, .5, 1.5), box(1.5, .5, 2, 1.5)]
        points, faces = [], []
        for polygon in polygons:
            coords = list(polygon.exterior.coords)[:-1]
            start = len(points)
            points.extend([[x, y, .1] for x, y in coords])
            faces.extend([[start, start+1, start+2], [start, start+2, start+3]])
        start = len(points)
        outside = [[4, 0, .2], [5, 0, .3], [4, 1, .4]]
        points.extend(outside); faces.append([start, start+1, start+2])
        source = {'points': points, 'triangles': faces, 'colors': [1]*8+[2]}
        terrain = []
        for x0, x1 in [(0, 1), (1, 2)]:
            quad = [[x, y, 1-abs(x-1)] for x, y in [(x0, 0), (x1, 0), (x1, 2), (x0, 2)]]
            terrain.extend([[quad[i] for i in face] for face in [(0, 1, 2), (0, 2, 3)]])
        # The original bottom face is flat at 0.1 above a 1.0 ridge.
        self.assertLess(.1-(1-abs(1-1)), 0)
        candidate, record = recut(source, np.asarray(terrain), box(0, 0, 2, 2))
        self.assertEqual(record['outsideTrianglesCopiedExactly'], 1)
        self.assertLess(record['coverageDifferenceSquareMeters'], .000001)
        actual = np.asarray(candidate['points'])[candidate['triangles']]
        self.assertTrue(any(np.array_equal(face, outside) for face in actual))
        courtyard = box(.5, .5, 1.5, 1.5)
        for face in actual:
            if face[:, 0].min() >= 4:
                continue
            self.assertLess(Polygon(face[:, :2]).intersection(courtyard).area, 1e-12)
            height = 1-np.abs(face[:, 0]-1)+face[:, 2]
            for weights in [[1/3]*3, [.5, .5, 0], [0, .5, .5], [.5, 0, .5]]:
                x = np.asarray(weights) @ face[:, 0]
                clearance = np.asarray(weights) @ height-(1-abs(x-1))
                self.assertAlmostEqual(clearance, .1)

    def test_unaffected_mesh_is_identical(self):
        mesh = {'points': [[0, 0, .1], [1, 0, .2], [0, 1, .3]],
                'triangles': [[0, 1, 2]], 'colors': [2]}
        result, record = recut(mesh, np.zeros((0, 3, 3)), box(3, 3, 4, 4))
        self.assertEqual(result, mesh)
        self.assertFalse(record['changed'])

    def test_missing_native_ground_is_rejected(self):
        mesh = {'points': [[0, 0, .1], [1, 0, .1], [0, 1, .1]],
                'triangles': [[0, 1, 2]], 'colors': [1]}
        terrain = np.asarray([[[0, 0, 0], [.9, 0, 0], [0, 1, 0]]])
        with self.assertRaises(CoverageError) as caught:
            recut(mesh, terrain, box(-1, -1, 2, 2))
        self.assertGreater(caught.exception.report['missingSquareMeters'], 400)

    def test_partition_precision_does_not_snap_woodland_boundary(self):
        mesh = {'points': [[.1234567, .1234567, .1], [.9876543, .1234567, .1], [.1234567, .9876543, .1]],
                'triangles': [[0, 1, 2]], 'colors': [1]}
        terrain = np.asarray([[[0, 0, 0], [2, 0, 0], [0, 2, 0]]])
        result, record = recut(mesh, terrain, box(0, 0, 1, 1), partition_tolerance_meters=.002)
        self.assertLess(record['coverageDifferenceSquareMeters'], 1e-8)
        self.assertEqual({tuple(p[:2]) for p in mesh['points']}, {tuple(p[:2]) for p in result['points']})

    def test_submillimetre_native_seam_is_closed_without_coverage_loss(self):
        mesh = {'points': [[0, 0, .1], [2, 0, .1], [2, 1, .1], [0, 1, .1]],
                'triangles': [[0, 1, 2], [0, 2, 3]], 'colors': [1, 1]}
        terrain = []
        for west, east in [(0, 1), (1.000006, 2)]:
            quad = [[west, 0, 0], [east, 0, 0], [east, 1, 0], [west, 1, 0]]
            terrain.extend([[quad[i] for i in face] for face in [[0, 1, 2], [0, 2, 3]]])
        with self.assertRaises(CoverageError):
            recut(mesh, np.asarray(terrain), box(0, 0, 2, 1))
        _, record = recut(mesh, np.asarray(terrain), box(0, 0, 2, 1), .002)
        self.assertLess(record['coverageDifferenceSquareMeters'], 1e-8)
        self.assertLess(record['maximumPartitionAxisShiftMeters'], .00031)


if __name__ == '__main__':
    unittest.main()
