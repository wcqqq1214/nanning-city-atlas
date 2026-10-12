"""Check compound roofs and supplied ground support without historical candidates."""
import sys
import unittest
from pathlib import Path

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from prepare_block_rollout import record
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'blender'))
from block_massing import build_compound

ROOT = Path(__file__).resolve().parents[1]


class Capture:
    def __init__(self): self.faces = []
    def face(self, vertices, material): self.faces.append((vertices, material))


class CompoundTests(unittest.TestCase):
    def make_building(self):
        site = {'id': 'test', 'use': 'commercial', 'template': {'type': 'commercial-promenade'}}
        return record(site, 'tower', 'court', [(box(0, 0, 1, 1), 0, 8), (box(.3, .3, .7, .7), 8, 30)], None)

    def test_roof_cap_at_and_below_podium(self):
        for cap in [.55, .582, .65, None]:
            capture = Capture()
            result = build_compound(capture, self.make_building(), (.4, .5), 'wall', cap)
            self.assertIsNotNone(result)
            roof = [Polygon([(x, y) for x, y, z in f]) for f, m in capture.faces if m == 'roof']
            self.assertAlmostEqual(sum(p.area for p in roof), 1)
            self.assertLess(unary_union(roof).symmetric_difference(box(0, 0, 1, 1)).area, 1e-10)
            if cap is not None: self.assertLessEqual(max(z for f, m in capture.faces for x, y, z in f), cap)
        capture = Capture()
        self.assertIsNone(build_compound(capture, self.make_building(), (.4, .5), 'wall', .5))
        self.assertEqual(capture.faces, [])

    def test_ground_support_uses_complete_supplied_range(self):
        capture = Capture()
        result = build_compound(capture, self.make_building(), (.2, .8), 'wall')
        self.assertEqual(result['supportRange'], [.2, .8])
        self.assertAlmostEqual(result['floor'], .802)
        self.assertAlmostEqual(min(z for f, m in capture.faces for x, y, z in f), .195)
        with self.assertRaises(ValueError): build_compound(Capture(), self.make_building(), (1, 0), 'wall')


if __name__ == '__main__': unittest.main()
