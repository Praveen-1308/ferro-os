#!/usr/bin/env python3
"""
tools/run_official_challenge_comparative_matrix.py - Official $12 Challenge Comparative Matrix
Runs the genuine #1 challenge winner (rust-epoll-scooter1337) on:
  1. Ubuntu 24.04 LTS (the official challenge OS)
  2. FerroOS (our pure-Rust OS environment)

Strict Hardware Constraints (Rule 8):
  - 1 vCPU (--cpus 1.0)
  - 2 GB RAM (--memory 2048m --memory-swap 2048m, no swap)
  - In-process SQLite WAL durability (PRAGMA synchronous = NORMAL)
  - LimitNOFILE = 65535

Load Testing (Rules 4, 11 & bench/load.js):
  - Uses tools/k6 with authentic human think time (3-7s browsing, 15% likes, 2% posts)
  - Measures sustained throughput, p95/p99 tail latencies, error rates, peak RAM, and CPU efficiency.
"""

import os
import sys
import time
import json
import subprocess
import threading

K6_BIN = os.path.abspath("tools/k6")
REPO_DIR = os.path.abspath("benchmarks/twelve-dollar-server-challenge")
TOKENS_JSON = os.path.join(REPO_DIR, "seed/tokens.json")
LOAD_JS = os.path.join(REPO_DIR, "bench/load.js")
PORT = 9123
BASE_URL = f"http://127.0.0.1:{PORT}"

TIERS = [
    {"vus": 200, "duration": "12s", "ramp": "3s", "ramp_down": "2s"},
    {"vus": 500, "duration": "12s", "ramp": "3s", "ramp_down": "2s"},
    {"vus": 800, "duration": "12s", "ramp": "3s", "ramp_down": "2s"},
]

def clean_container(name="bench_challenge_run"):
    subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def start_server(os_name, image_name, container_name="bench_challenge_run"):
    clean_container(container_name)
    print(f"\n🚀 Launching Genuine Server in [{os_name}] ({image_name})...")
    print(f"   Resource Limits: 1.0 vCPU | 2048 MB RAM (0 swap) | LimitNOFILE=65535")
    
    cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "--privileged",
        "--cpus", "1.0",
        "--memory", "2048m",
        "--memory-swap", "2048m",
        "--ulimit", "nofile=65535:65535",
        "-p", f"{PORT}:{PORT}",
        "-v", f"{REPO_DIR}:/repo",
        "-e", "SQLITE_PATH=/tmp/feed.db",
        "-e", "JWT_SECRET=twelve-dollar-challenge",
        "-e", f"PORT={PORT}",
        image_name,
        "bash", "-c",
        "cp /repo/seed/feed.db /tmp/feed.db && rm -f /tmp/feed.db-wal /tmp/feed.db-shm && "
        "/repo/submissions/rust-epoll-scooter1337/target/release/twelve-rust-poll"
    ]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL)
    
    # Wait for health
    for _ in range(20):
        time.sleep(0.5)
        res = subprocess.run(["curl", "-s", f"{BASE_URL}/health"], capture_output=True, text=True)
        if res.returncode == 0 and '"status":"ok"' in res.stdout:
            print(f"   ✅ Server Healthy: {res.stdout.strip()}")
            return True
    print("   ❌ Server failed to become healthy!")
    return False

def sample_container_stats(container_name, stop_event, stats_recorder):
    max_mem = 0.0
    max_cpu = 0.0
    while not stop_event.is_set():
        try:
            res = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}|{{.CPUPerc}}", container_name],
                capture_output=True, text=True, timeout=3
            )
            if res.returncode == 0 and res.stdout.strip():
                mem_part, cpu_part = res.stdout.strip().split("|")
                mem_mb_str = mem_part.split("/")[0].strip()
                if "GiB" in mem_mb_str:
                    m = float(mem_mb_str.replace("GiB", "").strip()) * 1024
                elif "MiB" in mem_mb_str:
                    m = float(mem_mb_str.replace("MiB", "").strip())
                else:
                    m = 0.0
                c = float(cpu_part.replace("%", "").strip())
                if m > max_mem: max_mem = m
                if c > max_cpu: max_cpu = c
        except Exception:
            pass
        time.sleep(0.5)
    stats_recorder["max_mem"] = max_mem
    stats_recorder["max_cpu"] = max_cpu

