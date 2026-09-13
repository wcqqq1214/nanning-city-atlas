import unittest
import mapbox_earcut
import numpy as np
from shapely.geometry import Point, Polygon
from check_canopy_clearance import check


class CanopyClearanceTests(unittest.TestCase):
    def test_vertical_face_cannot_bridge_an_uncovered_ground_interval(self):
        ground = np.asarray([[[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                             [[2, 0, 0], [3, 0, 0], [2, 1, 0]]])
        canopy = np.asarray([[[0, 0, .1], [1, 0, .1], [0, 1, .1]],
                             [[.1, .1, .1], [2.1, .1, .1], [2.1, .1, .2]]])
        result = check(canopy, ground)
        self.assertFalse(result['passed'])
        self.assertEqual(result['verticalFacesWithUncoveredEdges'], [1])

    def test_vertical_canopy_faces_are_checked_not_discarded(self):
        ground = np.asarray([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]])
        horizontal = [[0, 0, .1], [1, 0, .1], [0, 1, .1]]
        vertical = [[.1, .1, .1], [.4, .1, .1], [.1, .1, .2]]
        result = check(np.asarray([horizontal, vertical]), ground)
        self.assertTrue(result['passed'])
        self.assertEqual(result['verticalCanopyFacesChecked'], 1)
        vertical[0][2] = -.01
        result = check(np.asarray([horizontal, vertical]), ground)
        self.assertFalse(result['passed'])
        self.assertEqual(result['failedVerticalCanopyFaces'], [1])

    def test_explicit_coverage_tolerance_does_not_hide_large_holes(self):
        ground = np.asarray([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]])
        canopy = ground.astype(float);canopy[:, :, 0] += .00001;canopy[:, :, 2] += .1
        self.assertFalse(check(canopy, ground)['passed'])
        result = check(canopy, ground, coverage_tolerance_meters=.002)
        self.assertTrue(result['passed'])
        self.assertGreater(result['missingCoverageSquareMeters'], 0)
        canopy[:, :, 0] += .01
        self.assertFalse(check(canopy, ground, coverage_tolerance_meters=.002)['passed'])

    def test_interior_ridge_missed_by_four_samples_fails(self):
        canopy = np.asarray([[[0, 0, .1], [2, 0, .1], [0, 2, .1]]])
        # A small peak between all four production sample locations.
        coords = np.asarray([[0, 0], [2, 0], [0, 2], [.1, .1], [.3, .1], [.1, .3]])
        faces = mapbox_earcut.triangulate_float64(coords, np.asarray([3, 6], dtype=np.uint32)).reshape(-1, 3)
        ground = [[[float(x), float(y), 0] for x, y in coords[face]] for face in faces]
        for a, b in [(3, 4), (4, 5), (5, 3)]:
            ground.append([[*coords[a], 0], [*coords[b], 0], [.15, .15, .2]])
        hill = Polygon(coords[3:])
        for weights in [[1/3]*3, [.5, .5, 0], [0, .5, .5], [.5, 0, .5]]:
            point = Point(np.asarray(weights) @ canopy[0, :, :2])
            self.assertFalse(hill.intersects(point))
        ground = np.asarray(ground)
        report = check(canopy, ground)
        self.assertEqual(report['failedClearanceFaces'], 1)
        self.assertAlmostEqual(report['minimumClearanceMeters'], -10)
        self.assertFalse(report['passed'])

    def test_parallel_slopes_pass_over_different_triangulation(self):
        canopy = np.asarray([[[0, 0, .1], [1, 0, 1.1], [1, 1, 1.1]],
                             [[0, 0, .1], [1, 1, 1.1], [0, 1, .1]]])
        ground = np.asarray([[[0, 0, 0], [1, 0, 1], [0, 1, 0]],
                             [[1, 0, 1], [1, 1, 1], [0, 1, 0]]])
        report = check(canopy, ground)
        self.assertTrue(report['passed'])
        self.assertAlmostEqual(report['minimumClearanceMeters'], 10)

    def test_duplicate_ground_does_not_hide_missing_coverage(self):
        canopy = np.asarray([[[0, 0, .1], [1, 0, .1], [0, 1, .1]]])
        half = [[0, 0, 0], [.5, 0, 0], [0, 1, 0]]
        report = check(canopy, np.asarray([half, half]))
        self.assertAlmostEqual(report['missingCoverageSquareMeters'], 2500)
        self.assertFalse(report['passed'])


if __name__ == '__main__':
    unittest.main()
