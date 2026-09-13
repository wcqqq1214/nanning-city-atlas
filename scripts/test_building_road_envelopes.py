"""Prevent stale road clearance when prepared buildings change site or visibility."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blender'))
import road_solids
from road_inputs import BUILDING_ENVELOPE_INPUTS,building_envelopes,capture_building_levels
from building_placement import envelope,validate_road_envelope


class Support:
    payload={'runtimeInputs':{}}
    def bounds(self,building):return 1.,1.03


def building(identity='visible'):
    return {'id':identity,'qualityGeometry':True,'height':10,
            'rings':[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}


class Visibility:
    def __init__(self):self.calls=[]
    def building_visible(self,b,railway_hidden=False):
        self.calls.append((b['id'],railway_hidden))
        return b['id']!='site-overlap' and not railway_hidden


class Tests(unittest.TestCase):
    def setUp(self):
        self.geo={'buildings':[building(),building('site-overlap'),building('railway')]}
        self.levels=[[0,.995,1.187]]
        self.visibility=Visibility()
        self.env={'GEO':self.geo,'BUILDING_SUPPORT':Support(),'city_visibility':self.visibility,
                  'RAILWAY_BUILDINGS':{2},'height':lambda x,y:0}

    def fixture(self,root):
        hashes={}
        for name in BUILDING_ENVELOPE_INPUTS:
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(self.levels) if name.endswith('building-levels.json') else name)
            hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
        for profile in ['detail','smooth']:
            path=root/f'data/road-solids-{profile}.npz';path.parent.mkdir(exist_ok=True)
            np.savez(path,ground=np.zeros((0,3,3)))
            metadata={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'inputHashes':hashes,
                      'buildings':[],'buildingEnvelopes':building_envelopes(self.geo,self.levels)}
            path.with_suffix('.json').write_text(json.dumps(metadata))

    def test_capture_uses_city_visibility_and_full_footprint_support(self):
        rows=capture_building_levels(self.env)
        self.assertEqual(self.visibility.calls,[('visible',False),('site-overlap',False),('railway',True)])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][:2],[0,.995]);self.assertAlmostEqual(rows[0][2],1.187)

    def test_changed_ground_is_rejected_even_for_unclipped_or_hidden_roofs(self):
        p=envelope(self.geo['buildings'][0],Support())
        captured={r['index']:r for r in building_envelopes(self.geo,self.levels)}
        validate_road_envelope(0,self.geo['buildings'][0],p,captured)
        for key in ['bottom','top']:
            changed={**p,key:p[key]+.0001}  # 1 cm exceeds the 5 mm parity tolerance.
            with self.assertRaisesRegex(ValueError,'support changed'):
                validate_road_envelope(0,self.geo['buildings'][0],changed,captured)
        with self.assertRaisesRegex(ValueError,'support changed'):
            validate_road_envelope(0,self.geo['buildings'][0],{**p,'top':float('nan')},captured)
        with self.assertRaisesRegex(ValueError,'mismatched'):
            validate_road_envelope(0,building('reordered'),p,captured)
        with self.assertRaisesRegex(ValueError,'Missing'):
            validate_road_envelope(0,self.geo['buildings'][0],p,{})

    def test_access_bound_support_cannot_be_used_to_rebuild_its_own_roads(self):
        self.env['BUILDING_SUPPORT']=copy.deepcopy(Support())
        self.env['BUILDING_SUPPORT'].payload={'runtimeInputs':{'data/road-solids-detail.json':'hash'}}
        with self.assertRaisesRegex(ValueError,'dependency cycle'):capture_building_levels(self.env)

    def test_every_captured_volume_survives_even_when_no_roof_was_adjusted(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(road_solids,'ROOT',Path(tmp)):
            self.fixture(Path(tmp));road_solids.load.cache_clear()
            result=road_solids.building_envelopes(self.geo)
            self.assertEqual(result[0]['id'],'visible');self.assertEqual(result[0]['top'],1.187)

    def test_old_or_incomplete_profile_metadata_cannot_accept_prepared_geometry(self):
        for mutation in ['old','missing-row','wrong-id','changed-roof']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp,patch.object(road_solids,'ROOT',Path(tmp)):
                root=Path(tmp);self.fixture(root)
                path=root/'data/road-solids-smooth.json';data=json.loads(path.read_text())
                if mutation=='old':del data['inputHashes']['blender/road_inputs.py']
                elif mutation=='missing-row':data['buildingEnvelopes']=[]
                elif mutation=='wrong-id':data['buildingEnvelopes'][0]['id']='other'
                else:data['buildingEnvelopes'][0]['top']+=.01
                path.write_text(json.dumps(data));road_solids.load.cache_clear()
                with self.assertRaisesRegex(ValueError,'[Ee]nvelopes'):road_solids.building_envelopes(self.geo)

    def test_source_or_capture_edits_invalidate_road_results(self):
        for name in BUILDING_ENVELOPE_INPUTS:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp,patch.object(road_solids,'ROOT',Path(tmp)):
                root=Path(tmp);self.fixture(root)
                path=root/name;path.write_text(path.read_text()+' ');road_solids.load.cache_clear()
                with self.assertRaisesRegex(AssertionError,'Recapture'):road_solids.building_envelopes(self.geo)

    def test_invalid_and_duplicate_captured_records_fail(self):
        for rows in [[[0,0,1],[0,0,1]],[[3,0,1]],[[0,1,1]],[[0,0,float('nan')]],[[False,0,1]]]:
            with self.subTest(rows=rows),self.assertRaises(ValueError):building_envelopes(self.geo,rows)

    def tearDown(self):road_solids.load.cache_clear()


if __name__=='__main__':unittest.main()
