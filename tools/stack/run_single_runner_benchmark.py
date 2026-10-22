#!/usr/bin/env python3
"""
tools/stack/run_single_runner_benchmark.py
Single-Runner Core-Pinned Enterprise Business Stack Benchmark Harness.

Implements Option B (CPU Core Pinning & Docker veth):
- Evaluates Candidate OS (FerroOS vs Ubuntu vs Alpine)
- Fast sub-second hydration of pre-baked zstd database
- Hardware CPU isolation via cpuset-cpus / taskset
- Background kernel observability scraper (nr_dirty, writeback, PSI stalls)
- Grafana k6 distributed user simulation (Zipfian product access, orders)
"""

import os
import sys
import time
import json
import shutil
import subprocess
import argparse

STACK_DIR = os.path.abspath(os.path.dirname(__file__))
BASE_DIR = os.path.abspath(os.path.join(STACK_DIR, "..", ".."))
DATASET_ZST = os.path.join(BASE_DIR, "tools", "datasets", "enterprise_seed.db.zst")
ACTIVE_DIR = os.path.join(STACK_DIR, "active_data")
ACTIVE_DB = os.path.join(ACTIVE_DIR, "enterprise_seed.db")
K6_SCRIPT = os.path.join(STACK_DIR, "enterprise_k6_load.js")
K6_BIN = os.path.join(BASE_DIR, "tools", "k6")
SCRAPER_SCRIPT = os.path.join(BASE_DIR, "tools", "observability", "kernel_telemetry_scraper.py")
TELEMETRY_CSV = os.path.join(BASE_DIR, "tools", "observability", "active_run_telemetry.csv")

def hydrate_database():
    print("\n📦 [1/5] Hydrating Pre-Baked Enterprise Database via Zstandard...")
    if not os.path.exists(DATASET_ZST):
        print(f"⚠️ {DATASET_ZST} not found! Generating dataset now...")
        subprocess.check_call(["python3", os.path.join(BASE_DIR, "tools", "datasets", "generate_enterprise_dataset.py")])
        
    os.makedirs(ACTIVE_DIR, exist_ok=True)
    for f in [ACTIVE_DB, f"{ACTIVE_DB}-wal", f"{ACTIVE_DB}-shm"]:
        if os.path.exists(f):
            try: os.remove(f)
            except Exception: pass

    t0 = time.perf_counter()
    subprocess.check_call(["zstd", "-d", "-q", "-f", DATASET_ZST, "-o", ACTIVE_DB])
    os.chmod(ACTIVE_DIR, 0o777)
    os.chmod(ACTIVE_DB, 0o666)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    size_mb = os.path.getsize(ACTIVE_DB) / (1024 * 1024)
    print(f"✅ Hydrated {size_mb:.2f} MB database in {elapsed_ms:.1f} ms!")

def determine_core_allocation():
    cpu_count = os.cpu_count() or 2
    if cpu_count >= 4:
        client_cpus = "0,1"
        server_cpus = "2,3"
    elif cpu_count >= 2:
        client_cpus = "0"
        server_cpus = "1"
    else:
        client_cpus = "0"
        server_cpus = "0"
    print(f"🧠 [2/5] CPU Core Partitioning ({cpu_count} Physical vCPUs Detected):")
    print(f"    • Client Load Generator (k6): CPU Cores [{client_cpus}]")
    print(f"    • Candidate OS & Ingress:     CPU Cores [{server_cpus}]")
    return client_cpus, server_cpus

