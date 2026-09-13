"""Source binding and final-storage sampling for site grading integration."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'blender'))
from site_grading import SiteGrading,load


class Batch:
    def __init__(self):self.faces=[]
    def face(self,points,key):self.faces.append((points,key))


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload=json.loads((ROOT/'work/urban-structure/p5/grading/candidate.json').read_text())

    def test_emission_and_sampler_share_stored_triangles(self):
        plan=SiteGrading(self.payload);site=self.payload['sites'][0]
        ground=lambda x,y:.8+.005*(x-site['bounds'][0])
        coarse=lambda x,y,g,b,c,r,m:g(x,y)+(.02 if m else 0)
        for mobile in [False,True]:
            batch=Batch();plan.build(batch,ground,site['bounds'],617,465,mobile,coarse,lambda x,y:'ground')
            for face,key in batch.faces:
                for p in [*face,tuple(sum(v[k] for v in face)/3 for k in range(3))]:
                    z=plan.sample(p[0],p[1],ground,site['bounds'],617,465,mobile,coarse)
                    self.assertIsNotNone(z)
                    self.assertAlmostEqual(z,p[2],places=7)
            self.assertTrue(any(k=='block_paving' for _,k in batch.faces))
        self.assertIsNone(plan.sample(-10000,10000,ground,site['bounds'],617,465,False,coarse))

    def test_pad_and_profile_specific_boundaries(self):
        import struct
        plan=SiteGrading(self.payload);site=self.payload['sites'][0]
        ground=lambda x,y:.9
        coarse=lambda x,y,g,b,c,r,m:g(x,y)+(.02 if m else 0)
        rounded=lambda p:struct.unpack('<fff',struct.pack('<fff',*p))
        for mobile in [False,True]:
            for (x,y),weight in zip(site['points'],site['weights']):
                if weight not in [0,1]:continue
                expected=site['targetSceneZ'] if weight else .9+(.02 if mobile else 0)
                p=rounded((x,y,expected))
                actual=plan.sample(p[0],p[1],ground,site['bounds'],617,465,mobile,coarse)
                self.assertIsNotNone(actual);self.assertAlmostEqual(actual,p[2],places=7)

    def test_overlap_and_coarse_alignment_are_rejected(self):
        payload=copy.deepcopy(self.payload);payload['sites'].append(payload['sites'][0])
        with self.assertRaisesRegex(ValueError,'overlap'):SiteGrading(payload)
        payload=copy.deepcopy(self.payload);payload['sites'][0]['columnRange'][0]+=1
        with self.assertRaisesRegex(ValueError,'align'):SiteGrading(payload)

    def test_loader_rejects_stale_or_unbound_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'plan.json'
            self.assertIsNone(load(path,root))
            path.write_text(json.dumps(self.payload))
            with self.assertRaisesRegex(ValueError,'bindings'):load(path,root)
            inputs={}
            for name in ['public/data/geography.json','public/data/terrain.json','data/block-grading-source.json']:
                f=root/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text('{}')
                inputs[name]=hashlib.sha256(f.read_bytes()).hexdigest()
            path.write_text(json.dumps({**self.payload,'runtimeInputs':inputs}))
            self.assertIsNotNone(load(path,root))
            (root/'public/data/terrain.json').write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError,'terrain.json'):load(path,root)


if __name__=='__main__':unittest.main()
