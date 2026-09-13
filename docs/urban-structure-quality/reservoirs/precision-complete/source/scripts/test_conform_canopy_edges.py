import unittest
import numpy as np
from shapely.geometry import Polygon, box
from shapely.ops import unary_union
from conform_canopy_edges import conform_edges

class ConformEdgesTest(unittest.TestCase):
    def setUp(self):
        # The lower face has a long boundary; upper faces introduce its midpoint.
        self.mesh={'points':[[0,0,.1],[2,0,.1],[0,-2,.1],[1,0,.1],[0,1,.1],[2,1,.1]],
                   'triangles':[[0,2,1],[0,3,4],[3,1,5],[3,5,4]],'colors':[0,1,2,1]}
    def test_boundary_midpoint_is_shared_after_non_linear_ground_sampling(self):
        result, report=conform_edges(self.mesh)
        edges=[{a,b} for f in result['triangles'] for a,b in zip(f,f[1:]+f[:1])]
        self.assertNotIn({0,1},edges)
        self.assertEqual(edges.count({0,3}),2);self.assertEqual(edges.count({1,3}),2)
        p=np.array(result['points']);p[:,2]+=p[:,0]*(2-p[:,0])
        self.assertEqual(report['trianglesSplit'],1)
        self.assertEqual(report['maximumRiseDifferenceMeters'],0)
        self.assertGreater(p[3,2],(p[0,2]+p[1,2])/2)
        def coverage(m):return unary_union([Polygon(np.array(m['points'])[f,:2]) for f in m['triangles']])
        self.assertLess(coverage(self.mesh).symmetric_difference(coverage(result)).area,1e-12)
        self.assertEqual(self.mesh['triangles'][0],[0,2,1])
    def test_unrelated_domain_preserves_source(self):
        result,report=conform_edges(self.mesh,box(10,10,11,11))
        self.assertEqual(result,self.mesh);self.assertEqual(report['trianglesSplit'],0)
    def test_unreferenced_vertex_does_not_split_edge(self):
        self.mesh['points'].append([.5,0,.1])
        result,report=conform_edges(self.mesh)
        self.assertTrue(all(6 not in f for f in result['triangles']))
    def test_second_pass_is_stable(self):
        once,_=conform_edges(self.mesh);twice,report=conform_edges(once)
        self.assertEqual(once,twice);self.assertEqual(report['trianglesSplit'],0)
    def test_boundary_triangulation_preserves_shared_station_without_extra_center(self):
        result,report=conform_edges(self.mesh,triangulation='boundary')
        edges=[{a,b} for f in result['triangles'] for a,b in zip(f,f[1:]+f[:1])]
        self.assertEqual(edges.count({0,3}),2);self.assertEqual(edges.count({1,3}),2)
        self.assertNotIn({0,1},edges)
        self.assertEqual(result['points'],self.mesh['points'])
        self.assertEqual(len(result['triangles']),len(self.mesh['triangles'])+1)
        self.assertEqual(report['trianglesAdded'],1)
        twice,second=conform_edges(result,triangulation='boundary')
        self.assertEqual(result,twice);self.assertEqual(second['trianglesSplit'],0)

if __name__=='__main__':unittest.main()
