"""Regression checks for the simplified boulevard and level lake approaches."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'blender'))
from minzu_avenue import MinzuAvenue, PLAN


class MinzuProfileTests(unittest.TestCase):
    def test_lake_crossing_stays_level_on_uneven_shores(self):
        def ground(x, y, mobile=False):
            return .35 + .006*x + .04*math.sin(x) + (.006 if mobile else 0)
        road = MinzuAvenue(lambda x,y: ground(x,y)+.065, ground)
        heights = [road.at(key,s)[2] for key,path in road.paths.items()
                   for s in path.lengths if road.in_nanhu(*path.at(s)[:2])]
        self.assertGreater(len(heights), 80)
        self.assertLess(max(heights)-min(heights), 1e-8)
        for key,path in road.paths.items():
            for s in path.lengths:
                x,y,z = road.at(key,s)
                self.assertGreater(z-ground(x,y,True), .06)

    def test_only_three_lane_main_carriageways_are_emitted(self):
        self.assertEqual(len(PLAN['omittedPaths']), 44)
        self.assertEqual(len(PLAN['paths']), 67)
        self.assertTrue(all(not r['frontage'] and r['lanes']==3 for r in PLAN['paths']))
        self.assertEqual(set(PLAN['replacedRoads']), {r['roadIndex'] for r in PLAN['paths']+PLAN['omittedPaths']})


if __name__ == '__main__':
    unittest.main()
