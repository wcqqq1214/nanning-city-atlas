import copy
import json
from pathlib import Path
import sys
import unittest
import numpy as np
from shapely.geometry import Polygon
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blender'))
from water_control_structures import WaterControlStructure,digest
from reduced_surface import ReducedSurface


class Tests(unittest.TestCase):
    def fixture(self):
        spec=json.loads((Path(__file__).resolve().parents[1]/'data/water-control-sources/linglong.json').read_text())
        rings=[[[0,0],[.2,0],[.2,.34],[0,.34],[0,0]]]
        geo={'center':spec['center'],'water':[rings]*4,'buildings':[{'id':spec['buildingId'],'sourceRef':spec['sourceRef'],'use':'dam','rings':rings}]}
        spec['expectedFootprintSha256']=spec['expectedWaterSha256']=digest(rings)
        return spec,geo

    def test_source_footprint_and_water_passage_survive_dedicated_geometry(self):
        spec,geo=self.fixture();model=WaterControlStructure(spec,geo)
        result=model.geometry(lambda x,y:(.202,.202),lambda x,y:.2)
        self.assertEqual(result['openings'],3)
        self.assertAlmostEqual(result['spanMeters'],34)
        self.assertAlmostEqual(result['deckHeight'],.215)
        self.assertGreater(result['gateBottom'],result['waterHeight'])
        footprint=Polygon(geo['buildings'][0]['rings'][0])
        for part in result['parts']:
            if not part['name'].startswith('approach-'):
                self.assertLess(Polygon(part['footprint']).difference(footprint).area,1e-12)
            # Each individual structural member is closed and outward wound.
            volume=0
            for face in part['faces']:
                a,b,c,d=np.asarray(face);volume+=np.dot(a,np.cross(b,c))/6+np.dot(a,np.cross(c,d))/6
            self.assertGreater(volume,0,part['name'])
        for p in result['approaches']:
            self.assertLessEqual(p['riseMeters']/p['steps'],.18)
            self.assertGreaterEqual(p['treadMeters'],.28)

    def test_changed_footprint_or_water_cannot_reuse_source(self):
        spec,geo=self.fixture();changed=copy.deepcopy(geo);changed['buildings'][0]['rings'][0][0][0]=.001
        with self.assertRaisesRegex(ValueError,'footprint'):WaterControlStructure(spec,changed)
        spec['expectedWaterSha256']='stale'
        with self.assertRaisesRegex(ValueError,'shoreline'):WaterControlStructure(spec,geo)

    def test_native_bank_rounding_is_bounded_and_never_replaced_with_water_height(self):
        spec,geo=self.fixture();model=WaterControlStructure(spec,geo)
        def surface(edge):
            faces=[]
            for bottom,top in [(-1,edge),(.34-edge,1)]:
                faces.extend([[[-1,bottom,.202],[1,bottom,.202],[1,top,.202]],
                              [[-1,bottom,.202],[1,top,.202],[-1,top,.202]]])
            return ReducedSurface(faces,['ground']*4)
        s=surface(-.000002)
        r=model.geometry_on_surfaces([s,s],lambda x,y:.2)
        self.assertGreater(r['shorelineSupportSnapCount'],0)
        self.assertLess(r['maximumShorelineSupportSnapMeters'],.005)
        far=surface(-.001)
        with self.assertRaisesRegex(ValueError,'outside its terrain'):model.geometry_on_surfaces([far,far],lambda x,y:.2)

    def test_invalid_hydraulic_geometry_does_not_silently_generate(self):
        spec,geo=self.fixture();spec['displayParametersMeters']['gateOpeningAboveWater']=3
        with self.assertRaisesRegex(ValueError,'Gate opening'):WaterControlStructure(spec,geo).geometry(lambda x,y:(.2,.2),lambda x,y:.2)
        spec,geo=self.fixture();spec['estimatedBayCount']=100
        with self.assertRaisesRegex(ValueError,'no usable'):WaterControlStructure(spec,geo)
        spec,geo=self.fixture();spec['sourceFeature']['tags']['layer']='0'
        with self.assertRaisesRegex(ValueError,'layer=1'):WaterControlStructure(spec,geo)

    def test_ground_constraints_affect_deck_and_reject_buried_approach(self):
        spec,geo=self.fixture();model=WaterControlStructure(spec,geo)
        r=model.geometry(lambda x,y:(.22,.22),lambda x,y:.2)
        self.assertGreaterEqual(r['deckHeight'],.2205)
        def hill(x,y):return (.3,.3) if -.04<y<-.02 else (.2,.2)
        with self.assertRaises(ValueError):model.geometry(hill,lambda x,y:.2)


if __name__=='__main__':unittest.main()
