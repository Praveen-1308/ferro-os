#!/usr/bin/env python3
"""
Tier 1 Feature Tests: Features 1 through 5.
- Feature 1: Target OS Matrix Verification (7 Targets)
- Feature 2: Alpine 3.20 Image Alignment
- Feature 3: FerroOS Bash Invocation Safety
- Feature 4: 3-Container Topology Orchestration
- Feature 5: Docker Bridge Network Isolation
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from tests.test_harness import (
    VALID_OS_TARGETS,
    validate_os_target,
    validate_alpine_image_alignment,
    validate_ferro_command_safety,
    validate_topology_allocation,
    validate_network_isolation,
    SLOT_LIMITS,
    NETWORK_SPEC,
    MAX_TOTAL_CPUS,
    MAX_TOTAL_RAM_GB,
)

class TestFeature01TargetOSMatrix(unittest.TestCase):
    """Feature 1: Target OS Matrix Verification (7 Distributions)."""

    def test_01_all_seven_target_distributions_present(self):
        expected = {"ferro-server", "bench-ubuntu", "bench-debian", "bench-rocky",
                    "almalinux:9", "bench-alpine", "amazonlinux:2023"}
        self.assertEqual(set(VALID_OS_TARGETS.keys()), expected)

    def test_02_valid_target_ids_pass_verification(self):
        for target_id in VALID_OS_TARGETS:
            valid, err = validate_os_target(target_id)
            self.assertTrue(valid, f"Target {target_id} failed validation: {err}")
            self.assertIsNone(err)

    def test_03_unknown_target_distribution_rejected(self):
        valid, err = validate_os_target("archlinux:latest")
        self.assertFalse(valid)
        self.assertIn("Unknown OS target", err)

    def test_04_target_metadata_has_required_attributes(self):
        for target_id, meta in VALID_OS_TARGETS.items():
            self.assertIn("name", meta, f"{target_id} missing 'name'")
            self.assertIn("category", meta, f"{target_id} missing 'category'")
            self.assertIn("init", meta, f"{target_id} missing 'init'")
            self.assertIn("libc", meta, f"{target_id} missing 'libc'")

    def test_05_ferro_target_has_specialized_components(self):
        ferro = VALID_OS_TARGETS["ferro-server"]
        self.assertEqual(ferro["init"], "ferro-init")
        self.assertEqual(ferro["allocator"], "libmimalloc.so.2")
        self.assertIn("libferro_io.so", ferro["io_engine"])


class TestFeature02AlpineAlignment(unittest.TestCase):
    """Feature 2: Alpine 3.20 Image Alignment."""

    def test_01_pinned_alpine_320_passes(self):
        valid, err = validate_alpine_image_alignment("alpine:3.20")
        self.assertTrue(valid)
        self.assertIsNone(err)

    def test_02_unpinned_alpine_latest_rejected(self):
        valid, err = validate_alpine_image_alignment("alpine:latest")
        self.assertFalse(valid)
        self.assertIn("latest", err)

    def test_03_outdated_alpine_version_rejected(self):
        valid, err = validate_alpine_image_alignment("alpine:3.18")
        self.assertFalse(valid)
        self.assertIn("3.20", err)

    def test_04_custom_repo_alpine_320_passes(self):
        valid, err = validate_alpine_image_alignment("registry.internal/bench/alpine:3.20-custom")
        self.assertTrue(valid)

    def test_05_empty_or_whitespace_image_ref_rejected(self):
        valid, err = validate_alpine_image_alignment("   ")
        self.assertFalse(valid)


class TestFeature03FerroBashSafety(unittest.TestCase):
    """Feature 3: FerroOS Bash Invocation Safety."""

    def test_01_direct_bash_binary_passes(self):
        valid, err = validate_ferro_command_safety("/usr/bin/bash -c 'python3 run.py'")
        self.assertTrue(valid)

    def test_02_direct_python3_passes(self):
        valid, err = validate_ferro_command_safety("python3 /bench/run_matrix.py")
        self.assertTrue(valid)

    def test_03_applet_sh_invocation_rejected(self):
        valid, err = validate_ferro_command_safety("sh -c 'echo test'")
        self.assertFalse(valid)
        self.assertIn("applet shell loops", err)

    def test_04_bin_sh_absolute_path_rejected(self):
        valid, err = validate_ferro_command_safety("/bin/sh /bench/script.sh")
        self.assertFalse(valid)

    def test_05_empty_command_rejected(self):
        valid, err = validate_ferro_command_safety("")
        self.assertFalse(valid)


class TestFeature04TopologyOrchestration(unittest.TestCase):
    """Feature 4: 3-Container Topology Orchestration."""

    def test_01_nominal_topology_within_limits(self):
        slots = {
            "slot_a": {"cpus": 2.0, "memory_gb": 4.0},
            "slot_b": {"cpus": 2.0, "memory_gb": 4.0},
            "slot_c": {"cpus": 1.0, "memory_gb": 2.0},
        }
        valid, err = validate_topology_allocation(slots)
        self.assertTrue(valid)
        self.assertIsNone(err)

    def test_02_cpu_oversubscription_rejected(self):
        slots = {
            "slot_a": {"cpus": 3.0, "memory_gb": 4.0},
            "slot_b": {"cpus": 2.0, "memory_gb": 4.0},
            "slot_c": {"cpus": 1.0, "memory_gb": 2.0},
        }
        valid, err = validate_topology_allocation(slots)
        self.assertFalse(valid)

    def test_03_memory_oversubscription_rejected(self):
        slots = {
            "slot_a": {"cpus": 2.0, "memory_gb": 5.0},
            "slot_b": {"cpus": 2.0, "memory_gb": 4.0},
            "slot_c": {"cpus": 1.0, "memory_gb": 2.0},
        }
        valid, err = validate_topology_allocation(slots)
        self.assertFalse(valid)

    def test_04_total_envelope_is_five_cpus_ten_gb(self):
        total_cpus = sum(s["cpus"] for s in SLOT_LIMITS.values())
        total_ram = sum(s["memory_gb"] for s in SLOT_LIMITS.values())
        self.assertEqual(total_cpus, MAX_TOTAL_CPUS)
        self.assertEqual(total_ram, MAX_TOTAL_RAM_GB)

    def test_05_scratch_storage_requirements_defined(self):
        self.assertEqual(SLOT_LIMITS["slot_a"]["scratch_storage_gb"], 15.0)
        self.assertEqual(SLOT_LIMITS["slot_b"]["scratch_storage_gb"], 15.0)
        self.assertEqual(SLOT_LIMITS["slot_c"]["scratch_storage_gb"], 5.0)


class TestFeature05NetworkIsolation(unittest.TestCase):
    """Feature 5: Docker Bridge Network Isolation."""

    def test_01_canonical_network_name_is_realworld_matrix_net(self):
        self.assertEqual(NETWORK_SPEC["network_name"], "realworld_matrix_net")

    def test_02_subnet_is_class_b_172_30_0_0_16(self):
        self.assertEqual(NETWORK_SPEC["subnet"], "172.30.0.0/16")

    def test_03_driver_is_isolated_bridge(self):
        self.assertEqual(NETWORK_SPEC["driver"], "bridge")

    def test_04_valid_network_spec_passes_verification(self):
        valid, err = validate_network_isolation(NETWORK_SPEC)
        self.assertTrue(valid)

    def test_05_incorrect_network_name_fails_verification(self):
        bad_net = dict(NETWORK_SPEC)
        bad_net["network_name"] = "default_bridge"
        valid, err = validate_network_isolation(bad_net)
        self.assertFalse(valid)
        self.assertIn("realworld_matrix_net", err)

if __name__ == "__main__":
    unittest.main()
