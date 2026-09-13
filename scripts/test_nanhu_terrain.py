"""A removed coarse cell cannot substitute for the native Nanhu patch."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'blender'))
from nanhu_terrain import build_surface


class NanhuSurfaceTests(unittest.TestCase):
    def test_native_diagonal_differs_from_bilinear_or_reversed_diagonal(self):
        mesh = {'points': [[0, 0], [1, 0], [1, 1], [0, 1]],
                'triangles': [[0, 1, 2], [0, 2, 3]]}
        ground = lambda x, y: (x-10)*(y-20)
        surface = build_surface([mesh], (10, 20), ground)
        self.assertAlmostEqual(surface.sample(10.5, 20.5), .5)
        self.assertAlmostEqual(ground(10.5, 20.5), .25)
        self.assertAlmostEqual(surface.sample(10.75, 20.25), .25)
        self.assertIsNone(surface.sample(9, 20))

    def test_explicit_water_hole_is_not_filled(self):
        meshes = [{'points': [[0, 0], [1, 0], [0, 1]], 'triangles': [[0, 1, 2]]},
                  {'points': [[2, 2], [3, 2], [3, 3]], 'triangles': [[0, 1, 2]]}]
        surface = build_surface(meshes, (0, 0), lambda x, y: 4)
        self.assertEqual(surface.sample(.1, .1), 4)
        self.assertIsNone(surface.sample(1.5, 1.5))


if __name__ == '__main__':
    unittest.main()
