#!/usr/bin/env python3
"""
tools/benchmarks/sustained_realworld_matrix/tests/test_adversarial_m1.py

Adversarial Stress & Verification Test Suite for Milestone 1 Infrastructure.
Executed by Challenger 1 to empirically stress-test:
1. Container Topology & cgroup v2 enforcement (cpu.max, memory.max, swap, inter-slot routing)
2. Scratch Volume Isolation & Wipe Idempotency (including dangling container lock behavior)
3. FerroOS Command Invocation Safety (probing applet loops, /usr/bin/sh, entrypoint bypasses, and exec_in_slot)
4. Docker Bridge Network Setup (idempotency, subnet drift detection in script vs ContainerManager)
"""

import os
import sys
import time
import unittest
import subprocess
from typing import Dict, List, Optional

MATRIX_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if MATRIX_DIR not in sys.path:
    sys.path.insert(0, MATRIX_DIR)

from infra.container_manager import (
    ContainerManager,
    SlotId,
    SLOT_DEFINITIONS,
    NETWORK_NAME,
    NETWORK_SUBNET,
    NETWORK_GATEWAY,
)


class TestContainerTopologyAndCgroups(unittest.TestCase):
    """Stress tests container resource caps, cgroup v2 enforcement, and network connectivity."""

    def setUp(self):
        self.cm = ContainerManager(auto_cleanup=False)
        self.cm.ensure_network()
        self.cm.preflight_cleanup()

    def tearDown(self):
        self.cm.teardown(remove_network=False, remove_volumes=True)

    def test_01_concurrent_three_slot_cgroup_caps(self):
        """Starts Slots A, B, and C concurrently and probes cgroup v2 limits."""
        inst_a = self.cm.start_slot(SlotId.SLOT_A, "bench-alpine:latest", command=["sleep", "60"])
        inst_b = self.cm.start_slot(SlotId.SLOT_B, "bench-alpine:latest", command=["sleep", "60"])
        inst_c = self.cm.start_slot(SlotId.SLOT_C, "bench-alpine:latest", command=["sleep", "60"])

        self.assertEqual(len(self.cm.active_containers), 3)

        # 1. Verify Slot A (2.0 vCPUs, 4 GiB, 0 swap)
        res_cpu_a = self.cm.exec_in_slot(SlotId.SLOT_A, ["cat", "/sys/fs/cgroup/cpu.max"])
        self.assertEqual(res_cpu_a.stdout.strip(), "200000 100000")
        res_mem_a = self.cm.exec_in_slot(SlotId.SLOT_A, ["cat", "/sys/fs/cgroup/memory.max"])
        self.assertEqual(int(res_mem_a.stdout.strip()), 4 * 1024 * 1024 * 1024)
        res_swap_a = self.cm.exec_in_slot(SlotId.SLOT_A, ["cat", "/sys/fs/cgroup/memory.swap.max"])
        self.assertEqual(res_swap_a.stdout.strip(), "0")

        # 2. Verify Slot B (2.0 vCPUs, 4 GiB, 0 swap)
        res_cpu_b = self.cm.exec_in_slot(SlotId.SLOT_B, ["cat", "/sys/fs/cgroup/cpu.max"])
        self.assertEqual(res_cpu_b.stdout.strip(), "200000 100000")
        res_mem_b = self.cm.exec_in_slot(SlotId.SLOT_B, ["cat", "/sys/fs/cgroup/memory.max"])
        self.assertEqual(int(res_mem_b.stdout.strip()), 4 * 1024 * 1024 * 1024)
        res_swap_b = self.cm.exec_in_slot(SlotId.SLOT_B, ["cat", "/sys/fs/cgroup/memory.swap.max"])
        self.assertEqual(res_swap_b.stdout.strip(), "0")

        # 3. Verify Slot C (1.0 vCPUs, 2 GiB, 0 swap)
        res_cpu_c = self.cm.exec_in_slot(SlotId.SLOT_C, ["cat", "/sys/fs/cgroup/cpu.max"])
        self.assertEqual(res_cpu_c.stdout.strip(), "100000 100000")
        res_mem_c = self.cm.exec_in_slot(SlotId.SLOT_C, ["cat", "/sys/fs/cgroup/memory.max"])
        self.assertEqual(int(res_mem_c.stdout.strip()), 2 * 1024 * 1024 * 1024)
        res_swap_c = self.cm.exec_in_slot(SlotId.SLOT_C, ["cat", "/sys/fs/cgroup/memory.swap.max"])
        self.assertEqual(res_swap_c.stdout.strip(), "0")

        # 4. Verify Static IP bindings
        res_ip_a = self.cm.exec_in_slot(SlotId.SLOT_A, ["ip", "-4", "addr", "show", "eth0"])
        self.assertIn("172.30.0.10", res_ip_a.stdout)
        res_ip_b = self.cm.exec_in_slot(SlotId.SLOT_B, ["ip", "-4", "addr", "show", "eth0"])
        self.assertIn("172.30.0.11", res_ip_b.stdout)
        res_ip_c = self.cm.exec_in_slot(SlotId.SLOT_C, ["ip", "-4", "addr", "show", "eth0"])
        self.assertIn("172.30.0.20", res_ip_c.stdout)

        # 5. Inter-container connectivity across isolated bridge network
        ping_res = self.cm.exec_in_slot(SlotId.SLOT_C, ["ping", "-c", "2", "-W", "1", "172.30.0.10"])
        self.assertEqual(ping_res.exit_code, 0)
        dns_res = self.cm.exec_in_slot(SlotId.SLOT_C, ["ping", "-c", "2", "-W", "1", "matrix-slot-a"])
        self.assertEqual(dns_res.exit_code, 0)

    def test_02_cgroup_oom_enforcement_slot_c(self):
        """Verifies that exceeding memory.max (2 GiB) in Slot C triggers immediate SIGKILL (exit code 137)."""
        self.cm.start_slot(SlotId.SLOT_C, "bench-alpine:latest", command=["sleep", "60"])
        res = self.cm.exec_in_slot(SlotId.SLOT_C, ["python3", "-c", "a = bytearray(2500 * 1024 * 1024)"])
        self.assertEqual(res.exit_code, 137, "Cgroup memory.max must trigger OOM killer exit code 137")


