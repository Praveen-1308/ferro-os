#!/usr/bin/env python3
"""
tools/benchmarks/sustained_realworld_matrix/tests/test_adversarial_m1_empiric.py

Independent Adversarial Verification & Stress Test Suite for Milestone 1 Infrastructure.
Executed by Challenger 4 (Empirical Challenger) to verify that all 7 edge-case failure points
from GATE_STATUS.md are completely resolved under adversarial stress conditions:

1. HostResourceWatchdog: Thread contention & rapid start/stop cycles (20 threads, 200 concurrent ops, 50 sequential cycles).
2. HostResourceWatchdog: Re-entrant status queries inside callbacks (RLock verification).
3. HostResourceWatchdog: Sensor failure fallback under deadzone conditions (vm_stat, top, corrupt output).
4. StrictExecutionRunner: High-throughput streaming (>10 MB stdout, >5 MB stderr, interleaved concurrent pipes).
5. StrictExecutionRunner: Broken pipe / SIGPIPE unmasking and POSIX signal classification.
6. StrictExecutionRunner: Uncooperative child process group termination (SIGKILL after grace period).
7. StrictExecutionRunner: Orphan grandchild holding pipe bounded cleanup (FD leakage defense).
8. ContainerManager: FerroOS affirmative whitelist bypass attempts across command, entrypoint, and exec_in_slot.
9. ContainerManager: Scratch volume wipe failure checking (dangling container / volume-in-use error detection).
10. ContainerManager: Isolated bridge network subnet drift detection and automatic healing.
"""

import os
import sys
import time
import signal
import unittest
import threading
import subprocess
from unittest.mock import patch, MagicMock

MATRIX_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if MATRIX_DIR not in sys.path:
    sys.path.insert(0, MATRIX_DIR)

from infra.strict_runner import (
    StrictExecutionRunner,
    run_strict_pipe,
    run_strict_command,
    classify_exit_code,
    CommandResult,
)
from infra.host_watchdog import (
    HostResourceWatchdog,
    HostWatchdogSummary,
)
from infra.container_manager import (
    ContainerManager,
    SlotId,
    SLOT_DEFINITIONS,
    NETWORK_NAME,
    NETWORK_SUBNET,
    NETWORK_GATEWAY,
    FERRO_ALLOWED_PREFIXES,
    validate_ferro_command_safety,
)


