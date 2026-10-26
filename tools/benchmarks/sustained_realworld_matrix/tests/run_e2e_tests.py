#!/usr/bin/env python3
"""
tools/benchmarks/sustained_realworld_matrix/tests/run_e2e_tests.py
Unified E2E Test Runner for the Sustained Real-World Benchmark Matrix suite.

Executes test tiers (Tiers 1–4), computes statistics, displays a formatted summary table,
and returns exit code 0 on complete pass, or 1 on any failure/error.
"""

import sys
import os
import time
import argparse
import unittest
from typing import Dict, List, Any

# Ensure tests package is on path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

TIERS_CONFIG = [
    {
        "id": 1,
        "name": "Tier 1: Feature Tests (Isolated)",
        "dir": os.path.join(CURRENT_DIR, "tier1_feature_tests"),
        "pattern": "test_*.py",
        "min_expected": 135,
    },
    {
        "id": 2,
        "name": "Tier 2: Boundary Tests (Limits & Edge Cases)",
        "dir": os.path.join(CURRENT_DIR, "tier2_boundary_tests"),
        "pattern": "test_*.py",
        "min_expected": 135,
    },
    {
        "id": 3,
        "name": "Tier 3: Pairwise Tests (Combinatorial Interactions)",
        "dir": os.path.join(CURRENT_DIR, "tier3_pairwise_tests"),
        "pattern": "test_*.py",
        "min_expected": 15,
    },
    {
        "id": 4,
        "name": "Tier 4: Application Tests (Real Enterprise Workloads)",
        "dir": os.path.join(CURRENT_DIR, "tier4_application_tests"),
        "pattern": "test_*.py",
        "min_expected": 10,
    },
]

def run_test_tier(tier_info: Dict[str, Any], verbose: bool = False) -> Dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.discover(
        start_dir=tier_info["dir"],
        pattern=tier_info["pattern"],
        top_level_dir=PROJECT_ROOT
    )

    runner = unittest.TextTestRunner(
        verbosity=2 if verbose else 1,
        stream=sys.stdout
    )

    t0 = time.perf_counter()
    result = runner.run(suite)
    elapsed = time.perf_counter() - t0

    return {
        "id": tier_info["id"],
        "name": tier_info["name"],
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
        "elapsed_s": elapsed,
        "success": result.wasSuccessful(),
    }

def print_summary_table(results: List[Dict[str, Any]], total_elapsed: float):
    print("\n" + "=" * 90)
    print("       SUSTAINED REAL-WORLD BENCHMARK MATRIX — E2E TEST EXECUTION SUMMARY")
    print("=" * 90)
    header = f"{'Tier':<45} | {'Run':<6} | {'Pass':<6} | {'Fail':<6} | {'Err':<5} | {'Time (s)':<8} | {'Status':<8}"
    print(header)
    print("-" * 90)

    total_run = 0
    total_pass = 0
    total_fail = 0
    total_err = 0
    all_success = True

    for r in results:
        total_run += r["tests_run"]
        total_pass += r["passed"]
        total_fail += r["failures"]
        total_err += r["errors"]
        if not r["success"]:
            all_success = False

        status = "\033[92mPASS\033[0m" if r["success"] else "\033[91mFAIL\033[0m"
        line = f"{r['name']:<45} | {r['tests_run']:<6} | {r['passed']:<6} | {r['failures']:<6} | {r['errors']:<5} | {r['elapsed_s']:<8.3f} | {status:<8}"
        print(line)

    print("-" * 90)
    overall_status = "\033[92m100% PASSED\033[0m" if all_success else "\033[91mFAILED\033[0m"
    summary_line = f"{'TOTAL':<45} | {total_run:<6} | {total_pass:<6} | {total_fail:<6} | {total_err:<5} | {total_elapsed:<8.3f} | {overall_status:<8}"
    print(summary_line)
    print("=" * 90)

    if all_success:
        print("\n\033[92m✔ All test suites passed successfully with zero failures or errors.\033[0m\n")
    else:
        print("\n\033[91m✘ One or more test suites failed. Review logs above.\033[0m\n")

def main():
    parser = argparse.ArgumentParser(description="Run Sustained Real-World Benchmark Matrix E2E Tests.")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3, 4], help="Run a specific test tier only (1, 2, 3, or 4).")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose test output.")
    args = parser.parse_args()

    selected_tiers = TIERS_CONFIG
    if args.tier:
        selected_tiers = [t for t in TIERS_CONFIG if t["id"] == args.tier]

    print(f"[*] Starting E2E Test Suite Execution across {len(selected_tiers)} tier(s)...")
    t_start = time.perf_counter()
    tier_results = []

    for tier_cfg in selected_tiers:
        print(f"\n[+] Executing {tier_cfg['name']}...")
        res = run_test_tier(tier_cfg, verbose=args.verbose)
        tier_results.append(res)

    total_time = time.perf_counter() - t_start
    print_summary_table(tier_results, total_time)

    # Return exit code: 0 if all succeeded, 1 if any failure or error
    all_passed = all(r["success"] for r in tier_results)
    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    main()
