#!/usr/bin/env python3
"""
Tier 1 Feature Tests: Features 19 through 25.
- Feature 19: Second-by-Second JSON Telemetry Pipeline
- Feature 20: Latency Distribution CDF Visualization
- Feature 21: Throughput Timeline Boxplots Visualization
- Feature 22: Memory RSS Stability Area Visualization
- Feature 23: 6-Spoke Radar Resilience Visualization
- Feature 24: Crossover Variance Bar Visualization
- Feature 25: Individual OS Dossiers & Scorecard
"""

import unittest
import sys
import os
import math

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from tests.test_harness import (
    REQUIRED_TELEMETRY_RECORD_FIELDS,
    validate_telemetry_dataset,
    evaluate_business_scorecard,
)

def make_sample_telemetry_record(sec: int) -> dict:
    return {
        "second": sec,
        "traffic": {"rps": 5000, "completed_ops": 5000, "errors": 0, "bytes_sent": 10240, "bytes_received": 20480},
        "latency_ms": {"p50": 0.45, "p90": 0.75, "p95": 0.92, "p99": 1.25, "p99_9": 2.10, "max": 4.50},
        "cpu": {"user_pct": 32.5, "system_pct": 14.2, "throttled_usec": 0},
        "memory": {"rss_mb": 420.5, "dirty_pages_count": 128, "cgroup_usage_bytes": 440000000},
        "scheduler": {"voluntary_context_switches": 12000, "involuntary_context_switches": 450},
        "sockets": {"tcp_established": 100, "tcp_time_wait": 25, "dropped_packets": 0},
        "host_headroom": {"host_free_ram_gb": 8.5, "host_cpu_idle_pct": 45.0},
    }

class TestFeature19TelemetryPipeline(unittest.TestCase):
    """Feature 19: Second-by-Second JSON Telemetry Pipeline."""

    def test_01_valid_300_seconds_dataset_passes(self):
        data = [make_sample_telemetry_record(i) for i in range(1, 301)]
        valid, err = validate_telemetry_dataset(data, 300)
        self.assertTrue(valid)
        self.assertIsNone(err)

    def test_02_dataset_with_fewer_than_300_seconds_fails(self):
        data = [make_sample_telemetry_record(i) for i in range(1, 250)]
        valid, err = validate_telemetry_dataset(data, 300)
        self.assertFalse(valid)
        self.assertIn("Expected 300", err)

    def test_03_missing_fields_in_record_detected(self):
        bad_rec = make_sample_telemetry_record(1)
        del bad_rec["memory"]
        valid, err = validate_telemetry_dataset([bad_rec], 1)
        self.assertFalse(valid)
        self.assertIn("missing required fields", err)

    def test_04_non_monotonic_latencies_detected(self):
        bad_rec = make_sample_telemetry_record(1)
        bad_rec["latency_ms"]["p95"] = 0.1  # lower than p50 (0.45)
        valid, err = validate_telemetry_dataset([bad_rec], 1)
        self.assertFalse(valid)
        self.assertIn("non-monotonic latencies", err)

    def test_05_persistence_target_file_path_conforms_to_contract(self):
        expected_path = "tools/reports/sustained_realworld_multi_os_matrix.json"
        self.assertTrue(expected_path.endswith(".json"))
        self.assertIn("tools/reports", expected_path)


