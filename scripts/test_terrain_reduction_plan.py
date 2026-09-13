"""Check explicit activation, provenance and full mesh replacement contracts."""
import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blender'))
from terrain_reduction_plan import TerrainReductionPlan,mesh_digest,activate,suspended,replacement_height


def fixture():
    corners=[[0,0,1],[1,0,1],[1,1,1],[0,1,1]]
    old=np.array([[a,b,[.5,.5,1.001]] for a,b in zip(corners,corners[1:]+corners[:1])])
    new=np.array([[corners[i] for i in face] for face in [(0,1,2),(0,2,3)]])
    payload={'schemaVersion':1,'metersPerUnit':100,'profile':'smooth','inputHashes':{},'materialKeys':['ground'],
             'originalMeshSha256':mesh_digest(old,[0]*4),'candidateMeshSha256':mesh_digest(new,[0]*2),
             'removedOriginalFaces':[0,1,2,3],'newTriangles':new.tolist(),'newMaterials':[0,0]}
    return old,new,payload


class PlanTests(unittest.TestCase):
    def test_native_mesh_must_be_validated_before_sampling(self):
        old,new,payload=fixture();plan=TerrainReductionPlan(payload)
        with self.assertRaisesRegex(ValueError,'Validate'):plan.sample(.5,.5,'smooth',lambda x,y:9)
        result,materials=plan.apply(old,[0]*4,'smooth');np.testing.assert_array_equal(result,new)
        self.assertEqual(plan.sample(.5,.5,'smooth',lambda x,y:9),1)
        self.assertEqual(plan.sample(5,5,'smooth',lambda x,y:9),9)
        self.assertEqual(plan.sample(.5,.5,'detail',lambda x,y:7),7)

    def test_wrong_native_mesh_and_profile_are_rejected(self):
        old,_,payload=fixture();plan=TerrainReductionPlan(payload)
        with self.assertRaisesRegex(ValueError,'quality profile'):plan.apply(old,[0]*4,'detail')
        old[0,0,2]+=.001
        with self.assertRaisesRegex(ValueError,'differs'):plan.apply(old,[0]*4,'smooth')

    def test_replacement_payload_is_bound_to_audited_mesh(self):
        old,_,payload=fixture();payload=copy.deepcopy(payload);payload['newTriangles'][0][0][2]+=.001
        plan=TerrainReductionPlan(payload)
        with self.assertRaisesRegex(ValueError,'independently checked'):plan.apply(old,[0]*4,'smooth')

    def test_retained_faces_and_materials_are_not_reordered(self):
        old,new,payload=fixture();extra=old[:1].copy();extra[:,:,0]+=4
        source=np.concatenate([old,extra]);candidate=np.concatenate([extra,new])
        payload['originalMeshSha256']=mesh_digest(source,[0]*5)
        payload['candidateMeshSha256']=mesh_digest(candidate,[0]*3)
        result,_=TerrainReductionPlan(payload).apply(source,[0]*5,'smooth')
        np.testing.assert_array_equal(result,candidate)

    def test_source_changes_and_path_escape_are_rejected(self):
        _,_,payload=fixture()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.json';source.write_text('{}')
            payload['inputHashes']={'source.json':hashlib.sha256(source.read_bytes()).hexdigest()}
            TerrainReductionPlan(payload,root)
            source.write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError,'source changed'):TerrainReductionPlan(payload,root)
            payload['inputHashes']={'../outside.json':'x'}
            with self.assertRaisesRegex(ValueError,'escapes'):TerrainReductionPlan(payload,root)

    def test_native_capture_suspends_and_restores_active_sampling(self):
        old,_,payload=fixture();plan=TerrainReductionPlan(payload);plan.apply(old,[0]*4,'smooth')
        with suspended():
            activate(plan)
            self.assertEqual(replacement_height(.5,.5,True),1)
            self.assertIsNone(replacement_height(.5,.5,False))
            with suspended():self.assertIsNone(replacement_height(.5,.5,True))
            self.assertEqual(replacement_height(.5,.5,True),1)


if __name__=='__main__':unittest.main()
