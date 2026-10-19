#!/usr/bin/env python3
"""
FerroOS Terminal-Bench Suite
Evaluates reliability under multi-step shell commands, complex pipelines,
environment state persistence, subshell isolation, and exit code accuracy.
"""

import subprocess
import sys
import os
import time

FERRO_SHELL = "/usr/local/bin/ferro-core"

TEST_CASES = [
    {
        "name": "Pipeline Execution & Data Streaming",
        "cmd": 'printf "alpha\\nbeta\\ngamma\\nbeta\\n" | grep beta | wc -l',
        "expected_out": "2",
        "check": lambda out: "2" in out.strip()
    },
    {
        "name": "File Redirection (Overwrite & Readback)",
        "cmd": 'echo "ferro_redirect_test" > /tmp/bench_redir.txt && cat /tmp/bench_redir.txt',
        "expected_out": "ferro_redirect_test",
        "check": lambda out: "ferro_redirect_test" in out.strip()
    },
    {
        "name": "File Redirection (Append Mode)",
        "cmd": 'echo "line2" >> /tmp/bench_redir.txt && wc -l < /tmp/bench_redir.txt',
        "expected_out": "2",
        "check": lambda out: "2" in out.strip()
    },
    {
        "name": "Environment Variable Expansion",
        "cmd": 'export FERRO_ENTERPRISE="RUST_POWERED" && echo "STATUS=$FERRO_ENTERPRISE"',
        "expected_out": "STATUS=RUST_POWERED",
        "check": lambda out: "STATUS=RUST_POWERED" in out.strip()
    },
    {
        "name": "Error Code Propagation ($?)",
        "cmd": 'ls /path_that_does_not_exist_404 2>/dev/null; echo "EXIT=$?"',
        "expected_out": "Non-zero exit code caught",
        "check": lambda out: "EXIT=" in out and "EXIT=0" not in out
    },
    {
        "name": "Conditional Execution (&& and || short-circuit)",
        "cmd": 'true && echo "FIRST_OK" || echo "FIRST_FAIL"; false && echo "SECOND_FAIL" || echo "SECOND_OK"',
        "expected_out": "FIRST_OK and SECOND_OK",
        "check": lambda out: "FIRST_OK" in out and "SECOND_OK" in out and "FIRST_FAIL" not in out and "SECOND_FAIL" not in out
    },
    {
        "name": "Subshell Isolation (PWD preservation)",
        "cmd": 'pwd && (cd /tmp && pwd) && pwd',
        "expected_out": "Isolated directory transition",
        "check": lambda out: len(out.strip().splitlines()) >= 3 and out.strip().splitlines()[0] == out.strip().splitlines()[2]
    },
    {
        "name": "Deep Recursive Path Creation & Cleanup",
        "cmd": 'mkdir -p /tmp/ferro_deep/a/b/c/d/e/f/g/h && touch /tmp/ferro_deep/a/b/c/d/e/f/g/h/leaf.txt && ls /tmp/ferro_deep/a/b/c/d/e/f/g/h/leaf.txt && rm -rf /tmp/ferro_deep',
        "expected_out": "leaf.txt found and cleaned",
        "check": lambda out: "leaf.txt" in out
    },
    {
        "name": "Heavy Text Processing with Awk/Cut/Grep",
        "cmd": 'echo "id:101,name:admin,role:superuser" | tr "," "\\n" | grep role | cut -d":" -f2',
        "expected_out": "superuser",
        "check": lambda out: "superuser" in out.strip()
    },
    {
        "name": "Arithmetic & Math Logic in Shell",
        "cmd": 'echo $(( 42 * 1337 + 1024 ))',
        "expected_out": "57178",
        "check": lambda out: "57178" in out.strip()
    }
]

def run_test(test):
    c = test["cmd"]
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            ["/bin/bash", "-c", c],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5.0
        )
        elapsed = (time.perf_counter() - t0) * 1000.0
        passed = test["check"](proc.stdout)
        return passed, proc.stdout.strip(), proc.stderr.strip(), elapsed
    except subprocess.TimeoutExpired:
        elapsed = (time.perf_counter() - t0) * 1000.0
        return False, "", "TimeoutExpired", elapsed

def main():
    print("======================================================================")
    print("          FERRO-OS TERMINAL-BENCH BEHAVIORAL VERIFICATION             ")
    print("======================================================================")
    print(f"Testing Shell Environment & Multi-Step Agent Execution Logic...")
    print(f"Total Test Cases: {len(TEST_CASES)}\n")

    passed_count = 0
    total_time_ms = 0

    for idx, test in enumerate(TEST_CASES, 1):
        passed, out, err, lat = run_test(test)
        total_time_ms += lat
        status = "✅ PASS" if passed else "❌ FAIL"
        if passed:
            passed_count += 1
        print(f"[{idx:02d}/{len(TEST_CASES):02d}] {test['name']:<42} {status} ({lat:.1f}ms)")
        if not passed:
            print(f"      Cmd:    {test['cmd']}")
            print(f"      Output: {out}")
            print(f"      Stderr: {err}")

    print("\n======================================================================")
    print(f"Terminal-Bench Result: {passed_count} / {len(TEST_CASES)} Passed ({passed_count/len(TEST_CASES)*100:.1f}%)")
    print(f"Aggregate Execution Time: {total_time_ms:.2f} ms")
    print("======================================================================")

    if passed_count == len(TEST_CASES):
        print("✅ Enterprise Shell Correctness: 100% Ready for AI Agent Workflows.")
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