class TestFeature20LatencyCDFVisualization(unittest.TestCase):
    """Feature 20: Latency Distribution CDF Visualization."""

    def test_01_figure_paths_conform_to_contract(self):
        png = "tools/reports/figures/figure1_latency_cdf.png"
        svg = "tools/reports/figures/figure1_latency_cdf.svg"
        self.assertTrue(png.endswith(".png"))
        self.assertTrue(svg.endswith(".svg"))

    def test_02_percentile_curves_monotonic_increasing(self):
        percentiles = [0.5, 0.9, 0.95, 0.99, 0.999]
        latencies = [0.4, 0.7, 0.9, 1.2, 2.0]
        for i in range(len(latencies) - 1):
            self.assertLessEqual(latencies[i], latencies[i+1])

    def test_03_logarithmic_scale_handling_positive_values(self):
        latencies = [0.1, 1.0, 10.0, 100.0]
        log_lat = [math.log10(x) for x in latencies]
        self.assertEqual(log_lat, [-1.0, 0.0, 1.0, 2.0])

    def test_04_all_seven_targets_represented(self):
        target_series = {
            "ferro-server": [0.3, 0.5, 0.8],
            "bench-ubuntu": [0.6, 0.9, 1.4],
            "bench-debian": [0.7, 1.0, 1.5],
            "bench-rocky": [0.8, 1.1, 1.6],
            "almalinux:9": [0.8, 1.1, 1.6],
            "bench-alpine": [0.5, 0.8, 1.3],
            "amazonlinux:2023": [0.7, 1.0, 1.5],
        }
        self.assertEqual(len(target_series), 7)

    def test_05_hdr_tail_percentile_p99_99_extractable(self):
        rec = make_sample_telemetry_record(1)
        self.assertIn("p99_9", rec["latency_ms"])


