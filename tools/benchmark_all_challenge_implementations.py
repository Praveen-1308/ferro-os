#!/usr/bin/env python3
"""
tools/benchmark_all_challenge_implementations.py
Comprehensive 4-Way Comparative Benchmark Matrix for the $12 Server Challenge:

Evaluates:
  1. Community #1 Winner (rust-epoll-scooter1337) on Ubuntu 24.04 LTS
  2. Community #1 Winner (rust-epoll-scooter1337) on FerroOS Server
  3. Ferro-C500K Server (Practical Rust Implementation) on Ubuntu 24.04 LTS
  4. Ferro-C500K Server (Practical Rust Implementation) on FerroOS Server

Strict Hardware Enforcement (Rule 8):
  - 1.0 vCPU (--cpus 1.0)
  - 2048 MB RAM (0 swap: --memory 2048m --memory-swap 2048m)
  - In-process SQLite WAL durability (PRAGMA synchronous = NORMAL)
  - LimitNOFILE = 65535
  - Authentic 238 MB feed.db (500,000 posts, 50,000 users, 2,000,000 likes)
  - Authentic 20,000 user JWT tokens (seed/tokens.json)
  - Official k6 test suite (bench/load.js)
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
TEST_SH = os.path.join(REPO_DIR, "test/test.sh")
PORT = 9125
BASE_URL = f"http://127.0.0.1:{PORT}"

CONFIGS = [
    {
        "id": "scooter_ubuntu",
        "name": "Community #1 (scooter1337)",
        "os": "Ubuntu 24.04 LTS",
        "image": "bench-ubuntu:latest",
        "bin": "/repo/submissions/rust-epoll-scooter1337/target/release/twelve-rust-poll"
    },
    {
        "id": "scooter_ferro",
        "name": "Community #1 (scooter1337)",
        "os": "FerroOS Server",
        "image": "ferro-server:latest",
        "bin": "/repo/submissions/rust-epoll-scooter1337/target/release/twelve-rust-poll"
    },
    {
        "id": "ferroc500k_ubuntu",
        "name": "Ferro-C500K Server",
        "os": "Ubuntu 24.04 LTS",
        "image": "bench-ubuntu:latest",
        "bin": "/repo/submissions/ferro-c500k-server/target/release/ferro-c500k-server"
    },
    {
        "id": "ferroc500k_ferro",
        "name": "Ferro-C500K Server",
        "os": "FerroOS Server",
        "image": "ferro-server:latest",
        "bin": "/repo/submissions/ferro-c500k-server/target/release/ferro-c500k-server"
    }
]

TIERS = [
    {"vus": 200, "duration": "10s", "ramp": "2s", "ramp_down": "1s"},
    {"vus": 500, "duration": "10s", "ramp": "2s", "ramp_down": "1s"},
    {"vus": 800, "duration": "10s", "ramp": "2s", "ramp_down": "1s"},
    {"vus": 1200, "duration": "10s", "ramp": "2s", "ramp_down": "1s"},
]

def clean_container(name="bench_challenge_matrix"):
    subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def start_server(cfg, container_name="bench_challenge_matrix"):
    clean_container(container_name)
    print(f"\n🚀 Launching [{cfg['name']}] on [{cfg['os']}]...")
    print(f"   Limits: 1.0 vCPU | 2048 MB RAM (0 swap) | LimitNOFILE=65535")
    
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
        cfg["image"],
        "bash", "-c",
        f"cp /repo/seed/feed.db /tmp/feed.db && rm -f /tmp/feed.db-wal /tmp/feed.db-shm && {cfg['bin']}"
    ]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL)
    
    # Wait for health
    for _ in range(30):
        time.sleep(0.5)
        res = subprocess.run(["curl", "-s", f"{BASE_URL}/health"], capture_output=True, text=True)
        if res.returncode == 0 and '"status":"ok"' in res.stdout:
            print(f"   ✅ Server Online: {res.stdout.strip()}")
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
                elif "KiB" in mem_mb_str:
                    m = float(mem_mb_str.replace("KiB", "").strip()) / 1024
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

def run_k6_tier(vus, duration, ramp, ramp_down, container_name="bench_challenge_matrix"):
    summary_file = f"/tmp/k6_matrix_{vus}.json"
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
        "avg_ms": 0.0,
        "p95_ms": 0.0,
        "p99_ms": 0.0,
        "max_ms": 0.0,
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
            metrics["avg_ms"] = float(http_dur.get("avg", 0.0))
            metrics["p95_ms"] = float(http_dur.get("p(95)", 0.0))
            metrics["p99_ms"] = float(http_dur.get("p(99)", 0.0))
            metrics["max_ms"] = float(http_dur.get("max", 0.0))
            
            failed_count = int(http_failed.get("passes", 0))
            total_count = metrics["reqs_total"]
            metrics["error_pct"] = (failed_count / total_count * 100.0) if total_count > 0 else 0.0
            metrics["passed"] = (metrics["p95_ms"] < 500.0) and (metrics["p99_ms"] < 1000.0) and (metrics["error_pct"] < 1.0) and (metrics["reqs_total"] > 0)
        except Exception as e:
            print(f"Error parsing k6 summary: {e}")
    return metrics

def run_evaluation_for_config(cfg):
    if not start_server(cfg):
        return None
        
    print(f"   🔍 Verifying Correctness: Running 42-check test suite...")
    test_run = subprocess.run(
        ["bash", TEST_SH, BASE_URL],
        capture_output=True, text=True
    )
    if "passed=42 failed=0" in test_run.stdout:
        print(f"   ✅ Correctness Verified: 42/42 tests passed (100% compliant)")
    else:
        print(f"   ❌ Correctness Failed!")
        print(test_run.stdout[-500:])
        clean_container()
        return None

    print(f"   ⚡ Running K6 progressive load ladder...")
    tiers_out = []
    for tier in TIERS:
        vus = tier["vus"]
        print(f"      📊 {vus:,} VUs (hold {tier['duration']})...", end="", flush=True)
        res = run_k6_tier(vus, tier["duration"], tier["ramp"], tier["ramp_down"])
        tiers_out.append(res)
        
        status_sym = "✅ PASS" if res["passed"] else "⚠️ CHOKE"
        print(f" {status_sym} | {res['req_per_sec']:,.1f} req/s | avg={res['avg_ms']:.2f}ms | p95={res['p95_ms']:.2f}ms | p99={res['p99_ms']:.2f}ms | Err={res['error_pct']:.2f}% | RAM={res['mem_mb']:.1f}MB | CPU={res['cpu_pct']:.1f}%")
        time.sleep(1)

    clean_container()
    return {
        "config": cfg,
        "correctness": "42/42 PASS",
        "tiers": tiers_out
    }

def main():
    print("=" * 90)
    print("       DEFINITIVE 4-WAY COMPARATIVE BENCHMARK: THEORETICAL TO PRACTICAL REALITY      ")
    print("=" * 90)
    print("  • Engines Compared:")
    print("      A) Community #1 Winner (rust-epoll-scooter1337)")
    print("      B) Ferro-C500K Server (Practical Rust Implementation of Theoretical Design)")
    print("  • OS Environments Compared:")
    print("      1) Ubuntu 24.04 LTS (Official Challenge OS)")
    print("      2) FerroOS Server (Pure-Rust Kernel/User Environment)")
    print("  • Hardware Constraints: 1.0 vCPU | 2048 MB RAM (0 swap) | LimitNOFILE=65535")
    print("  • Workload: Authentic 238 MB feed.db | 20,000 real JWT tokens | Human think times")
    print("=" * 90)

    all_results = []
    for cfg in CONFIGS:
        res = run_evaluation_for_config(cfg)
        if res:
            all_results.append(res)
        time.sleep(2)

    # Print Summary Table
    print("\n" + "=" * 90)
    print("                              FULL EMPIRICAL BENCHMARK MATRIX                         ")
    print("=" * 90)
    header = f"{'Engine':<20} | {'OS':<15} | {'VUs':<6} | {'Throughput':<12} | {'p95':<10} | {'p99':<10} | {'RAM':<10} | {'Status'}"
    print(header)
    print("-" * 90)
    
    for item in all_results:
        cfg = item["config"]
        for tier in item["tiers"]:
            vus = tier["vus"]
            thr = f"{tier['req_per_sec']:.1f} r/s"
            p95 = f"{tier['p95_ms']:.2f} ms"
            p99 = f"{tier['p99_ms']:.2f} ms"
            ram = f"{tier['mem_mb']:.1f} MB"
            status = "PASS" if tier["passed"] else "CHOKE"
            print(f"{cfg['name']:<20} | {cfg['os']:<15} | {vus:<6} | {thr:<12} | {p95:<10} | {p99:<10} | {ram:<10} | {status}")
        print("-" * 90)

    out_file = "benchmarks/complete_challenge_comparative_results.json"
    with open(out_file, "w") as f:
        json.dump({
            "timestamp": time.time(),
            "results": all_results
        }, f, indent=2)
    print(f"\n📁 Saved complete empirical benchmark results to {out_file}\n")

if __name__ == "__main__":
    main()
