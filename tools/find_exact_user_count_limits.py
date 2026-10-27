#!/usr/bin/env python3
"""
tools/find_exact_user_count_limits.py
Finds the exact maximum passing user count for:
  1. Community #1 (rust-epoll-scooter1337) on Ubuntu 24.04 LTS
  2. Community #1 (rust-epoll-scooter1337) on FerroOS Server
  3. Our Practical System Design (ferro-c500k-server) on Ubuntu 24.04 LTS
  4. Our Practical System Design (ferro-c500k-server) on FerroOS Server

Adheres strictly to the official challenge thresholds:
  - Pass Condition: p95 < 500ms, p99 < 1000ms, errors < 1.0%
  - Hardware: 1.0 vCPU, 2048 MB RAM (0 swap), LimitNOFILE=65535
  - Seed: Authentic 238 MB feed.db (50k users, 500k posts, 2M likes)
  - Workload: bench/load.js human think-times (feed -> think -> post -> think -> 15% like, 2% post)
"""

import os
import sys
import time
import json
import resource
import subprocess
import threading

# Ensure process can open 65,535 file descriptors
try:
    resource.setrlimit(resource.RLIMIT_NOFILE, (65535, 65535))
except Exception as e:
    print(f"Warning setting ulimit: {e}")

K6_BIN = os.path.abspath("tools/k6")
REPO_DIR = os.path.abspath("benchmarks/twelve-dollar-server-challenge")
TOKENS_JSON = os.path.join(REPO_DIR, "seed/tokens.json")
LOAD_JS = os.path.join(REPO_DIR, "bench/load.js")
PORT = 9130
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
        "id": "ferro_ubuntu",
        "name": "Our Design (ferro-c500k-server)",
        "os": "Ubuntu 24.04 LTS",
        "image": "bench-ubuntu:latest",
        "bin": "/repo/submissions/ferro-c500k-server/target/release/ferro-c500k-server"
    },
    {
        "id": "ferro_ferro",
        "name": "Our Design (ferro-c500k-server)",
        "os": "FerroOS Server",
        "image": "ferro-server:latest",
        "bin": "/repo/submissions/ferro-c500k-server/target/release/ferro-c500k-server"
    }
]

# Concurrency Ladder
LADDER = [1000, 2000, 3000, 5000, 7500, 10000, 15000, 20000, 25000]

def clean_container(name="bench_user_limit"):
    subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def start_server(cfg, container_name="bench_user_limit"):
    clean_container(container_name)
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
    for _ in range(25):
        time.sleep(0.5)
        res = subprocess.run(["curl", "-s", f"{BASE_URL}/health"], capture_output=True, text=True)
        if res.returncode == 0 and '"status":"ok"' in res.stdout:
            return True
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

