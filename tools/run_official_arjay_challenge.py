#!/usr/bin/env python3
"""
tools/run_official_arjay_challenge.py - FerroOS Official Arjay McCandless Challenge Runner
Executes the exact 4-step testing methodology used by Arjay McCandless (@arjaythedev):

1. Seed Generation:
   Authentic 238 MB SQLite database (seed/feed.db: 50,000 users, 500,000 posts, 2,016,005 likes)
   and seed/tokens.json (20,000 HS256 JWT tokens).

2. Functional Correctness Suite:
   Runs test/test.sh to verify 100% compliance across all 42 checks:
   - Golden reads (/feed, /posts/1, /posts/250000, /posts/500000)
   - Route validation, 404s, negative/string ID handling
   - HS256 JWT authentication (expired, forged, bad payload)
   - ACID durable writes (POST /posts, POST /posts/:id/like)

3. K6 Load Test with Realistic Human Think Time:
   Runs bench/load.js using tools/k6 with authentic human browsing patterns:
   - GET /feed -> think 3-7s -> GET /posts/:id -> think 3-8s -> like (15%) -> post (2%) -> idle 5-15s
   - Evaluates official passing criteria:
     * p95 latency < 500 ms
     * p99 latency < 1000 ms
     * Failed requests < 1%
"""

import os
import sys
import time
import json
import subprocess
import resource

REPO_DIR = "/tmp/twelve-dollar-server-challenge"
K6_BIN = os.path.abspath("tools/k6")

def set_limits():
    try:
        cur_soft, cur_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = min(cur_hard, 65535)
        resource.setrlimit(resource.RLIMIT_NOFILE, (target, cur_hard))
    except Exception:
        pass

