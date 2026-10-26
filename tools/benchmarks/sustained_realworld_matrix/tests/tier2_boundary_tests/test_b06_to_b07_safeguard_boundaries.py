#!/usr/bin/env python3
"""
Tier 2 Boundary Tests: Features 6 through 7.
- Feature 6: Host Headroom Watchdog Daemon Boundaries
- Feature 7: Shell & Process Pipefail Enforcement Boundaries
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from tests.test_harness import (
    HostResourceWatchdog,
    execute_with_pipefail,
    MIN_SAFE_HOST_RAM_GB,
    EMERGENCY_ABORT_RAM_GB,
)

class TestFeature06WatchdogBoundaries(unittest.TestCase):
    """Feature 6 Boundary Tests: Host Headroom Watchdog."""

    def test_b06_01_exact_abort_boundary_at_4_5_gb(self):
        watchdog = HostResourceWatchdog(sample_interval_s=1.0)
        res = watchdog.record_sample(free_ram_gb=4.500, cpu_idle_pct=50.0)
        self.assertTrue(res, "4.500 GB is at the safe threshold and should not abort")
        self.assertFalse(watchdog.get_summary().emergency_abort_triggered)

    def test_b06_02_just_below_abort_boundary_at_4_499_gb_aborts(self):
        watchdog = HostResourceWatchdog(sample_interval_s=1.0)
        res = watchdog.record_sample(free_ram_gb=4.499, cpu_idle_pct=50.0)
        self.assertFalse(res, "4.499 GB must trigger immediate emergency abort")
        self.assertTrue(watchdog.get_summary().emergency_abort_triggered)

    def test_b06_03_exact_warning_boundary_at_6_0_gb(self):
        watchdog = HostResourceWatchdog(sample_interval_s=1.0)
        watchdog.record_sample(free_ram_gb=6.000, cpu_idle_pct=20.000)
        self.assertEqual(watchdog.get_summary().violations_count, 0)

    def test_b06_04_just_below_warning_boundary_at_5_999_gb(self):
        watchdog = HostResourceWatchdog(sample_interval_s=1.0)
        watchdog.record_sample(free_ram_gb=5.999, cpu_idle_pct=20.0)
        self.assertEqual(watchdog.get_summary().violations_count, 1)

    def test_b06_05_zero_and_negative_ram_triggers_immediate_abort(self):
        watchdog = HostResourceWatchdog(sample_interval_s=1.0)
        res = watchdog.record_sample(free_ram_gb=0.0, cpu_idle_pct=0.0)
        self.assertFalse(res)
        self.assertTrue(watchdog.get_summary().emergency_abort_triggered)


class TestFeature07PipefailBoundaries(unittest.TestCase):
    """Feature 7 Boundary Tests: Shell & Process Pipefail Enforcement."""

    def test_b07_01_middle_pipe_failure_in_four_stage_pipeline(self):
        # stage 1 ok, stage 2 fails, stage 3 ok, stage 4 ok
        cmd = "echo 'stage1' | grep 'missing_pattern' | tr 'a-z' 'A-Z' | wc -l"
        code, out, err = execute_with_pipefail(cmd)
        self.assertEqual(code, 1)

    def test_b07_02_first_pipe_failure_propagates_exit_code(self):
        cmd = "(exit 17) | cat | cat"
        code, out, err = execute_with_pipefail(cmd)
        self.assertEqual(code, 17)

    def test_b07_03_exit_code_137_sigkill_oom_preservation(self):
        cmd = "(kill -9 $$ 2>/dev/null) | cat"
        # In bash subshell kill -9 returns 137 (128 + 9)
        code, out, err = execute_with_pipefail("bash -c 'kill -9 $$' | cat")
        self.assertEqual(code, 137)

    def test_b07_04_exit_code_139_sigsegv_preservation(self):
        code, out, err = execute_with_pipefail("bash -c 'kill -11 $$' | cat")
        self.assertEqual(code, 139)

    def test_b07_05_multi_command_pipefail_with_semicolon(self):
        cmd = "echo 'ok'; false | cat; echo 'should_not_run'"
        code, out, err = execute_with_pipefail(cmd)
        self.assertEqual(code, 1)
        self.assertNotIn("should_not_run", out)

if __name__ == "__main__":
    unittest.main()
