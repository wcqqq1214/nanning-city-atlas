"""Regression coverage for scoped validation gates and reference clipping."""
import contextlib
import io
import unittest
from unittest.mock import patch

import numpy as np
from shapely.geometry import box

from asset_budgets import MODEL_BYTE_LIMITS, validate_model_bytes
from scoped_validation import retained_triangles


class RuntimeValidationTests(unittest.TestCase):
    def test_download_budget_is_absolute_even_if_source_was_larger(self):
        for profile, limit in MODEL_BYTE_LIMITS.items():
            validate_model_bytes(profile, limit-1)
            with self.assertRaisesRegex(AssertionError, 'absolute loading budget'):
                validate_model_bytes(profile, limit)
            with self.assertRaises(AssertionError):
                validate_model_bytes(profile, limit+1_000_000)

    def test_native_reference_clips_coverage_without_losing_height_plane(self):
        source = np.array([[[-2., 0., 1.], [2., 0., 5.], [0., 4., 3.]]])
        result = retained_triangles(source, box(-1, -1, 1, 5))
        self.assertGreater(len(result), 0)
        self.assertTrue((np.abs(result[:, :, 0]) <= 1).all())
        np.testing.assert_allclose(result[:, :, 2], result[:, :, 0]+3)

    def test_scoped_edge_tolerance_still_detects_face_interior_penetration(self):
        from validate_ground_roads import clearance
        upper = np.array([[[0., 1., 0.], [1., 1., 0.], [0., 1., 1.]]])
        lower = upper.copy()
        lower[:, :, 1] = 2
        with contextlib.redirect_stdout(io.StringIO()):
            gap, _, _ = clearance(upper, lower, 'test', edge_tolerance=.0001)
        self.assertAlmostEqual(gap, -1)

    def test_scoped_runtime_continues_through_every_geometry_validator(self):
        # Use real published GLB headers/counts; expensive geometry is separately
        # exercised by each validator. A scoped return/exit must fail this test.
        import validate_runtime_assets as runtime
        validators = ['validate_railways', 'validate_minzu', 'validate_bridges',
                      'validate_ground_roads', 'validate_elevated_roads',
                      'validate_road_solids', 'validate_zhuxi', 'validate_malls',
                      'validate_cultural', 'validate_terrain']
        with contextlib.ExitStack() as stack:
            calls = {name: stack.enter_context(patch.object(runtime, name)) for name in validators}
            scope_check = stack.enter_context(patch('check_urban_scope_exports.validate'))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            runtime.validate_runtime_assets()
            scope_check.assert_called_once()
            for check in calls.values():
                check.assert_called_once()

    def test_one_failed_audit_does_not_skip_other_independent_checks(self):
        import validate_runtime_assets as runtime
        validators = ['validate_railways', 'validate_minzu', 'validate_bridges',
                      'validate_ground_roads', 'validate_elevated_roads',
                      'validate_road_solids', 'validate_zhuxi', 'validate_malls',
                      'validate_cultural', 'validate_terrain']
        with contextlib.ExitStack() as stack:
            calls = {name: stack.enter_context(patch.object(runtime, name)) for name in validators}
            calls['validate_ground_roads'].side_effect = AssertionError('stale plan')
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            with self.assertRaisesRegex(AssertionError, 'stale plan'):
                runtime.validate_geometry()
            for check in calls.values():
                check.assert_called_once()

    def test_scoped_geometry_failure_is_not_reported_as_success(self):
        import validate_runtime_assets as runtime
        with patch('check_urban_scope_exports.validate', side_effect=AssertionError('penetration')):
            with self.assertRaisesRegex(AssertionError, 'penetration'):
                runtime.validate_runtime_assets()


if __name__ == '__main__':
    unittest.main()
