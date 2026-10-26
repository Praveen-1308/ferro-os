#!/usr/bin/env python3
"""
Tier 1 Feature Tests: Features 8 through 13.
- Feature 8: Web & Microservices Scenarios (15 Scenarios)
- Feature 9: Databases & State Engines Scenarios (12 Scenarios)
- Feature 10: High-Churn I/O & Media Scenarios (10 Scenarios)
- Feature 11: Queueing, Telemetry & Streaming Scenarios (10 Scenarios)
- Feature 12: Incident Radar & Fault Injection Scenarios (10 Scenarios)
- Feature 13: Deadzone & Hardware Extremes Scenarios (8 Scenarios)
Total Scenarios: 65
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from tests.test_harness import (
    build_reference_scenario_catalog,
    SCENARIO_COUNTS_BY_CATEGORY,
    TOTAL_SCENARIOS_COUNT,
)

class TestScenariosCatalogFeatures08To13(unittest.TestCase):
    """Features 8 through 13: Catalog Integrity and Scenario Completeness."""

    @classmethod
    def setUpClass(cls):
        cls.catalog = build_reference_scenario_catalog()

    # Feature 8: Web & Microservices (15)
    def test_f08_01_web_scenarios_count_is_fifteen(self):
        web_scenarios = [s for s in self.catalog.values() if s["category"] == "web_microservices"]
        self.assertEqual(len(web_scenarios), 15)

    def test_f08_02_web_scenarios_ids_continuous_01_to_15(self):
        expected_ids = {f"SCEN-WEB-{i:02d}" for i in range(1, 16)}
        actual_ids = {s["id"] for s in self.catalog.values() if s["category"] == "web_microservices"}
        self.assertEqual(actual_ids, expected_ids)

    def test_f08_03_web_scenarios_cover_key_frameworks(self):
        names = " ".join(s["name"] for s in self.catalog.values() if s["category"] == "web_microservices")
        for framework in ["FastAPI", "Express", "Axum", "Nginx", "GraphQL"]:
            self.assertIn(framework, names)

    def test_f08_04_web_scenarios_have_valid_target_ports(self):
        web_scenarios = [s for s in self.catalog.values() if s["category"] == "web_microservices"]
        for s in web_scenarios:
            self.assertGreater(s["target_port"], 0)
            self.assertLessEqual(s["target_port"], 65535)

    def test_f08_05_web_scenarios_have_realistic_sla_targets(self):
        web_scenarios = [s for s in self.catalog.values() if s["category"] == "web_microservices"]
        for s in web_scenarios:
            self.assertGreater(s["sla_p95_ms"], 0.0)
            self.assertLessEqual(s["sla_p95_ms"], 50.0)

    # Feature 9: Databases & State Engines (12)
    def test_f09_01_database_scenarios_count_is_twelve(self):
        db_scenarios = [s for s in self.catalog.values() if s["category"] == "databases_state_engines"]
        self.assertEqual(len(db_scenarios), 12)

    def test_f09_02_database_scenarios_ids_continuous_01_to_12(self):
        expected_ids = {f"SCEN-DB-{i:02d}" for i in range(1, 13)}
        actual_ids = {s["id"] for s in self.catalog.values() if s["category"] == "databases_state_engines"}
        self.assertEqual(actual_ids, expected_ids)

    def test_f09_03_database_scenarios_cover_postgres_sqlite_redis_valkey(self):
        names = " ".join(s["name"] for s in self.catalog.values() if s["category"] == "databases_state_engines")
        for engine in ["PostgreSQL", "SQLite", "Redis", "Valkey", "PgBouncer"]:
            self.assertIn(engine, names)

    def test_f09_04_database_scenarios_include_tpc_b_and_fts5(self):
        names = " ".join(s["name"] for s in self.catalog.values() if s["category"] == "databases_state_engines")
        self.assertIn("TPC-B", names)
        self.assertIn("FTS5", names)

    def test_f09_05_database_scenarios_have_positive_sla(self):
        db_scenarios = [s for s in self.catalog.values() if s["category"] == "databases_state_engines"]
        for s in db_scenarios:
            self.assertGreater(s["sla_p95_ms"], 0.0)

    # Feature 10: High-Churn I/O & Media (10)
    def test_f10_01_io_media_scenarios_count_is_ten(self):
        io_scenarios = [s for s in self.catalog.values() if s["category"] == "high_churn_io_media"]
        self.assertEqual(len(io_scenarios), 10)

    def test_f10_02_io_media_scenarios_ids_continuous_01_to_10(self):
        expected_ids = {f"SCEN-IO-{i:02d}" for i in range(1, 11)}
        actual_ids = {s["id"] for s in self.catalog.values() if s["category"] == "high_churn_io_media"}
        self.assertEqual(actual_ids, expected_ids)

    def test_f10_03_io_scenarios_cover_multipart_sendfile_minio_fdatasync(self):
        names = " ".join(s["name"] for s in self.catalog.values() if s["category"] == "high_churn_io_media")
        for keyword in ["Multipart", "sendfile", "MinIO", "fdatasync", "libvips", "mmap"]:
            self.assertIn(keyword, names)

    def test_f10_04_io_multipart_specifies_chunk_size_range(self):
        s1 = self.catalog["SCEN-IO-01"]
        self.assertIn("1 MB - 25 MB", s1["name"])

    def test_f10_05_io_scenarios_have_valid_protocols(self):
        io_scenarios = [s for s in self.catalog.values() if s["category"] == "high_churn_io_media"]
        for s in io_scenarios:
            self.assertIn("protocol", s)
            self.assertTrue(len(s["protocol"]) > 0)

    # Feature 11: Queueing, Telemetry & Streaming (10)
    def test_f11_01_queueing_scenarios_count_is_ten(self):
        q_scenarios = [s for s in self.catalog.values() if s["category"] == "queueing_telemetry_streaming"]
        self.assertEqual(len(q_scenarios), 10)

    def test_f11_02_queueing_scenarios_ids_continuous_01_to_10(self):
        expected_ids = {f"SCEN-Q-{i:02d}" for i in range(1, 11)}
        actual_ids = {s["id"] for s in self.catalog.values() if s["category"] == "queueing_telemetry_streaming"}
        self.assertEqual(actual_ids, expected_ids)

    def test_f11_03_queueing_scenarios_cover_rabbitmq_nats_zeromq_prometheus(self):
        names = " ".join(s["name"] for s in self.catalog.values() if s["category"] == "queueing_telemetry_streaming")
        for keyword in ["RabbitMQ", "NATS", "ZeroMQ", "Prometheus", "Vector", "OpenTelemetry"]:
            self.assertIn(keyword, names)

    def test_f11_04_prometheus_scenario_specifies_10k_scrapes(self):
        s4 = self.catalog["SCEN-Q-04"]
        self.assertIn("10,000 Metrics/Sec", s4["name"])

    def test_f11_05_queueing_scenarios_protocols_include_amqp_nats_udp(self):
        protos = {s["protocol"] for s in self.catalog.values() if s["category"] == "queueing_telemetry_streaming"}
        self.assertIn("AMQP", protos)
        self.assertIn("NATS", protos)
        self.assertIn("UDP", protos)

    # Feature 12: Incident Radar & Fault Injection (10)
    def test_f12_01_incident_faults_scenarios_count_is_ten(self):
        flt_scenarios = [s for s in self.catalog.values() if s["category"] == "incident_radar_faults"]
        self.assertEqual(len(flt_scenarios), 10)

    def test_f12_02_incident_faults_ids_continuous_01_to_10(self):
        expected_ids = {f"SCEN-FLT-{i:02d}" for i in range(1, 11)}
        actual_ids = {s["id"] for s in self.catalog.values() if s["category"] == "incident_radar_faults"}
        self.assertEqual(actual_ids, expected_ids)

    def test_f12_03_incident_faults_cover_time_wait_sigkill_slowloris(self):
        names = " ".join(s["name"] for s in self.catalog.values() if s["category"] == "incident_radar_faults")
        for keyword in ["TIME_WAIT", "Leak", "SIGKILL", "Zombie", "Slowloris", "Corruption"]:
            self.assertIn(keyword, names)

    def test_f12_04_incident_faults_cover_file_descriptor_leaks(self):
        s3 = self.catalog["SCEN-FLT-03"]
        self.assertIn("File Descriptor Leak", s3["name"])

    def test_f12_05_incident_faults_include_socket_unlinking(self):
        s9 = self.catalog["SCEN-FLT-09"]
        self.assertIn("Socket", s9["name"])

    # Feature 13: Deadzone & Hardware Extremes (8)
    def test_f13_01_deadzone_scenarios_count_is_eight(self):
        dzn_scenarios = [s for s in self.catalog.values() if s["category"] == "deadzone_hardware_extremes"]
        self.assertEqual(len(dzn_scenarios), 8)

    def test_f13_02_deadzone_scenarios_ids_continuous_01_to_08(self):
        expected_ids = {f"SCEN-DZN-{i:02d}" for i in range(1, 9)}
        actual_ids = {s["id"] for s in self.catalog.values() if s["category"] == "deadzone_hardware_extremes"}
        self.assertEqual(actual_ids, expected_ids)

    def test_f13_03_deadzone_scenarios_cover_cgroup_oom_c10k_hackbench(self):
        names = " ".join(s["name"] for s in self.catalog.values() if s["category"] == "deadzone_hardware_extremes")
        for keyword in ["OOM", "10,000 Concurrent Open Network Sockets", "Hackbench", "Epoll"]:
            self.assertIn(keyword, names)

    def test_f13_04_deadzone_scenarios_cover_pids_max_and_io_throttle(self):
        names = " ".join(s["name"] for s in self.catalog.values() if s["category"] == "deadzone_hardware_extremes")
        self.assertIn("pids.max", names)
        self.assertIn("io.max", names)

    def test_f13_05_total_scenarios_sum_is_sixty_five(self):
        self.assertEqual(len(self.catalog), TOTAL_SCENARIOS_COUNT)
        self.assertEqual(len(self.catalog), 65)

if __name__ == "__main__":
    unittest.main()