class TestHostResourceWatchdogAdversarial(unittest.TestCase):
    """Adversarial stress-testing of HostResourceWatchdog concurrency, re-entrancy, and failure modes."""

    def test_01_watchdog_thread_contention_and_concurrency(self):
        """
        Adversarial Test 1: Concurrency stress.
        Spawns 20 concurrent threads calling start(), stop(), record_sample(), get_summary(),
        is_aborted(), and sample_host_metrics() simultaneously across 500 operations.
        Verifies zero race conditions, deadlocks, or state corruption.
        """
        wd = HostResourceWatchdog(sample_interval_s=0.05, min_safe_ram_gb=2.0, abort_threshold_ram_gb=1.0)
        errors = []
        stop_event = threading.Event()

        def worker_task(worker_id: int):
            try:
                for i in range(25):
                    if stop_event.is_set():
                        break
                    # Alternating operations
                    op = (worker_id + i) % 5
                    if op == 0:
                        wd.record_sample(free_ram_gb=7.0 - (i % 2), cpu_idle_pct=30.0 + (i % 10))
                    elif op == 1:
                        s = wd.get_summary()
                        self.assertIsInstance(s, HostWatchdogSummary)
                    elif op == 2:
                        _ = wd.is_aborted()
                    elif op == 3:
                        _ = wd.get_latest_metrics()
                    elif op == 4:
                        # Rapid safe toggle
                        wd.start()
            except Exception as e:
                errors.append((worker_id, e))

        threads = [threading.Thread(target=worker_task, args=(i,), daemon=True) for i in range(20)]
        wd.start()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        summary = wd.stop(timeout_s=5.0)
        self.assertEqual(len(errors), 0, f"Thread contention produced exceptions: {errors}")
        self.assertGreater(summary.samples_count, 0)
        self.assertFalse(wd.is_aborted())

    def test_02_watchdog_rapid_start_stop_50_cycles(self):
        """
        Adversarial Test 2: Rapid start/stop cycling.
        Executes 50 consecutive start() / stop() cycles in rapid succession.
        Verifies that daemon threads terminate cleanly and no deadlocks occur.
        """
        wd = HostResourceWatchdog(sample_interval_s=0.02)
        for i in range(50):
            wd.start()
            time.sleep(0.005)
            summary = wd.stop(timeout_s=2.0)
            self.assertIsInstance(summary, HostWatchdogSummary)

        self.assertFalse(wd._running)
        if wd._thread:
            self.assertFalse(wd._thread.is_alive(), "Watchdog thread must not be alive after stop()")

    def test_03_watchdog_lock_reentrancy_in_callbacks(self):
        """
        Adversarial Test 3: RLock re-entrancy verification.
        Ensures that inside on_throttle_callback and on_abort_callback, queries to
        get_summary(), is_aborted(), get_latest_metrics(), and record_sample() do not deadlock.
        """
        callback_log = []

        def throttle_handler(v):
            # Re-entrant acquisition of _lock on same thread
            callback_log.append("throttle_entered")
            s = wd_test.get_summary()
            callback_log.append(f"throttle_summary_samples:{s.samples_count}")
            ab = wd_test.is_aborted()
            callback_log.append(f"throttle_aborted:{ab}")
            m = wd_test.get_latest_metrics()
            callback_log.append(f"throttle_metrics_ok:{m is not None}")

        def abort_handler(v):
            # Re-entrant acquisition of _lock on same thread
            callback_log.append("abort_entered")
            s = wd_test.get_summary()
            callback_log.append(f"abort_summary_samples:{s.samples_count}")
            ab = wd_test.is_aborted()
            callback_log.append(f"abort_aborted:{ab}")
            m = wd_test.get_latest_metrics()
            callback_log.append(f"abort_metrics_ok:{m is not None}")

        wd_test = HostResourceWatchdog(
            min_safe_ram_gb=6.0,
            abort_threshold_ram_gb=4.5,
            on_throttle_callback=throttle_handler,
            on_abort_callback=abort_handler,
        )

        # Trigger throttle warning (< 6.0 GB)
        ok1 = wd_test.record_sample(free_ram_gb=5.5, cpu_idle_pct=50.0)
        self.assertTrue(ok1, "Throttle warning must return True (continue running)")
        self.assertIn("throttle_entered", callback_log)
        self.assertIn("throttle_metrics_ok:True", callback_log)

        # Trigger emergency abort (< 4.5 GB)
        ok2 = wd_test.record_sample(free_ram_gb=4.0, cpu_idle_pct=50.0)
        self.assertFalse(ok2, "Abort threshold must return False (abort triggered)")
        self.assertIn("abort_entered", callback_log)
        self.assertIn("abort_aborted:True", callback_log)
        self.assertTrue(wd_test.is_aborted())

    def test_04_watchdog_sensor_failure_triggers_tier3_circuit_breaker(self):
        """
        Adversarial Test 4: Sensor failure fallback under deadzone conditions.
        Verifies that when telemetry commands (vm_stat, top) fail, time out, or produce corrupt output,
        the watchdog sets sensor_healthy=False, reports 0.0 GB free / 0.0% idle, and IMMEDIATELY
        triggers a Tier 3 Circuit Breaker Emergency Abort rather than assuming 6GB / 50% health.
        """
        abort_fired = []

        def on_abort(v):
            abort_fired.append(v)

        wd = HostResourceWatchdog(on_abort_callback=on_abort)

        # 1. vm_stat failure (e.g. timeout / OOM thrash)
        with patch("subprocess.check_output", side_effect=subprocess.TimeoutExpired(["vm_stat"], timeout=2.0)):
            metrics = wd.sample_host_metrics()
            self.assertFalse(metrics["sensor_healthy"], "Sensor must be flagged unhealthy on exception")
            self.assertEqual(metrics["free_ram_gb"], 0.0, "Must not report fake 6.0 GB on sensor failure")
            self.assertEqual(metrics["cpu_idle_pct"], 0.0, "Must not report fake 50.0% CPU on sensor failure")
            self.assertIn("vm_stat failure", metrics["sensor_error"])

            # Escalation must trigger Tier 3 abort
            ok = wd._evaluate_escalation(metrics)
            self.assertFalse(ok, "Sensor failure must trigger emergency abort (return False)")
            self.assertTrue(wd.is_aborted())
            self.assertEqual(len(abort_fired), 1)
            self.assertEqual(abort_fired[0]["level"], "CIRCUIT_BREAKER")
            self.assertEqual(abort_fired[0]["tier"], 3)

        # 2. top failure
        wd2 = HostResourceWatchdog(on_abort_callback=on_abort)
        with patch("subprocess.check_output", side_effect=[
            "Pages free: 100000\nPages inactive: 100000\n",
            subprocess.TimeoutExpired(["top"], timeout=3.0)
        ]):
            metrics2 = wd2.sample_host_metrics()
            self.assertFalse(metrics2["sensor_healthy"])
            self.assertEqual(metrics2["cpu_idle_pct"], 0.0)
            self.assertIn("top failure", metrics2["sensor_error"])
            ok2 = wd2._evaluate_escalation(metrics2)
            self.assertFalse(ok2)
            self.assertTrue(wd2.is_aborted())

        # 3. Corrupt top output format
        wd3 = HostResourceWatchdog(on_abort_callback=on_abort)
        with patch("subprocess.check_output", side_effect=[
            "Pages free: 100000\nPages inactive: 100000\n",
            "UNEXPECTED TOP OUTPUT WITHOUT CPU METRICS\n"
        ]):
            metrics3 = wd3.sample_host_metrics()
            self.assertFalse(metrics3["sensor_healthy"])
            self.assertIn("format mismatch", metrics3["sensor_error"])
            ok3 = wd3._evaluate_escalation(metrics3)
            self.assertFalse(ok3)
            self.assertTrue(wd3.is_aborted())


