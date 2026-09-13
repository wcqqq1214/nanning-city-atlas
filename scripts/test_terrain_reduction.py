"""Check terrain error, coverage and ambiguity against analytic examples."""
import unittest
import numpy as np
from audit_terrain_reduction import audit


def square(diagonal=False):
    corners=np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0]],dtype=float)
    return corners[[(0,1,3),(1,2,3)] if diagonal else [(0,1,2),(0,2,3)],:]


class TerrainReductionTests(unittest.TestCase):
    def test_coplanar_retriangulation(self):
        old,new=square(),square(True)
        for faces in [old,new]:faces[:,:,2]=2*faces[:,:,0]+3*faces[:,:,1]+7
        result,_=audit(old,new)
        self.assertTrue(result['heightErrorInterpretationValid'])
        self.assertLess(result['maximumVerticalErrorMeters'],1e-10)
        self.assertEqual(result['lostOldCoverageSquareMeters'],0)
        self.assertEqual(result['addedCoverageSquareMeters'],0)

    def test_peak_at_interior_vertex(self):
        corners=[[0,0,0],[1,0,0],[1,1,0],[0,1,0]]
        old=np.array([[a,b,[.5,.5,.08]] for a,b in zip(corners,corners[1:]+corners[:1])])
        result,_=audit(old,square())
        self.assertAlmostEqual(result['maximumVerticalErrorMeters'],8)
        self.assertEqual(result['maximumErrorWitness']['sceneXY'],[.5,.5])

    def test_removed_and_added_coverage(self):
        for before,after,key in [(square(),square()[:1],'lostOldCoverageSquareMeters'),
                                 (square()[:1],square(),'addedCoverageSquareMeters')]:
            result,_=audit(before,after)
            self.assertAlmostEqual(result[key],5000)

    def test_material_change(self):
        result,_=audit(square(),square(),[0,0],[0,1])
        self.assertAlmostEqual(result['materialMismatchSquareMeters'],5000)

    def test_vertical_surface_is_explicitly_outside_audit(self):
        old=np.concatenate([square(),[[[0,0,0],[1,0,0],[1,0,10]]]])
        result,_=audit(old,square())
        self.assertEqual(result['ignoredBeforeVerticalFaces'],1)
        self.assertEqual(result['ignoredAfterVerticalFaces'],0)

    def test_self_overlap_does_not_become_simplification_error(self):
        second=square().copy();second[:,:,2]+=1
        mesh=np.concatenate([square(),second])
        result,_=audit(mesh,mesh)
        self.assertFalse(result['heightErrorInterpretationValid'])
        self.assertIsNone(result['maximumVerticalErrorMeters'])
        self.assertIsNone(result['verticalErrorMetersP95'])
        self.assertIsNone(result['materialMismatchSquareMeters'])
        self.assertAlmostEqual(result['maximumPairedHeightDifferenceMeters'],100)
        self.assertEqual(result['lostOldCoverageSquareMeters'],0)

    def test_duplicate_coverage_does_not_hide_missing_area(self):
        old=square();new=np.repeat(old[:1],2,axis=0)
        result,_=audit(old,new)
        self.assertAlmostEqual(result['lostOldCoverageSquareMeters'],5000)
        self.assertAlmostEqual(result['afterSelfOverlap']['pairwiseOverlapSquareMeters'],5000)


if __name__=='__main__':unittest.main()
