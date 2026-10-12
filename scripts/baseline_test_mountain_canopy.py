"""Compare forest geometry outside the P3 patch against its preserved baseline."""
import json
import unittest
from collections import Counter
from shapely.geometry import Polygon, Point, box
from test_mountain_canopy import PLAN, FOREST, GEO
from baseline_inputs import baseline_input

class CanopyTests(unittest.TestCase):
    def test_outside_patch_unchanged(self):
        before = json.loads((baseline_input('urban-structure/p3/p2-forest-plan.json')).read_text())
        patch = box(*PLAN['bounds']).buffer(.000001)
        def faces(mesh):
            result = Counter()
            for tri, color in zip(mesh['triangles'], mesh['colors']):
                vertices = [tuple(mesh['points'][i]) for i in tri]
                if not patch.intersects(Polygon([p[:2] for p in vertices])):
                    result[(tuple(sorted(vertices)), color)] += 1
            return result
        for old, new in zip(before['regions'], FOREST['regions']):
            self.assertEqual(old['woodland'], new['woodland'])
            for profile in ['detail', 'smooth']:
                self.assertEqual(faces(old[profile]), faces(new[profile]), (old['id'], profile))
            self.assertEqual([c for c in old['crownClusters'] if not patch.intersects(Point(c[:2]).buffer(c[2]))],
                             [c for c in new['crownClusters'] if not patch.intersects(Point(c[:2]).buffer(c[2]))])
            self.assertEqual([c for c in old['crownClusters'][::2] if not patch.intersects(Point(c[:2]).buffer(c[2]))],
                             [c for c in new.get('smoothCrownClusters', new['crownClusters'][::2]) if not patch.intersects(Point(c[:2]).buffer(c[2]))])
        self.assertTrue(all(patch.contains(Point(GEO['trees'][i][:2])) for i in FOREST['mountainRemovedTreeIndices']))
