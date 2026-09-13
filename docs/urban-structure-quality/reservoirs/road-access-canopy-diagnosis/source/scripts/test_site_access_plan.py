"""Access activation requires the matching native geometry and material scope."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blender'))
from site_access_plan import SiteAccessPlan,activate,replacement_height,suspended


class Tests(unittest.TestCase):
    def make(self):
        faces=[[[0,0,1],[1,0,1],[0,1,1]]]
        payload={'sites':{'yard':{p:{'nativeStorageAudit':{},'terrainTriangles':faces,'terrainMaterials':['ground']} for p in ['detail','smooth']}}}
        base={'triangles':np.asarray([[[0,0,0],[1,0,0],[0,1,0]]]),'materials':np.array([0])}
        return SiteAccessPlan(payload,{'sites':[{'id':'yard','bounds':[0,0,1,1]}]}, {('yard',p):copy.deepcopy(base) for p in ['detail','smooth']}),base

    def test_requires_matching_profile_then_samples_exact_surface(self):
        plan,base=self.make()
        with self.assertRaisesRegex(ValueError,'Validate'):plan.sample(.2,.2,'detail',lambda x,y:-1)
        plan.validate_base('yard','detail',base['triangles'],base['materials'])
        self.assertEqual(plan.sample(.2,.2,'detail',lambda x,y:-1),1)
        self.assertEqual(plan.sample(3,3,'detail',lambda x,y:-1),-1)
        with self.assertRaisesRegex(ValueError,'Validate'):plan.sample(.2,.2,'smooth',lambda x,y:-1)

    def test_order_is_flexible_but_winding_material_and_height_must_match(self):
        plan,base=self.make()
        plan.validate_base('yard','detail',base['triangles'][:,[1,2,0]],base['materials'])
        for triangles,materials in [(base['triangles'][:,[0,2,1]],base['materials']),
                                     (base['triangles']+.01,base['materials']),(base['triangles'],np.array([1]))]:
            with self.assertRaisesRegex(ValueError,'changed'):plan.validate_base('yard','smooth',triangles,materials)

    def test_activation_requires_both_profiles_and_suspension_restores_registry(self):
        with suspended():
            plan,base=self.make()
            self.assertIsNone(replacement_height(.2,.2,False))
            plan.validate_base('yard','detail',base['triangles'],base['materials'])
            with self.assertRaisesRegex(ValueError,'both'):activate(plan)
            plan.validate_base('yard','smooth',base['triangles'],base['materials'])
            activate(plan)
            self.assertEqual(replacement_height(.2,.2,False),1)
            self.assertEqual(replacement_height(.2,.2,True),1)
            self.assertIsNone(replacement_height(3,3,False))
            with suspended():self.assertIsNone(replacement_height(.2,.2,False))
            self.assertEqual(replacement_height(.2,.2,False),1)

    def test_unchanged_manifest_does_not_hide_a_changed_upstream_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'source.py').write_text('changed')
            metadata={'inputHashes':{'source.py':hashlib.sha256(b'original').hexdigest()}}
            source=root/'road-solids-detail.json';source.write_text(json.dumps(metadata))
            candidate=root/'candidate.json'
            candidate.write_text(json.dumps({'inputs':{source.name:hashlib.sha256(source.read_bytes()).hexdigest()}}))
            with self.assertRaisesRegex(ValueError,'Stale access dependency'):
                SiteAccessPlan.read(candidate,root)


if __name__=='__main__':unittest.main()
