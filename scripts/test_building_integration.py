"""Integration inventory checks: stable IDs, cross-tier exclusions and real holes."""
import unittest

from audit_building_integration import frozen_masks, extrusion_triangles


class IntegrationTests(unittest.TestCase):
    def test_baseline_indices_resolve_to_stable_ids(self):
        baseline = {'buildings': [{'id': 'a'}, {'id': 'b'}, {'id': 'c'}]}
        hidden, limits = frozen_masks(baseline, {'removedBuildings': [1]}, [
            {'buildings': [{'index': 2, 'top': 4}, {'index': 0, 'top': 8}]},
            {'buildings': [{'index': 2, 'top': 3}]}])
        self.assertEqual(hidden, {'b'})
        self.assertEqual(limits, {'a': 8, 'c': 3})
        # Removing/reordering a candidate cannot transfer b's railway mask to c.
        candidate = [{'id': 'c'}, {'id': 'a'}]
        self.assertFalse(any(b['id'] in hidden for b in candidate))

    def test_either_profile_can_hide_a_building(self):
        before = {'buildings': [{'id': 'a'}]}
        for tops in [(None, 4), (4, None)]:
            _, limits = frozen_masks(before, {'removedBuildings': []},
                                     [{'buildings': [{'index': 0, 'top': t}]} for t in tops])
            self.assertIsNone(limits['a'])

    def test_roof_hole_adds_inner_walls_without_filling_courtyard(self):
        outer = [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]]
        inner = [[1, 1], [1, 3], [3, 3], [3, 1], [1, 1]]
        self.assertEqual(extrusion_triangles({'rings': [outer]}), 10)
        # A rectangular annulus has eight roof triangles and eight wall quads.
        new = {'qualityGeometry': True, 'rings': [outer, inner], 'roofTriangles': [None]*8}
        self.assertEqual(extrusion_triangles(new), 24)

    def test_compound_exposed_roofs_and_unchanged_p1_guard(self):
        ring = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
        b = {'massing': [{'rings': [ring], 'roofTriangles': [None]*8},
                         {'rings': [ring], 'roofTriangles': [None]*2}]}
        self.assertEqual(extrusion_triangles(b), 26)
        with self.assertRaises(ValueError): extrusion_triangles({'blockId': 'p1', 'rings': [ring]})


if __name__ == '__main__': unittest.main()
