"""Verify pilot scope, exclusions, deterministic massing, holes and palette slots."""
import copy
import json
import sys
import unittest
from pathlib import Path
from shapely.geometry import Polygon, LineString, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'blender'))
from prepare_urban_blocks import apply_blocks, roof_triangles
from urban_blocks import palette_records, build_massing


class BlockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = json.loads((ROOT/'work/urban-structure/baseline-73edbb7/public/data/geography.json').read_text())
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

    def test_hole_and_ground_support(self):
        shape = box(0, 0, 1, 1).difference(box(.3, .3, .7, .7))
        roof = roof_triangles(shape)
        self.assertLess(unary_union([Polygon(t) for t in roof]).symmetric_difference(shape).area, 1e-8)
        building = {'id': 'test-courtyard', 'height': 18, 'rings': [list(r.coords) for r in [shape.exterior, *shape.interiors]], 'roofTriangles': roof}
        class Capture:
            def __init__(self): self.faces = []
            def face(self, vertices, material): self.faces.append((vertices, material))
        capture = Capture()
        surface = lambda x, y: (.5+x*.1+y*.03, .52+x*.1+y*.03)
        result = build_massing(capture, building, surface, 'building')
        self.assertAlmostEqual(result['floor'], .662)
        self.assertAlmostEqual(result['top'], .842)
        for face, material in capture.faces:
            if material != 'roof':
                for x, y, z in face[:2]:
                    self.assertLess(z, surface(x, y)[0])
        # Hole walls exist and their roofs never cover the central void.
        self.assertGreater(len(capture.faces), len(roof)+4)


if __name__ == '__main__':
    unittest.main()
