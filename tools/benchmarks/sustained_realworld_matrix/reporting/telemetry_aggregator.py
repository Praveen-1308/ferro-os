#!/usr/bin/env python3
"""
tools/benchmarks/sustained_realworld_matrix/reporting/telemetry_aggregator.py

Milestone 4: Second-by-Second JSON Telemetry Pipeline & Aggregation Engine.
Persists complete empirical benchmark datasets to:
  tools/reports/sustained_realworld_multi_os_matrix.json
"""

import os
import sys
import json
import time
import gzip
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple

# Add matrix root to path
MATRIX_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if MATRIX_ROOT not in sys.path:
    sys.path.insert(0, MATRIX_ROOT)

from tests.test_harness import validate_telemetry_dataset, evaluate_business_scorecard
from engine.stress_ladder import StressLadderResult


DEFAULT_REPORT_JSON_PATH = os.path.abspath(
    os.path.join(MATRIX_ROOT, "../../../tools/reports/sustained_realworld_multi_os_matrix.json")
)


class TelemetryAggregator:
    """
    Collects, validates, and serializes second-by-second benchmark telemetry records
    across all tested operating systems and scenarios.
    """

    def __init__(self, output_path: str = DEFAULT_REPORT_JSON_PATH):
        self.output_path = output_path
        self.metadata: Dict[str, Any] = {
            "version": "2.0",
            "project": "sustained_realworld_matrix",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "hardware_caps": {
                "max_docker_vcpus": 5.0,
                "max_docker_memory_gb": 10.0,
                "host_preserved_cores": 5,
                "host_preserved_ram_gb": 6.0,
            },
        }
        self.scenarios_data: Dict[str, Dict[str, Any]] = {}
        self.os_summaries: Dict[str, Dict[str, Any]] = {}

    def record_scenario_run(
        self,
        scenario_id: str,
        target_os: str,
        slot_id: str,
        result: StressLadderResult,
        crossover_partner: Optional[str] = None,
        crossover_variance_pct: Optional[float] = None,
    ) -> None:
        """Records a completed 300s stress ladder run."""
        if scenario_id not in self.scenarios_data:
            self.scenarios_data[scenario_id] = {
                "scenario_id": scenario_id,
                "runs": {},
            }

        scorecard = evaluate_business_scorecard(result.aggregate_metrics)

        run_entry = {
            "target_os": target_os,
            "slot_id": slot_id,
            "total_seconds": result.total_seconds,
            "completed": result.completed,
            "exit_classification": result.exit_classification,
            "business_scorecard": scorecard,
            "crossover_partner": crossover_partner,
            "crossover_variance_pct": crossover_variance_pct,
            "aggregate_metrics": result.aggregate_metrics,
            "telemetry_records": result.telemetry_records,
        }

        run_key = f"{target_os}_{slot_id}"
        self.scenarios_data[scenario_id]["runs"][run_key] = run_entry

        # Accumulate into OS summaries
        if target_os not in self.os_summaries:
            self.os_summaries[target_os] = {
                "total_runs": 0,
                "passed_runs": 0,
                "total_completed_ops": 0,
                "total_errors": 0,
                "p95_latencies": [],
                "p99_latencies": [],
                "peak_rps_list": [],
                "average_rps_list": [],
                "peak_rss_mb_list": [],
                "scorecards": {},
            }

        os_acc = self.os_summaries[target_os]
        os_acc["total_runs"] += 1
        if result.completed and result.exit_classification == "CLEAN":
            os_acc["passed_runs"] += 1
        os_acc["total_completed_ops"] += result.aggregate_metrics["total_completed_ops"]
        os_acc["total_errors"] += result.aggregate_metrics["total_errors"]
        os_acc["p95_latencies"].append(result.aggregate_metrics["p95_latency_ms"])
        os_acc["p99_latencies"].append(result.aggregate_metrics["p99_latency_ms"])
        os_acc["peak_rps_list"].append(result.aggregate_metrics["peak_rps"])
        os_acc["average_rps_list"].append(result.aggregate_metrics["average_rps"])
        os_acc["peak_rss_mb_list"].append(result.aggregate_metrics["peak_rss_mb"])

        score_tag = scorecard.split()[0]  # Emoji
        os_acc["scorecards"][score_tag] = os_acc["scorecards"].get(score_tag, 0) + 1

    def validate_all(self) -> Tuple[bool, List[str]]:
        """Validates all recorded runs against validate_telemetry_dataset()."""
        errors = []
        for scen_id, sdata in self.scenarios_data.items():
            for rkey, run_entry in sdata["runs"].items():
                records = run_entry["telemetry_records"]
                valid, err = validate_telemetry_dataset(records, expected_seconds=len(records))
                if not valid:
                    errors.append(f"{scen_id} [{rkey}]: {err}")
        return len(errors) == 0, errors

    def compile_final_dataset(self) -> Dict[str, Any]:
        """Compiles the full serializable dictionary."""
        # Calculate rollup metrics for each OS
        compiled_os_profiles = {}
        for os_name, acc in self.os_summaries.items():
            count = acc["total_runs"]
            if count == 0:
                continue
            compiled_os_profiles[os_name] = {
                "total_runs": count,
                "passed_runs": acc["passed_runs"],
                "pass_rate_pct": round((acc["passed_runs"] / count) * 100.0, 1),
                "total_completed_ops": acc["total_completed_ops"],
                "total_errors": acc["total_errors"],
                "error_rate_pct": round((acc["total_errors"] / max(1, acc["total_completed_ops"])) * 100.0, 4),
                "mean_throughput_rps": round(sum(acc["average_rps_list"]) / count, 1),
                "peak_throughput_rps": max(acc["peak_rps_list"]),
                "mean_p95_latency_ms": round(sum(acc["p95_latencies"]) / count, 3),
                "mean_p99_latency_ms": round(sum(acc["p99_latencies"]) / count, 3),
                "peak_rss_mb": round(max(acc["peak_rss_mb_list"]), 2),
                "scorecards": acc["scorecards"],
            }

        return {
            "metadata": self.metadata,
            "os_profiles": compiled_os_profiles,
            "scenarios": self.scenarios_data,
        }

    def compile_summary_dataset(self) -> Dict[str, Any]:
        """Compiles a lightweight summary dataset omitting per-second telemetry records."""
        final_ds = self.compile_final_dataset()
        summary_scenarios = {}
        for s_id, s_val in final_ds.get("scenarios", {}).items():
            summary_scenarios[s_id] = {
                "scenario_id": s_id,
                "runs": {},
            }
            for r_key, r_val in s_val.get("runs", {}).items():
                summary_scenarios[s_id]["runs"][r_key] = {
                    "target_os": r_val.get("target_os"),
                    "slot_id": r_val.get("slot_id"),
                    "total_seconds": r_val.get("total_seconds"),
                    "completed": r_val.get("completed"),
                    "exit_classification": r_val.get("exit_classification"),
                    "business_scorecard": r_val.get("business_scorecard"),
                    "crossover_partner": r_val.get("crossover_partner"),
                    "crossover_variance_pct": r_val.get("crossover_variance_pct"),
                    "aggregate_metrics": r_val.get("aggregate_metrics"),
                }
        return {
            "metadata": final_ds.get("metadata", {}),
            "os_profiles": final_ds.get("os_profiles", {}),
            "scenarios_summary": summary_scenarios,
        }

    def save_to_file(self, target_path: Optional[str] = None) -> str:
        """Saves telemetry dataset to disk (both compressed .json.gz and summary .json)."""
        out_file = target_path or self.output_path
        os.makedirs(os.path.dirname(out_file), exist_ok=True)
        dataset = self.compile_final_dataset()

        # 1. Save uncompressed JSON
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(dataset, f, indent=2)

        # 2. Save compressed full JSON (.json.gz) for git persistence
        gz_file = f"{out_file}.gz"
        with gzip.open(gz_file, "wt", encoding="utf-8") as f:
            json.dump(dataset, f)

        # 3. Save lightweight summary JSON
        summary_file = out_file.replace(".json", "_summary.json")
        summary_dataset = self.compile_summary_dataset()
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary_dataset, f, indent=2)

        return out_file
