"""Test complete-footprint terrain extrema, holes, discontinuities and coverage."""
import unittest

import numpy as np
from shapely.geometry import Polygon, box

from prepare_building_support import TerrainSurface, prepare


def plane_square(w=0, s=0, e=2, n=2, lift=0):
    points = [(x, y, 2*x+3*y+lift) for x, y in [(w, s), (e, s), (e, n), (w, n)]]
    return np.array([[points[i] for i in tri] for tri in [(0, 1, 2), (0, 2, 3)]])


class SupportTests(unittest.TestCase):
    def test_plane_extrema_at_clipped_vertices(self):
        surface = TerrainSurface(plane_square())
        result = surface.bounds(box(.5, .5, 1.5, 1.5))
        self.assertEqual(result['status'], 'covered')
        self.assertAlmostEqual(result['minimumSceneZ'], 2.5)
        self.assertAlmostEqual(result['maximumSceneZ'], 7.5)
        self.assertEqual(result['minimumWitnessSceneXYZ'], [.5, .5, 2.5])
        self.assertEqual(result['maximumWitnessSceneXYZ'], [1.5, 1.5, 7.5])
        self.assertAlmostEqual(result['coveredFraction'], 1)

    def test_interior_peak_and_courtyard_exclusion(self):
        corners = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]
        triangles = [[a, b, [.5, .5, 10]] for a, b in zip(corners, corners[1:]+corners[:1])]
        surface = TerrainSurface(triangles)
        footprint = box(.1, .1, .9, .9)
        self.assertAlmostEqual(surface.bounds(footprint)['maximumSceneZ'], 10)
        courtyard = footprint.difference(box(.4, .4, .6, .6))
        measured = surface.bounds(courtyard)
        self.assertEqual(measured['status'], 'covered')
        self.assertAlmostEqual(measured['maximumSceneZ'], 8)
        self.assertAlmostEqual(measured['minimumSceneZ'], 2)

    def test_vertical_faces_do_not_supply_ground(self):
        faces = np.concatenate([plane_square(), np.array([[[0, 0, 0], [1, 0, 50], [2, 0, 0]]])])
        surface = TerrainSurface(faces)
        self.assertEqual(surface.ignoredVerticalOrDegenerateFaces, 1)
        self.assertEqual(surface.bounds(box(.5, .5, 1, 1))['maximumSceneZ'], 5)

    def test_partial_and_missing_coverage(self):
        surface = TerrainSurface(plane_square()[:1])
        measured = surface.bounds(box(0, 0, 2, 2))
        self.assertEqual(measured['status'], 'incomplete-terrain')
        self.assertAlmostEqual(measured['coveredFraction'], .5)
        self.assertGreater(measured['uncoveredBeyondToleranceSquareMeters'], 19000)
        self.assertEqual(surface.bounds(box(5, 5, 6, 6))['status'], 'missing-terrain')

    def test_quantization_gap_tolerance_does_not_hide_real_void(self):
        for half_gap, expected in [(.0001, 'covered'), (.01, 'incomplete-terrain')]:
            faces = np.concatenate([plane_square(e=.5-half_gap, n=1),
                                    plane_square(w=.5+half_gap, e=1, n=1)])
            result = TerrainSurface(faces).bounds(box(0, 0, 1, 1))
            self.assertEqual(result['status'], expected)
            self.assertGreater(result['uncoveredAreaSquareMeters'], 0)

    def test_union_of_profile_extrema_and_source_scope(self):
        footprints = [[[.5, .5], [1.5, .5], [1.5, 1.5], [.5, 1.5], [.5, .5]]]
        geography = {'metersPerUnit': 100, 'buildings': [
            {'id': 'changed', 'qualityGeometry': True, 'rings': footprints},
            {'id': 'unchanged', 'rings': footprints}]}
        surfaces = {'detail': TerrainSurface(plane_square()), 'smooth': TerrainSurface(plane_square(lift=2))}
        result = prepare(geography, surfaces)
        self.assertEqual(result['statistics']['buildings'], 1)
        self.assertEqual(result['records'][0]['groundRangeSceneZ'], [2.5, 9.5])
        self.assertEqual(result['records'][0]['status'], 'supported')
        self.assertEqual(geography['buildings'][0]['rings'], footprints)

    def test_invalid_input_is_rejected(self):
        with self.assertRaises(ValueError): TerrainSurface([[[0, 0, 0], [1, 0, 0], [0, 1, float('nan')]]])
        with self.assertRaises(ValueError): TerrainSurface([[[0, 0, 0], [1, 0, 0], [2, 0, 0]]])
        surface = TerrainSurface(plane_square())
        with self.assertRaises(ValueError): surface.bounds(Polygon())
        with self.assertRaises(ValueError): prepare({'metersPerUnit': 1}, {})


if __name__ == '__main__': unittest.main()
