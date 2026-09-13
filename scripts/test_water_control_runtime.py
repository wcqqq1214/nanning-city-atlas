"""Source ownership, final profile support and scene parenting for sluices."""
from pathlib import Path
import copy
import hashlib
import json
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blender'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_water_control_structures as geometry_tests
from reservoir_terrain import ReservoirTerrain
from reservoir_group import ReservoirGroup
from water_control_runtime import WaterControls


class Tests(unittest.TestCase):
    def fixture(self,root):
        spec,geo=geometry_tests.Tests().fixture();geo['bounds']=[-1,-1,1,1]
        (root/'public/data').mkdir(parents=True);(root/'data').mkdir()
        (root/'public/data/geography.json').write_text(json.dumps(geo))
        path=root/'data/control.json';path.write_text(json.dumps(spec))
        points=[];triangles=[]
        for bottom,top in [(-1,0),(.34,1)]:
            i=len(points);points.extend([[-1,bottom],[1,bottom],[1,top],[-1,top]])
            triangles.extend([[i,i+1,i+2],[i,i+2,i+3]])
        dem={'cols':5,'rows':5,'verticalDatumMeters':0,'verticalOffset':0,'verticalExaggeration':1}
        p={'id':'lake','center':geo['center'],'bounds':geo['bounds'],'columnRange':[0,4],'rowRange':[0,4],
           'points':points,'triangles':triangles,'weights':[1]*len(points),'targetMeters':[20.2]*len(points),
           'materials':['reservoir_ground']*len(triangles),'waterBodies':[{'geographyWaterIndex':3,'rings':geo['water'][3],'levelMeters':20}],'dams':[]}
        group=ReservoirGroup([ReservoirTerrain(p,dem)])
        entry={'id':spec['id'],'source':'data/control.json','sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'reservoirId':'lake'}
        return entry,geo,group

    def test_final_two_profile_support_and_building_layer_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);entry,geo,group=self.fixture(root);controls=WaterControls([entry],group,root);objects=[];calls=[]
            class Object(dict):parent=None
            class Batch:
                def __init__(self,name,keys):self.faces=[];self.object=Object(name=name)
                def face(self,face,key):self.faces.append((face,key))
                def finish(self):objects.append((self.object,self.faces));return self.object
            def final(x,y,*args,lightweight=False):calls.append(lightweight);return .223 if lightweight else .22
            env={'ROOT':root,'GEO':geo,'COLS':5,'ROWS':5,'height':lambda x,y:0,'unpatched_height':lambda x,y:0,
                 'coarse_terrain_surface':lambda *a:0,'terrain_surface':final,'Batch':Batch}
            parent=Object(name='Buildings');result=controls.build(env,parent)[0]['geometry']
            self.assertIs(objects[0][0].parent,parent)
            self.assertEqual(objects[0][0]['mappedBuildingId'],geo['buildings'][0]['id'])
            self.assertEqual(set(calls),{False,True});self.assertTrue(result['usesFinalCitySampler'])
            self.assertAlmostEqual(result['deckHeight'],.2235)
            self.assertEqual(len(objects[0][1]),6*len(result['parts']))

    def test_stale_source_wrong_owner_and_duplicate_structure_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);entry,geo,group=self.fixture(root)
            wrong={**entry,'reservoirId':'other'}
            with self.assertRaisesRegex(ValueError,'active lake'):WaterControls([wrong],group,root)
            with self.assertRaisesRegex(ValueError,'Duplicate'):WaterControls([entry,entry],group,root)
            group.dam_ids=frozenset([geo['buildings'][0]['id']])
            with self.assertRaisesRegex(ValueError,'ownership'):WaterControls([entry],group,root)
            (root/'data/control.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'changing'):WaterControls([entry],group,root)

    def test_missing_final_support_cannot_use_native_height_as_fallback(self):
        spec,geo=geometry_tests.Tests().fixture()
        from water_control_structures import WaterControlStructure
        from reduced_surface import ReducedSurface
        s=ReducedSurface([[[-1,-1,.2],[1,-1,.2],[1,1,.2]],[[-1,-1,.2],[1,1,.2],[-1,1,.2]]],['ground']*2)
        with self.assertRaisesRegex(ValueError,'final land support'):
            WaterControlStructure(spec,geo).geometry_on_surfaces([s,s],lambda x,y:.2,lambda *a:None)


if __name__=='__main__':unittest.main()
