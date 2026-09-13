"""Guard lighting and topology when sharing flat-surface positions."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import numpy as np
from pack_flat_surfaces import flat_faces, face_signatures
from check_flat_surfaces import check


class FlatSurfaceTests(unittest.TestCase):
    def composed_check(self, move_existing=False, tilt_converted=False):
        points=np.array([[0,0,0],[1,0,0],[0,1,0]],dtype=np.float32)
        faces=np.array([[0,1,2]])
        normals=np.tile([0,.1,.995] if tilt_converted else [0,0,1],(3,1))
        before=[SimpleNamespace(points=points,faces=faces,normals=None),
                SimpleNamespace(points=points+2,faces=faces,normals=normals)]
        after=[SimpleNamespace(points=points+(.01 if move_existing else 0),faces=faces,normals=None),
               SimpleNamespace(points=points+2,faces=faces,normals=None)]
        doc={'meshes':[{'name':'sample','primitives':[{'key':0,'material':0},{'key':1,'material':1}]}]}
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'before.glb';b=Path(folder)/'after.glb'
            a.write_bytes(b'fixture before');b.write_bytes(b'fixture after')
            with patch('check_flat_surfaces.glb',side_effect=[(doc,lambda p:before[p['key']]),(doc,lambda p:after[p['key']])]):
                return check(a,b)

    def test_composed_pass_preserves_preexisting_flat_faces(self):
        report=self.composed_check()
        self.assertEqual(report['triangles'],2)
        self.assertEqual(report['flatFaces'],2)

    def test_composed_pass_rejects_changed_flat_geometry_and_custom_normals(self):
        with self.assertRaisesRegex(AssertionError,'Face positions'):
            self.composed_check(move_existing=True)
        with self.assertRaisesRegex(AssertionError,'normal deviation'):
            self.composed_check(tilt_converted=True)

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
