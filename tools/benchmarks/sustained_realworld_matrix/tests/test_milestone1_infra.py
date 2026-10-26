#!/usr/bin/env python3
"""
tools/benchmarks/sustained_realworld_matrix/tests/test_milestone1_infra.py

Comprehensive Unit & Integration Test Suite for Milestone 1 Infrastructure Components:
- Target OS Matrix & Alpine 3.20 Image (musl 1.2.5, VERSION_ID=3.20.10)
- Docker Bridge Network Setup (setup_bridge_network.sh)
- Container Manager (Topology, cgroup limits, scratch volumes, FerroOS bash safety, crossover)
- Host Headroom Watchdog Daemon (Dynamic 16KB page size, 3-tier escalation, circuit breaker)
- Strict Execution Runner (Pipefail enforcement, unmasked exit codes 0/1/127/137/139/143)
"""

import os
import sys
import time
import signal
import unittest
import threading
import subprocess

MATRIX_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if MATRIX_DIR not in sys.path:
    sys.path.insert(0, MATRIX_DIR)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from infra import (
    HostResourceWatchdog,
    HostWatchdogSummary,
    DEFAULT_SAMPLE_INTERVAL_S,
    DEFAULT_MIN_SAFE_RAM_GB,
    DEFAULT_ABORT_THRESHOLD_RAM_GB,
    DEFAULT_MIN_CPU_IDLE_PCT,
    StrictExecutionRunner,
    CommandResult,
    run_strict_pipe,
    run_strict_command,
    execute_with_pipefail,
    classify_exit_code,
    ContainerManager,
    SlotId,
    SlotConfig,
    SLOT_DEFINITIONS,
    NETWORK_NAME,
    NETWORK_SUBNET,
    NETWORK_GATEWAY,
)


class TestHostHeadroomWatchdog(unittest.TestCase):
    """Verifies HostResourceWatchdog dynamic page detection, metrics sampling, and 3-tier escalation."""

    def test_01_page_size_detection(self):
        wd = HostResourceWatchdog()
        self.assertIn(wd.page_size_bytes, [4096, 16384])
        if sys.platform == "darwin" and os.uname().machine == "arm64":
            self.assertEqual(wd.page_size_bytes, 16384, "Apple Silicon must detect 16384 (16 KB) pages")

    def test_02_sample_host_metrics_format(self):
        wd = HostResourceWatchdog()
        metrics = wd.sample_host_metrics()
        self.assertIn("timestamp", metrics)
        self.assertIn("free_ram_gb", metrics)
        self.assertIn("cpu_idle_pct", metrics)
        self.assertIn("load_avg_1m", metrics)
        self.assertGreater(metrics["free_ram_gb"], 0.0)
        self.assertGreaterEqual(metrics["cpu_idle_pct"], 0.0)

    def test_03_tier1_healthy_operation(self):
        wd = HostResourceWatchdog(min_safe_ram_gb=6.0, abort_threshold_ram_gb=4.5, min_cpu_idle_pct=20.0)
        res = wd.record_sample(free_ram_gb=8.0, cpu_idle_pct=50.0)
        self.assertTrue(res)
        self.assertEqual(wd.violations_count, 0)
        self.assertFalse(wd.is_aborted())

    def test_04_tier2_warning_low_ram(self):
        wd = HostResourceWatchdog(min_safe_ram_gb=6.0, abort_threshold_ram_gb=4.5, min_cpu_idle_pct=20.0)
        warning_called = []
        wd.on_throttle_callback = lambda v: warning_called.append(v)
        res = wd.record_sample(free_ram_gb=5.2, cpu_idle_pct=50.0)
        self.assertTrue(res)
        self.assertEqual(wd.violations_count, 1)
        self.assertEqual(len(warning_called), 1)
        self.assertEqual(warning_called[0]["level"], "THROTTLE_WARNING")
        self.assertFalse(wd.is_aborted())

    def test_05_tier2_warning_low_cpu_idle(self):
        wd = HostResourceWatchdog(min_safe_ram_gb=6.0, abort_threshold_ram_gb=4.5, min_cpu_idle_pct=20.0)
        res = wd.record_sample(free_ram_gb=7.0, cpu_idle_pct=15.0)
        self.assertTrue(res)
        self.assertEqual(wd.violations_count, 1)
        self.assertFalse(wd.is_aborted())

    def test_06_tier3_circuit_breaker_emergency_abort(self):
        wd = HostResourceWatchdog(min_safe_ram_gb=6.0, abort_threshold_ram_gb=4.5, min_cpu_idle_pct=20.0)
        abort_called = []
        wd.on_abort_callback = lambda v: abort_called.append(v)
        res = wd.record_sample(free_ram_gb=4.2, cpu_idle_pct=40.0)
        self.assertFalse(res, "record_sample must return False when emergency abort triggers")
        self.assertEqual(wd.violations_count, 1)
        self.assertTrue(wd.is_aborted())
        self.assertEqual(len(abort_called), 1)
        self.assertEqual(abort_called[0]["level"], "CIRCUIT_BREAKER")

    def test_07_summary_contract_fields(self):
        wd = HostResourceWatchdog(min_safe_ram_gb=6.0, abort_threshold_ram_gb=4.5, min_cpu_idle_pct=20.0)
        wd.record_sample(free_ram_gb=8.0, cpu_idle_pct=60.0)
        wd.record_sample(free_ram_gb=5.5, cpu_idle_pct=45.0)
        wd.record_sample(free_ram_gb=4.1, cpu_idle_pct=30.0)
        summary = wd.get_summary()
        self.assertEqual(summary.samples_count, 3)
        self.assertEqual(summary.violations_count, 2)
        self.assertEqual(summary.min_free_ram_gb, 4.1)
        self.assertEqual(summary.min_cpu_idle_pct, 30.0)
        self.assertTrue(summary.emergency_abort_triggered)

    def test_08_empty_summary_defaults(self):
        wd = HostResourceWatchdog()
        summary = wd.get_summary()
        self.assertEqual(summary.samples_count, 0)
        self.assertEqual(summary.violations_count, 0)
        self.assertEqual(summary.min_free_ram_gb, 0.0)
        self.assertFalse(summary.emergency_abort_triggered)


