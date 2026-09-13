import unittest
import mapbox_earcut
import numpy as np
from shapely.geometry import Point, Polygon
from check_canopy_clearance import check


class CanopyClearanceTests(unittest.TestCase):
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