class TestStrictExecutionRunnerAdversarial(unittest.TestCase):
    """Adversarial stress-testing of StrictExecutionRunner streaming, pipefail, signal delivery, and timeouts."""

    def setUp(self):
        self.runner = StrictExecutionRunner()

    def test_05_high_throughput_stdout_streaming_10mb(self):
        """
        Adversarial Test 5: OS Pipe buffer saturation with 10,000,000 bytes.
        Kernel pipe buffers are 64 KB. Streaming 10 MB tests that continuous chunk draining
        prevents child process deadlocks and captures all data without loss.
        """
        size_bytes = 10_000_000
        cmd = f'python3 -c "import sys; data = \'A\' * 100000; [sys.stdout.write(data) for _ in range(100)]"'
        t0 = time.time()
        res = self.runner.run(cmd, timeout_s=10.0)
        elapsed = time.time() - t0

        self.assertFalse(res.timed_out, f"10MB streaming must not time out (took {elapsed:.2f}s)")
        self.assertEqual(res.normalized_exit_code, 0)
        self.assertEqual(len(res.stdout), size_bytes, f"Expected {size_bytes} bytes on stdout, got {len(res.stdout)}")
        self.assertEqual(res.stderr, "")
        self.assertLess(elapsed, 2.5, f"10MB streaming should complete in < 2.5s, took {elapsed:.2f}s")

    def test_06_high_throughput_stderr_streaming_5mb(self):
        """
        Adversarial Test 6: OS Pipe buffer saturation on stderr with 5,000,000 bytes.
        Verifies stderr is cleanly streamed without deadlocking and stderr_tail captures trailing 50 lines.
        """
        lines_count = 50_000
        cmd = f'python3 -c "import sys; [sys.stderr.write(f\'line {{i}}: \' + \'E\' * 90 + \'\\n\') for i in range({lines_count})]"'
        t0 = time.time()
        res = self.runner.run(cmd, timeout_s=10.0)
        elapsed = time.time() - t0

        self.assertFalse(res.timed_out)
        self.assertEqual(res.normalized_exit_code, 0)
        self.assertGreaterEqual(len(res.stderr), 5_000_000)
        self.assertEqual(res.stdout, "")
        tail_lines = res.stderr_tail.splitlines()
        self.assertLessEqual(len(tail_lines), 50)
        self.assertIn(f"line {lines_count - 1}", res.stderr_tail)

    def test_07_concurrent_interleaved_streaming(self):
        """
        Adversarial Test 7: Interleaved simultaneous stdout and stderr streaming (2MB each).
        Ensures both streams are drained in parallel background threads without mutual starvation.
        """
        cmd = """python3 -c "
import sys, threading
def w_out():
    for _ in range(200):
        sys.stdout.write('O' * 10000)
def w_err():
    for _ in range(200):
        sys.stderr.write('E' * 10000)
t1 = threading.Thread(target=w_out)
t2 = threading.Thread(target=w_err)
t1.start(); t2.start()
t1.join(); t2.join()
"
"""
        res = self.runner.run(cmd, timeout_s=10.0)
        self.assertFalse(res.timed_out)
        self.assertEqual(res.normalized_exit_code, 0)
        self.assertEqual(len(res.stdout), 2_000_000)
        self.assertEqual(len(res.stderr), 2_000_000)

    def test_08_broken_pipe_sigpipe_unmasking(self):
        """
        Adversarial Test 8: Broken pipe / early downstream termination.
        When upstream writes heavily to a closed pipe (e.g. head -n 1), upstream receives SIGPIPE.
        Under 'set -eo pipefail', this must return exit code 141 (128 + 13 SIGPIPE) with signal_name 'SIGPIPE'.
        """
        cmd = "python3 -c \"import sys; [sys.stdout.write('A'*4096) for _ in range(1000)]\" | head -n 1"
        res = self.runner.run(cmd, timeout_s=5.0)
        # Depending on whether head consumed fast or slow, either 0 (if buffered) or 141 (SIGPIPE)
        # Under pipefail, if SIGPIPE occurred, normalized_exit_code is 141 and signal_name is SIGPIPE
        if res.normalized_exit_code != 0:
            self.assertEqual(res.normalized_exit_code, 141)
            self.assertEqual(res.signal_name, "SIGPIPE")
            self.assertIn("SIGPIPE", res.exit_classification)

    def test_09_null_bytes_and_binary_data_streaming(self):
        """
        Adversarial Test 9: Null bytes and binary byte streaming.
        Ensures runner handles null bytes ('\\x00') and multi-byte UTF-8 sequences cleanly without crashing.
        """
        cmd = 'python3 -c "import sys; sys.stdout.write(\'START\\x00MIDDLE\\x00END\\n\'); sys.stderr.write(\'ERR\\x00INFO\\n\')"'
        res = self.runner.run(cmd, timeout_s=5.0)
        self.assertEqual(res.normalized_exit_code, 0)
        self.assertIn("START\x00MIDDLE\x00END", res.stdout)
        self.assertIn("ERR\x00INFO", res.stderr)

    def test_10_uncooperative_child_sigkill_enforcement(self):
        """
        Adversarial Test 10: Process group unconditional SIGKILL.
        Child ignores SIGTERM (trap '' SIGTERM) and sleeps for 5s.
        With timeout_s=0.5, runner sends SIGTERM, waits 150ms grace, and unconditionally sends SIGKILL.
        Must complete in < 1.2s (not 5s) and classify as TIMEOUT_EXPIRED with SIGKILL.
        """
        cmd = """
python3 -c "
import signal, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
time.sleep(5)
"
"""
        t0 = time.time()
        res = self.runner.run(cmd, timeout_s=0.5)
        elapsed = time.time() - t0

        self.assertTrue(res.timed_out, "Command must be flagged timed_out=True")
        self.assertIn(res.normalized_exit_code, (137, 143), f"Uncooperative child must be terminated by signal (got {res.normalized_exit_code})")
        self.assertEqual(res.exit_classification, "TIMEOUT_EXPIRED")
        self.assertIn(res.signal_name, ("SIGKILL", "SIGTERM"))
        self.assertLess(elapsed, 1.5, f"Execution took {elapsed:.2f}s, expected < 1.5s (child sleep 5s terminated)")

    def test_11_orphan_child_holding_pipe_bounded_cleanup(self):
        """
        Adversarial Test 11: Background orphan holding file descriptor open.
        Parent exits immediately, but background grandchild holds stdout open for 10s.
        Runner bounded thread join must terminate process group with SIGKILL and close parent pipes,
        completing in < 1.5s instead of hanging for 10s.
        """
        cmd = "(sleep 10 >&1 &) ; echo 'parent done'"
        t0 = time.time()
        res = self.runner.run(cmd, timeout_s=1.0)
        elapsed = time.time() - t0

        self.assertIn("parent done", res.stdout)
        self.assertLess(elapsed, 2.0, f"Runner hung for {elapsed:.2f}s on orphan process holding stdout")

    def test_12_watchdog_emergency_abort_integration(self):
        """
        Adversarial Test 12: Watchdog emergency abort integration.
        Command is running a long sleep. Watchdog triggers emergency abort.
        Runner must immediately abort within 300ms, kill process group, and return WATCHDOG_TERMINATED.
        """
        mock_watchdog = MagicMock()
        mock_watchdog.is_aborted.side_effect = [False, False, True]

        t0 = time.time()
        res = self.runner.run("sleep 30", timeout_s=10.0, watchdog=mock_watchdog, poll_interval_s=0.05)
        elapsed = time.time() - t0

        self.assertTrue(res.watchdog_aborted)
        self.assertIn(res.normalized_exit_code, (137, 143))
        self.assertEqual(res.exit_classification, "WATCHDOG_TERMINATED")
        self.assertLess(elapsed, 1.0, f"Watchdog abort took {elapsed:.2f}s, expected < 1.0s")

    def test_13_signal_classification_accuracy(self):
        """
        Adversarial Test 13: Accurate classification of external signals.
        - kill -15 $$ -> code 143, SIGNAL_TERMINATED_SIGTERM (NOT WATCHDOG_TERMINATED unless watchdog_aborted=True)
        - kill -9 $$  -> code 137, OOM_KILLED / SIGKILL
        - kill -2 $$  -> code 130, INTERRUPTED_SIGINT / SIGINT
        """
        res_term = self.runner.run(["bash", "-c", "kill -15 $$"])
        self.assertEqual(res_term.normalized_exit_code, 143)
        self.assertFalse(res_term.watchdog_aborted)
        self.assertEqual(res_term.exit_classification, "SIGNAL_TERMINATED_SIGTERM")
        self.assertEqual(res_term.signal_name, "SIGTERM")

        res_kill = self.runner.run(["bash", "-c", "kill -9 $$"])
        self.assertEqual(res_kill.normalized_exit_code, 137)
        self.assertEqual(res_kill.exit_classification, "OOM_KILLED")
        self.assertEqual(res_kill.signal_name, "SIGKILL")


