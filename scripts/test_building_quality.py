"""Check source-constrained footprints, height evidence, and unchanged city scope."""
import copy
import sys
import unittest
from pathlib import Path

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from prepare_building_quality import (
    estimate_height, height_donors, positive_number, prepare, simplify_footprint, mesh_roof_triangles, stable_roof_diagonals,
)
from prepare_urban_blocks import rings, roof_triangles

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'blender'))
from urban_blocks import palette_records


def building(identity=1, x=0, height=16, use='apartments'):
    return {'id': f'b{identity}', 'sourceRef': f'osm/way/{identity}', 'source': 'osm',
            'legacyIndex': identity-1, 'rings': rings(box(x, 0, x+.1, .1)),
            'height': height, 'use': use, 'mappedHeight': False}


def donor(identity, x, height=16):
    return {'sourceRef': f'osm/way/{identity}', 'heightMeters': height,
            'kind': 'height', 'center': (x, .05)}


class FootprintTests(unittest.TestCase):
    def test_needle_diagonal_is_flipped_without_changing_boundary(self):
        import numpy as np
        vertices=np.array([[0.,0.],[2.,-.001],[4.,0.],[2.,1.]])
        old=np.array([[0,1,2],[0,2,3]])
        new=stable_roof_diagonals(vertices,old)
        def altitude(f):
            a,b,c=vertices[f];area=abs(np.linalg.det([b-a,c-a]))
            return area/max(np.linalg.norm(b-a),np.linalg.norm(c-b),np.linalg.norm(a-c))
        self.assertGreater(min(map(altitude,new)),min(map(altitude,old)))
        self.assertTrue(np.array_equal(new,stable_roof_diagonals(vertices,old)))
        before=unary_union([Polygon(vertices[f]) for f in old])
        after=unary_union([Polygon(vertices[f]) for f in new])
        self.assertLess(before.symmetric_difference(after).area,1e-12)

    def test_roof_is_triangulated_after_float32_storage(self):
        import numpy as np
        # Near-collinear courtyard/wing vertices can cross an internal diagonal
        # after float32 storage at a far-from-origin city position.
        outline=[[159.998,-71.129],[159.952,-71.254],[159.983,-71.265],
                 [159.95,-71.356],[159.918,-71.345],[159.888,-71.426],
                 [159.764,-71.617],[159.281,-71.435],[159.588,-70.59],[159.998,-71.129]]
        shape=Polygon(np.asarray(outline,dtype=np.float32).astype(float))
        faces=[Polygon(t) for t in mesh_roof_triangles([outline])]
        union=unary_union(faces)
        self.assertLess(union.symmetric_difference(shape).area,1e-10)
        self.assertLess(sum(t.area for t in faces)-union.area,1e-10)

    def test_small_wing_and_reentrant_corners(self):
        # A 1 m-wide projecting wing and a U-shaped courtyard mouth survive.
        shape = Polygon([(0, 0), (.2, 0), (.2, .2), (.15, .2),
                         (.15, .05), (.05, .05), (.05, .25), (.04, .25),
                         (.04, .2), (0, .2)])
        simplified, provenance = simplify_footprint(shape, {})
        self.assertTrue(simplified.covers(box(.041, .201, .049, .249)))
        self.assertFalse(simplified.intersects(box(.06, .06, .14, .19)))
        self.assertLessEqual(provenance['toleranceMeters'], .25)
        self.assertLessEqual(shape.symmetric_difference(simplified).area/shape.area, .02)

    def test_courtyard_roof_matches_all_rings(self):
        shape = box(0, 0, 2, 2).difference(box(.5, .5, 1.5, 1.5))
        simplified, _ = simplify_footprint(shape, {'building': 'university'})
        self.assertEqual(len(simplified.interiors), 1)
        triangles = [Polygon(t) for t in roof_triangles(simplified)]
        self.assertAlmostEqual(sum(t.area for t in triangles), shape.area)
        self.assertLess(unary_union(triangles).symmetric_difference(shape).area, 1e-10)

    def test_error_guard_reduces_tolerance(self):
        # Large initial tolerance is not accepted when it removes substantial area.
        from prepare_building_quality import POLICY
        policy = {**POLICY['footprints'], 'smallToleranceMeters': 20}
        shape = Polygon([(0, 0), (.2, 0), (.2, .2), (.12, .2),
                         (.12, .07), (.08, .07), (.08, .2), (0, .2)])
        simplified, provenance = simplify_footprint(shape, {}, policy)
        self.assertLess(provenance['toleranceMeters'], 20)
        self.assertLessEqual(shape.symmetric_difference(simplified).area/shape.area, .02)

    def test_size_and_name_caps(self):
        for shape, tags, expected in [(box(0, 0, .1, .1), {}, .25),
                                      (box(0, 0, .5, .5), {}, .75),
                                      (box(0, 0, 2, 2), {}, 1.5),
                                      (box(0, 0, 2, 2), {'name': '校舍'}, .5)]:
            self.assertEqual(simplify_footprint(shape, tags)[1]['toleranceMeters'], expected)


