#!/usr/bin/env python3
"""
tools/run_5os_fio_dedicated.py - High-Precision FIO Block I/O Benchmark for 5 Operating Systems
Measures:
  1. Synchronous Random Write with fsync (Persistence latency & sync IOPS)
  2. Asynchronous / Buffered Random Write (Peak page cache & kernel block pipeline IOPS)
"""

import os
import sys
import time
import json
import subprocess

TARGETS = [
    {"id": "ferro-os-server", "name": "FerroOS Server (Real)", "image": "ferro-os-server:latest"},
    {"id": "alpine-3-20", "name": "Alpine Linux 3.20", "image": "bench-alpine:latest"},
    {"id": "ubuntu-24-04", "name": "Ubuntu 24.04 LTS", "image": "bench-ubuntu:latest"},
    {"id": "debian-12", "name": "Debian 12 Bookworm", "image": "bench-debian:latest"},
    {"id": "rocky-linux-9", "name": "Rocky Linux 9 (RHEL 9)", "image": "bench-rocky:latest"}
]

WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPORTS_DIR = os.path.join(WORKSPACE, "tools", "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

def run_fio_test(image, sync_mode=True):
    """
    Run FIO 4KB random write.
    If sync_mode: --fsync=1, --size=4M (1,024 synced writes)
    If not sync_mode: buffered randwrite, --time_based=1, --runtime=10, --size=64M
    """
    if sync_mode:
        fio_cmd = [
            "docker", "run", "--rm", "-u", "0",
            "--cpus=2.0", "--memory=6g",
            "--security-opt", "seccomp=unconfined",
            image,
            "fio",
            "--name=randwrite_sync",
            "--filename=/tmp/bench_fio_sync.tmp",
            "--ioengine=sync",
            "--rw=randwrite",
            "--bs=4k",
            "--size=4M",
            "--numjobs=1",
            "--fsync=1",
            "--time_based=0",
            "--group_reporting",
            "--output-format=json"
        ]
    else:
        fio_cmd = [
            "docker", "run", "--rm", "-u", "0",
            "--cpus=2.0", "--memory=6g",
            "--security-opt", "seccomp=unconfined",
            image,
            "fio",
            "--name=randwrite_buffered",
            "--filename=/tmp/bench_fio_buf.tmp",
            "--ioengine=sync",
            "--rw=randwrite",
            "--bs=4k",
            "--size=64M",
            "--numjobs=1",
            "--runtime=8",
            "--time_based=1",
            "--group_reporting",
            "--output-format=json"
        ]

    try:
        res = subprocess.run(fio_cmd, capture_output=True, text=True, timeout=45)
        if res.returncode != 0:
            return {"iops": 0.0, "bw_mib_s": 0.0, "lat_ms": 0.0, "error": res.stderr[:100]}
        data = json.loads(res.stdout)
        job = data["jobs"][0]["write"]
        iops = job.get("iops", 0.0)
        bw_kib = job.get("bw", 0.0)
        clat = job.get("clat_ns", {})
        p95_ns = clat.get("percentile", {}).get("95.000000", 0)
        p99_ns = clat.get("percentile", {}).get("99.000000", 0)
        mean_lat_us = clat.get("mean", 0) / 1000.0

        return {
            "iops": round(iops, 1),
            "bw_mib_s": round(bw_kib / 1024.0, 2),
            "mean_lat_us": round(mean_lat_us, 2),
            "p95_ms": round(p95_ns / 1_000_000.0, 3),
            "p99_ms": round(p99_ns / 1_000_000.0, 3)
        }
    except Exception as e:
        return {"iops": 0.0, "bw_mib_s": 0.0, "lat_ms": 0.0, "error": str(e)}

def main():
    print("=== RUNNING DEDICATED 5-OS FIO BENCHMARK ===")
    results = {}
    for target in TARGETS:
        t_id = target["id"]
        t_name = target["name"]
        image = target["image"]
        print(f"\n--- Testing FIO on {t_name} [{image}] ---")

        print("  Running Synchronous Fsync Write (4MB, 1024 commits)...")
        sync_res = run_fio_test(image, sync_mode=True)
        print(f"  -> Sync IOPS: {sync_res['iops']} | BW: {sync_res['bw_mib_s']} MiB/s | Mean Lat: {sync_res['mean_lat_us']} µs | p95: {sync_res['p95_ms']} ms")

        print("  Running Peak Buffered Randwrite (4KB, 8 sec)...")
        buf_res = run_fio_test(image, sync_mode=False)
        print(f"  -> Buffered IOPS: {buf_res['iops']} | BW: {buf_res['bw_mib_s']} MiB/s | Mean Lat: {buf_res['mean_lat_us']} µs")

        results[t_id] = {
            "name": t_name,
            "sync_fsync": sync_res,
            "buffered_write": buf_res
        }

    out_file = os.path.join(REPORTS_DIR, "fio_5os_benchmark_results.json")
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved FIO results to {out_file}")

if __name__ == "__main__":
    main()
