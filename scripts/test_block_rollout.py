"""Verify P5 source-bound scope, typology structure, open space and compound roofs."""
import copy
import json
import math
import sys
import unittest
from pathlib import Path

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

from prepare_block_rollout import SOURCE, prepare, record
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'blender'))
from urban_blocks import palette_records
from block_massing import build_compound

ROOT = Path(__file__).resolve().parents[1]


class Capture:
    def __init__(self): self.faces = []
    def face(self, vertices, material): self.faces.append((vertices, material))


class RolloutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = json.loads((ROOT/'work/urban-structure/p5/quality-candidate.json').read_text())
        cls.config = json.loads(SOURCE.read_text())
        cls.after = prepare(cls.before)
        cls.sites = {s['id']: s for s in cls.config['sites']}
        cls.plans = [p for p in cls.after['urbanBlocks'] if p['id'] in cls.sites]

    def test_scope_and_palette(self):
        removed = {b['id'] for p in self.plans for b in p['removedBuildings']}
        self.assertEqual(sum(len(p['removedBuildings']) for p in self.plans), len(removed))
        before = {b['id']: b for b in self.before['buildings']}
        for b in self.after['buildings']:
            if b['id'] in before:
                self.assertEqual(b, before[b['id']])
        after_ids = {b['id'] for b in self.after['buildings']}
        self.assertEqual(set(before)-after_ids, removed)
        self.assertTrue(all(before[i]['source'] == 'procedural' and not before[i].get('blockId') for i in removed))
        for key in self.before:
            if key not in ['buildings', 'urbanBlocks', 'urban', 'stats']:
                self.assertEqual(self.before[key], self.after[key])
        self.assertEqual(self.before['urbanBlocks'], self.after['urbanBlocks'][:len(self.before['urbanBlocks'])])
        self.assertEqual(palette_records(self.before), palette_records(self.after))
        added_urban = [p for site in self.plans for p in site['addedUrban']]
        self.assertEqual(self.after['urban'], self.before['urban']+added_urban)

    def test_saved_candidate_matches_current_sources(self):
        saved = json.loads((ROOT/'work/urban-structure/p5/rollout/candidate.json').read_text())
        self.assertEqual(saved, self.after)

    def test_repeatability_and_independent_sites(self):
        self.assertEqual(self.after, prepare(self.before))
        with self.assertRaises(ValueError): prepare(self.after)
        modified = copy.deepcopy(self.config)
        modified['sites'][0]['template']['towerHeightsMeters'][0] += 3
        result = prepare(self.before, modified)
        self.assertEqual([b for b in self.after['buildings'] if b.get('blockId') != self.config['sites'][0]['id']],
                         [b for b in result['buildings'] if b.get('blockId') != self.config['sites'][0]['id']])

    def test_exclusions_and_open_space(self):
        buildings = self.after['buildings']
        shapes = [Polygon(b['rings'][0], b['rings'][1:]) for b in buildings]
        tree = STRtree(shapes)
        water = unary_union([Polygon(p[0], p[1:]) for p in self.after['water']])
        parks = unary_union([Polygon(p[0], p[1:]) for p in self.after['parks']])
        roads = unary_union([LineString(r['points']).buffer(.19 if r['class'] in ['primary', 'trunk', 'motorway'] else
                            .135 if r['class'] == 'secondary' else .10) for r in self.after['roads']])
        plans = {p['id']: p for p in self.plans}
        for b, shape in zip(buildings, shapes):
            if b.get('blockId') not in self.sites: continue
            plan = plans[b['blockId']]; limits = self.sites[b['blockId']]['limits']
            self.assertTrue(shape.is_valid)
            self.assertTrue(Polygon(plan['boundary'][0]).buffer(-limits['siteSetbackMeters']/100).covers(shape))
            self.assertEqual(len(tree.query(shape, predicate='intersects')), 1)
            self.assertFalse(shape.intersects(water.buffer(limits['waterClearanceMeters']/100)))
            self.assertFalse(shape.intersects(parks) or shape.intersects(roads))
            for space in plan['reservedSpaces']:
                self.assertFalse(shape.intersects(Polygon(space['rings'][0], space['rings'][1:])))

    def test_typologies_and_bounded_map_adjustments(self):
        groups = {use: [b for b in self.after['buildings'] if b.get('blockId') in self.sites and b['use'] == use]
                  for use in ['residential', 'commercial', 'campus', 'industrial']}
        self.assertTrue(all(groups.values()))
        for b in groups['residential']+groups['commercial']:
            self.assertEqual(len(b['massing']), 2)
            podium, tower = b['massing']
            self.assertEqual(podium['topMeters'], tower['baseMeters'])
            self.assertTrue(Polygon(podium['rings'][0]).contains(Polygon(tower['rings'][0])))
        self.assertTrue(any(len(b['rings']) > 1 for b in groups['campus']))
        for b in groups['campus']:
            adjustment = b['registrationAdjustment']
            self.assertLessEqual(math.hypot(*adjustment['translationMeters']), 12)
            self.assertGreaterEqual(adjustment['footprintScale'], .9)
            self.assertEqual(b['height'], b['levels']*3.2)
        for b in groups['industrial']:
            self.assertEqual(len(b['massing']), 1)
            self.assertLessEqual(b['height'], 20)
            self.assertGreater(Polygon(b['rings'][0]).area*10000, 7000)

    def test_exposed_roof_partition(self):
        for b in self.after['buildings']:
            if b.get('blockId') not in self.sites: continue
            # With a podium and tower, their visible roofs partition the ground
            # footprint in projection; no courtyard may acquire a cap.
            roofs = [Polygon(t) for p in b['massing'] for t in p['roofTriangles']]
            footprint = Polygon(b['rings'][0], b['rings'][1:])
            self.assertLess(unary_union(roofs).symmetric_difference(footprint).area, 1e-8)
            self.assertAlmostEqual(sum(p.area for p in roofs), footprint.area)
            for part in b['massing']:
                for triangle in part['fullRoofTriangles']:
                    a, c, d = triangle
                    self.assertGreater((c[0]-a[0])*(d[1]-a[1])-(c[1]-a[1])*(d[0]-a[0]), 0)


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