def run_ladder_tier(vus, container_name="bench_user_limit"):
    summary_file = f"/tmp/k6_ladder_{vus}.json"
    if os.path.exists(summary_file):
        os.remove(summary_file)
        
    cmd = [
        K6_BIN, "run",
        "-e", f"BASE_URL={BASE_URL}",
        "-e", f"VUS={vus}",
        "-e", "DURATION=10s",
        "-e", "RAMP_UP=2s",
        "-e", "RAMP_DOWN=2s",
        "-e", "GRACEFUL_RAMP_DOWN=2s",
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
        "error_pct": 0.0,
        "passed": False,
        "fail_reason": "",
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
            
            failed_count = int(http_failed.get("passes", 0))
            total_count = metrics["reqs_total"]
            metrics["error_pct"] = (failed_count / total_count * 100.0) if total_count > 0 else 0.0
            
            # Check thresholds: p95 < 500ms, p99 < 1000ms, error < 1%
            if metrics["p95_ms"] >= 500.0:
                metrics["fail_reason"] = f"p95 exceeded ({metrics['p95_ms']:.1f}ms >= 500ms)"
            elif metrics["p99_ms"] >= 1000.0:
                metrics["fail_reason"] = f"p99 exceeded ({metrics['p99_ms']:.1f}ms >= 1000ms)"
            elif metrics["error_pct"] >= 1.0:
                metrics["fail_reason"] = f"errors exceeded ({metrics['error_pct']:.2f}% >= 1%)"
            elif metrics["reqs_total"] == 0:
                metrics["fail_reason"] = "zero requests processed"
            else:
                metrics["passed"] = True
        except Exception as e:
            metrics["fail_reason"] = f"JSON parse error: {e}"
    else:
        err_hint = proc.stderr[-300:] if proc.stderr else proc.stdout[-300:]
        metrics["fail_reason"] = f"k6 exited with no summary: {err_hint.strip()}"
        
    return metrics

def find_max_users_for_config(cfg):
    print(f"\n================================================================================")
    print(f"🔥 EVALUATING MAX CAPACITY: {cfg['name']} on [{cfg['os']}]")
    print(f"================================================================================")
    if not start_server(cfg):
        print("❌ Failed to start server container!")
        return None
        
    passed_ladder = []
    max_passing_users = 0
    final_reason = ""
    
    for vus in LADDER:
        print(f"  👉 Testing Concurrency: {vus:,} Virtual Users ... ", end="", flush=True)
        res = run_ladder_tier(vus)
        
        if res["passed"]:
            max_passing_users = vus
            passed_ladder.append(res)
            print(f"✅ PASS | {res['req_per_sec']:,.1f} req/s | avg={res['avg_ms']:.2f}ms | p95={res['p95_ms']:.2f}ms | p99={res['p99_ms']:.2f}ms | Err={res['error_pct']:.2f}% | RAM={res['mem_mb']:.1f}MB | CPU={res['cpu_pct']:.1f}%")
        else:
            final_reason = res["fail_reason"]
            print(f"❌ CHOKE ({res['fail_reason']}) | {res['req_per_sec']:,.1f} req/s | p95={res['p95_ms']:.2f}ms | Err={res['error_pct']:.2f}% | RAM={res['mem_mb']:.1f}MB")
            passed_ladder.append(res)
            break
            
        time.sleep(1)

    clean_container()
    print(f"🏆 MAX PASSING USER COUNT FOR [{cfg['name']} on {cfg['os']}]: {max_passing_users:,} USERS")
    return {
        "config": cfg,
        "max_passing_users": max_passing_users,
        "stop_reason": final_reason if final_reason else "Completed all ladder tiers",
        "ladder": passed_ladder
    }

def main():
    print("=" * 90)
    print("       OFFICIAL $12 CHALLENGE: DETERMINING EXACT MAXIMUM USER COUNT BENCHMARK         ")
    print("=" * 90)
    print("  • Comparing:")
    print("      1. Community #1 (scooter1337) on Ubuntu 24.04")
    print("      2. Community #1 (scooter1337) on FerroOS Server")
    print("      3. Our Practical Design (ferro-c500k-server) on Ubuntu 24.04")
    print("      4. Our Practical Design (ferro-c500k-server) on FerroOS Server")
    print("  • Progressive Ladder: 1,000 -> 2,000 -> 3,000 -> 5,000 -> 7,500 -> 10,000 -> 15,000 -> 20,000 -> 25,000 VUs")
    print("  • Strict Pass Criteria: p95 < 500 ms, p99 < 1,000 ms, error rate < 1.0%")
    print("=" * 90)

    results = []
    for cfg in CONFIGS:
        out = find_max_users_for_config(cfg)
        if out:
            results.append(out)
        time.sleep(2)

    # Print Final Definitive Summary Table
    print("\n" + "=" * 90)
    print("                         DEFINITIVE USER COUNT BREAKING POINTS                        ")
    print("=" * 90)
    header = f"{'Rank / System':<32} | {'Operating System':<18} | {'Max Passing Users':<18} | {'Breaking Factor'}"
    print(header)
    print("-" * 90)
    
    for r in results:
        cfg = r["config"]
        max_u = f"{r['max_passing_users']:,} Users"
        reason = r["stop_reason"]
        print(f"{cfg['name']:<32} | {cfg['os']:<18} | {max_u:<18} | {reason}")
    print("=" * 90)

    out_file = "benchmarks/exact_user_count_ladder_results.json"
    with open(out_file, "w") as f:
        json.dump({"timestamp": time.time(), "results": results}, f, indent=2)
    print(f"\n📁 Saved exact user count dataset to {out_file}\n")

if __name__ == "__main__":
    main()
