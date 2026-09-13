"""Reject missing, moved or misdeclared access in a composed city."""
import copy
import unittest
from pathlib import Path

import numpy as np

from road_access_validation import check_access, read_access, check_support, check_contact
from shapely.geometry import box


class AccessTests(unittest.TestCase):
    def setUp(self):
        top=[[0,0,1],[1,0,1],[0,1,1]]
        soil=[[0,0,0],[1,0,0],[0,1,0]]
        record={'topPoints':top,'soilPoints':soil,'triangles':[[0,1,2]]}
        self.payload={'sites':{'yard':{'detail':record,'smooth':record}}}
        # Six independently stated outward wall faces around the triangular pad.
        walls=[[top[0],soil[0],top[1]],[top[1],soil[0],soil[1]],
               [top[1],soil[1],top[2]],[top[2],soil[1],soil[2]],
               [top[2],soil[2],top[0]],[top[0],soil[2],soil[0]]]
        self.actual={'GroundRoads_access_yard_0_0':{'road':np.asarray([top],float),'walls':np.asarray(walls,float)}}
        self.counts={'yard':{'pavingTriangles':1,'wallTriangles':6}}

    def test_checks_paving_and_walls_against_the_source(self):
        r=check_access(self.payload,self.counts,'detail',self.actual)[0]
        self.assertEqual(r['sourceFootprint'].area,.5)
        self.assertTrue(r['geometry']['bijectiveFaceMatch'])
        self.assertTrue(r['wallGeometry']['bijectiveFaceMatch'])

    def test_rejects_missing_node_shifted_surface_and_wrong_winding(self):
        with self.assertRaisesRegex(ValueError,'nodes'):
            check_access(self.payload,self.counts,'detail',{})
        for field in ['road','walls']:
            wrong=copy.deepcopy(self.actual);wrong['GroundRoads_access_yard_0_0'][field]+= .001
            with self.assertRaises(ValueError):check_access(self.payload,self.counts,'detail',wrong)
        wrong=copy.deepcopy(self.actual);wrong['GroundRoads_access_yard_0_0']['road']=wrong['GroundRoads_access_yard_0_0']['road'][:,[0,2,1]]
        with self.assertRaisesRegex(ValueError,'reversed'):
            check_access(self.payload,self.counts,'detail',wrong)

    def test_rejects_forged_summary_and_undeclared_geometry(self):
        with self.assertRaisesRegex(ValueError,'summary'):
            check_access(self.payload,{'yard':{'pavingTriangles':2,'wallTriangles':6}},'detail',self.actual)
        with self.assertRaisesRegex(ValueError,'nodes'):
            check_access(None,{},'detail',self.actual)

    def test_existing_cities_need_no_access_but_declared_sites_need_a_source(self):
        self.assertIsNone(read_access(None,Path('.'),{'detail':{},'smooth':{}}))
        with self.assertRaisesRegex(ValueError,'site-access-plan'):
            read_access(None,Path('.'),{'detail':{'siteAccess':self.counts},'smooth':{'siteAccess':self.counts}})

    def test_support_hole_cannot_be_hidden_by_overlapping_terrain_faces(self):
        ground=np.asarray([[[0,0,0],[1,0,0],[0,1,0]]]*4,float)
        with self.assertRaisesRegex(ValueError,'missing terrain'):
            check_support(box(0,0,1,1),ground)
        square=np.asarray([[[0,0,0],[1,0,0],[0,1,0]],[[1,0,0],[1,1,0],[0,1,0]]],float)
        self.assertEqual(check_support(box(0,0,1,1),square)['unsupportedSquareMeters'],0)

    def test_contact_allows_only_the_existing_export_precision(self):
        check_contact(0)
        check_contact(-.00000001)
        with self.assertRaisesRegex(ValueError,'penetrates'):
            check_contact(-.00001)


if __name__=='__main__':unittest.main()
