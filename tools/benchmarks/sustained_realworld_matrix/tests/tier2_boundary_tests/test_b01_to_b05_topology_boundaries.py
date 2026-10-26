#!/usr/bin/env python3
"""
Tier 2 Boundary Tests: Features 1 through 5.
- Feature 1: Target OS Matrix Verification Boundaries
- Feature 2: Alpine 3.20 Image Alignment Boundaries
- Feature 3: FerroOS Bash Invocation Safety Boundaries
- Feature 4: 3-Container Topology Orchestration Boundaries
- Feature 5: Docker Bridge Network Isolation Boundaries
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from tests.test_harness import (
    validate_os_target,
    validate_alpine_image_alignment,
    validate_ferro_command_safety,
    validate_topology_allocation,
    validate_network_isolation,
    NETWORK_SPEC,
)

class TestFeature01TargetOSBoundaries(unittest.TestCase):
    """Feature 1 Boundary Tests: OS Target Matrix."""

    def test_b01_01_empty_string_target_id_rejected(self):
        valid, err = validate_os_target("")
        self.assertFalse(valid)

    def test_b01_02_non_string_target_type_rejected(self):
        valid, err = validate_os_target(None)
        self.assertFalse(valid)
        valid2, err2 = validate_os_target(12345)
        self.assertFalse(valid2)

    def test_b01_03_case_variance_rejected(self):
        valid, err = validate_os_target("FERRO-SERVER")
        self.assertFalse(valid)
        valid2, err2 = validate_os_target("Bench-Ubuntu")
        self.assertFalse(valid2)

    def test_b01_04_extreme_length_identifier_rejected(self):
        valid, err = validate_os_target("a" * 10000)
        self.assertFalse(valid)

    def test_b01_05_injection_characters_rejected(self):
        valid, err = validate_os_target("ferro-server; rm -rf /")
        self.assertFalse(valid)


class TestFeature02AlpineAlignmentBoundaries(unittest.TestCase):
    """Feature 2 Boundary Tests: Alpine 3.20 Image Alignment."""

    def test_b02_01_empty_and_whitespace_rejected(self):
        valid, err = validate_alpine_image_alignment("")
        self.assertFalse(valid)
        valid2, err2 = validate_alpine_image_alignment("   \t\n")
        self.assertFalse(valid2)

    def test_b02_02_boundary_just_below_320_rejected(self):
        valid, err = validate_alpine_image_alignment("alpine:3.19.9")
        self.assertFalse(valid)
        self.assertIn("3.20", err)

    def test_b02_03_boundary_just_above_320_rejected(self):
        valid, err = validate_alpine_image_alignment("alpine:3.21.0")
        self.assertFalse(valid)

    def test_b02_04_composite_tag_with_latest_rejected(self):
        valid, err = validate_alpine_image_alignment("alpine:3.20-latest")
        self.assertFalse(valid)
        self.assertIn("latest", err)

    def test_b02_05_exact_semver_3200_accepted(self):
        valid, err = validate_alpine_image_alignment("alpine:3.20.0")
        self.assertTrue(valid)


class TestFeature03FerroBashSafetyBoundaries(unittest.TestCase):
    """Feature 3 Boundary Tests: FerroOS Bash Invocation Safety."""

    def test_b03_01_empty_string_rejected(self):
        valid, err = validate_ferro_command_safety("")
        self.assertFalse(valid)

    def test_b03_02_whitespace_only_rejected(self):
        valid, err = validate_ferro_command_safety("   \t  ")
        self.assertFalse(valid)

    def test_b03_03_inlined_sh_flag_rejected(self):
        valid, err = validate_ferro_command_safety("sh -c 'python3 run.py'")
        self.assertFalse(valid)

    def test_b03_04_direct_python3_leading_slash_accepted(self):
        valid, err = validate_ferro_command_safety("/usr/bin/python3 run_matrix.py")
        self.assertTrue(valid)

    def test_b03_05_other_scripting_languages_rejected_without_bash(self):
        valid, err = validate_ferro_command_safety("perl script.pl")
        self.assertFalse(valid)
        valid2, err2 = validate_ferro_command_safety("ruby bench.rb")
        self.assertFalse(valid2)


class TestFeature04TopologyBoundaries(unittest.TestCase):
    """Feature 4 Boundary Tests: 3-Container Topology Allocation Limits."""

    def test_b04_01_exact_total_envelope_boundary_passes(self):
        slots = {
            "slot_a": {"cpus": 2.0, "memory_gb": 4.0},
            "slot_b": {"cpus": 2.0, "memory_gb": 4.0},
            "slot_c": {"cpus": 1.0, "memory_gb": 2.0},
        }
        valid, err = validate_topology_allocation(slots)
        self.assertTrue(valid)

    def test_b04_02_total_cpus_exceeded_by_point_zero_one_fails(self):
        slots = {
            "slot_a": {"cpus": 2.0, "memory_gb": 4.0},
            "slot_b": {"cpus": 2.0, "memory_gb": 4.0},
            "slot_c": {"cpus": 1.01, "memory_gb": 2.0}, # Slot C exceeds limit
        }
        valid, err = validate_topology_allocation(slots)
        self.assertFalse(valid)

    def test_b04_03_total_ram_exceeded_by_point_zero_one_fails(self):
        slots = {
            "slot_a": {"cpus": 2.0, "memory_gb": 4.0},
            "slot_b": {"cpus": 2.0, "memory_gb": 4.01}, # Slot B exceeds limit
            "slot_c": {"cpus": 1.0, "memory_gb": 2.0},
        }
        valid, err = validate_topology_allocation(slots)
        self.assertFalse(valid)

    def test_b04_04_zero_cpu_or_zero_ram_rejected(self):
        slots = {
            "slot_a": {"cpus": 0.0, "memory_gb": 4.0},
            "slot_b": {"cpus": 2.0, "memory_gb": 4.0},
            "slot_c": {"cpus": 1.0, "memory_gb": 2.0},
        }
        valid, err = validate_topology_allocation(slots)
        self.assertFalse(valid)

    def test_b04_05_negative_resource_allocation_rejected(self):
        slots = {
            "slot_a": {"cpus": -2.0, "memory_gb": 4.0},
            "slot_b": {"cpus": 2.0, "memory_gb": -4.0},
            "slot_c": {"cpus": 1.0, "memory_gb": 2.0},
        }
        valid, err = validate_topology_allocation(slots)
        self.assertFalse(valid)


class TestFeature05NetworkIsolationBoundaries(unittest.TestCase):
    """Feature 5 Boundary Tests: Network Isolation."""

    def test_b05_01_host_networking_driver_rejected(self):
        bad_net = dict(NETWORK_SPEC)
        bad_net["driver"] = "host"
        valid, err = validate_network_isolation(bad_net)
        self.assertFalse(valid)

    def test_b05_02_none_networking_driver_rejected(self):
        bad_net = dict(NETWORK_SPEC)
        bad_net["driver"] = "none"
        valid, err = validate_network_isolation(bad_net)
        self.assertFalse(valid)

    def test_b05_03_mismatched_subnet_cidr_rejected(self):
        bad_net = dict(NETWORK_SPEC)
        bad_net["subnet"] = "192.168.1.0/24"
        valid, err = validate_network_isolation(bad_net)
        self.assertFalse(valid)

    def test_b05_04_empty_network_name_rejected(self):
        bad_net = dict(NETWORK_SPEC)
        bad_net["network_name"] = ""
        valid, err = validate_network_isolation(bad_net)
        self.assertFalse(valid)

    def test_b05_05_missing_network_keys_handled(self):
        empty_cfg = {}
        valid, err = validate_network_isolation(empty_cfg)
        self.assertFalse(valid)

if __name__ == "__main__":
    unittest.main()
