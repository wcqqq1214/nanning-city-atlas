"""Prove same-material object seams survive reduction and plan packaging."""
import copy
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blender'))
from prepare_partitioned_terrain_reduction import reduce,protect_source_seams
from prepare_terrain_reduction import Reducer
from prepare_terrain_reduction_plan import prepare
from terrain_reduction_plan import TerrainReductionPlan
from terrain_partitions import partition_digest
from check_terrain_reduction import boundary_edges


def fixture():
    # Two adjacent objects share a material and a three-vertex border. Each
    # object's interior can simplify, but its border midpoint must remain.
    left=[[0,0,1],[1,0,1],[1,.5,1],[1,1,1],[0,1,1]]
    right=[[1,0,1],[2,0,1],[2,1,1],[1,1,1],[1,.5,1]]
    faces=[]
    for i,ring in enumerate([left,right]):
        faces.extend([[a,b,[i+.5,.5,1]] for a,b in zip(ring,ring[1:]+ring[:1])])
    return {'triangles':np.asarray(faces,dtype=float),'materials':np.zeros(10,dtype=int),
            'partitionNames':np.asarray(['Terrain_0_0','Terrain_grading_yard_0_0']),
            'partitionIndices':np.repeat([0,1],5)}


class PartitionTests(unittest.TestCase):
    def test_fine_vertex_below_coarse_edge_freezes_incident_faces(self):
        # Adjacent coarse/fine fans disagree only on their shared line. Area
        # coverage and material checks alone cannot detect this sampler hazard.
        left=[[0,0,1],[1,0,1],[1,1,1],[0,1,1]]
        right=[[1,0,1],[2,0,1],[2,1,1],[1,1,1],[1,.5,.99]]
        faces=[]
        for i,ring in enumerate([left,right]):
            faces.extend([[a,b,[i+.5,.5,1]] for a,b in zip(ring,ring[1:]+ring[:1])])
        reducer=Reducer(np.asarray(faces),np.zeros(len(faces),dtype=int),2,5)
        original_protected=set(reducer.protected)
        result=protect_source_seams(reducer)
        self.assertAlmostEqual(result['maximumSourceJunctionDifferenceMeters'],1)
        self.assertIn(1,result['sourceFaces'])
        self.assertGreater(len(reducer.protected),len(original_protected))
        for i in result['sourceFaces']:self.assertTrue(set(reducer.faces[i])<=reducer.protected)

    def test_real_reduction_preserves_same_material_object_seam(self):
        source=fixture();candidate,report,audit=reduce(source,.01,1)
        self.assertGreater(report['savedTriangles'],0)
        self.assertTrue(audit['objectPartitionsUnchanged'])
        self.assertEqual(boundary_edges(source['triangles'],source['partitionIndices']),
                         boundary_edges(candidate['triangles'],candidate['partitionIndices']))
        for owner in [0,1]:
            self.assertTrue(np.any(np.all(candidate['triangles'][candidate['partitionIndices']==owner]==[1,.5,1],axis=2)))
        payload=prepare(source,candidate,audit,{'inputHashes':{},'materialKeys':['ground','reservoir']},'smooth')
        self.assertEqual(payload['materialKeys'],['ground','reservoir'])
        plan=TerrainReductionPlan(payload)
        after,_=plan.apply(source['triangles'],source['materials'],'smooth',source['partitionNames'].tolist(),source['partitionIndices'])
        np.testing.assert_array_equal(after,candidate['triangles'])
        np.testing.assert_array_equal(plan.result_partitions,candidate['partitionIndices'])

    def test_source_and_candidate_ownership_tampering_rejected(self):
        source=fixture();candidate,_,audit=reduce(source,.01,1)
        payload=prepare(source,candidate,audit,{'inputHashes':{},'materialKeys':['ground']},'smooth')
        owners=source['partitionIndices'].copy();owners[0]=1
        with self.assertRaisesRegex(ValueError,'ownership changed'):
            TerrainReductionPlan(payload).apply(source['triangles'],source['materials'],'smooth',source['partitionNames'].tolist(),owners)
        changed=copy.deepcopy(payload);changed['newPartitionIndices'][0]=1-changed['newPartitionIndices'][0]
        with self.assertRaisesRegex(ValueError,'ownership changed'):
            TerrainReductionPlan(changed).apply(source['triangles'],source['materials'],'smooth',source['partitionNames'].tolist(),source['partitionIndices'])
        audit.pop('objectPartitionsUnchanged')
        with self.assertRaisesRegex(ValueError,'independently checked'):
            prepare(source,candidate,audit,{'inputHashes':{}},'smooth')

    def test_malformed_partition_vector_rejected(self):
        for ids in [np.zeros((10,1),dtype=int),np.full(10,2),np.zeros(10,dtype=float)]:
            source=fixture();source['partitionIndices']=ids
            with self.assertRaises(ValueError):reduce(source,.01,1)
        with self.assertRaises(ValueError):partition_digest(['same','same'],[0,1])


if __name__=='__main__':unittest.main()
