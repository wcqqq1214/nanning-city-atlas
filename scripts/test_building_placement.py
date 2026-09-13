"""Rendering and road envelopes must agree through support and roof clipping."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blender'))
from building_placement import envelope,render


class Support:
    def bounds(self,building):return 1.,1.03


class Batch:
    def __init__(self):self.faces=[]
    def face(self,points,material):self.faces.append((points,material))


class Tests(unittest.TestCase):
    def mapped(self):
        ring=[[0,0],[1,0],[1,1],[0,1],[0,0]];roof=[ring[:3],[ring[0],ring[2],ring[3]]]
        return {'id':'building','qualityGeometry':True,'rings':[ring],'height':10,
                'roofTriangles':roof,'meshRoofTriangles':roof}

    def test_full_support_and_height_scale_define_the_actual_volume(self):
        b=self.mapped();placement=envelope(b,Support());batch=Batch();result=render(batch,b,placement,'wall')
        heights=[point[2] for face,_ in batch.faces for point in face]
        self.assertEqual(min(heights),.995)
        self.assertAlmostEqual(max(heights),1.187)
        self.assertEqual(result['floor'],1.032)

    def test_limit_below_occupied_floor_cannot_leave_a_foundation_only_building(self):
        b=self.mapped();placement=envelope(b,Support());batch=Batch()
        self.assertIsNone(render(batch,b,placement,'wall',1.01));self.assertFalse(batch.faces)
        result=render(batch,b,placement,'wall',1.10)
        self.assertEqual(result['top'],1.10)
        self.assertTrue(all(p[2]==1.10 for face,key in batch.faces if key=='roof' for p in face))

    def test_compound_clips_with_a_complete_roof_and_shared_envelope(self):
        b=self.mapped();b['massing']=[{'baseMeters':0,'topMeters':8,'rings':b['rings'],
                                      'roofTriangles':b['roofTriangles'],'fullRoofTriangles':b['roofTriangles']}]
        p=envelope(b,Support());self.assertAlmostEqual(p['top'],1.112)
        batch=Batch();result=render(batch,b,p,'wall',1.08)
        self.assertEqual(result['top'],1.08)
        self.assertEqual(len([f for f,key in batch.faces if key=='roof']),2)

    def test_special_structures_and_missing_support_cannot_silently_fall_back(self):
        b=self.mapped()
        with self.assertRaisesRegex(ValueError,'support'):envelope(b,None)
        b['use']='dam'
        with self.assertRaisesRegex(ValueError,'hydraulic'):envelope(b,Support())


if __name__=='__main__':unittest.main()