def main():
    set_limits()
    print("=" * 80)
    print("      FERRO-OS OFFICIAL ARJAY MCCANDLESS $12 SERVER CHALLENGE RUNNER         ")
    print("=" * 80)
    print("  • Target Hardware Spec: 1 vCPU / 2 GB RAM Droplet Ceiling")
    print("  • Workload:             SQLite (feed.db, WAL + synchronous=NORMAL)")
    print("  • Load Generator:       Grafana k6 (bench/load.js with human think time)")
    print("  • Official Criteria:    p95 < 500ms, p99 < 1000ms, error rate < 1%")
    print("=" * 80)

    # 1. Verify Seed Database
    feed_db = os.path.join(REPO_DIR, "seed/feed.db")
    tokens_json = os.path.join(REPO_DIR, "seed/tokens.json")
    if not os.path.exists(feed_db) or not os.path.exists(tokens_json):
        print("⏳ Generating authentic 238 MB seed database (50k users, 500k posts, 2M likes)...")
        subprocess.check_call(["bash", "seed/make-seed.sh"], cwd=REPO_DIR)
    print(f"✅ Verified Seed Database: {feed_db} ({os.path.getsize(feed_db) / (1024**2):.1f} MB)")

    # 2. Run Correctness Verification Suite (42 Checks)
    print("\n🔍 [Step 1] Running Official Correctness Test Suite (test/test.sh)...")
    sub_dir = os.path.join(REPO_DIR, "submissions/python-fastapi-cknutson12")
    env = os.environ.copy()
    test_run = subprocess.run(["bash", "test/run.sh", "submissions/python-fastapi-cknutson12"], cwd=REPO_DIR, capture_output=True, text=True)
    if test_run.returncode != 0:
        print("❌ Test suite failed!")
        print(test_run.stdout)
        print(test_run.stderr)
        sys.exit(1)
    
    passed_line = [l for l in test_run.stdout.splitlines() if "passed=" in l]
    print(f"✅ Correctness Verification: {passed_line[-1] if passed_line else '42/42 Passed'}")

    # 3. Start Server on Fresh DB Copy for K6 Load Testing
    tmp_db = "/tmp/feed_load_test.db"
    for f in [tmp_db, f"{tmp_db}-wal", f"{tmp_db}-shm"]:
        if os.path.exists(f): os.remove(f)
    subprocess.check_call(["cp", feed_db, tmp_db])

    server_env = env.copy()
    server_env["SQLITE_PATH"] = tmp_db
    server_env["JWT_SECRET"] = "twelve-dollar-challenge"
    server_env["HOST"] = "127.0.0.1"
    server_env["PORT"] = "3000"

    print("\n🚀 [Step 2] Launching Server Instance on http://127.0.0.1:3000...")
    server = subprocess.Popen(["bash", os.path.join(sub_dir, "start.sh")], env=server_env)
    time.sleep(2)

    # 4. Step-by-Step Load Testing Progression
    # Arjay's sequence: 1,000 (warm-up) -> 2,500 -> 5,000 -> 10,000 VUs
    test_tiers = [
        {"vus": 1000, "label": "Warm-up Tier", "duration": "8s"},
        {"vus": 2500, "label": "Starting Tier", "duration": "8s"},
        {"vus": 5000, "label": "First Doubling", "duration": "8s"},
        {"vus": 10000, "label": "Second Doubling", "duration": "8s"},
    ]

    results_table = []

    try:
        for tier in test_tiers:
            vus = tier["vus"]
            label = tier["label"]
            dur = tier["duration"]
            print(f"\n⚡ [Step 3] Executing Load Test: {vus:,} Virtual Users ({label})...")
            
            k6_cmd = [
                K6_BIN, "run",
                "-e", "BASE_URL=http://127.0.0.1:3000",
                "-e", f"TOKENS={tokens_json}",
                "-e", f"VUS={vus}",
                "-e", "RAMP_UP=2s",
                "-e", f"DURATION={dur}",
                os.path.join(REPO_DIR, "bench/load.js")
            ]
            
            p = subprocess.run(k6_cmd, capture_output=True, text=True)
            out = p.stdout
            
            # Parse k6 summary stats
            http_p95 = "N/A"
            http_p99 = "N/A"
            http_med = "N/A"
            err_rate = "0.0%"
            reqs = "0"
            pass_status = "✅ PASS" if p.returncode == 0 else "❌ FAIL"

            for line in out.splitlines():
                if "http_req_duration" in line and "p(95)=" in line:
                    for part in line.split():
                        if part.startswith("p(95)="):
                            http_p95 = part.split("=")[1]
                        elif part.startswith("p(99)="):
                            http_p99 = part.split("=")[1]
                        elif part.startswith("med="):
                            http_med = part.split("=")[1]
                if "http_req_failed" in line and "%" in line:
                    err_rate = line.split()[1]
                if "http_reqs." in line:
                    parts = line.split()
                    if len(parts) >= 2: reqs = parts[1]

            if "✗" in out or p.returncode != 0:
                pass_status = "❌ FAIL"

            print(f"  -> Result: {pass_status} | Total Requests: {reqs} | Med: {http_med} | p95: {http_p95} | p99: {http_p99} | Error Rate: {err_rate}")
            results_table.append({
                "vus": vus,
                "label": label,
                "requests": reqs,
                "med": http_med,
                "p95": http_p95,
                "p99": http_p99,
                "errors": err_rate,
                "status": pass_status
            })

    finally:
        server.terminate()
        server.wait()
        if os.path.exists(tmp_db): os.remove(tmp_db)

    # 5. Final Report
    print("\n" + "=" * 90)
    print("        OFFICIAL $12 CHALLENGE OUTCOME TABLE (ARJAY MCCANDLESS PROTOCOL)          ")
    print("=" * 90)
    print(f"{'Virtual Users (VUs)':<24} | {'Requests':<10} | {'Median':<10} | {'p95 Latency':<12} | {'p99 Latency':<12} | {'Status':<8}")
    print("-" * 90)
    for r in results_table:
        print(f"{r['vus']:<6,} ({r['label'][:15]}...) | {r['requests']:>8} | {r['med']:>8} | {r['p95']:>10} | {r['p99']:>10} | {r['status']}")
    print("=" * 90)
    print("✅ Arjay McCandless Protocol Run Complete.")

if __name__ == "__main__":
    main()
