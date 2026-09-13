"""Do not discard float32 shoreline faces during production water validation."""
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blender'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from reservoir_terrain import ReservoirTerrain
from check_reservoir_runtime_exports import prepared_water_faces


class Tests(unittest.TestCase):
    def fixture(self):
        points=[[1,0],[1+2e-7,.2],[1+2e-7,.8]]
        p={'points':[],'weights':[],'targetMeters':[],
           'waterBodies':[{'rings':[[[0,0],[1,0],[1,1],[0,1],[0,0]]],
                           'waterMesh':{'points':points,'targetMeters':[50]*3,'triangles':[[0,1,2]]}}]}
        model=ReservoirTerrain(p,{'verticalDatumMeters':0,'verticalOffset':0,'verticalExaggeration':1})
        return model,np.asarray(model.water_surface(0).triangles)

    def test_outside_centroid_does_not_drop_a_prepared_shoreline_face(self):
        model,native=self.fixture()
        self.assertGreater(native[:,:,0].mean(),1)
        claimed=set();actual=prepared_water_faces(native,{},model,0,claimed)
        self.assertTrue(np.array_equal(actual,native));self.assertEqual(claimed,{0})

    def test_missing_duplicate_and_multiply_owned_water_are_rejected(self):
        model,native=self.fixture()
        for data,claimed in [(native[:0],set()),(np.concatenate([native,native]),set()),(native,{0})]:
            with self.assertRaisesRegex(ValueError,'Missing, duplicate or multiply owned'):
                prepared_water_faces(data,{},model,0,claimed)

    def test_constant_water_uses_active_source_triangles_and_level(self):
        model,_=self.fixture();lake=model.payload['waterBodies'][0]
        lake.pop('waterMesh');lake['levelMeters']=50
        model=ReservoirTerrain(model.payload,model.dem)
        geo={'waterTriangles':[[[0,0],[1,0],[0,1]],[[2,0],[3,0],[2,1]]]}
        native=np.asarray([[[0,0,.5],[1,0,.5],[0,1,.5]],[[2,0,.26],[3,0,.26],[2,1,.26]]])
        selected=prepared_water_faces(native,geo,model,0,set())
        self.assertEqual(len(selected),1);self.assertTrue(np.array_equal(selected[0],native[0]))


if __name__=='__main__':unittest.main()
