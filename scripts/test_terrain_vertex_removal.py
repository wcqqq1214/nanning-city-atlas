"""Analytic checks for error-bounded, material-preserving terrain candidates."""
import unittest
import numpy as np
from audit_terrain_reduction import audit
from prepare_terrain_reduction import Reducer,triangulate_ring
from check_terrain_reduction import check


def grid(size=5,height=lambda x,y:0.):
    points=np.array([(x,y,height(x,y)) for y in range(size) for x in range(size)],dtype=float)
    faces=[]
    for y in range(size-1):
        for x in range(size-1):
            a=y*size+x;b=a+1;c=b+size;d=a+size
            faces.extend([(a,b,c),(a,c,d)])
    return points[np.asarray(faces)]


def reduce(faces,materials=None,tolerance=.05,normal=2.):
    return Reducer(faces,np.zeros(len(faces),dtype=int) if materials is None else materials,tolerance,normal).run()


class VertexRemovalTests(unittest.TestCase):
    def test_flat_grid_reduces_and_preserves_boundary(self):
        source=grid();new,materials,origins,report=reduce(source)
        self.assertGreater(report['removedVertices'],0)
        self.assertEqual(report['savedTriangles'],report['removedVertices']*2)
        old_boundary={tuple(p) for p in source.reshape(-1,3) if p[0] in (0,4) or p[1] in (0,4)}
        vertices={tuple(p) for p in new.reshape(-1,3)}
        self.assertTrue(old_boundary<=vertices)
        result,_=audit(source,new,np.zeros(len(source)),materials)
        self.assertEqual(result['maximumVerticalErrorMeters'],0)
        self.assertEqual(result['lostOldCoverageSquareMeters'],0)
        self.assertEqual(result['addedCoverageSquareMeters'],0)
        for i,origin in enumerate(origins):
            if origin>=0:np.testing.assert_array_equal(new[i],source[origin])

    def test_cumulative_operations_stay_within_original_error(self):
        source=grid(8,lambda x,y:.0004*np.sin(x*.7)*np.cos(y*.6))
        new,materials,_,report=reduce(source,tolerance=.03)
        self.assertGreater(report['removedVertices'],2)
        result,_=audit(source,new)
        self.assertLessEqual(result['maximumVerticalErrorMeters'],.03000001)
        # Same input also fixes ordering and topology, not only the total count.
        again=reduce(source,tolerance=.03)
        np.testing.assert_array_equal(new,again[0]);np.testing.assert_array_equal(materials,again[1])

    def test_peak_is_preserved_beyond_error(self):
        source=grid(3,lambda x,y:.01 if (x,y)==(1,1) else 0)
        new,_,_,report=reduce(source)
        self.assertEqual(report['removedVertices'],0)
        np.testing.assert_array_equal(source,new)

    def test_material_boundary_is_preserved(self):
        source=grid(6);materials=(source[:,:,0].mean(axis=1)>2).astype(int)
        new,new_materials,_,report=reduce(source,materials)
        self.assertGreater(report['removedVertices'],0)
        result,_=audit(source,new,materials,new_materials)
        self.assertEqual(result['materialMismatchSquareMeters'],0)

    def test_hole_and_vertical_wall_remain(self):
        source=grid(6);centers=source[:,:,:2].mean(axis=1)
        source=source[~((centers[:,0]>2)&(centers[:,0]<3)&(centers[:,1]>2)&(centers[:,1]<3))]
        wall=np.array([[[2,2,0],[2,3,0],[2,3,1]],[[2,2,0],[2,3,1],[2,2,1]]])
        source=np.concatenate([source,wall]);new,_,origins,report=reduce(source)
        self.assertTrue(set([len(source)-1,len(source)-2])<=set(origins))
        result,_=audit(source,new)
        self.assertEqual(result['addedCoverageSquareMeters'],0)
        self.assertEqual(result['lostOldCoverageSquareMeters'],0)

    def test_collinear_ring_stations_are_retained(self):
        p=np.array([[0,0],[1,0],[2,0],[2,1],[2,2],[1,2],[0,2],[0,1]],dtype=float)
        faces=triangulate_ring(p)
        self.assertEqual(len(faces),6)
        self.assertEqual(set(faces.ravel()),set(range(8)))
        self.assertIsNone(triangulate_ring([[0,0],[1,1],[0,1],[1,0]]))

    def test_overlapping_faces_are_frozen(self):
        source=grid();overlap=source[10:12].copy();overlap[:,:,2]+=.005
        source=np.concatenate([source,overlap]);new,_,origins,report=reduce(source)
        self.assertTrue({10,11,len(source)-1,len(source)-2}<=set(origins))

    def test_normal_constraint_rejects_small_sharp_peak(self):
        source=grid(3,lambda x,y:.0004 if (x,y)==(1,1) else 0)
        source[:,:,:2]*=.001
        _,_,_,report=reduce(source,tolerance=.05,normal=2)
        self.assertEqual(report['removedVertices'],0)
        self.assertGreater(report['rejections'].get('normal',0),0)

    def test_independent_checker_accepts_valid_candidate(self):
        source=grid();new,materials,origins,_=reduce(source)
        result=check({'triangles':source,'materials':np.zeros(len(source),dtype=int)},
                     {'triangles':new,'materials':materials,'originFaceIndices':origins})
        self.assertTrue(result['boundaryAndMaterialSeamsUnchanged'])
        self.assertEqual(result['replacementUnchangedOverlapSquareMeters'],0)

    def test_independent_checker_rejects_false_provenance(self):
        source=grid();new,materials,origins,_=reduce(source)
        origins[origins<0]=0
        with self.assertRaisesRegex(ValueError,'provenance|differ'):
            check({'triangles':source,'materials':np.zeros(len(source),dtype=int)},
                  {'triangles':new,'materials':materials,'originFaceIndices':origins})

    def test_independent_checker_rejects_coverage_hole(self):
        source=grid();new,materials,origins,_=reduce(source)
        with self.assertRaisesRegex(ValueError,'Boundary|coverage'):
            check({'triangles':source,'materials':np.zeros(len(source),dtype=int)},
                  {'triangles':new[1:],'materials':materials[1:],'originFaceIndices':origins[1:]})

    def test_independent_checker_rejects_larger_height_limit(self):
        source=grid(3,lambda x,y:.001 if (x,y)==(1,1) else 0)
        new,materials,origins,_=reduce(source,tolerance=.2)
        with self.assertRaisesRegex(ValueError,'Height error'):
            check({'triangles':source,'materials':np.zeros(len(source),dtype=int)},
                  {'triangles':new,'materials':materials,'originFaceIndices':origins},tolerance_meters=.05)


if __name__=='__main__':unittest.main()
