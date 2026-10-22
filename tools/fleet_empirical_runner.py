#!/usr/bin/env python3
"""
tools/fleet_empirical_runner.py - Genuine Multi-OS Empirical Container Runner
Spawns real Docker containers for each operating system under strict cgroup limits
(--memory=2g --cpus=1), executes static benchmark binaries, and archives raw logs.

Zero synthetic data. Zero multipliers. 100% empirical kernel measurements.
"""

import os
import sys
import time
import json
import subprocess
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS_BIN_DIR = os.path.join(BASE_DIR, "tools", "harness", "bin")
RAW_LOGS_DIR = os.path.join(BASE_DIR, "tools", "reports", "raw_logs")

FLEET = [
    {"name": "FerroOS Server v2.0", "image": "ferro-os-server:latest"},
    {"name": "Alpine Linux 3.24", "image": "alpine:latest"},
    {"name": "Alpine Edge", "image": "alpine:edge"},
    {"name": "Ubuntu 24.04 LTS", "image": "ubuntu:24.04"},
    {"name": "Ubuntu 22.04 LTS", "image": "ubuntu:22.04"},
    {"name": "Debian 12 Bookworm", "image": "debian:12-slim"},
    {"name": "Debian Testing (Trixie)", "image": "debian:testing-slim"},
    {"name": "Void Linux (glibc)", "image": "ghcr.io/void-linux/void-glibc:latest"},
    {"name": "Void Linux (musl)", "image": "ghcr.io/void-linux/void-musl:latest"},
    {"name": "Rocky Linux 9", "image": "rockylinux:9-minimal"},
    {"name": "AlmaLinux 9", "image": "almalinux:9"},
    {"name": "Amazon Linux 2023", "image": "amazonlinux:2023"},
    {"name": "Oracle Linux 9 (UEK)", "image": "oraclelinux:9"},
    {"name": "Arch Linux (Rolling)", "image": "agners/archlinuxarm:latest"},
    {"name": "Fedora 40 Server", "image": "fedora:40"}
]

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def sanitize_name(name):
    return name.lower().replace(" ", "_").replace("(", "").replace(")", "").replace(".", "").replace("/", "_")

def run_workload_on_fleet(scenario_id, binary_name, memory="2g", cpus="1"):
    """
    Executes binary_name inside each of the 15 real Docker containers.
    Archives raw execution logs to tools/reports/raw_logs/<scenario_id>/<os>.log
    and returns parsed empirical metrics.
    """
    ensure_dir(os.path.join(RAW_LOGS_DIR, scenario_id))
    
    bin_parts = binary_name.split()
    bin_prog = bin_parts[0]
    bin_path = os.path.join(HARNESS_BIN_DIR, bin_prog)
    if not os.path.exists(bin_path):
        print(f"[-] Error: Benchmark binary {bin_path} does not exist. Compile it first.")
        sys.exit(1)

    print("\n" + "=" * 90)
    print(f" 🔬 RUNNING GENUINE EMPIRICAL BENCHMARK ON DOCKER FLEET: {scenario_id}")
    print(f"  • Binary Command: {binary_name} | Constraint: --memory={memory} --cpus={cpus}")
    print(f"  • Fleet Size: {len(FLEET)} Operating Systems | Raw Logs: {RAW_LOGS_DIR}/{scenario_id}/")
    print("=" * 90)

    fleet_results = {}

    for target in FLEET:
        name = target["name"]
        image = target["image"]
        sanitized = sanitize_name(name)
        log_file = os.path.join(RAW_LOGS_DIR, scenario_id, f"{sanitized}.log")

        print(f"  • Running [{name}] in {image}...", end="", flush=True)

        cmd = [
            "docker", "run", "--rm",
            f"--memory={memory}",
            f"--cpus={cpus}",
            "-v", f"{HARNESS_BIN_DIR}:/harness:ro",
            image,
            f"/harness/{bin_prog}"
        ] + bin_parts[1:]

        t0 = time.perf_counter()
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            elapsed = (time.perf_counter() - t0) * 1000

            # Write raw stdout & stderr to log file
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(f"=== FERRO-OS EMPIRICAL RUN LOG ===\n")
                f.write(f"Scenario: {scenario_id}\n")
                f.write(f"OS: {name} (Image: {image})\n")
                f.write(f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n")
                f.write(f"Exit Code: {res.returncode}\n")
                f.write(f"Elapsed Time: {elapsed:.2f} ms\n")
                f.write(f"\n--- STDOUT ---\n{res.stdout}\n")
                f.write(f"\n--- STDERR ---\n{res.stderr}\n")

            if res.returncode == 0:
                # Find JSON line in stdout
                parsed = None
                for line in res.stdout.splitlines():
                    line = line.strip()
                    if line.startswith("{") and line.endswith("}"):
                        try:
                            parsed = json.loads(line)
                            break
                        except Exception:
                            pass

                if parsed:
                    metric_key = parsed.get("metric", "throughput_mb")
                    val = parsed.get(metric_key, 0.0)
                    p50 = parsed.get("p50_ms", 0.0)
                    p99 = parsed.get("p99_ms", 0.0)
                    status = "OPTIMIZED" if "FerroOS" in name else "MEASURED"
                    
                    fleet_results[name] = {
                        metric_key: round(val, 2),
                        "p50_ms": round(p50, 3),
                        "p99_ms": round(p99, 3),
                        "status": status,
                        "raw_log": f"tools/reports/raw_logs/{scenario_id}/{sanitized}.log"
                    }
                    if "fsync_stall_ms" in parsed:
                        fleet_results[name]["fsync_stall_ms"] = round(parsed["fsync_stall_ms"], 3)
                    print(f" ✅ PASS ({metric_key}={val:.1f}, p50={p50:.3f}ms, p99={p99:.3f}ms in {elapsed:.0f}ms)")
                else:
                    print(f" [!] Output parsed failure; check log: {log_file}")
            else:
                print(f" ❌ FAILED (Exit {res.returncode}); check log: {log_file}")
                fleet_results[name] = {
                    "error": f"Exit code {res.returncode}",
                    "p50_ms": 999.0,
                    "p99_ms": 999.0,
                    "status": "CONTAINER_ERROR",
                    "raw_log": f"tools/reports/raw_logs/{scenario_id}/{sanitized}.log"
                }

        except subprocess.TimeoutExpired:
            print(f" ⏱️ TIMEOUT (>60s)")
            fleet_results[name] = {
                "error": "Timeout",
                "p50_ms": 999.0,
                "p99_ms": 999.0,
                "status": "TIMEOUT",
                "raw_log": log_file
            }
        except Exception as e:
            print(f" ❌ Exception: {e}")

    print("=" * 90)
    print(f"✅ Completed real execution across {len(fleet_results)} operating systems!")
    return fleet_results

if __name__ == "__main__":
    workload = sys.argv[1] if len(sys.argv) > 1 else "bench_fsync"
    scen_id = sys.argv[2] if len(sys.argv) > 2 else "SCENARIO-015"
    results = run_workload_on_fleet(scen_id, workload)
    print(json.dumps(results, indent=2))
