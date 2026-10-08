import unittest
import json
import numpy as np
from shapely.geometry import Polygon, LineString, Point

from check_variable_canopy_clearance import Requirement, check, from_plan


class VariableCanopyTests(unittest.TestCase):
    def test_internal_requirement_peak_is_checked_between_outer_vertices(self):
        # All outer vertices require 2 m, but the interior point requires 9 m.
        points = np.asarray([[0,0,.02],[1,0,.02],[0,1,.02],[.2,.2,.09]])
        triangles = points[[[0,1,3],[1,2,3],[2,0,3]]]
        rule = Requirement(triangles, 9.5)
        margin, location = rule.margin(Polygon(points[:3,:2]), np.array([0,0,.05]))
        self.assertAlmostEqual(margin, -4)
        np.testing.assert_allclose(location, [.2,.2])

    def test_outside_the_mountain_retains_the_full_requirement(self):
        rule = Requirement(np.asarray([[[0,0,.02],[1,0,.02],[0,1,.02]]]),9.5)
        self.assertAlmostEqual(rule.margin(Point(.1,.1),np.array([0,0,.05]))[0],3)
        self.assertAlmostEqual(rule.margin(Point(2,2),np.array([0,0,.05]))[0],-4.5)

    def test_vertical_edge_crosses_requirement_peak(self):
        points=np.asarray([[0,0,.02],[1,0,.02],[0,1,.02],[.2,.2,.09]])
        rule=Requirement(points[[[0,1,3],[1,2,3],[2,0,3]]],9.5)
        margin,_=rule.margin(LineString([[.05,.2],[.6,.2]]),np.array([0,0,.05]))
        self.assertAlmostEqual(margin,-4)

    def test_actual_sloped_canopy_passes_varying_requirement(self):
        ground=np.asarray([[[0,0,0],[1,0,0],[0,1,0]]],float)
        requirement=ground.copy();requirement[0,:,2]=[.025,.05,.025]
        canopy=requirement.copy();canopy[:,:,2]+=.005
        result=check(canopy,ground,requirement)
        json.dumps(result)
        self.assertTrue(result['passed'])
        self.assertAlmostEqual(result['minimumMarginMeters'],.5)
        canopy[0,1,2]-=.006
        self.assertFalse(check(canopy,ground,requirement)['passed'])

    def test_vertical_face_failure_and_ground_hole_remain_failures(self):
        ground=np.asarray([[[0,0,0],[1,0,0],[0,1,0]]],float)
        requirement=ground.copy();requirement[:,:,2]=.025
        canopy=np.asarray([[[0,0,.03],[1,0,.03],[0,1,.03]],
                           [[.1,.1,.03],[.3,.1,.03],[.1,.1,.05]]])
        self.assertTrue(check(canopy,ground,requirement)['passed'])
        canopy[1,0,2]=.02
        self.assertFalse(check(canopy,ground,requirement)['passed'])
        canopy=np.asarray([[[0,0,.1],[2,0,.1],[0,2,.1]]])
        self.assertFalse(check(canopy,ground,requirement)['passed'])

    def test_plan_uses_source_weight_and_rejects_invalid_values(self):
        plan={'points':[[0,0],[1,0],[0,1]],'triangles':[[0,1,2]],
              'weights':[0,.5,1],'source':{'canopyRiseFactor':.25}}
        np.testing.assert_allclose(from_plan(plan)[0,:,2],[.095,.059375,.02375])
        plan['weights'][0]=-1
        with self.assertRaises(ValueError):from_plan(plan)


if __name__=='__main__':unittest.main()
