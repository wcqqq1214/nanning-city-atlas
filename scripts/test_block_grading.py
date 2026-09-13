"""Check replacement topology, water holes, shared surfaces and source reservations."""
import json
from pathlib import Path
import unittest

from shapely.geometry import Polygon, Point, box
from shapely.ops import unary_union

from prepare_block_grading import prepare_site, rings, GradePatch, NativeXYGrid, triangulate_stations

ROOT=Path(__file__).resolve().parents[1]


class GradingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=json.loads((ROOT/'data/block-grading-source.json').read_text())['sites'][0]
        cls.geo={'bounds':[-5,-5,5,5],'water':[rings(box(1.7,1.7,1.9,1.9))],'parks':[],
                 'roads':[{'name':'华兴路','bridge':False,'class':'unclassified','points':[[2,-4],[2,4]]}],
                 'buildings':[{'id':str(i),'blockId':cls.config['id'],'rings':rings(p)} for i,p in enumerate(
                     [box(-.8,-.9,.8,-.25),box(-.8,.25,.8,.9)])],
                 'urbanBlocks':[{'id':cls.config['id'],'boundary':rings(box(-1.5,-1.5,1.5,1.5)),
                     'reservedSpaces':[{'kind':'loading-space','rings':rings(box(-1,-.15,1,.15))}]}]}
        cls.dem={'cols':21,'rows':21}
        cls.base=staticmethod(lambda x,y:2+.07*x+.12*y)
        cls.plan=prepare_site(cls.geo,cls.dem,cls.config,{'detail':cls.base,'smooth':cls.base})
        cls.patch=GradePatch(cls.plan);cls.levels=cls.patch.levels(cls.base)

    def test_single_coverage_preserves_water(self):
        faces=[Polygon([self.plan['points'][i] for i in tri]) for tri in self.plan['triangles']]
        coverage=unary_union(faces);grid=NativeXYGrid(self.plan['bounds'])
        original=box(*self.plan['bounds']).difference(box(1.7,1.7,1.9,1.9))
        expected=grid.decode(grid.encode(box(*self.plan['bounds'])).difference(grid.encode(box(1.7,1.7,1.9,1.9))))
        self.assertLess(coverage.symmetric_difference(expected).area,1e-8)
        self.assertLess(coverage.hausdorff_distance(original),sum(grid.steps)+1e-10)
        self.assertLess(abs(sum(p.area for p in faces)-coverage.area),1e-8)
        self.assertIsNone(self.patch.sample(1.8,1.8,self.levels))

    def test_xy_vertices_survive_native_storage_exactly(self):
        import numpy as np
        points=np.asarray(self.plan['points'])
        self.assertTrue(np.array_equal(points,points.astype(np.float32).astype(float)))

    def test_retaining_collar_has_continuous_material_and_leaves_outer_ground(self):
        pad=Polygon(self.plan['pad'][0],self.plan['pad'][1:])
        collar=pad.buffer(self.config['retainingWidthMeters']/100,join_style=2)
        walls=[]
        for ids,material in zip(self.plan['triangles'],self.plan['materials']):
            shape=Polygon([self.plan['points'][i] for i in ids])
            if material=='block_retaining':walls.append(shape)
        self.assertTrue(walls)
        self.assertLess(unary_union(walls).symmetric_difference(collar.difference(pad)).area,1e-6)
        for (x,y),weight,level in zip(self.plan['points'],self.plan['weights'],self.levels):
            if Point(x,y).distance(pad)>self.config['retainingWidthMeters']/100*1.5:
                self.assertEqual(weight,0)
                self.assertEqual(level,self.base(x,y))

    def test_retaining_collar_cannot_cross_protected_site_boundary(self):
        config={**self.config,'retainingWidthMeters':40,'patchMarginMeters':60}
        with self.assertRaisesRegex(ValueError,'available site'):
            prepare_site(self.geo,self.dem,config,{'detail':self.base,'smooth':self.base})

    def test_collinear_terrain_station_is_not_bridged_by_a_long_edge(self):
        import numpy as np
        points=np.array([[0.,0.],[1.,0.],[2.,0.],[2.,1.],[0.,1.]])
        triangles=triangulate_stations(points,np.array([5],dtype=np.uint32))
        self.assertEqual({int(i) for t in triangles for i in t},set(range(5)))
        edges={tuple(sorted((int(a),int(b)))) for t in triangles for a,b in zip(t,np.roll(t,-1))}
        self.assertNotIn((0,2),edges)
        self.assertIn((0,1),edges);self.assertIn((1,2),edges)

    def test_pad_footprints_and_access_start_are_flat(self):
        for b in self.geo['buildings']:
            for x,y in b['rings'][0]:
                self.assertAlmostEqual(self.patch.sample(x,y,self.levels),self.plan['targetSceneZ'],places=8)
        self.assertAlmostEqual(self.patch.sample(0,0,self.levels),self.plan['targetSceneZ'],places=8)

    def test_boundary_and_outside_effect_keep_base_surface(self):
        outer=box(*self.plan['bounds']).boundary
        effect=unary_union([Polygon(r[0],r[1:]) for r in self.plan['gradingArea']])
        for i,(x,y) in enumerate(self.plan['points']):
            if Point(x,y).distance(outer)<1e-8 or not effect.buffer(1e-8).contains(Point(x,y)):
                self.assertAlmostEqual(self.levels[i],self.base(x,y),places=9)
        self.assertIsNone(self.patch.sample(20,20,self.levels))

    def test_sampler_matches_each_triangle_centroid(self):
        for ids in self.plan['triangles']:
            x,y=[sum(self.plan['points'][i][k] for i in ids)/3 for k in [0,1]]
            self.assertAlmostEqual(self.patch.sample(x,y,self.levels),sum(self.levels[i] for i in ids)/3,places=8)

    def test_repeatability_and_protected_road(self):
        self.assertEqual(self.plan,prepare_site(self.geo,self.dem,self.config,{'detail':self.base,'smooth':self.base}))
        pad=Polygon(self.plan['pad'][0]);self.assertFalse(pad.intersects(box(1.9,-4,2.1,4)))
        self.assertEqual(self.plan['columnRange'][0]%2,0)
        self.assertEqual(self.plan['rowRange'][1]%2,0)

    def test_each_profile_supplies_its_own_base_but_shares_pad(self):
        shifted=self.patch.levels(lambda x,y:self.base(x,y)+.12)
        for i,w in enumerate(self.plan['weights']):
            self.assertAlmostEqual(shifted[i]-self.levels[i],.12*(1-w),places=9)
        for i,p in enumerate(self.plan['points']):
            value=self.patch.sample(*p,self.levels)
            self.assertIsNotNone(value,p)
            self.assertAlmostEqual(value,self.levels[i],places=8)

    def test_build_reuses_surface_and_preserves_base_material(self):
        class Capture:
            def __init__(self):self.faces=[]
            def face(self,vertices,material):self.faces.append((vertices,material))
        batch=Capture();self.patch.build(batch,self.base,lambda x,y:'existing-landcover')
        self.assertEqual(len(batch.faces),len(self.plan['triangles']))
        for (vertices,key),ids,material in zip(batch.faces,self.plan['triangles'],self.plan['materials']):
            self.assertEqual(vertices,[(*self.plan['points'][i],self.levels[i]) for i in ids])
            if material=='base':self.assertEqual(key,'existing-landcover')


if __name__=='__main__':unittest.main()
