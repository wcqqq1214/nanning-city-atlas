"""A removed coarse cell cannot substitute for the native Nanhu patch."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'blender'))
from nanhu_terrain import build_surface
import nanhu_landmark


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

    def test_outer_edge_matches_coarse_surface_without_moving_interior(self):
        mesh = {'points': [[0, 0], [0, 1], [0, 2], [1, 1]],
                'triangles': [[0, 3, 1], [1, 3, 2]]}
        ground = lambda x, y: (x-10)**2+(y-20)**2
        coarse = lambda x, y: 2*(y-20)
        plan = {'terrainPatch': {'bounds': [0, 0, 2, 2], 'meshes': [mesh]},
                'park': [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]}
        class Batch:
            def __init__(self): self.faces = []
            def face(self, vertices, material): self.faces.append(vertices)
        with patch.object(nanhu_landmark, 'PLAN', plan):
            vertices = nanhu_landmark.terrain_vertices(mesh, (10, 20), ground, coarse)
            self.assertEqual(vertices[1], (10, 21, 2))
            self.assertEqual(vertices[3], (11, 21, 2))
            legacy = nanhu_landmark.terrain_vertices(mesh, (10, 20), ground)
            self.assertEqual(legacy[1][2], 1)
            self.assertEqual(vertices[3], legacy[3])
            batch = Batch()
            nanhu_landmark.build_park_terrain(batch, 10, 20, ground, coarse)
            sampler = build_surface([mesh], (10, 20), ground, coarse)
            for face in batch.faces:
                for x, y, z in face:
                    self.assertAlmostEqual(sampler.sample(x, y), z)
            for y in [.25, .75, 1.25, 1.75]:
                self.assertAlmostEqual(sampler.sample(10, 20+y), coarse(10, 20+y))

    def test_stored_boundary_precision_matches_unrounded_plan_bounds(self):
        mesh = {'points': [[19.54003, 0], [19.34, 0]]}
        with patch.object(nanhu_landmark, 'PLAN', {'terrainPatch': {
                'bounds': [-12.839866709, -9.985814732, 19.540032770, 22.402547336]}}):
            vertices = nanhu_landmark.terrain_vertices(mesh, (0, 0), lambda x,y: 1,
                                                       lambda x,y: 2)
        self.assertEqual(vertices[0][2], 2)
        self.assertEqual(vertices[1][2], 1)


if __name__ == '__main__':
    unittest.main()
