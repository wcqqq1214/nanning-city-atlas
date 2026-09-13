"""Source and geometry failures must block use of an old support range."""
import copy
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blender'))
from building_support_plan import BuildingSupportPlan
from prepare_building_support import bind_runtime


def example():
    building={'id':'warehouse','rings':[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}
    row={'id':building['id'],'footprintHash':hashlib.sha256(json.dumps(building['rings'],separators=(',',':')).encode()).hexdigest(),
         'status':'supported','groundRangeSceneZ':[1.,3.],
         'profiles':{'detail':{'status':'covered','minimumSceneZ':1.,'maximumSceneZ':2.},
                     'smooth':{'status':'covered','minimumSceneZ':2.,'maximumSceneZ':3.}}}
    return building,{'metersPerUnit':100,'records':[row]}


class Tests(unittest.TestCase):
    def test_bounds_use_both_actual_profiles(self):
        building,payload=example();self.assertEqual(BuildingSupportPlan(payload).bounds(building),(1.,3.))

    def test_changed_footprint_or_incomplete_ground_is_rejected(self):
        building,payload=example();changed=copy.deepcopy(building);changed['rings'][0][1][0]=2
        with self.assertRaisesRegex(ValueError,'Stale'):BuildingSupportPlan(payload).bounds(changed)
        payload['records'][0]['profiles']['smooth']['status']='incomplete-terrain'
        with self.assertRaisesRegex(ValueError,'Incomplete'):BuildingSupportPlan(payload).bounds(building)

    def test_forged_range_is_rejected(self):
        building,payload=example();payload['records'][0]['groundRangeSceneZ']=[1.,2.]
        with self.assertRaisesRegex(ValueError,'extrema'):BuildingSupportPlan(payload).bounds(building)

    def test_changed_runtime_sources_and_context_are_rejected(self):
        building,payload=example()
        with TemporaryDirectory() as temp:
            root=Path(temp);(root/'public/data').mkdir(parents=True)
            for name in ['geography','terrain']:(root/f'public/data/{name}.json').write_text(name)
            paths={'geography':root/'public/data/geography.json','detail':root/'detail.glb','smooth':root/'smooth.glb'}
            paths['detail'].write_bytes(b'detail mesh');paths['smooth'].write_bytes(b'smooth mesh')
            hashes={f'public/data/{name}.json':hashlib.sha256((root/f'public/data/{name}.json').read_bytes()).hexdigest() for name in ['geography','terrain']}
            manifest=root/'sources.json';manifest.write_text(json.dumps({'inputHashes':hashes}))
            bind_runtime(payload,paths,manifest,root);plan=root/'support.json';plan.write_text(json.dumps(payload))
            self.assertEqual(BuildingSupportPlan.read(plan,root).bounds(building),(1.,3.))
            paths['detail'].write_bytes(b'changed mesh')
            with self.assertRaisesRegex(ValueError,'context'):BuildingSupportPlan.read(plan,root)
            (root/'public/data/terrain.json').write_text('new terrain')
            with self.assertRaisesRegex(ValueError,'source'):BuildingSupportPlan.read(plan,root)
            with self.assertRaisesRegex(ValueError,'Stale'):bind_runtime(payload,paths,manifest,root)


if __name__=='__main__':unittest.main()
