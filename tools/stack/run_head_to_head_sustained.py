#!/usr/bin/env python3
"""
tools/stack/run_head_to_head_sustained.py
5-Minute Sustained Head-to-Head Enterprise Benchmark (FerroOS vs Ubuntu 24.04 LTS).

Features:
- 5-Minute (300s) Sustained Test targeting >50,000 requests per OS
- Per-Endpoint Latency Isolation (Cache Read vs DB Read vs Checkout Write)
- 64 KB Durable Audit Block writes to build Dirty Memory and engage EBS gp3 throttle
- Hardware CPU Pinning (Cores 0,1 for client, Cores 2,3 for target)
- Automated Kernel PSI Telemetry & Time-Series Latency Correlation
"""

import os
import sys
import time
import json
import shutil
import subprocess

STACK_DIR = os.path.abspath(os.path.dirname(__file__))
BASE_DIR = os.path.abspath(os.path.join(STACK_DIR, "..", ".."))
REPORTS_DIR = os.path.join(BASE_DIR, "reports", "enterprise_sustained")
RUNNER_SCRIPT = os.path.join(STACK_DIR, "run_single_runner_benchmark.py")
SCRAPER_SCRIPT = os.path.join(BASE_DIR, "tools", "observability", "kernel_telemetry_scraper.py")

TARGETS = [
    {
        "id": "ferro",
        "name": "FerroOS Server v2.0",
        "image": "ferro-os-server:latest",
        "port": 10000
    },
    {
        "id": "ubuntu",
        "name": "Ubuntu Server 24.04 LTS",
        "image": "bench-ubuntu:latest",
        "port": 10001
    }
]

