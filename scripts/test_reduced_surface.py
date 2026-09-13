"""Check the explicit replacement sampler used by the next integration step."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blender'))
from reduced_surface import ReducedSurface


class SurfaceTests(unittest.TestCase):
    def test_plane_vertices_edges_and_interior(self):
        points=[(0,0,7),(2,0,11),(2,2,17),(0,2,13)]
        triangles=[tuple(points[i] for i in face) for face in [(0,1,2),(0,2,3)]]
        surface=ReducedSurface(triangles,['ground','ground'])
        for x,y in [(0,0),(2,2),(1,1),(1,0),(0,1),(.2,1.7),(1.2,.8)]:
            self.assertAlmostEqual(surface.sample(x,y),7+2*x+3*y)
        self.assertIsNone(surface.sample(-.01,1))

    def test_disconnected_patch_gap_and_zero_height(self):
        triangles=[[(0,0,0),(1,0,0),(0,1,0)],[(2,0,3),(3,0,3),(2,1,3)]]
        surface=ReducedSurface(triangles,['a','b'])
        self.assertEqual(surface.sample(.2,.2),0)
        self.assertEqual(surface.sample(2.2,.2),3)
        self.assertIsNone(surface.sample(1.5,.2))

    def test_emitted_geometry_is_the_sampled_geometry(self):
        triangles=[[(0,0,1),(1,0,2),(0,1,4)]]
        surface=ReducedSurface(triangles,['hill']);faces=[]
        class Batch:
            def face(self,t,m):faces.append((t,m))
        surface.emit(Batch())
        self.assertEqual(faces,[(tuple(triangles[0]),'hill')])
        for point in faces[0][0]:self.assertAlmostEqual(surface.sample(*point[:2]),point[2])

    def test_invalid_replacement_is_rejected(self):
        with self.assertRaises(ValueError):ReducedSurface([[(0,0,0),(0,1,0),(0,1,1)]],['a'])
        with self.assertRaises(ValueError):ReducedSurface([[(0,0,0),(1,0,0),(0,1,0)]],[])


if __name__=='__main__':unittest.main()
