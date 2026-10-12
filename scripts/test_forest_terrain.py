"""Woodland outside a park must follow its replacement terrain triangles."""
import contextlib
import io
import unittest

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from prepare_forest_canopy import prepare_region


class ForestTerrainTests(unittest.TestCase):
    def test_both_profiles_partition_along_off_grid_park_ridge(self):
        # The summit is off both coarse-grid diagonals. A canopy on the old
        # grid would span terrain creases while preserving its outer footprint.
        points = [[0, 0], [4, 0], [4, 4], [0, 4], [1, 2]]
        triangles = [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]]
        patch = {'origin': [0, 0], 'columnRange': [0, 2], 'rowRange': [0, 2],
                 'meshes': [{'points': points, 'triangles': triangles}]}
        supports = [Polygon([points[i] for i in face]) for face in triangles]
        woodland = box(-2, -2, 6, 6)
        with contextlib.redirect_stdout(io.StringIO()):
            region = prepare_region('sample', woodland, Polygon(),
                {'trees': [], 'bounds': [0, 0, 4, 4]}, {'cols': 3, 'rows': 3},
                2, 123, terrain_patch=patch)
        for profile in ['detail', 'smooth']:
            mesh = region[profile]
            faces = [Polygon([mesh['points'][i][:2] for i in ids]) for ids in mesh['triangles']]
            self.assertLess(unary_union(faces).symmetric_difference(box(0, 0, 4, 4)).area, 1e-8)
            self.assertTrue(all(any(s.buffer(1e-8).covers(f) for s in supports) for f in faces))


if __name__ == '__main__':
    unittest.main()