def main():
    os.makedirs(REPORTS_DIR, exist_ok=True)
    print("=" * 90)
    print("      5-MINUTE SUSTAINED HEAD-TO-HEAD ENTERPRISE BENCHMARK (50,000+ REQS)      ")
    print("=" * 90)
    print("  • Workload:               Zipfian Catalog Browsing, Search & 64KB Audit Orders")
    print("  • Targets:                FerroOS Server v2.0 vs Ubuntu Server 24.04 LTS")
    print("  • Target Hardware Limit:  --cpuset-cpus=2,3 --memory=2g (125MB/s EBS gp3 cap)")
    print("  • Target Requests:        50,000 - 150,000 requests per operating system")
    print("=" * 90)

    results = {}

    for target in TARGETS:
        tid = target["id"]
        tname = target["name"]
        timage = target["image"]
        tport = target["port"]

        print(f"\n🚀 >>> [STARTING 5-MIN SUSTAINED RUN] {tname} ({timage}) ...")
        t0 = time.perf_counter()

        # Run benchmark
        cmd = ["python3", RUNNER_SCRIPT, "--image", timage, "--port", str(tport)]
        p = subprocess.run(cmd, capture_output=True, text=True)
        elapsed = time.perf_counter() - t0
        print(p.stdout)
        if p.stderr:
            print("Errors/Warnings:", p.stderr[:500])

        # Archive Telemetry CSV
        src_telemetry = os.path.join(BASE_DIR, "tools", "observability", "active_run_telemetry.csv")
        dst_telemetry = os.path.join(REPORTS_DIR, f"{tid}_telemetry.csv")
        if os.path.exists(src_telemetry):
            shutil.copy(src_telemetry, dst_telemetry)
            print(f"📁 Archived telemetry: {dst_telemetry}")

        # Archive K6 Summary JSON
        summary_name = f"k6_summary_{timage.split(':')[0].replace('/', '_')}.json"
        src_summary = os.path.join(STACK_DIR, summary_name)
        dst_summary = os.path.join(REPORTS_DIR, f"{tid}_k6_summary.json")
        if os.path.exists(src_summary):
            shutil.copy(src_summary, dst_summary)
            print(f"📁 Archived k6 summary: {dst_summary}")

            with open(dst_summary, "r") as f:
                k6_data = json.load(f)
            metrics = k6_data.get("metrics", {})

            def extract_stat(m_name):
                m = metrics.get(m_name, {})
                v = m.get("values", m)
                return {
                    "count": v.get("count", m.get("count", 0)),
                    "avg": v.get("avg", 0.0),
                    "med": v.get("med", 0.0),
                    "p95": v.get("p(95)", 0.0),
                    "p99": v.get("p(99)", v.get("p(95)", 0.0))
                }

            results[tid] = {
                "name": tname,
                "elapsed_s": round(elapsed, 1),
                "total_requests": metrics.get("http_reqs", {}).get("count", 0),
                "cache_read": extract_stat("cache_read_duration"),
                "db_read": extract_stat("db_read_duration"),
                "checkout_write": extract_stat("checkout_write_duration"),
                "http_duration": extract_stat("http_req_duration"),
                "fail_rate": metrics.get("http_req_failed", {}).get("value", 0.0) * 100
            }

        # Cool down between runs to let disk buffers settle
        print("⏳ Waiting 10s cooldown for kernel page cache and disk sync...")
        time.sleep(10)

    # Save aggregated head-to-head report JSON
    final_json = os.path.join(REPORTS_DIR, "head_to_head_sustained_report.json")
    with open(final_json, "w") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 100)
    print("                 HEAD-TO-HEAD 5-MINUTE SUSTAINED BENCHMARK SUMMARY                 ")
    print("=" * 100)
    print(f"{'Metric / Latency Percentile':<32} | {'FerroOS Server v2.0':<30} | {'Ubuntu Server 24.04 LTS':<30}")
    print("-" * 100)
    f_res = results.get("ferro", {})
    u_res = results.get("ubuntu", {})

    print(f"{'Total Requests Served':<32} | {f_res.get('total_requests', 0):>20,} reqs | {u_res.get('total_requests', 0):>20,} reqs")
    print(f"{'Average Throughput':<32} | {f_res.get('total_requests', 0)/(f_res.get('elapsed_s', 300) or 1):>20.1f} req/s | {u_res.get('total_requests', 0)/(u_res.get('elapsed_s', 300) or 1):>20.1f} req/s")
    print(f"{'Cache Read Median (p50)':<32} | {f_res.get('cache_read', {}).get('med', 0):>20.2f} ms | {u_res.get('cache_read', {}).get('med', 0):>20.2f} ms")
    print(f"{'Cache Read Tail (p95)':<32} | {f_res.get('cache_read', {}).get('p95', 0):>20.2f} ms | {u_res.get('cache_read', {}).get('p95', 0):>20.2f} ms")
    print(f"{'DB Read Median (p50)':<32} | {f_res.get('db_read', {}).get('med', 0):>20.2f} ms | {u_res.get('db_read', {}).get('med', 0):>20.2f} ms")
    print(f"{'DB Read Tail (p95)':<32} | {f_res.get('db_read', {}).get('p95', 0):>20.2f} ms | {u_res.get('db_read', {}).get('p95', 0):>20.2f} ms")
    print(f"{'Checkout Write Median (p50)':<32} | {f_res.get('checkout_write', {}).get('med', 0):>20.2f} ms | {u_res.get('checkout_write', {}).get('med', 0):>20.2f} ms")
    print(f"{'Checkout Write Tail (p95)':<32} | {f_res.get('checkout_write', {}).get('p95', 0):>20.2f} ms | {u_res.get('checkout_write', {}).get('p95', 0):>20.2f} ms")
    print(f"{'Checkout Write Tail (p99)':<32} | {f_res.get('checkout_write', {}).get('p99', 0):>20.2f} ms | {u_res.get('checkout_write', {}).get('p99', 0):>20.2f} ms")
    print(f"{'Error / Timeout Rate':<32} | {f_res.get('fail_rate', 0):>19.2f}% | {u_res.get('fail_rate', 0):>19.2f}%")
    print("=" * 100)
    print(f"✅ Head-to-Head Report Generated: {final_json}")

if __name__ == "__main__":
    main()