class TestStrictExecutionRunner(unittest.TestCase):
    """Verifies StrictExecutionRunner pipefail unmasking, exit code preservation, and signal normalization."""

    def test_01_pipefail_success(self):
        code, out, err = run_strict_pipe("echo 'alpha beta' | grep alpha | wc -w")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "2")

    def test_02_pipefail_unmasks_middle_failure(self):
        code, out, err = run_strict_pipe("echo 'hello' | grep 'missing_str' | cat")
        self.assertEqual(code, 1)

    def test_03_pipefail_unmasks_command_not_found_127(self):
        code, out, err = run_strict_pipe("nonexistent_binary_matrix_xyz | cat")
        self.assertEqual(code, 127)

    def test_04_preserves_custom_exit_code(self):
        code, out, err = run_strict_pipe("(exit 55) | cat")
        self.assertEqual(code, 55)

    def test_05_preserves_sigkill_137(self):
        code, out, err = run_strict_pipe("bash -c 'kill -9 $$' | cat")
        self.assertEqual(code, 137)

    def test_06_preserves_sigsegv_139(self):
        code, out, err = run_strict_pipe("bash -c 'kill -11 $$' | cat")
        self.assertEqual(code, 139)

    def test_07_command_result_classification_and_tail(self):
        res = run_strict_command("echo 'line 1' >&2; echo 'line 2' >&2; exit 4")
        self.assertEqual(res.normalized_exit_code, 4)
        self.assertEqual(res.exit_classification, "APPLICATION_ERROR")
        self.assertFalse(res.is_success)
        self.assertIn("line 2", res.stderr_tail)

    def test_08_watchdog_abort_terminates_process_group(self):
        wd = HostResourceWatchdog()
        runner = StrictExecutionRunner()

        def background_abort():
            time.sleep(0.15)
            wd.record_sample(free_ram_gb=4.0, cpu_idle_pct=10.0)

        t = threading.Thread(target=background_abort)
        t.start()
        res = runner.run("sleep 15", timeout_s=10.0, watchdog=wd)
        t.join()

        self.assertTrue(res.watchdog_aborted)
        self.assertEqual(res.exit_classification, "WATCHDOG_TERMINATED")
        self.assertIn(res.normalized_exit_code, [137, 143])


