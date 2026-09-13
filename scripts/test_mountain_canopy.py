"""Check local canopy support, clearings and frozen P2 scope preservation."""
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

import numpy as np
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'blender'), str(ROOT/'scripts')]
from forest_canopy import PLAN as FOREST, terrain_surface
from mountain_terrain import PLAN, canopy_factor
from test_waterfront import ground, GEO, DEM


def shape(rings):
    return unary_union([Polygon(r[0], r[1:]) for r in rings])


class CanopyTests(unittest.TestCase):
    def test_coverage_and_park_clearings(self):
        paths = unary_union([shape(r) for r in PLAN['pathFootprints'].values()])
        coverage = unary_union([shape(r['coverage']) for r in FOREST['regions']])
        self.assertLess(coverage.intersection(paths.buffer(.03999, join_style=2)).intersection(box(*PLAN['bounds'])).area, 1e-8)
        tower = Point(PLAN['towerCenterSceneXY'])
        self.assertLess(coverage.intersection(tower.buffer(.14999)).area, 1e-8)
        self.assertGreater(coverage.intersection(tower.buffer(.85)).area, .1)
        for region in FOREST['regions']:
            area = shape(region['coverage'])
            for profile in ['detail', 'smooth']:
                mesh = region[profile]
                actual = unary_union([Polygon([mesh['points'][i][:2] for i in tri]) for tri in mesh['triangles']])
                self.assertLess(actual.difference(area.buffer(.00002)).area, .00001)
                self.assertLess(area.buffer(-.00002).difference(actual).area, .00001)

    def test_faces_supported_by_final_terrain(self):
        patch = box(*PLAN['bounds'])
        checked = 0
        for region in FOREST['regions']:
            for profile in ['detail', 'smooth']:
                mesh = region[profile]
                points = np.asarray(mesh['points'])
                z = {}
                for tri in mesh['triangles']:
                    vertices = points[tri]
                    if not patch.intersects(Polygon(vertices[:, :2])):
                        continue
                    levels = []
                    for i, (x, y, rise) in zip(tri, vertices):
                        if i not in z:
                            z[i] = terrain_surface(x, y, ground, GEO['bounds'], DEM['cols'], DEM['rows'], profile=='smooth')+rise
                        levels.append(z[i])
                    for weights in [[1/3]*3, [.5, .5, 0], [0, .5, .5], [.5, 0, .5]]:
                        x, y = np.asarray(weights)@vertices[:, :2]
                        floor = terrain_surface(x, y, ground, GEO['bounds'], DEM['cols'], DEM['rows'], profile=='smooth')
                        gap = np.dot(weights, levels)-floor
                        self.assertGreater(gap, .095*canopy_factor(x, y), (region['id'], profile, tri, gap))
                    checked += 1
        self.assertGreater(checked, 10000)

    def test_outside_patch_unchanged(self):
        before = json.loads((ROOT/'work/urban-structure/p3/p2-forest-plan.json').read_text())
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


if __name__ == '__main__':
    unittest.main()
