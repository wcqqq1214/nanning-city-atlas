from types import SimpleNamespace
import unittest
import numpy as np
from decoded_surface import face_arrays


class DecodedSurfaceTests(unittest.TestCase):
    def test_shared_positions_retain_separate_face_normals(self):
        mesh = SimpleNamespace(points=np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]),
                               faces=np.asarray([[0, 1, 2], [0, 3, 1]]), normals=None)
        faces, normals = face_arrays(mesh)
        self.assertTrue(np.array_equal(normals[0], [[0, -1, 0]]*3))
        self.assertTrue(np.array_equal(normals[1], [[0, 0, 1]]*3))
        self.assertTrue(np.array_equal(faces[0, 0], faces[1, 0]))

    def test_explicit_artistic_normals_are_not_recomputed(self):
        mesh = SimpleNamespace(points=np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]]),
                               faces=np.asarray([[0, 1, 2]]), normals=np.asarray([[1, 0, 0]]*3))
        _, normals = face_arrays(mesh)
        self.assertTrue(np.array_equal(normals[0], [[1, 0, 0]]*3))

    def test_missing_normal_on_degenerate_face_is_rejected(self):
        mesh = SimpleNamespace(points=np.asarray([[0, 0, 0], [1, 0, 0], [2, 0, 0]]),
                               faces=np.asarray([[0, 1, 2]]), normals=None)
        with self.assertRaises(ValueError):
            face_arrays(mesh)


if __name__ == '__main__':
    unittest.main()