def run_k6_tier(vus, duration, ramp, ramp_down, container_name="bench_challenge_run"):
    summary_file = f"/tmp/k6_summary_{vus}.json"
    if os.path.exists(summary_file):
        os.remove(summary_file)
        
    cmd = [
        K6_BIN, "run",
        "-e", f"BASE_URL={BASE_URL}",
        "-e", f"VUS={vus}",
        "-e", f"DURATION={duration}",
        "-e", f"RAMP_UP={ramp}",
        "-e", f"RAMP_DOWN={ramp_down}",
        "-e", f"TOKENS={TOKENS_JSON}",
        "--summary-export", summary_file,
        LOAD_JS
    ]
    
    # Start background monitor thread
    stop_event = threading.Event()
    stats_rec = {"max_mem": 0.0, "max_cpu": 0.0}
    t = threading.Thread(target=sample_container_stats, args=(container_name, stop_event, stats_rec))
    t.daemon = True
    t.start()
    
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stop_event.set()
    t.join(timeout=2.0)
    
    metrics = {
        "vus": vus,
        "reqs_total": 0,
        "req_per_sec": 0.0,
        "p95_ms": 0.0,
        "p99_ms": 0.0,
        "error_pct": 0.0,
        "passed": False,
        "mem_mb": stats_rec["max_mem"],
        "cpu_pct": stats_rec["max_cpu"]
    }
    
    if os.path.exists(summary_file):
        try:
            with open(summary_file) as f:
                data = json.load(f)
            
            http_reqs = data.get("metrics", {}).get("http_reqs", {})
            http_dur = data.get("metrics", {}).get("http_req_duration", {})
            http_failed = data.get("metrics", {}).get("http_req_failed", {})
            
            metrics["reqs_total"] = int(http_reqs.get("count", 0))
            metrics["req_per_sec"] = float(http_reqs.get("rate", 0.0))
            metrics["p95_ms"] = float(http_dur.get("p(95)", 0.0))
            metrics["p99_ms"] = float(http_dur.get("p(99)", 0.0))
            
            # In k6, http_req_failed 'passes' is count of failed requests
            failed_count = int(http_failed.get("passes", 0))
            total_count = metrics["reqs_total"]
            metrics["error_pct"] = (failed_count / total_count * 100.0) if total_count > 0 else 0.0
            metrics["passed"] = (metrics["p95_ms"] < 500.0) and (metrics["p99_ms"] < 1000.0) and (metrics["error_pct"] < 1.0)
        except Exception as e:
            print(f"Error parsing k6 summary: {e}")
    return metrics

def run_suite_for_os(os_name, image_name):
    if not start_server(os_name, image_name):
        return None
        
    print(f"\n🔍 [Phase 1: Correctness] Running 42-check test suite on {os_name}...")
    test_run = subprocess.run(
        ["bash", os.path.join(REPO_DIR, "test/test.sh"), BASE_URL],
        capture_output=True, text=True
    )
    if "passed=42 failed=0" in test_run.stdout:
        print(f"   ✅ Correctness: 42/42 Tests Passed (100% compliant)")
    else:
        print(f"   ❌ Correctness Failed!")
        print(test_run.stdout[-500:])
        clean_container()
        return None

    print(f"\n⚡ [Phase 2: K6 Load Testing] Running human think-time workloads...")
    tier_results = []
    for tier in TIERS:
        vus = tier["vus"]
        print(f"   📊 Testing Concurrency: {vus:,} Virtual Users (Hold {tier['duration']})...", end="", flush=True)
        res = run_k6_tier(vus, tier["duration"], tier["ramp"], tier["ramp_down"])
        tier_results.append(res)
        
        status_sym = "✅ PASS" if res["passed"] else "⚠️ SLOW"
        print(f" {status_sym} | {res['req_per_sec']:,.1f} req/s | p95={res['p95_ms']:.1f}ms | p99={res['p99_ms']:.1f}ms | Err={res['error_pct']:.2f}% | RAM={res['mem_mb']:.1f}MB | CPU={res['cpu_pct']:.1f}%")
        time.sleep(2)

    clean_container()
    return tier_results

