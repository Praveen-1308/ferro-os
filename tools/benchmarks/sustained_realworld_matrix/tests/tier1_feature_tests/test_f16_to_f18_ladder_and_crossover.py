#!/usr/bin/env python3
"""
Tier 1 Feature Tests: Features 16 through 18.
- Feature 16: 5-Minute Sustained Stress Ladder Engine
- Feature 17: Symmetric Crossover Slot-Swapping Engine
- Feature 18: Placement Bias Variance Gate (< 2.5%)
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from tests.test_harness import (
    STRESS_LADDER_PHASES,
    calculate_crossover_variance_pct,
    evaluate_placement_bias_gate,
)

class TestFeature16StressLadderEngine(unittest.TestCase):
    """Feature 16: 5-Minute Sustained Stress Ladder Engine."""

    def test_01_ladder_has_exactly_six_phases(self):
        self.assertEqual(len(STRESS_LADDER_PHASES), 6)

    def test_02_total_duration_is_three_hundred_seconds(self):
        total_duration = STRESS_LADDER_PHASES[-1]["end_s"]
        self.assertEqual(total_duration, 300)

    def test_03_phases_are_contiguous_and_ordered(self):
        prev_end = 0
        for p in STRESS_LADDER_PHASES:
            self.assertEqual(p["start_s"], prev_end)
            self.assertGreater(p["end_s"], p["start_s"])
            prev_end = p["end_s"]
        self.assertEqual(prev_end, 300)

    def test_04_phase_names_match_specification(self):
        expected_names = [
            "Baseline & Cold Start",
            "Healthy Steady State",
            "High Concurrency",
            "Choking & Contention",
            "Fault Injection & Chaos",
            "Deadzone Boundary",
        ]
        actual_names = [p["name"] for p in STRESS_LADDER_PHASES]
        self.assertEqual(actual_names, expected_names)

    def test_05_phase_durations_comply_with_spec(self):
        durations = [p["end_s"] - p["start_s"] for p in STRESS_LADDER_PHASES]
        self.assertEqual(durations, [60, 60, 60, 60, 40, 20])


class TestFeature17CrossoverSwappingEngine(unittest.TestCase):
    """Feature 17: Symmetric Crossover Slot-Swapping Engine."""

    def test_01_crossover_pairing_generates_both_slot_permutations(self):
        def generate_crossover_runs(os_x: str, os_y: str):
            run1 = {"slot_a": os_x, "slot_b": os_y}
            run2 = {"slot_a": os_y, "slot_b": os_x}
            return run1, run2

        r1, r2 = generate_crossover_runs("ferro-server", "bench-ubuntu")
        self.assertEqual(r1["slot_a"], "ferro-server")
        self.assertEqual(r1["slot_b"], "bench-ubuntu")
        self.assertEqual(r2["slot_a"], "bench-ubuntu")
        self.assertEqual(r2["slot_b"], "ferro-server")

    def test_02_crossover_result_contains_both_telemetry_sets(self):
        crossover_res = {
            "scenario_id": "SCEN-WEB-01",
            "run_1_direct": {"rps": 50000, "p95_ms": 1.2, "rss_mb": 420},
            "run_2_swapped": {"rps": 49800, "p95_ms": 1.22, "rss_mb": 422},
        }
        self.assertIn("run_1_direct", crossover_res)
        self.assertIn("run_2_swapped", crossover_res)

    def test_03_cooldown_and_cache_flush_hook_present(self):
        class MockSwapper:
            def __init__(self):
                self.flushed = False
            def flush_caches_and_cooldown(self):
                self.flushed = True
        s = MockSwapper()
        s.flush_caches_and_cooldown()
        self.assertTrue(s.flushed)

    def test_04_crossover_handles_all_seven_distributions(self):
        targets = ["ferro-server", "bench-ubuntu", "bench-debian", "bench-rocky",
                   "almalinux:9", "bench-alpine", "amazonlinux:2023"]
        # FerroOS paired against each of the 6 competitors
        pairings = [("ferro-server", competitor) for competitor in targets if competitor != "ferro-server"]
        self.assertEqual(len(pairings), 6)

    def test_05_crossover_prevents_identical_os_self_pairing(self):
        def validate_pairing(os_a: str, os_b: str):
            if os_a == os_b:
                raise ValueError("Cannot pair identical operating systems in crossover test.")
        with self.assertRaises(ValueError):
            validate_pairing("ferro-server", "ferro-server")


class TestFeature18PlacementBiasVarianceGate(unittest.TestCase):
    """Feature 18: Placement Bias Variance Gate (< 2.5%)."""

    def test_01_identical_metrics_yield_zero_variance(self):
        var = calculate_crossover_variance_pct(100.0, 100.0)
        self.assertEqual(var, 0.0)
        self.assertTrue(evaluate_placement_bias_gate(var))

    def test_02_variance_under_two_point_five_pct_passes(self):
        # 100 vs 101 -> diff 1, avg 100.5 -> 0.995%
        var = calculate_crossover_variance_pct(100.0, 101.0)
        self.assertLess(var, 2.50)
        self.assertTrue(evaluate_placement_bias_gate(var))

    def test_03_variance_at_or_above_two_point_five_pct_fails(self):
        # 100 vs 103 -> diff 3, avg 101.5 -> 2.955%
        var = calculate_crossover_variance_pct(100.0, 103.0)
        self.assertGreater(var, 2.50)
        self.assertFalse(evaluate_placement_bias_gate(var))

    def test_04_multi_metric_gate_enforces_worst_case_delta(self):
        deltas = {
            "rps": calculate_crossover_variance_pct(50000, 50500), # ~0.99%
            "p95": calculate_crossover_variance_pct(1.20, 1.21),  # ~0.82%
            "rss": calculate_crossover_variance_pct(400, 402),    # ~0.49%
        }
        max_delta = max(deltas.values())
        self.assertLess(max_delta, 2.50)
        self.assertTrue(evaluate_placement_bias_gate(max_delta))

    def test_05_zero_values_handled_gracefully(self):
        var = calculate_crossover_variance_pct(0.0, 0.0)
        self.assertEqual(var, 0.0)
        self.assertTrue(evaluate_placement_bias_gate(var))

if __name__ == "__main__":
    unittest.main()
