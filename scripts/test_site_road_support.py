"""Road endpoints alone do not detect terrain penetrating the face interior."""
import unittest
import numpy as np
from check_site_road_support import audit


def strip(xs,z):
    result=[]
    for a,b,c,d in zip(xs,xs[1:],z,z[1:]):
        p=[[a,0,c],[b,0,d],[b,1,d],[a,1,c]]
        result.extend([[p[i] for i in ids] for ids in [[0,1,2],[0,2,3]]])
    return np.asarray(result,dtype=float)


class Tests(unittest.TestCase):
    def test_unsegmented_road_misses_ground_crest(self):
        terrain=strip([0,1,2],[0,.02,0]);road=strip([0,2],[.008,.008])
        result=audit(terrain,road,[0,0,2,1])
        self.assertFalse(result['passed']);self.assertAlmostEqual(result['maximumPenetrationMeters'],1.2)
        self.assertAlmostEqual(result['witnessSceneXY'][0],1.)

    def test_segmentation_matches_every_ground_face(self):
        terrain=strip([0,1,2],[0,.02,0]);road=strip([0,1,2],[.008,.028,.008])
        result=audit(terrain,road,[0,0,2,1])
        self.assertTrue(result['passed']);self.assertAlmostEqual(result['minimumPavementClearanceMeters'],.8)


if __name__=='__main__':unittest.main()
