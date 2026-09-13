import unittest
from shapely.geometry import box
from prepare_geodata import coords
from reservoir_interfaces import audit_interfaces


class Tests(unittest.TestCase):
    def fixture(self):
        geography={'water':[coords(box(0,0,1,1)),coords(box(2,0,3,1)),coords(box(8,8,9,9))]}
        plan={'bounds':[-1,-1,4,4],'points':[[2,0],[3,0],[3,1],[2,1]],'weights':[0,0,0,0],
              'waterBodies':[{'geographyWaterIndex':0}]}
        return plan,geography

    def test_all_neighbors_are_checked_and_outside_waters_are_excluded(self):
        p,g=self.fixture();a=audit_interfaces(p,g)
        self.assertEqual([r['geographyWaterIndex'] for r in a['neighbors']],[1])
        self.assertEqual(a['unresolvedWaterIndices'],[])
        p['weights'][2]=.01
        self.assertEqual(audit_interfaces(p,g)['unresolvedWaterIndices'],[1])

    def test_unsampled_boundary_is_not_assumed_safe(self):
        p,g=self.fixture();p['points']=[[0,0]];p['weights']=[0]
        self.assertEqual(audit_interfaces(p,g)['unresolvedWaterIndices'],[1])

    def test_shared_water_edge_requires_resolution_even_without_land_restore(self):
        p,g=self.fixture();g['water'][0]=coords(box(0,0,2,1))
        a=audit_interfaces(p,g);self.assertEqual(a['unresolvedWaterIndices'],[1])
        self.assertEqual(a['neighbors'][0]['sharedSelectedBoundaryMeters'],100)


if __name__=='__main__':unittest.main()
