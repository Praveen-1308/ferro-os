#!/usr/bin/env python3
"""
Tier 1 Feature Tests: Features 6 through 7.
- Feature 6: Host Headroom Watchdog Daemon
- Feature 7: Shell & Process Pipefail Enforcement
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from tests.test_harness import (
    HostResourceWatchdog,
    HostWatchdogSummary,
    execute_with_pipefail,
    MIN_SAFE_HOST_RAM_GB,
    EMERGENCY_ABORT_RAM_GB,
    MIN_SAFE_CPU_IDLE_PCT,
)

class TestFeature06HostHeadroomWatchdog(unittest.TestCase):
    """Feature 6: Host Headroom Watchdog Daemon."""

    def test_01_healthy_headroom_records_zero_violations(self):
        watchdog = HostResourceWatchdog(sample_interval_s=1.0)
        watchdog.record_sample(free_ram_gb=8.5, cpu_idle_pct=45.0)
        watchdog.record_sample(free_ram_gb=7.2, cpu_idle_pct=35.0)
        summary = watchdog.get_summary()
        self.assertEqual(summary.violations_count, 0)
        self.assertFalse(summary.emergency_abort_triggered)
        self.assertGreaterEqual(summary.min_free_ram_gb, MIN_SAFE_HOST_RAM_GB)

    def test_02_emergency_abort_triggered_below_four_point_five_gb(self):
        watchdog = HostResourceWatchdog(sample_interval_s=1.0)
        watchdog.record_sample(free_ram_gb=6.5, cpu_idle_pct=50.0)
        res = watchdog.record_sample(free_ram_gb=4.2, cpu_idle_pct=30.0)
        self.assertFalse(res, "record_sample should return False on emergency abort")
        summary = watchdog.get_summary()
        self.assertTrue(summary.emergency_abort_triggered)
        self.assertGreater(summary.violations_count, 0)

    def test_03_warning_violation_between_four_five_and_six_gb(self):
        watchdog = HostResourceWatchdog(sample_interval_s=1.0)
        watchdog.record_sample(free_ram_gb=5.2, cpu_idle_pct=40.0)
        summary = watchdog.get_summary()
        self.assertEqual(summary.violations_count, 1)
        self.assertFalse(summary.emergency_abort_triggered)

    def test_04_cpu_idle_violation_below_twenty_percent(self):
        watchdog = HostResourceWatchdog(sample_interval_s=1.0)
        watchdog.record_sample(free_ram_gb=8.0, cpu_idle_pct=14.0)
        summary = watchdog.get_summary()
        self.assertEqual(summary.violations_count, 1)
        self.assertEqual(summary.min_cpu_idle_pct, 14.0)

    def test_05_summary_reports_correct_sample_counts_and_extrema(self):
        watchdog = HostResourceWatchdog(sample_interval_s=0.5)
        for ram in [10.0, 9.2, 8.1, 7.5, 6.8]:
            watchdog.record_sample(free_ram_gb=ram, cpu_idle_pct=50.0)
        summary = watchdog.get_summary()
        self.assertEqual(summary.samples_count, 5)
        self.assertEqual(summary.min_free_ram_gb, 6.8)
        self.assertFalse(summary.emergency_abort_triggered)


class TestFeature07PipefailEnforcement(unittest.TestCase):
    """Feature 7: Shell & Process Pipefail Enforcement."""

    def test_01_successful_pipeline_returns_zero(self):
        code, out, err = execute_with_pipefail("echo 'alpha beta' | grep alpha | wc -w")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "2")

    def test_02_early_pipeline_failure_propagates_non_zero(self):
        # Without pipefail, 'grep missing' fails (1) but 'echo done' would mask it (0)
        code, out, err = execute_with_pipefail("echo 'hello' | grep 'missing_string' | cat")
        self.assertNotEqual(code, 0)
        self.assertEqual(code, 1)

    def test_03_exit_code_127_command_not_found_preserved(self):
        code, out, err = execute_with_pipefail("nonexistent_binary_xyz_123 | cat")
        self.assertEqual(code, 127)

    def test_04_exit_code_preserves_explicit_custom_failures(self):
        code, out, err = execute_with_pipefail("(exit 42) | cat")
        self.assertEqual(code, 42)

    def test_05_stderr_is_captured_without_loss(self):
        code, out, err = execute_with_pipefail("echo 'critical error log' >&2; exit 1")
        self.assertEqual(code, 1)
        self.assertIn("critical error log", err)

if __name__ == "__main__":
    unittest.main()