def run_benchmark(target_image="ferro-os-server:latest", port=10000):
    hydrate_database()
    client_cpus, server_cpus = determine_core_allocation()

    container_name = "candidate_business_node"
    subprocess.run(["docker", "rm", "-f", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print(f"\n🚀 [3/5] Launching Candidate OS Container ({target_image})...")
    # Launch candidate container with:
    # - Strict CPU pinning: --cpuset-cpus
    # - Cloud Droplet memory limit: --memory=2g --memory-swap=2g
    # - AWS EBS gp3 Storage Limits (125 MB/s throughput, 3,000 IOPS)
    # - Mounted active database and enterprise service
    docker_cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        f"--cpuset-cpus={server_cpus}",
        "--memory=2g", "--memory-swap=2g",
        "--device-read-bps", "/dev/vda:131072000",
        "--device-write-bps", "/dev/vda:131072000",
        "--device-read-iops", "/dev/vda:3000",
        "--device-write-iops", "/dev/vda:3000",
        "-p", f"{port}:3000",
        "-v", f"{ACTIVE_DIR}:/data",
        "-v", f"{STACK_DIR}/enterprise_service.py:/app/enterprise_service.py",
        "-e", "SQLITE_PATH=/data/enterprise_seed.db",
        "-e", "PORT=3000",
        "-e", "MAX_IN_FLIGHT=64",
        target_image,
        "python3", "/app/enterprise_service.py"
    ]

    subprocess.check_call(docker_cmd)
    time.sleep(1.5)

    # Verify service readiness
    import urllib.request
    ready = False
    for _ in range(10):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1) as resp:
                if resp.status == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(0.5)

    if not ready:
        print("❌ Container failed health check probe! Checking logs:")
        subprocess.run(["docker", "logs", container_name])
        sys.exit(1)
    print("✅ Service Health Check Probe: 200 OK")

    # Start Observability Scraper in background
    print("\n📡 [4/5] Initiating Background Kernel Observability Telemetry Scraper...")
    scraper_proc = subprocess.Popen([
        "python3", SCRAPER_SCRIPT,
        "--output", TELEMETRY_CSV,
        "--interval", "250",
        "--container", container_name
    ])

    time.sleep(0.5)
    summary_json = os.path.join(STACK_DIR, f"k6_summary_{target_image.split(':')[0].replace('/', '_')}.json")
    if os.path.exists(summary_json): os.remove(summary_json)

    try:
        print("\n⚡ [5/5] Executing Grafana k6 Enterprise Sustained 5-Minute Load Test...")
        k6_cmd = [
            K6_BIN, "run",
            "-e", f"BASE_URL=http://127.0.0.1:{port}",
            "--summary-export", summary_json,
            K6_SCRIPT
        ]
        
        t_bench0 = time.perf_counter()
        k6_res = subprocess.run(k6_cmd, capture_output=True, text=True)
        t_bench = time.perf_counter() - t_bench0

        print(k6_res.stdout)
        
        # Parse per-endpoint metrics
        if os.path.exists(summary_json):
            with open(summary_json, "r") as sf:
                summary_data = json.load(sf)
            metrics = summary_data.get("metrics", {})
            
            def get_trend(name):
                t = metrics.get(name, {})
                vals = t.get("values", t)
                return {
                    "avg": vals.get("avg", 0.0),
                    "med": vals.get("med", 0.0),
                    "p90": vals.get("p(90)", 0.0),
                    "p95": vals.get("p(95)", 0.0),
                    "p99": vals.get("p(99)", vals.get("p(95)", 0.0)),
                    "count": vals.get("count", t.get("count", 0))
                }

            cache_trend = get_trend("cache_read_duration")
            db_trend = get_trend("db_read_duration")
            checkout_trend = get_trend("checkout_write_duration")
            
            http_reqs_metric = metrics.get("http_reqs", {})
            total_reqs = http_reqs_metric.get("count", http_reqs_metric.get("values", {}).get("count", 0))
            
            failed_metric = metrics.get("http_req_failed", {})
            fail_rate = (failed_metric.get("value", failed_metric.get("values", {}).get("rate", 0.0))) * 100

            print("\n" + "=" * 90)
            print(f"      ENTERPRISE SUSTAINED BENCHMARK: PER-ENDPOINT LATENCY BREAKDOWN ({target_image})")
            print("=" * 90)
            print(f"{'Endpoint / Workload':<28} | {'Requests':<10} | {'Median (p50)':<14} | {'p95 Latency':<14} | {'p99 Latency':<14}")
            print("-" * 90)
            print(f"{'1. Cache Read (/feed)':<28} | {cache_trend['count']:<10} | {cache_trend['med']:>10.2f} ms | {cache_trend['p95']:>10.2f} ms | {cache_trend['p99']:>10.2f} ms")
            print(f"{'2. DB Read (/products/:id)':<28} | {db_trend['count']:<10} | {db_trend['med']:>10.2f} ms | {db_trend['p95']:>10.2f} ms | {db_trend['p99']:>10.2f} ms")
            print(f"{'3. Checkout Write (/orders)':<28} | {checkout_trend['count']:<10} | {checkout_trend['med']:>10.2f} ms | {checkout_trend['p95']:>10.2f} ms | {checkout_trend['p99']:>10.2f} ms")
            print("-" * 90)
            print(f"Total Requests: {total_reqs:,} | Duration: {t_bench:.1f}s | Throughput: {total_reqs/t_bench:.1f} req/s | Error Rate: {fail_rate:.2f}%")
            print("=" * 90)

    finally:
        # Stop scraper
        scraper_proc.terminate()
        scraper_proc.wait()
        # Analyze collected telemetry
        subprocess.run(["python3", SCRAPER_SCRIPT, "--output", TELEMETRY_CSV, "--analyze"])
        # Cleanup
        subprocess.run(["docker", "rm", "-f", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(ACTIVE_DB):
            try: os.remove(ACTIVE_DB)
            except Exception: pass

    print("\n🏁 Single-Runner Enterprise Benchmark Execution Complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Single-Runner Enterprise Benchmark")
    parser.add_argument("--image", default="ferro-os-server:latest", help="Target container image")
    parser.add_argument("--port", type=int, default=10000, help="Port to expose")
    args = parser.parse_args()

    run_benchmark(args.image, args.port)
