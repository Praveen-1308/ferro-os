#!/usr/bin/env python3
"""
Server Edition Market Comparison Benchmark Harness
Executes identical real-world enterprise workloads across:
1. FerroOS Server Edition (Rust Userland + mimalloc + libferro_io)
2. Ubuntu Server 24.04 LTS (Cloud & Enterprise Standard)
3. Debian 12 Bookworm (Enterprise Reliability Standard)
4. Alpine Linux 3.20 (Microservices & Minimal Container Standard)
5. Rocky Linux 9 Minimal (RHEL 9 Compatible Enterprise Standard)
"""

import subprocess
import json
import time
import os
import sys

TARGETS = [
    {
        "name": "FerroOS Server Edition",
        "id": "ferro",
        "image": "ferro-os-server:latest",
        "description": "Rust userland (ferro-core/init) + mimalloc 2.1 + libferro_io"
    },
    {
        "name": "Ubuntu Server 24.04 LTS",
        "id": "ubuntu",
        "image": "bench-ubuntu:latest",
        "description": "Standard GNU/Linux cloud leader (glibc ptmalloc3)"
    },
    {
        "name": "Debian 12 Bookworm",
        "id": "debian",
        "image": "bench-debian:latest",
        "description": "Mission-critical reliability enterprise standard"
    },
    {
        "name": "Alpine Linux 3.20",
        "id": "alpine",
        "image": "bench-alpine:latest",
        "description": "musl-libc ultra-lightweight microservices standard"
    },
    {
        "name": "Rocky Linux 9 Minimal",
        "id": "rocky",
        "image": "bench-rocky:latest",
        "description": "RHEL 9 binary compatible enterprise server standard"
    }
]

HOST_DIR = "/Users/praveenkumar/rust os"
BENCH_SCRIPT = "/bench/tools/realworld_server_benchmark.py"

def get_image_size(image_name):
    try:
        out = subprocess.check_output(f"docker inspect -f '{{{{.Size}}}}' {image_name}", shell=True).decode().strip()
        return round(int(out) / (1024 * 1024), 1)
    except Exception:
        return 0.0

def measure_cold_boot(image_name):
    # Measures time to execute a minimal command inside a cold fresh container
    t0 = time.perf_counter()
    subprocess.check_call(f"docker run --rm {image_name} python3 -c 'exit(0)'", shell=True)
    t1 = time.perf_counter()
    return round((t1 - t0) * 1000, 1)

def run_benchmark_on_target(target):
    print(f"\n>>> [BENCHMARKING] {target['name']} ({target['image']}) ...")
    
    # 1. Cold boot latency
    boot_ms = measure_cold_boot(target["image"])
    print(f"    Cold Spawn Latency: {boot_ms:.1f} ms")
    
    # 2. Image size
    size_mb = get_image_size(target["image"])
    print(f"    Image Footprint:    {size_mb:.1f} MB")
    
    # 3. Real-world performance suite
    cmd = f"docker run --rm -v '{HOST_DIR}:/bench' {target['image']} python3 {BENCH_SCRIPT}"
    raw_out = subprocess.check_output(cmd, shell=True).decode('utf-8')
    
    # Extract JSON block
    json_str = raw_out.split("FINAL BENCHMARK JSON RESULTS:")[1].split("=" * 70)[0].strip()
    data = json.loads(json_str)
    data["cold_boot_ms"] = boot_ms
    data["image_size_mb"] = size_mb
    data["name"] = target["name"]
    data["id"] = target["id"]
    data["description"] = target["description"]
    
    return data

def main():
    print("=" * 75)
    print(" FERRO-OS SERVER EDITION vs. MARKET-LEADING SERVER OPERATING SYSTEMS")
    print("                Real-World Enterprise Workload Benchmark            ")
    print("=" * 75)
    
    all_results = {}
    for target in TARGETS:
        try:
            res = run_benchmark_on_target(target)
            all_results[target["id"]] = res
        except Exception as e:
            print(f"❌ Error benchmarking {target['name']}: {e}")
            
    # Save results to json
    results_path = os.path.join(HOST_DIR, "tools/server_comparison_results.json")
    with open(results_path, "w") as f:
        json.dump(all_results, f, indent=2)
        
    print(f"\nAll results saved to: {results_path}")
    
    # Print formatted comparative table
    print("\n" + "=" * 95)
    print(f"{'METRIC':<36} | {'FERRO-OS':<10} | {'UBUNTU 24':<10} | {'DEBIAN 12':<10} | {'ALPINE 3.20':<11} | {'ROCKY 9':<10}")
    print("=" * 95)
    
    f_res = all_results.get("ferro", {})
    u_res = all_results.get("ubuntu", {})
    d_res = all_results.get("debian", {})
    a_res = all_results.get("alpine", {})
    r_res = all_results.get("rocky", {})
    
    rows = [
        ("SQL Database TPS (higher is better)", "sql_tps", " TPS", True),
        ("SQL 10k Txs Time (lower is better)", "sql_duration_s", " s", False),
        ("SQL p95 Latency (lower is better)", "sql_p95_ms", " ms", False),
        ("SQL Complex Analytics (lower is better)", "sql_analytics_ms", " ms", False),
        ("HTTP Microservice RPS (higher is better)", "http_rps", " RPS", True),
        ("HTTP Mean Latency (lower is better)", "http_mean_lat_ms", " ms", False),
        ("HTTP p99 Tail Latency (lower is better)", "http_p99_ms", " ms", False),
        ("JSON Processing (higher is better)", "json_ops_per_sec", " doc/s", True),
        ("Crypto HMAC/SHA256 (higher is better)", "crypto_throughput_mbs", " MB/s", True),
        ("Local Alloc Throughput (higher is better)", "mem_local_ops_sec", " op/s", True),
        ("Local Alloc Latency (lower is better)", "mem_local_ns_op", " ns", False),
        ("Remote-Free Throughput (higher is better)", "mem_remote_ops_sec", " op/s", True),
        ("Remote-Free Latency (lower is better)", "mem_remote_ns_op", " ns", False),
        ("Cold Spawn Latency (lower is better)", "cold_boot_ms", " ms", False),
        ("Image Size on Disk (lower is better)", "image_size_mb", " MB", False)
    ]
    
    for label, key, unit, higher_better in rows:
        def fmt(val):
            if isinstance(val, (int, float)):
                if val >= 1000000:
                    return f"{val/1000000:.2f}M{unit}"
                elif val >= 1000:
                    return f"{val:.0f}{unit}"
                else:
                    return f"{val:.2f}{unit}"
            return "N/A"
            
        f_v = fmt(f_res.get(key, 0))
        u_v = fmt(u_res.get(key, 0))
        d_v = fmt(d_res.get(key, 0))
        a_v = fmt(a_res.get(key, 0))
        r_v = fmt(r_res.get(key, 0))
        print(f"{label:<36} | {f_v:<10} | {u_v:<10} | {d_v:<10} | {a_v:<11} | {r_v:<10}")
        
    print("=" * 95)

if __name__ == "__main__":
    main()