class TestScratchVolumeLifecycle(unittest.TestCase):
    """Stress tests scratch volume isolation, purge on wipe, and dangling lock failure modes."""

    def setUp(self):
        self.cm = ContainerManager(auto_cleanup=False)
        self.cm.ensure_network()
        self.cm.preflight_cleanup()

    def tearDown(self):
        self.cm.teardown(remove_network=False, remove_volumes=True)

    def test_01_scratch_purge_removes_dirty_files(self):
        """Verifies clean wipe purges all files and subdirectories."""
        self.cm.start_slot(SlotId.SLOT_A, "bench-alpine:latest", command=["sleep", "60"])
        self.cm.exec_in_slot(SlotId.SLOT_A, ["sh", "-c", "echo dirty > /scratch/dirty.txt"])
        self.cm.exec_in_slot(SlotId.SLOT_A, ["sh", "-c", "mkdir -p /scratch/nested && echo data > /scratch/nested/data.bin"])

        ls_before = self.cm.exec_in_slot(SlotId.SLOT_A, ["sh", "-c", "ls -A /scratch"])
        self.assertIn("dirty.txt", ls_before.stdout)

        self.cm.wipe_scratch_volume(SlotId.SLOT_A)

        self.cm.start_slot(SlotId.SLOT_A, "bench-alpine:latest", command=["sleep", "60"])
        ls_after = self.cm.exec_in_slot(SlotId.SLOT_A, ["sh", "-c", "ls -A /scratch"])
        self.assertEqual(ls_after.stdout.strip(), "", "Scratch volume must be clean after wipe")

    def test_02_dangling_container_lock_causes_silent_wipe_failure(self):
        """
        Vulnerability Reproduction:
        If an external/dangling container holds the volume, docker volume rm -f fails.
        Because ContainerManager swallows the error without checking returncode,
        wipe_scratch_volume silently succeeds without wiping dirty data!
        """
        self.cm.start_slot(SlotId.SLOT_A, "bench-alpine:latest", command=["sleep", "60"])
        self.cm.exec_in_slot(SlotId.SLOT_A, ["sh", "-c", "echo persistent_leak > /scratch/leak.txt"])

        # Attach dangling holder
        dangling = subprocess.run(
            ["docker", "run", "-d", "--name", "adv-dangling-holder", "-v", "matrix-scratch-slot-a:/scratch", "bench-alpine:latest", "sleep", "30"],
            capture_output=True, text=True, check=True
        )

        try:
            # Wipe volume while dangling holder is attached
            self.cm.wipe_scratch_volume(SlotId.SLOT_A)

            # Start Slot A and check if dirty data persisted
            self.cm.start_slot(SlotId.SLOT_A, "bench-alpine:latest", command=["sleep", "60"])
            res = self.cm.exec_in_slot(SlotId.SLOT_A, ["sh", "-c", "cat /scratch/leak.txt 2>/dev/null || echo CLEAN"])

            # Data survived the wipe!
            dirty_survived = (res.stdout.strip() == "persistent_leak")
            self.assertTrue(dirty_survived, "Demonstrates that wipe_scratch_volume silently fails when volume is locked by another process")
        finally:
            subprocess.run(["docker", "rm", "-f", "adv-dangling-holder"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class TestFerroCommandSafetyVulnerabilities(unittest.TestCase):
    """
    Adversarially probes FerroOS command validation:
    Verifies that while simple 'sh' and '/bin/sh' are blocked,
    multiple bypass vectors exist (/usr/bin/sh, busybox sh, entrypoint override, exec_in_slot).
    """

    def setUp(self):
        self.cm = ContainerManager(auto_cleanup=False)

    def test_01_sh_and_bin_sh_blocked(self):
        """Standard sh and /bin/sh are blocked."""
        with self.assertRaises(ValueError):
            self.cm.start_slot(SlotId.SLOT_A, image="ferro-os-server:latest", command=["sh", "-c", "echo test"], wait_ready=False)

        with self.assertRaises(ValueError):
            self.cm.start_slot(SlotId.SLOT_A, image="ferro-os-server:latest", command=["/bin/sh", "-c", "echo test"], wait_ready=False)

    def test_02_usr_bin_sh_bypasses_validation(self):
        """Vulnerability: /usr/bin/sh does NOT raise ValueError and starts container."""
        # This will not raise ValueError; it will execute start_slot
        inst = self.cm.start_slot(SlotId.SLOT_A, image="ferro-os-server:latest", command=["/usr/bin/sh", "-c", "echo test"], wait_ready=False)
        self.assertEqual(inst.container_name, "matrix-slot-a")
        self.cm.stop_slot(SlotId.SLOT_A)

    def test_03_entrypoint_sh_bypasses_validation(self):
        """Vulnerability: entrypoint='/bin/sh' does NOT raise ValueError and starts container."""
        inst = self.cm.start_slot(SlotId.SLOT_A, image="ferro-os-server:latest", entrypoint="/bin/sh", command=["-c", "echo test"], wait_ready=False)
        self.assertEqual(inst.container_name, "matrix-slot-a")
        self.cm.stop_slot(SlotId.SLOT_A)

    def test_04_exec_in_slot_sh_has_zero_validation(self):
        """Vulnerability: exec_in_slot does NOT validate commands and permits 'sh' on FerroOS."""
        inst = self.cm.start_slot(SlotId.SLOT_A, image="ferro-os-server:latest", command=["/usr/bin/bash", "-c", "sleep 30"], wait_ready=True)
        res = self.cm.exec_in_slot(SlotId.SLOT_A, ["sh", "-c", "echo injected_sh"])
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.stdout.strip(), "injected_sh")
        self.cm.stop_slot(SlotId.SLOT_A)


class TestBridgeNetworkIdempotencyAndDrift(unittest.TestCase):
    """Verifies network script robustness and exposes ContainerManager subnet drift blindness."""

    SCRIPT = os.path.join(MATRIX_DIR, "docker/setup_bridge_network.sh")

    def test_01_script_idempotency_and_drift_healing(self):
        """Shell script handles idempotency and heals subnet drift."""
        for _ in range(2):
            res = subprocess.run([self.SCRIPT, "setup"], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)

        # Force wrong subnet
        subprocess.run([self.SCRIPT, "teardown"], capture_output=True, text=True)
        subprocess.run(["docker", "network", "create", "--subnet", "172.29.0.0/16", NETWORK_NAME], check=True, stdout=subprocess.DEVNULL)

        # Script detects drift and heals
        res_heal = subprocess.run([self.SCRIPT, "setup"], capture_output=True, text=True)
        self.assertEqual(res_heal.returncode, 0)
        self.assertIn("exists with wrong subnet", res_heal.stderr + res_heal.stdout)

        res_stat = subprocess.run([self.SCRIPT, "status"], capture_output=True, text=True)
        self.assertIn("172.30.0.0/16", res_stat.stdout)

    def test_02_container_manager_subnet_drift_blindness(self):
        """
        Vulnerability Reproduction:
        ContainerManager.ensure_network() only checks network name existence,
        ignoring subnet drift. If the network exists with a wrong subnet,
        ensure_network() returns blindly, causing subsequent container launches to crash.
        """
        # Create network with wrong subnet
        subprocess.run(["docker", "network", "rm", NETWORK_NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["docker", "network", "create", "--subnet", "10.88.0.0/16", NETWORK_NAME], check=True, stdout=subprocess.DEVNULL)

        cm = ContainerManager(auto_cleanup=False)
        try:
            # ensure_network does NOT raise or heal
            cm.ensure_network()

            # Launching slot crashes because 172.30.0.10 is outside 10.88.0.0/16
            with self.assertRaises(RuntimeError) as ctx:
                cm.start_slot(SlotId.SLOT_A, "bench-alpine:latest", command=["sleep", "10"], wait_ready=False)
            self.assertIn("no configured subnet contains IP address 172.30.0.10", str(ctx.exception))
        finally:
            # Heal network
            subprocess.run([self.SCRIPT, "setup"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main()