def main():
    print("=" * 80)
    print("      OFFICIAL $12 SERVER CHALLENGE COMPARATIVE BENCHMARK MATRIX        ")
    print("=" * 80)
    print("  • Workload: Genuine Rust #1 Submission (rust-epoll-scooter1337)")
    print("  • Database: SQLite WAL (seed/feed.db: 50k users, 500k posts, 2M likes)")
    print("  • Environments Compared:")
    print("     1. Ubuntu 24.04 LTS (Official Challenge OS)")
    print("     2. FerroOS Server (Pure-Rust OS Environment)")
    print("  • Strict Hardware Specs: 1.0 vCPU | 2048 MB RAM (0 swap)")
    print("=" * 80)

    # 1. Run on Ubuntu 24.04
    ubuntu_results = run_suite_for_os("Ubuntu 24.04 LTS", "bench-ubuntu:latest")
    
    # 2. Run on FerroOS
    ferro_results = run_suite_for_os("FerroOS Server", "ferro-server:latest")

    print("\n" + "=" * 80)
    print("                      HEAD-TO-HEAD RESULTS SUMMARY                      ")
    print("=" * 80)
    print(f"{'Concurrency':<12} | {'Metric':<18} | {'Ubuntu 24.04':<18} | {'FerroOS Server':<18} | {'Delta':<12}")
    print("-" * 80)
    
    if ubuntu_results and ferro_results:
        for u_res, f_res in zip(ubuntu_results, ferro_results):
            vus = u_res["vus"]
            # Throughput
            t_diff = f_res["req_per_sec"] - u_res["req_per_sec"]
            t_pct = (t_diff / u_res["req_per_sec"]) * 100 if u_res["req_per_sec"] > 0 else 0
            print(f"{vus} VUs{'':<6} | {'Throughput':<18} | {u_res['req_per_sec']:>10.1f} req/s   | {f_res['req_per_sec']:>10.1f} req/s   | {t_pct:>+6.1f}%")
            
            # p95 latency
            p95_diff = u_res["p95_ms"] - f_res["p95_ms"]
            print(f"{'':<12} | {'p95 Latency':<18} | {u_res['p95_ms']:>10.1f} ms      | {f_res['p95_ms']:>10.1f} ms      | {p95_diff:>+6.1f}ms")
            
            # p99 latency
            p99_diff = u_res["p99_ms"] - f_res["p99_ms"]
            print(f"{'':<12} | {'p99 Latency':<18} | {u_res['p99_ms']:>10.1f} ms      | {f_res['p99_ms']:>10.1f} ms      | {p99_diff:>+6.1f}ms")
            
            # Memory RSS
            mem_diff = u_res["mem_mb"] - f_res["mem_mb"]
            print(f"{'':<12} | {'Peak Memory':<18} | {u_res['mem_mb']:>10.1f} MB      | {f_res['mem_mb']:>10.1f} MB      | {mem_diff:>+6.1f}MB")
            print("-" * 80)
            
    # Save results to JSON
    output_data = {
        "timestamp": time.time(),
        "ubuntu": ubuntu_results,
        "ferro_os": ferro_results
    }
    with open("benchmarks/official_challenge_comparative_results.json", "w") as f:
        json.dump(output_data, f, indent=2)
    print("📁 Saved comparative dataset to benchmarks/official_challenge_comparative_results.json")

if __name__ == "__main__":
    main()
