"""Adversarial examples for compressed terrain face matching."""
import unittest
import numpy as np
from check_reduced_terrain_exports import match_faces


def mesh():
    return {'triangles':np.array([[[0,0,0],[1,0,0],[0,1,0]],[[4,0,0],[5,0,0],[4,1,0]]],dtype=float),
            'materials':np.array([0,0]),'cornerNormals':np.tile([0.,0.,1.],(2,3,1))}


class ExportTests(unittest.TestCase):
    def test_exact_float32_city_vertices_match_at_submillimetre_tolerance(self):
        source=mesh()
        source['triangles']=(source['triangles']*.01+[73.,-132.,1.216667]).astype(np.float32).astype(np.float64)
        target={k:v[::-1].copy() for k,v in source.items()}
        target['triangles']=target['triangles'][:,[1,2,0]].astype(np.float32)
        result=match_faces(source,target,position_meters=.0002)
        self.assertEqual(result['maximumVertexDisplacementMeters'],0.)
        target['triangles'][0,0,2]+=.00001
        with self.assertRaises(ValueError):match_faces(source,target,position_meters=.0002)

    def test_mapping_returns_original_global_indices_across_materials(self):
        source=mesh();source['materials']=np.array([1,0])
        target={k:v[::-1].copy() for k,v in source.items()}
        result=match_faces(source,target,include_mapping=True)
        self.assertEqual(result['nativeIndexByActualFace'],[1,0])

    def test_face_order_cyclic_order_and_small_quantization(self):
        source=mesh();target={k:v[::-1].copy() for k,v in source.items()}
        target['triangles']=target['triangles'][:,[1,2,0]]+.0001
        target['cornerNormals']=target['cornerNormals'][:,[1,2,0]]
        result=match_faces(source,target)
        self.assertTrue(result['bijectiveFaceMatch'])
        self.assertAlmostEqual(result['maximumVertexDisplacementMeters'],np.sqrt(3)*.01)

    def test_duplicate_cannot_stand_in_for_missing_face(self):
        source=mesh();target={k:np.repeat(v[:1],2,axis=0) for k,v in source.items()}
        with self.assertRaisesRegex(ValueError,'bijectively'):match_faces(source,target)

    def test_reversed_winding_is_rejected(self):
        source=mesh();target={k:v.copy() for k,v in source.items()};target['triangles'][0]=target['triangles'][0][[0,2,1]]
        with self.assertRaisesRegex(ValueError,'bijectively'):match_faces(source,target)

    def test_normal_and_material_changes_are_rejected(self):
        source=mesh();target={k:v.copy() for k,v in source.items()};target['cornerNormals'][0]*=-1
        with self.assertRaisesRegex(ValueError,'bijectively'):match_faces(source,target)
        target=mesh();target['materials'][0]=1
        with self.assertRaisesRegex(ValueError,'material'):match_faces(source,target)

    def test_large_position_error_is_rejected(self):
        source=mesh();target={k:v.copy() for k,v in source.items()};target['triangles'][:,:,2]+=.001
        with self.assertRaisesRegex(ValueError,'match native'):match_faces(source,target)


if __name__=='__main__':unittest.main()