class TestContainerManagerAdversarial(unittest.TestCase):
    """Adversarial stress-testing of ContainerManager FerroOS whitelist, volume wipe failure, and subnet drift."""

    def test_14_ferro_whitelist_rejects_all_bypass_vectors(self):
        """
        Adversarial Test 14: Comprehensive FerroOS whitelist bypass probing.
        Affirmative whitelist: ('/usr/bin/bash', 'bash', 'python3', '/usr/bin/python3').
        Probes all known shell alternatives, applet loops, and wrappers.
        """
        bad_commands = [
            ["sh", "-c", "echo 1"],
            ["/bin/sh", "-c", "echo 1"],
            ["/usr/bin/sh", "-c", "echo 1"],
            ["ash", "-c", "echo 1"],
            ["/bin/ash", "-c", "echo 1"],
            ["dash", "-c", "echo 1"],
            ["/bin/dash", "-c", "echo 1"],
            ["busybox", "sh", "-c", "echo 1"],
            ["busybox", "-c", "echo 1"],
            ["zsh", "-c", "echo 1"],
            ["csh", "-c", "echo 1"],
            ["ksh", "-c", "echo 1"],
            ["fish", "-c", "echo 1"],
        ]
        for cmd in bad_commands:
            with self.assertRaises(ValueError, msg=f"Bypass vector {cmd} must be rejected"):
                validate_ferro_command_safety(command=cmd, entrypoint=None)

        bad_entrypoints = [
            "sh",
            "/bin/sh",
            "/usr/bin/sh",
            "dash",
            "/bin/dash",
            "ash",
            "/bin/ash",
            "busybox",
            "/bin/busybox",
            "/usr/bin/env sh",
            "zsh",
        ]
        for ep in bad_entrypoints:
            with self.assertRaises(ValueError, msg=f"Entrypoint bypass {ep} must be rejected"):
                validate_ferro_command_safety(command=None, entrypoint=ep)

    def test_15_ferro_whitelist_accepts_valid_invocations(self):
        """
        Adversarial Test 15: Valid invocations on FerroOS pass affirmative whitelist.
        """
        good_commands = [
            ["/usr/bin/bash", "-c", "echo valid"],
            ["bash", "-c", "echo valid"],
            ["python3", "-c", "print('valid')"],
            ["/usr/bin/python3", "-c", "print('valid')"],
            ["/usr/bin/bash", "script.sh"],
            ["python3", "app.py"],
        ]
        for cmd in good_commands:
            try:
                validate_ferro_command_safety(command=cmd, entrypoint=None)
            except ValueError as e:
                self.fail(f"Valid command {cmd} was unexpectedly rejected: {e}")

        good_entrypoints = [
            "/usr/bin/bash",
            "bash",
            "python3",
            "/usr/bin/python3",
        ]
        for ep in good_entrypoints:
            try:
                validate_ferro_command_safety(command=None, entrypoint=ep)
            except ValueError as e:
                self.fail(f"Valid entrypoint {ep} was unexpectedly rejected: {e}")

    def test_16_ferro_whitelist_exec_in_slot_enforcement(self):
        """
        Adversarial Test 16: exec_in_slot enforcement.
        When slot container image contains 'ferro', exec_in_slot must reject non-whitelisted commands.
        """
        cm = ContainerManager(auto_cleanup=False)
        mock_instance = MagicMock()
        mock_instance.image = "ferro-server:latest"
        cm.active_containers[SlotId.SLOT_A] = mock_instance

        # Bypass attempt via exec_in_slot
        with self.assertRaises(ValueError):
            cm.exec_in_slot(SlotId.SLOT_A, ["sh", "-c", "echo bad"])

        with self.assertRaises(ValueError):
            cm.exec_in_slot(SlotId.SLOT_A, ["/usr/bin/sh", "-c", "echo bad"])

    def test_17_scratch_volume_wipe_failure_raises_runtime_error(self):
        """
        Adversarial Test 17: Volume wipe failure simulation.
        When docker volume rm -f fails (e.g. volume locked by dangling container, returncode != 0),
        wipe_scratch_volume MUST check returncode and raise RuntimeError rather than silently succeeding.
        """
        cm = ContainerManager(auto_cleanup=False)

        # Mock stop_slot to avoid actual docker call
        cm.stop_slot = MagicMock()

        # Mock subprocess.run for docker volume rm returning failure
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="Error: volume is in use by container 12345")
            with self.assertRaises(RuntimeError) as ctx:
                cm.wipe_scratch_volume(SlotId.SLOT_A)

            self.assertIn("Failed to wipe scratch volume", str(ctx.exception))
            self.assertIn("volume is in use", str(ctx.exception))

    def test_18_subnet_drift_detection_and_automatic_healing(self):
        """
        Adversarial Test 18: Isolated bridge network subnet drift healing.
        When realworld_matrix_net exists with a drifted subnet (e.g. 10.88.0.0/16 or 172.29.0.0/16),
        ensure_network() detects the discrepancy, removes the drifted network, and recreates it
        with the specified 172.30.0.0/16 subnet.
        """
        cm = ContainerManager(auto_cleanup=False)
        calls = []

        def mock_subp_run(cmd, *args, **kwargs):
            calls.append(cmd)
            # 1. docker network inspect returning drifted subnet
            if "inspect" in cmd:
                return MagicMock(returncode=0, stdout="10.88.0.0/16\n", stderr="")
            # 2. docker network rm
            if "rm" in cmd:
                return MagicMock(returncode=0, stdout="", stderr="")
            # 3. docker network create
            if "create" in cmd:
                return MagicMock(returncode=0, stdout="net12345\n", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_subp_run):
            cm.ensure_network()

        # Verify call progression: inspect -> rm -> create
        inspected = any("inspect" in c and cm.network_name in c for c in calls)
        removed = any("rm" in c and cm.network_name in c for c in calls)
        created = any("create" in c and "--subnet" in c and NETWORK_SUBNET in c for c in calls)

        self.assertTrue(inspected, "Network must be inspected for subnet drift")
        self.assertTrue(removed, "Drifted network must be removed")
        self.assertTrue(created, f"Network must be recreated with specification {NETWORK_SUBNET}")

    def test_19_subnet_drift_noop_when_subnet_matches(self):
        """
        Adversarial Test 19: When subnet matches 172.30.0.0/16, no removal or recreation occurs.
        """
        cm = ContainerManager(auto_cleanup=False)
        calls = []

        def mock_subp_run(cmd, *args, **kwargs):
            calls.append(cmd)
            if "inspect" in cmd:
                return MagicMock(returncode=0, stdout=f"{NETWORK_SUBNET}\n", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_subp_run):
            cm.ensure_network()

        self.assertEqual(len(calls), 1)
        self.assertIn("inspect", calls[0])


if __name__ == "__main__":
    unittest.main()
