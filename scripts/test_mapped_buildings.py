"""Geometry contracts for ordinary buildings with courtyards."""
import copy
from pathlib import Path
import sys
import unittest

import numpy as np
from shapely.geometry import Polygon,Point
from shapely.ops import triangulate,unary_union

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blender'))
from mapped_buildings import build_mapped


class Batch:
    def __init__(self):self.faces=[]
    def face(self,points,key):self.faces.append((points,key))


def courtyard():
    outer=[[0,0],[6,0],[6,5],[0,5],[0,0]]
    hole=[[2,1],[4,1],[4,3],[2,3],[2,1]]
    shape=Polygon(outer,[hole])
    triangles=[list(t.exterior.coords)[:3] for t in triangulate(shape) if shape.covers(t)]
    return {'id':'courtyard','rings':[outer,hole],'roofTriangles':triangles}


class Tests(unittest.TestCase):
    def test_stale_quality_candidate_is_rejected(self):
        b=courtyard();b['qualityGeometry']=True;batch=Batch()
        with self.assertRaisesRegex(ValueError,'Reprepare'):build_mapped(batch,b,0,1,'wall')
        self.assertEqual(batch.faces,[])

    def test_roof_leaves_courtyard_open(self):
        b=courtyard();batch=Batch();result=build_mapped(batch,b,1,2,'wall')
        roofs=[Polygon([p[:2] for p in face]) for face,key in batch.faces if key=='roof']
        shape=Polygon(b['rings'][0],b['rings'][1:])
        self.assertLess(unary_union(roofs).symmetric_difference(shape).area,1e-10)
        self.assertEqual(sum(t.area for t in roofs),shape.area)
        self.assertEqual(result['courtyards'],1)
        self.assertFalse(unary_union(roofs).covers(Point(3,2)))

    def test_normals_face_air_independent_of_input_winding(self):
        for reverse in [False,True]:
            b=courtyard()
            if reverse:
                b['rings']=[list(reversed(r)) for r in b['rings']]
                b['roofTriangles']=[list(reversed(t)) for t in b['roofTriangles']]
            batch=Batch();build_mapped(batch,b,1,2,'wall')
            shape=Polygon(b['rings'][0],b['rings'][1:])
            for face,key in batch.faces:
                a=np.asarray(face);normal=np.cross(a[1]-a[0],a[2]-a[0])
                if key=='roof':self.assertGreater(normal[2],0)
                else:
                    point=a.mean(axis=0)+normal/np.linalg.norm(normal)*.01
                    self.assertFalse(shape.contains(Point(*point[:2])))

    def test_road_limit_at_or_below_base_emits_nothing(self):
        for top in [1,.5]:
            batch=Batch();self.assertIsNone(build_mapped(batch,courtyard(),1,top,'wall'))
            self.assertEqual(batch.faces,[])

    def test_invalid_later_ring_does_not_partially_mutate_batch(self):
        b=courtyard();b['rings'][1]=b['rings'][1][:-1];batch=Batch()
        with self.assertRaises(ValueError):build_mapped(batch,b,1,2,'wall')
        self.assertEqual(batch.faces,[])

    def test_input_and_heights_are_preserved(self):
        b=courtyard();before=copy.deepcopy(b);batch=Batch()
        build_mapped(batch,b,.91,1.734,'wall')
        self.assertEqual(b,before)
        self.assertEqual({p[2] for face,key in batch.faces for p in face},{.91,1.734})

    def test_rounded_collinear_triangle_is_reported_and_omitted(self):
        b=courtyard();b['roofTriangles'].append([[159.888,-71.426],[159.918,-71.345],[159.998,-71.129]])
        batch=Batch();result=build_mapped(batch,b,0,1,'wall')
        self.assertEqual(result['omittedDegenerateRoofTriangles'],1)
        self.assertTrue(all(max(p[0] for p in face)<=6 for face,key in batch.faces))


if __name__=='__main__':unittest.main()
