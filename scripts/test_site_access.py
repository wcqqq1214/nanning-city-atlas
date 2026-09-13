"""Exact road mouths and terrain replacement, including non-linear edge stations."""
import unittest
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

from prepare_site_access import make_access, replace_soil, soil_penetration, triangulate_preserving_boundary, verify_inputs, stabilize_soil


def strip(xs, heights, south=-1, north=1):
    result=[]
    for x,y,a,b in zip(xs,xs[1:],heights,heights[1:]):
        p=[[x,south,a],[y,south,b],[y,north,b],[x,north,a]]
        result.extend([[p[i] for i in t] for t in [[0,1,2],[0,2,3]]])
    return np.asarray(result)


class AccessTests(unittest.TestCase):
    def test_storage_does_not_hide_overlapping_source_faces(self):
        triangle=[[73.,-132.,1.],[74.,-132.,1.],[74.,-131.,1.]]
        with self.assertRaisesRegex(ValueError,'already overlaps'):
            stabilize_soil([triangle,triangle],['ground','ground'],[73,-132,74,-131])

    def test_native_overlay_repairs_subpixel_fan_without_filling_real_hole(self):
        corners=[[73.,-132.],[74.,-132.],[74.,-131.],[73.,-131.]]
        center=[73.333333,-131.999998]
        faces=[[[x,y,1+(x-73)*.1+(y+132)*.2] for x,y in [a,b,center]] for a,b in zip(corners,corners[1:]+corners[:1])]
        stored=np.asarray(faces,dtype=np.float32).astype(float)
        self.assertTrue(np.any(np.cross(stored[:,1]-stored[:,0],stored[:,2]-stored[:,0])[:,2]==0))
        stable,materials,report=stabilize_soil(faces,['ground']*4,[73,-132,74,-131])
        values=np.asarray(stable);self.assertTrue(np.array_equal(values,values.astype(np.float32)))
        self.assertTrue(np.all(np.cross(values[:,1]-values[:,0],values[:,2]-values[:,0])[:,2]>0))
        self.assertAlmostEqual(unary_union([Polygon(t[:,:2]) for t in values]).area,1.)
        self.assertEqual(set(materials),{'ground'});self.assertLess(abs(report['overlapSquareMeters']),1e-5)
        domain=Polygon(corners).difference(Polygon([(73.3,-131.7),(73.7,-131.7),(73.7,-131.3),(73.3,-131.3)]))
        faces=[[[x,y,1.] for x,y in t] for t in triangulate_preserving_boundary(domain)]
        stable,_,_=stabilize_soil(faces,['ground']*len(faces),[73,-132,74,-131])
        self.assertLess(unary_union([Polygon(np.asarray(t)[:,:2]) for t in stable]).intersection(Polygon([(73.31,-131.69),(73.69,-131.69),(73.69,-131.31),(73.31,-131.31)])).area,1e-10)

    def test_rebuilt_access_rejects_stale_and_missing_sources(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);path=root/'terrain.json';path.write_bytes(b'old terrain')
            bindings={'terrain.json':hashlib.sha256(path.read_bytes()).hexdigest()}
            verify_inputs(root,bindings,['terrain.json'])
            with self.assertRaisesRegex(ValueError,'Missing'):verify_inputs(root,bindings,['geography.json'])
            path.write_bytes(b'rebuilt terrain')
            with self.assertRaisesRegex(ValueError,'Stale'):verify_inputs(root,bindings,['terrain.json'])

    @classmethod
    def setUpClass(cls):
        cls.plan={'estimatedAccess':{'points':[[.5,0],[3,0]],'widthMeters':8},
                  'pad':[[[0,-.5],[1.2,-.5],[1.2,.5],[0,.5],[0,-.5]]], 'targetSceneZ':2}
        cls.road=strip([2.8,3.2],[2.01,2.01])
        cls.access=make_access(cls.plan,cls.road,lambda x,y:2.002)

    def test_mouth_matches_road_without_pavement_overlap(self):
        a=self.access
        self.assertLess(a['statistics']['mouthMaximumHeightErrorMeters'],1e-8)
        footprint=unary_union([Polygon([a['topPoints'][i][:2] for i in ids]) for ids in a['triangles']])
        road=unary_union([Polygon(t[:,:2]) for t in self.road])
        self.assertLess(footprint.intersection(road).area,1e-10)
        self.assertAlmostEqual(min(p[1] for p in a['topPoints']),-.04)
        self.assertAlmostEqual(max(p[1] for p in a['topPoints']),.04)

    def test_pavement_and_soil_start_at_yard_and_end_at_road(self):
        a=self.access;columns=a['columns']
        self.assertTrue(all(abs(p[2]-2)<1e-12 for p in a['topPoints'][:columns]+a['soilPoints'][:columns]))
        self.assertTrue(all(abs(p[2]-2.01)<1e-12 for p in a['topPoints'][-columns:]))
        self.assertTrue(all(abs(p[2]-2.002)<1e-12 for p in a['soilPoints'][-columns:]))
        self.assertTrue(all(a[2]>=b[2]-1e-12 for a,b in zip(a['topPoints'],a['soilPoints'])))

    def test_hump_is_removed_with_single_terrain_coverage(self):
        old=strip([-1,0,1.2,1.8,2.8,4],[2,2,2,2.03,2.002,2.002])
        self.assertGreater(soil_penetration(self.access,old)['maximumOldTerrainAbovePavementMeters'],1)
        after,report=replace_soil(self.access,old,self.road)
        self.assertLess(soil_penetration(self.access,np.asarray(after))['maximumOldTerrainAbovePavementMeters'],1e-7)
        self.assertLess(report['coverageDifferenceSquareMeters'],1e-6)
        self.assertLess(abs(report['overlapSquareMeters']),1e-6)

    def test_collinear_boundary_stations_are_not_dropped(self):
        p=Polygon([(0,0),(.3,0),(.7,0),(1,0),(1,1),(0,1)])
        triangles=triangulate_preserving_boundary(p)
        used={tuple(v) for t in triangles for v in t}
        self.assertIn((.3,0),used);self.assertIn((.7,0),used)
        self.assertAlmostEqual(sum(Polygon(t).area for t in triangles),1)

    def test_zero_width_overlay_needle_is_removed_before_earcut(self):
        p=Polygon([(0,0),(1,0),(1,1),(.5,1),(.5,1.5),(.5,1),(0,1)])
        self.assertFalse(p.is_valid)
        triangles=triangulate_preserving_boundary(p)
        self.assertAlmostEqual(sum(Polygon(t).area for t in triangles),1)


if __name__=='__main__':unittest.main()