class HeightTests(unittest.TestCase):
    def test_invalid_source_numbers(self):
        for value in [None, '', 'unknown', 'nan', 'inf', '-2', '0', '3;4']:
            self.assertIsNone(positive_number(value))
        self.assertEqual(positive_number(' 18 m '), 18)

    def test_known_height_and_levels_preserve_existing_value(self):
        # Preserve the established clamped value; do not accidentally reclamp differently.
        b = building(height=450)
        value, source = estimate_height(b, {'height': '500'}, {})
        self.assertEqual(value, 450)
        self.assertEqual(source['value'], '500')
        b['height'] = 19.2
        value, source = estimate_height(b, {'building:levels': '6'}, {})
        self.assertEqual(value, 19.2)
        self.assertEqual(source['kind'], 'levels')

    def test_same_use_median_and_no_estimate_cascade(self):
        rows = [building(i, x=i, height=h) for i, h in [(2, 12), (3, 18), (4, 24), (5, 150)]]
        tags = {b['sourceRef']: {'building': 'apartments', 'height': str(b['height'])}
                for b in rows[:3]}
        tags[rows[3]['sourceRef']] = {'building': 'apartments'}
        donors = height_donors(rows, tags)
        self.assertEqual(len(donors['apartments']), 3)
        value, source = estimate_height(building(), {}, donors)
        self.assertEqual(value, 18)
        self.assertEqual(source['method'], 'nearby-use-median')
        rows[3]['heightSource'] = {'method': 'nearby-use-median'}
        self.assertEqual(height_donors(rows, tags), donors)

    def test_duplicate_parts_self_and_distant_donors_do_not_supply_evidence(self):
        sources = [donor(2, .2), donor(2, .3), donor(3, .4), donor(1, .1), donor(4, 6)]
        value, source = estimate_height(building(), {}, {'apartments': sources})
        self.assertEqual(value, 16)
        self.assertEqual(source['reason'], 'insufficient-same-use-neighbours')

    def test_unknown_use_and_disagreement_retain_fallback(self):
        sources = {'apartments': [donor(2, 1, 6), donor(3, 2, 18), donor(4, 3, 90)]}
        self.assertEqual(estimate_height(building(use='yes'), {}, sources)[1]['reason'], 'unknown-use')
        value, source = estimate_height(building(), {}, sources)
        self.assertEqual(value, 16)
        self.assertEqual(source['reason'], 'neighbour-heights-disagree')

    def test_nearest_distinct_sources_have_stable_order(self):
        sources = [donor(i, .2+i/10, 12+i) for i in range(2, 12)]
        sources += [donor(2, 1.5, 100)]
        result = estimate_height(building(), {}, {'apartments': sources})
        self.assertEqual(result, estimate_height(building(), {}, {'apartments': list(reversed(sources))}))
        self.assertEqual(len(result[1]['donors']), 7)
        self.assertEqual(result[1]['donors'][0]['heightMeters'], 14)


class ScopeTests(unittest.TestCase):
    def fixture(self):
        # Deliberately far from the current public terrain projection.
        b = building()
        b['rings'] = rings(box(0, 0, .12, .1))
        geography = {'metersPerUnit': 100, 'center': [0, 0], 'bounds': [-2, -2, 2, 2],
                     'buildings': [b, {**building(2, 1), 'source': 'infill'}],
                     'trees': [[1.5, 1.5, .1]], 'water': [], 'roads': [],
                     'urbanBlocks': [], 'testMetadata': {'preserve': [1, 2]}}
        snapshot = {'elements': [{'type': 'way', 'id': 1, 'tags': {'building': 'apartments'},
                     'geometry': [{'lon': x/1113.2, 'lat': y/1113.2}
                                  for x, y in box(0, 0, .1, .1).exterior.coords]}]}
        return geography, snapshot

    def test_candidate_scope_projection_and_repeatability(self):
        before, snapshot = self.fixture()
        frozen = copy.deepcopy(before)
        after = prepare(before, snapshot)
        self.assertEqual(before, frozen)
        self.assertEqual(after, prepare(before, snapshot))
        for key in before:
            if key != 'buildings':
                self.assertEqual(before[key], after[key])
        self.assertEqual(after['buildings'][1], before['buildings'][1])
        self.assertEqual([b['id'] for b in after['buildings']], [b['id'] for b in before['buildings']])
        self.assertAlmostEqual(Polygon(after['buildings'][0]['rings'][0]).area, .01)
        self.assertEqual(palette_records(after), palette_records(before))
        with self.assertRaises(ValueError):
            prepare(after, snapshot)

    def test_wrong_units_rejected(self):
        before, snapshot = self.fixture()
        before['metersPerUnit'] = 1
        with self.assertRaises(ValueError):
            prepare(before, snapshot)


if __name__ == '__main__':
    unittest.main()