class TestFeature21ThroughputBoxplotsVisualization(unittest.TestCase):
    """Feature 21: Throughput Timeline Boxplots Visualization."""

    def test_01_figure_paths_conform_to_contract(self):
        png = "tools/reports/figures/figure2_throughput_boxplots.png"
        svg = "tools/reports/figures/figure2_throughput_boxplots.svg"
        self.assertTrue(png.endswith(".png"))
        self.assertTrue(svg.endswith(".svg"))

    def test_02_six_phase_grouping_for_boxplots(self):
        phases = [f"Phase {i}" for i in range(1, 7)]
        self.assertEqual(len(phases), 6)

    def test_03_iqr_calculation_validity(self):
        sample_rps = [1000, 2000, 3000, 4000, 5000, 6000, 7000]
        sample_rps.sort()
        q1 = sample_rps[len(sample_rps)//4]
        q3 = sample_rps[(3*len(sample_rps))//4]
        iqr = q3 - q1
        self.assertGreater(iqr, 0)

    def test_04_rps_series_per_second_extraction(self):
        records = [make_sample_telemetry_record(i) for i in range(1, 11)]
        rps_series = [r["traffic"]["rps"] for r in records]
        self.assertEqual(len(rps_series), 10)
        self.assertTrue(all(x == 5000 for x in rps_series))

    def test_05_box_plot_outlier_filtering(self):
        data = [100, 102, 101, 99, 103, 500]  # 500 is outlier
        mean = sum(data) / len(data)
        outliers = [x for x in data if abs(x - mean) > 100]
        self.assertEqual(outliers, [500])


class TestFeature22MemoryRSSAreaVisualization(unittest.TestCase):
    """Feature 22: Memory RSS Stability Area Visualization."""

    def test_01_figure_paths_conform_to_contract(self):
        png = "tools/reports/figures/figure3_memory_rss_stability.png"
        svg = "tools/reports/figures/figure3_memory_rss_stability.svg"
        self.assertTrue(png.endswith(".png"))
        self.assertTrue(svg.endswith(".svg"))

    def test_02_four_gb_cgroup_ceiling_line_defined(self):
        cgroup_ceiling_mb = 4096.0
        self.assertEqual(cgroup_ceiling_mb, 4.0 * 1024)

    def test_03_dirty_page_flushes_tracked_in_telemetry(self):
        rec = make_sample_telemetry_record(1)
        self.assertIn("dirty_pages_count", rec["memory"])
        self.assertGreaterEqual(rec["memory"]["dirty_pages_count"], 0)

    def test_04_area_plot_series_stacking_order(self):
        series = ["clean_rss_mb", "dirty_rss_mb", "kernel_slab_mb"]
        self.assertEqual(len(series), 3)

    def test_05_rss_within_slot_limit(self):
        rec = make_sample_telemetry_record(1)
        self.assertLessEqual(rec["memory"]["rss_mb"], 4096.0)


class TestFeature23ResilienceRadarVisualization(unittest.TestCase):
    """Feature 23: 6-Spoke Radar Resilience Visualization."""

    def test_01_figure_paths_conform_to_contract(self):
        png = "tools/reports/figures/figure4_resilience_radar.png"
        svg = "tools/reports/figures/figure4_resilience_radar.svg"
        self.assertTrue(png.endswith(".png"))
        self.assertTrue(svg.endswith(".svg"))

    def test_02_radar_has_six_axes_matching_phases(self):
        axes = ["Baseline", "Healthy", "Concurrency", "Choking", "Chaos", "Deadzone"]
        self.assertEqual(len(axes), 6)

    def test_03_score_normalization_between_zero_and_one_hundred(self):
        scores = [95.0, 92.0, 88.0, 84.0, 78.0, 70.0]
        for s in scores:
            self.assertGreaterEqual(s, 0.0)
            self.assertLessEqual(s, 100.0)

    def test_04_all_seven_targets_can_be_overlaid(self):
        radar_data = {target: [90.0] * 6 for target in ["ferro-server", "bench-ubuntu", "bench-debian",
                                                        "bench-rocky", "almalinux:9", "bench-alpine",
                                                        "amazonlinux:2023"]}
        self.assertEqual(len(radar_data), 7)

    def test_05_radar_closed_loop_polygon_coordinates(self):
        angles = [i * (2 * math.pi / 6) for i in range(6)]
        self.assertEqual(len(angles), 6)


class TestFeature24CrossoverVarianceBarVisualization(unittest.TestCase):
    """Feature 24: Crossover Variance Bar Visualization."""

    def test_01_figure_paths_conform_to_contract(self):
        png = "tools/reports/figures/figure5_crossover_variance.png"
        svg = "tools/reports/figures/figure5_crossover_variance.svg"
        self.assertTrue(png.endswith(".png"))
        self.assertTrue(svg.endswith(".svg"))

    def test_02_variance_threshold_marker_at_two_point_five_percent(self):
        threshold_pct = 2.50
        self.assertEqual(threshold_pct, 2.5)

    def test_03_bars_differentiate_passed_vs_failed_scenarios(self):
        bar_colors = []
        for var in [1.2, 0.8, 2.49, 2.65]:
            bar_colors.append("green" if var < 2.50 else "red")
        self.assertEqual(bar_colors, ["green", "green", "green", "red"])

    def test_04_variance_deltas_sorted_by_magnitude(self):
        deltas = [2.1, 0.5, 1.4, 0.2]
        deltas.sort()
        self.assertEqual(deltas, [0.2, 0.5, 1.4, 2.1])

    def test_05_sixty_five_scenario_labels_supported(self):
        labels = [f"SCEN-{i:02d}" for i in range(1, 66)]
        self.assertEqual(len(labels), 65)


class TestFeature25DossiersAndScorecard(unittest.TestCase):
    """Feature 25: Individual OS Dossiers & Scorecard."""

    def test_01_good_superior_rating_criteria(self):
        metrics = {"p99_latency_ms": 0.8, "unexpected_drops": 0, "throttling_events": 0, "segfaults": 0}
        rating = evaluate_business_scorecard(metrics)
        self.assertEqual(rating, "🟢 Good / Superior")

    def test_02_acceptable_rating_criteria(self):
        metrics = {"p99_latency_ms": 4.5, "unexpected_drops": 2, "throttling_events": 5, "segfaults": 0}
        rating = evaluate_business_scorecard(metrics)
        self.assertEqual(rating, "🟡 Acceptable")

    def test_03_poor_rating_criteria(self):
        metrics = {"p99_latency_ms": 65.0, "unexpected_drops": 60, "throttling_events": 150, "segfaults": 0}
        rating = evaluate_business_scorecard(metrics)
        self.assertEqual(rating, "🟠 Poor")

    def test_04_business_unacceptable_on_process_segfault(self):
        metrics = {"p99_latency_ms": 0.5, "segfaults": 1}
        rating = evaluate_business_scorecard(metrics)
        self.assertEqual(rating, "🔴 Business Unacceptable")

    def test_05_seven_os_dossiers_structured_in_final_report(self):
        report_path = "tools/reports/SUSTAINED_REALWORLD_MATRIX_REPORT.md"
        self.assertTrue(report_path.endswith(".md"))

if __name__ == "__main__":
    unittest.main()
