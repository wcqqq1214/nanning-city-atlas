"""Verify pilot scope, exclusions, deterministic massing, holes and palette slots."""
import copy
import json
import sys
import unittest
from pathlib import Path
from shapely.geometry import Polygon, LineString
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'blender'))
from prepare_urban_blocks import apply_blocks
from urban_blocks import palette_records


from baseline_inputs import baseline_input

class BlockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = json.loads((baseline_input('urban-structure/baseline-73edbb7/public/data/geography.json')).read_text())
        cls.after = apply_blocks(copy.deepcopy(cls.before))


    def test_scope_and_palette(self):
        after = self.after
        plan = after['urbanBlocks'][0]
        self.assertEqual(len(plan['removedBuildings']), 18)
        self.assertEqual(len(plan['buildingIds']), 13)
        self.assertEqual([b['legacyIndex'] for b in palette_records(after)], list(range(len(self.before['buildings']))))
        self.assertEqual(len({b['id'] for b in after['buildings']}), len(after['buildings']))
        for key in ['water', 'waterTriangles', 'parks', 'urban', 'inferredUrban', 'trees', 'roads', 'bounds']:
            self.assertEqual(after[key], self.before[key])
        for b in after['buildings']:
            if 'legacyIndex' in b:
                for key, value in self.before['buildings'][b['legacyIndex']].items():
                    self.assertEqual(b[key], value)


    def test_determinism(self):
        self.assertEqual(self.after, apply_blocks(copy.deepcopy(self.before)))
        with self.assertRaises(ValueError):
            apply_blocks(copy.deepcopy(self.after))


    def test_exclusions_and_open_space(self):
        after = self.after
        shapes = [Polygon(b['rings'][0], b['rings'][1:]) for b in after['buildings']]
        pilot = [Polygon(b['rings'][0]) for b in after['buildings'] if b.get('blockId')]
        tree = STRtree(shapes)
        blocked = unary_union([Polygon(p[0], p[1:]) for p in after['water']+after['parks']])
        roads = unary_union([LineString(r['points']).buffer(.13 if r['class'] in ['primary', 'trunk', 'motorway'] else .085 if r['class']=='secondary' else .0475) for r in after['roads']])
        plan = after['urbanBlocks'][0]
        boundary = Polygon(plan['boundary'][0])
        open_space = unary_union([Polygon(p[0], p[1:]) for p in plan['openSpace']])
        for shape in pilot:
            self.assertTrue(shape.is_valid and boundary.covers(shape))
            self.assertEqual(len(tree.query(shape, predicate='intersects')), 1)
            self.assertFalse(blocked.intersects(shape) or roads.intersects(shape))
            self.assertFalse(open_space.intersects(shape))
        self.assertGreater(open_space.area/boundary.area, .6)
        for a in pilot:
            for b in pilot:
                if a != b:
                    self.assertGreater(a.distance(b), .20)
