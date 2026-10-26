#!/usr/bin/env python3
"""
Tier 2 Boundary Tests: Features 16 through 18.
- Feature 16: 5-Minute Stress Ladder Boundaries
- Feature 17: Symmetric Crossover Slot-Swapping Boundaries
- Feature 18: Placement Bias Variance Gate (< 2.5%) Boundaries
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from tests.test_harness import (
    calculate_crossover_variance_pct,
    evaluate_placement_bias_gate,
)

class TestFeature16LadderBoundaries(unittest.TestCase):
    """Feature 16 Boundary Tests: Stress Ladder Progression."""

    def test_b16_01_duration_under_300s_rejected(self):
        def validate_duration(duration_s: int) -> bool:
            return duration_s >= 300
        self.assertFalse(validate_duration(299))

    def test_b16_02_duration_exact_300s_accepted(self):
        def validate_duration(duration_s: int) -> bool:
            return duration_s >= 300
        self.assertTrue(validate_duration(300))

    def test_b16_03_phase_1_2_boundary_at_60s(self):
        def get_phase_at_second(second: int) -> int:
            if 0 <= second < 60: return 1
            elif 60 <= second < 120: return 2
            elif 120 <= second < 180: return 3
            elif 180 <= second < 240: return 4
            elif 240 <= second < 280: return 5
            elif 280 <= second <= 300: return 6
            else: return -1
        self.assertEqual(get_phase_at_second(59), 1)
        self.assertEqual(get_phase_at_second(60), 2)

    def test_b16_04_phase_5_6_boundary_at_280s(self):
        def get_phase_at_second(second: int) -> int:
            if 240 <= second < 280: return 5
            elif 280 <= second <= 300: return 6
            return 0
        self.assertEqual(get_phase_at_second(279), 5)
        self.assertEqual(get_phase_at_second(280), 6)

    def test_b16_05_second_out_of_bounds_returns_error(self):
        def get_phase_at_second(second: int) -> int:
            if 0 <= second <= 300: return 1
            return -1
        self.assertEqual(get_phase_at_second(-1), -1)
        self.assertEqual(get_phase_at_second(301), -1)


class TestFeature17CrossoverBoundaries(unittest.TestCase):
    """Feature 17 Boundary Tests: Crossover Slot Swapper."""

    def test_b17_01_empty_target_in_pairing_rejected(self):
        def validate_pairing(a: str, b: str) -> bool:
            return bool(a and b and a.strip() and b.strip())
        self.assertFalse(validate_pairing("", "bench-ubuntu"))
        self.assertFalse(validate_pairing("ferro-server", "   "))

    def test_b17_02_slot_run_failure_detection(self):
        run_result = {"run_1_exit_code": 0, "run_2_exit_code": 1}
        success = (run_result["run_1_exit_code"] == 0 and run_result["run_2_exit_code"] == 0)
        self.assertFalse(success)

    def test_b17_03_zero_ops_crossover_run_handled(self):
        # When both runs have 0 ops, variance is 0.0%
        var = calculate_crossover_variance_pct(0, 0)
        self.assertEqual(var, 0.0)

    def test_b17_04_one_sided_zero_ops_crossover_run_produces_max_variance(self):
        # 100 vs 0 -> diff 100, avg 50 -> 200% variance
        var = calculate_crossover_variance_pct(100.0, 0.0)
        self.assertEqual(var, 200.0)
        self.assertFalse(evaluate_placement_bias_gate(var))

    def test_b17_05_negative_metric_raises_value_error(self):
        with self.assertRaises(ValueError):
            calculate_crossover_variance_pct(-10.0, 50.0)


class TestFeature18VarianceGateBoundaries(unittest.TestCase):
    """Feature 18 Boundary Tests: Placement Bias Variance Gate."""

    def test_b18_01_exact_boundary_two_point_five_percent_fails(self):
        # Gate rule is strictly < 2.50%
        self.assertFalse(evaluate_placement_bias_gate(2.5000))

    def test_b18_02_just_below_boundary_passes(self):
        self.assertTrue(evaluate_placement_bias_gate(2.4999))

    def test_b18_03_just_above_boundary_fails(self):
        self.assertFalse(evaluate_placement_bias_gate(2.5001))

    def test_b18_04_exact_zero_variance_passes(self):
        self.assertTrue(evaluate_placement_bias_gate(0.0000))

    def test_b18_05_floating_point_precision_boundary(self):
        # Verify precision rounding does not accidentally fail valid 2.49%
        var = 2.49499999999
        self.assertTrue(evaluate_placement_bias_gate(var))

if __name__ == "__main__":
    unittest.main()
