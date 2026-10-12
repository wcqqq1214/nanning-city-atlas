"""Boundary regressions: concave cuts, vertical walls and whole buildings."""
import unittest

import numpy as np
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from scope_city import clip_face, crop_geometry, explicit_surface
from urban_scope import UrbanScope


def attributes(points):
    return np.concatenate([np.asarray(points, dtype=float), np.tile([0, 1, 0], (len(points), 1))], axis=1)


class ScopeGeometryTests(unittest.TestCase):
    def test_compact_flat_faces_keep_distinct_normals_at_shared_crease(self):
        from types import SimpleNamespace
        points = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])
        faces = np.array([[0, 1, 2], [0, 3, 1]])
        expanded = explicit_surface(SimpleNamespace(points=points, faces=faces, normals=None))
        np.testing.assert_array_equal(expanded.points[expanded.faces], points[faces])
        np.testing.assert_allclose(expanded.normals[:3], np.tile([0, 0, 1], (3, 1)))
        np.testing.assert_allclose(expanded.normals[3:], np.tile([0, 1, 0], (3, 1)))

    def test_outside_triangle_has_no_fragments(self):
        self.assertEqual(list(clip_face(attributes([[3, 0, 0], [4, 0, 0], [3, 0, -1]]), box(-1, -1, 1, 1))), [])

    def test_concave_cut_cannot_keep_triangle_just_because_vertices_are_inside(self):
        mask = Polygon([(0, 0), (4, 0), (4, 4), (3, 4), (3, 1), (1, 1), (1, 4), (0, 4)])
        a = attributes([[.5, 2, -.5], [3.5, 5, -3.5], [.5, 2, -3.5]])
        points, normals, faces, _ = crop_geometry(a[:, :3], a[:, 3:], np.array([[0, 1, 2]]), mask)
        actual = unary_union([Polygon(p[:, [0, 2]]*[1, -1]) for p in points[faces]])
        expected = Polygon(a[:, [0, 2]]*[1, -1]).intersection(mask)
        self.assertLess(actual.symmetric_difference(expected).area, 1e-6)
        # Original sloping plane y = x + 1.5 is retained by interpolation.
        np.testing.assert_allclose(points[:, 1], points[:, 0]+1.5, atol=1e-6)
        np.testing.assert_allclose(normals, np.tile([0, 1, 0], (len(normals), 1)))

    def test_vertical_road_wall_is_clipped_without_disappearing(self):
        a = attributes([[-2, 0, 0], [2, 0, 0], [2, 3, 0]])
        result = np.asarray(list(clip_face(a, box(-1, -1, 1, 1))))
        self.assertGreater(len(result), 0)
        self.assertGreaterEqual(result[:, :, 0].min(), -1)
        self.assertLessEqual(result[:, :, 0].max(), 1)
        before_normal = np.cross(a[1, :3]-a[0, :3], a[2, :3]-a[0, :3])
        for t in result:
            self.assertGreater(np.dot(np.cross(t[1, :3]-t[0, :3], t[2, :3]-t[0, :3]), before_normal), 0)

    def test_zero_width_broad_phase_does_not_leave_railway_wall_outside(self):
        for points in [[[-2, 0, 0], [2, 0, 0], [2, 3, 0]],
                       [[0, 0, -2], [0, 0, 2], [0, 3, 2]]]:
            a = attributes(points)
            p, _, faces, _ = crop_geometry(a[:, :3], a[:, 3:], np.array([[0, 1, 2]]), box(-1, -1, 1, 1))
            self.assertGreater(len(faces), 0)
            self.assertLessEqual(float(np.abs(p[:, [0, 2]]).max()), 1)

    def test_crossing_building_keeps_all_faces_but_outside_component_is_removed(self):
        a = attributes([[-2, 0, 0], [2, 0, 0], [2, 3, 0],
                        [8, 0, 0], [10, 0, 0], [10, 3, 0]])
        faces = np.array([[0, 1, 2], [3, 4, 5]])
        points, _, kept, stats = crop_geometry(a[:, :3], a[:, 3:], faces, box(-1, -1, 1, 1), whole=True)
        self.assertEqual(len(kept), 1)
        self.assertEqual(stats['created'], 0)
        self.assertEqual(set(map(tuple, points[kept[0]])), set(map(tuple, a[:3, :3])))

    def test_hole_and_disconnected_intersections_are_preserved(self):
        mask = box(-5, -5, 5, 5).difference(box(-1, -1, 1, 1))
        a = attributes([[-4, 0, 4], [4, 0, 4], [0, 0, -4]])
        result = list(clip_face(a, mask))
        actual = unary_union([Polygon(t[:, [0, 2]]*[1, -1]) for t in result])
        expected = Polygon(a[:, [0, 2]]*[1, -1]).intersection(mask)
        self.assertLess(actual.symmetric_difference(expected).area, 1e-8)

    def test_current_approved_scope_preserves_places_and_defers_unmapped_extension(self):
        import json
        from urban_scope import ROOT
        scope = UrbanScope.read()
        scope.require_approved()
        self.assertTrue(scope.context.covers(scope.core))
        self.assertTrue(scope.context.equals(scope.context.envelope))
        self.assertTrue(scope.context.covers(scope.transition))
        self.assertTrue(scope.coverage.covers(scope.context))
        self.assertTrue(scope.transition.buffer(1e-5).covers(scope.water_corridors))
        self.assertTrue(scope.landscape.covers(scope.core))
        self.assertGreater(scope.proposed.difference(scope.coverage).area, 0)
        for i in scope.retained_buildings:
            self.assertLess(scope.buildings[i].intersection(scope.coverage).difference(scope.core).area, 1e-8)
        from shapely.geometry import Point
        for place in json.loads((ROOT/'data/landmarks.json').read_text()):
            self.assertTrue(scope.core.covers(Point(scope.project(place['lon'], place['lat']))), place['id'])
        # Garden Expo stays outside the detailed scope by the user's decision.
        self.assertFalse(scope.core.covers(Point(scope.project(108.47, 22.727))))

    def test_coarse_context_fills_rectangle_and_meets_sloping_city_edge(self):
        from types import SimpleNamespace
        from city_context import build_context
        from scope_city import boundary_samples
        from shapely.geometry import Point
        bounds = box(0, 0, 12, 12)
        transition = box(3, 3, 9, 9)
        scope = SimpleNamespace(context=bounds, transition=transition, units=100,
                                source={'contextGridMeters': 300},
                                geo={'roads': [{'class': 'primary', 'points': [[0, 1], [12, 1]]}]})
        xy = np.array([[0, 0], [12, 0], [12, 12], [0, 12]])
        p = np.column_stack([xy[:, 0], xy[:, 0]*.1+xy[:, 1]*.2, -xy[:, 1]])
        source = p[[[0, 1, 2], [0, 2, 3]]]
        samples = [(transition.exterior.project(Point(x, y)), x*.1+y*.2)
                   for x, y in [(3, 3), (6, 3), (9, 3), (9, 9), (3, 9)]]
        # Small water polygon tests terrain coverage even when water is hidden.
        water = np.array([[[.2, .26, -.2], [2, .26, -.2], [.2, .26, -2]]])
        terrain, roads, report = build_context(scope, source, water, samples)
        tp, _, tf = terrain
        actual = unary_union([Polygon(t[:, [0, 2]]*[1, -1]) for t in tp[tf]])
        self.assertLess(actual.symmetric_difference(bounds.difference(transition)).area, 1e-5)
        np.testing.assert_allclose(tp[:, 1], tp[:, 0]*.1-tp[:, 2]*.2, atol=2e-6)
        rp, _, rf = roads
        self.assertGreater(len(rf), 0)
        np.testing.assert_allclose(rp[:, 1], rp[:, 0]*.1-rp[:, 2]*.2+.015, atol=2e-6)
        self.assertLess(report['coverageErrorSquareMeters'], .01)
        self.assertGreater(len(boundary_samples(tp, tf, bounds)), 4)

    def test_forest_crosses_city_line_and_merges_into_outer_ground(self):
        from city_context import fade_canopy, TerrainSampler
        from types import SimpleNamespace
        scope = SimpleNamespace(core=box(-1, -2, 1, 2), units=100,
                                source={'landscapeFadeMeters': 200})
        p = np.array([[0, 1, 0], [2, 1, 0], [3, 1, -1]], dtype=np.float32)
        n = np.tile([0, 1, 0], (3, 1)).astype(np.float32)
        f = np.array([[0, 1, 2]])
        actual, normals, faces = fade_canopy(p, n, f, scope,
            lambda xy: np.zeros(len(xy)), TerrainSampler(np.array([
                [[-10, -2, 10], [10, 2, 10], [0, 0, -10]]])))
        actual = actual[[np.argmin(np.linalg.norm(actual[:, [0, 2]]-q[[0, 2]], axis=1)) for q in p]]
        np.testing.assert_array_equal(actual[0], p[0])
        self.assertGreater(actual[1, 1], .4)  # Still raised past the city line.
        self.assertLess(actual[1, 1], p[1, 1])
        self.assertAlmostEqual(actual[2, 1], .6, places=3)
        self.assertGreaterEqual(len(faces), len(f))
        np.testing.assert_allclose(np.linalg.norm(normals, axis=1), 1, atol=1e-6)

    def test_canopy_face_is_refined_over_ridge_with_safe_original_vertices(self):
        from types import SimpleNamespace
        from city_context import TerrainSampler, conform_canopy, canopy_clearance
        scope = SimpleNamespace(core=box(-3, -3, -2, -2), units=100,
                                source={'landscapeFadeMeters': 10000})
        p = np.array([[0, 1, 0], [2, 1, 0], [0, 1, -2]], dtype=np.float32)
        n = np.tile([0, 1, 0], (3, 1)).astype(np.float32)
        f = np.array([[0, 1, 2]])
        ground_points = np.array([[0, 0, 0], [2, 0, 0], [0, 0, -2], [.5, 2, -.5]])
        ground = TerrainSampler(ground_points[[[0, 1, 3], [1, 2, 3], [2, 0, 3]]])
        self.assertTrue((p[:, 1]-ground(p[:, [0, 2]]*[1, -1]) > 0).all())
        self.assertLess(canopy_clearance(p[f], ground, scope.core).min(), -.9)
        result, normals, faces = conform_canopy(p, n, f, scope, ground)
        self.assertGreater(len(faces), 1)
        self.assertGreaterEqual(canopy_clearance(result[faces], ground, scope.core).min(), -1e-6)
        area = unary_union([Polygon(t[:, [0, 2]]*[1, -1]) for t in result[faces]])
        self.assertLess(area.symmetric_difference(Polygon(p[:, [0, 2]]*[1, -1])).area, 1e-7)

    def test_refinement_keeps_outer_forest_edge_on_a_ground_valley(self):
        from types import SimpleNamespace
        from city_context import TerrainSampler, conform_canopy, canopy_clearance
        scope = SimpleNamespace(core=box(-3, -3, 0, 3), units=100,
                                source={'landscapeFadeMeters': 200})
        p = np.array([[1, 2, 0], [2, 1.00005, -2], [2, 1.00005, 2]], dtype=np.float32)
        n = np.tile([0, 1, 0], (3, 1)).astype(np.float32)
        g = np.array([[1, 0, 0], [2, 1, -2], [2, 1, 2], [2, 0, 0]])
        ground = TerrainSampler(g[[[0, 1, 3], [0, 3, 2]]])
        result, _, faces = conform_canopy(p, n, np.array([[0, 1, 2]]), scope, ground)
        edge = result[result[:, 0] == 2]
        self.assertGreater(len(edge), 2)
        np.testing.assert_allclose(edge[:, 1]-ground(edge[:, [0, 2]]*[1, -1]), .00005, atol=1e-6)
        self.assertGreaterEqual(canopy_clearance(result[faces], ground, scope.core).min(), 0)

    def test_quantized_ground_join_uses_highest_adjacent_surface(self):
        from city_context import TerrainSampler
        ground = TerrainSampler(np.array([[[0, 0, 0], [1, 0, 0], [0, 0, -1]],
                                          [[0, 1, 0], [1, 1, 0], [0, 1, -1]]]))
        np.testing.assert_allclose(ground.upper_envelope(np.array([[.2, .2]])), [1])

    def test_terrain_gap_sampling_cannot_extrapolate_a_vertical_spike(self):
        from city_context import TerrainSampler
        source = np.array([[[0, 0, 0], [.0001, 4, 0], [0, 0, -1]]])
        sample = TerrainSampler(source)
        z = sample(np.array([[3, .5], [-3, .5], [.00005, .25]]))
        self.assertTrue(np.isfinite(z).all())
        self.assertGreaterEqual(z.min(), 0)
        self.assertLessEqual(z.max(), 4)
        self.assertAlmostEqual(z[2], 2)


if __name__ == '__main__':
    unittest.main()
