import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from check_reservoir_terrain import compare,shared_shoreline
import numpy as np
from shapely import union_all
from shapely.geometry import box,Point
from shapely.ops import polygonize
from prepare_geodata import coords
from prepare_block_grading import NativeXYGrid
from prepare_reservoir_terrain import prepare_water_mesh,water_mesh_lines,nearest_shore_level
from reservoir_connections import connect_water_fields,protected_banks,protection_weights
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blender'))
from reservoir_water import WaterLevelField


class Tests(unittest.TestCase):
    def lakes(self):
        return [({'geographyWaterIndex':i,'levelMeters':z,'transitionWidthMeters':30,
                  'waterMeshSpacingMeters':30,'transitionMeshSpacingMeters':5,
                  'levelRegions':[{'rings':coords(p),'levelMeters':z}]},p)
                for i,p,z in [(0,box(0,0,1,1),80),(1,box(1,0,2,1),84)]]

    def test_connected_meshes_share_exact_height_without_extending_local_coverage(self):
        original=self.lakes();lakes=connect_water_fields(original,[{'id':'pair','waterIndices':[0,1]}]);native=NativeXYGrid([0,0,2,1])
        network=union_all([line for e,p in lakes for line in water_mesh_lines(e,p,native)],grid_size=1);cells=list(polygonize(network));faces=[]
        for e,p in lakes:
            mesh=prepare_water_mesh(e,p,native,network,cells)
            xyz=np.column_stack([mesh['points'],np.asarray(mesh['targetMeters'])/100]);f=xyz[mesh['triangles']];compare(f,p);faces.append(f)
            self.assertEqual(WaterLevelField(e).meters(1,.5),82)
        for i in [0,1]:
            r=shared_shoreline(np.empty((0,3,3)),faces[i],.2,[0,0,2,1],faces[1-i])
            self.assertGreater(r['connectedWaterEdges'],10);self.assertEqual(r['maximumWaterJoinErrorMeters'],0)
        wrong=faces[1].copy();wrong[:,:,2]+=.01
        with self.assertRaisesRegex(ValueError,'Connected water height'):shared_shoreline(np.empty((0,3,3)),faces[0],.2,[0,0,2,1],wrong)
        self.assertNotIn('levelInfluenceRegions',original[0][0])

    def test_disconnected_or_repeated_water_group_is_rejected(self):
        lakes=self.lakes();lakes[1]=(lakes[1][0],box(2,0,3,1))
        with self.assertRaisesRegex(ValueError,'share edges'):connect_water_fields(lakes,[{'id':'x','waterIndices':[0,1]}])
        with self.assertRaisesRegex(ValueError,'distinct'):connect_water_fields(self.lakes(),[{'id':'x','waterIndices':[0,0]}])

    def test_island_bank_queries_its_nearest_ring_instead_of_the_outer_ring(self):
        hole=box(3,1,3.5,2);lake=box(0,0,4,4).difference(hole)
        field=WaterLevelField({'levelMeters':80,'transitionWidthMeters':30,'levelRegions':[
            {'rings':coords(box(0,0,2,4)),'levelMeters':80},
            {'rings':coords(box(2,0,4,4).difference(hole)),'levelMeters':84}]})
        self.assertEqual(nearest_shore_level(field,lake,Point(3,1.5)),84)
        self.assertEqual(nearest_shore_level(field,lake,Point(3.01,1.5)),84)

    def test_separate_bank_is_held_without_suppressing_selected_water_shore(self):
        lakes=self.lakes()[:1];geo={'water':[coords(box(0,0,1,1)),coords(box(1.2,0,2,1))]};native=NativeXYGrid([0,0,3,2])
        banks=protected_banks(geo,lakes,native,native.encode(box(0,0,3,2)),{'preserveUnselectedWaterBanksMeters':35,'nativeRestoreMeters':150})
        self.assertEqual(len(banks),1)
        weights=protection_weights([[1,.5],[1.1,.5],[1.19,.5],[1.2,.5]],banks)
        self.assertAlmostEqual(weights[0],1);self.assertAlmostEqual(weights[1],1,places=5)
        self.assertEqual(weights[2],0);self.assertEqual(weights[3],0)
        geo['water'][1]=coords(box(1,0,2,1))
        with self.assertRaisesRegex(ValueError,'Directly connected'):protected_banks(geo,lakes,native,native.encode(box(0,0,3,2)),{'preserveUnselectedWaterBanksMeters':35,'nativeRestoreMeters':150})


if __name__=='__main__':unittest.main()