class TestContainerTopologyAndManager(unittest.TestCase):
    """Verifies 3-container topology definitions, bridge network specs, and container manager lifecycle."""

    def test_01_slot_definitions_envelope(self):
        s_a = SLOT_DEFINITIONS[SlotId.SLOT_A]
        s_b = SLOT_DEFINITIONS[SlotId.SLOT_B]
        s_c = SLOT_DEFINITIONS[SlotId.SLOT_C]

        self.assertEqual(s_a.cpus, 2.0)
        self.assertEqual(s_a.memory, "4g")
        self.assertEqual(s_a.memory_swap, "4g")
        self.assertEqual(s_a.static_ip, "172.30.0.10")
        self.assertEqual(s_a.internal_port, 8080)
        self.assertEqual(s_a.scratch_limit_bytes, 15 * 1024 * 1024 * 1024)

        self.assertEqual(s_b.cpus, 2.0)
        self.assertEqual(s_b.memory, "4g")
        self.assertEqual(s_b.memory_swap, "4g")
        self.assertEqual(s_b.static_ip, "172.30.0.11")
        self.assertEqual(s_b.internal_port, 8080)
        self.assertEqual(s_b.scratch_limit_bytes, 15 * 1024 * 1024 * 1024)

        self.assertEqual(s_c.cpus, 1.0)
        self.assertEqual(s_c.memory, "2g")
        self.assertEqual(s_c.memory_swap, "2g")
        self.assertEqual(s_c.static_ip, "172.30.0.20")
        self.assertEqual(s_c.internal_port, 9090)
        self.assertEqual(s_c.scratch_limit_bytes, 5 * 1024 * 1024 * 1024)

        total_cpus = s_a.cpus + s_b.cpus + s_c.cpus
        self.assertEqual(total_cpus, 5.0)

    def test_02_bridge_network_specs(self):
        self.assertEqual(NETWORK_NAME, "realworld_matrix_net")
        self.assertEqual(NETWORK_SUBNET, "172.30.0.0/16")
        self.assertEqual(NETWORK_GATEWAY, "172.30.0.1")

    def test_03_ferro_bash_safety_enforced(self):
        cm = ContainerManager(auto_cleanup=False)
        with self.assertRaises(ValueError) as ctx:
            cm.start_slot(SlotId.SLOT_A, image="ferro-server", command=["sh", "-c", "echo test"], wait_ready=False)
        self.assertIn("FerroOS must invoke /usr/bin/bash", str(ctx.exception))

    def test_04_bridge_network_script_status(self):
        script_path = os.path.join(MATRIX_DIR, "docker/setup_bridge_network.sh")
        self.assertTrue(os.path.exists(script_path))
        self.assertTrue(os.access(script_path, os.X_OK))

        res = subprocess.run([script_path, "status"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("realworld_matrix_net", res.stdout)
        self.assertIn("172.30.0.0/16", res.stdout)


class TestAlpine320ImageVerification(unittest.TestCase):
    """Verifies that bench-alpine:latest is built from alpine:3.20 with musl 1.2.5."""

    def test_01_alpine_version_is_3_20(self):
        res = subprocess.run(
            ["docker", "run", "--rm", "bench-alpine:latest", "cat", "/etc/os-release"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn('VERSION_ID=3.20.10', res.stdout)
        self.assertIn('PRETTY_NAME="Alpine Linux v3.20"', res.stdout)

    def test_02_musl_libc_is_1_2_5(self):
        res = subprocess.run(
            ["docker", "run", "--rm", "bench-alpine:latest", "sh", "-c", "/lib/ld-musl-aarch64.so.1 --version 2>&1 || true"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res.returncode, 0)
        output = res.stdout + res.stderr
        self.assertIn("musl libc (aarch64)", output)
        self.assertIn("Version 1.2.5", output)

    def test_03_psutil_and_benchmark_tools_installed(self):
        res = subprocess.run(
            ["docker", "run", "--rm", "bench-alpine:latest", "python3", "-c", "import psutil; print('psutil_ok')"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("psutil_ok", res.stdout)

        res_fio = subprocess.run(
            ["docker", "run", "--rm", "bench-alpine:latest", "fio", "--version"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res_fio.returncode, 0)
        self.assertIn("fio-3.36", res_fio.stdout)

        res_sys = subprocess.run(
            ["docker", "run", "--rm", "bench-alpine:latest", "sysbench", "--version"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res_sys.returncode, 0)
        self.assertIn("sysbench 1.0.20", res_sys.stdout)


if __name__ == "__main__":
    unittest.main()
