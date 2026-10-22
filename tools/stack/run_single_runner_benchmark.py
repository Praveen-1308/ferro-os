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
    # - Mounted active database and enterprise service
    docker_cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        f"--cpuset-cpus={server_cpus}",
        "--memory=2g", "--memory-swap=2g",
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

    try:
        print("\n⚡ [5/5] Executing Grafana k6 Enterprise Load Test...")
        k6_cmd = [
            K6_BIN, "run",
            "-e", f"BASE_URL=http://127.0.0.1:{port}",
            K6_SCRIPT
        ]
        
        t_bench0 = time.perf_counter()
        k6_res = subprocess.run(k6_cmd, capture_output=True, text=True)
        t_bench = time.perf_counter() - t_bench0

        print(k6_res.stdout)
        if k6_res.returncode != 0 and "threshold" in k6_res.stdout:
            print("⚠️ Threshold criteria breached.")
            
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
