"""Guard lighting and topology when sharing flat-surface positions."""
import unittest
import numpy as np
from pack_flat_surfaces import flat_faces, face_signatures


class FlatSurfaceTests(unittest.TestCase):
    def test_custom_and_degenerate_normals_stay_explicit(self):
        points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32)
        faces = np.array([[0, 1, 2], [0, 2, 1], [0, 0, 1]])
        mask, _ = flat_faces(points, np.tile([0, 0, 1], (3, 1)), faces, .5)
        self.assertEqual(mask.tolist(), [True, False, False])
        mask, _ = flat_faces(points, np.tile([0, .1, .995], (3, 1)), faces[:1], .5)
        self.assertFalse(mask.any())

    def test_sharing_positions_preserves_count_and_winding(self):
        points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32)
        original = face_signatures(points, np.array([[0, 1, 2], [0, 1, 2]]))
        self.assertEqual(original, face_signatures(points, np.array([[1, 2, 0], [2, 0, 1]])))
        self.assertNotEqual(original, face_signatures(points, np.array([[0, 2, 1], [0, 1, 2]])))
        self.assertNotEqual(original, face_signatures(points, np.array([[0, 1, 2]])))


if __name__ == '__main__':
    unittest.main()
