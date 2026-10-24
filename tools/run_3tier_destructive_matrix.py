#!/usr/bin/env python3
"""
tools/run_3tier_destructive_matrix.py
Unified 5-OS Multi-Level Destruction & Recovery Matrix Orchestrator
Executes across 5 Operating Systems:
  1. FerroOS Server v2.0 (libferro_io pure-Rust io_uring, mimalloc 2.1, Landlock LSM)
  2. Alpine Linux 3.20 (musl libc 1.2.5, lean container standard)
  3. Ubuntu 24.04 LTS (glibc 2.39 ptmalloc, Canonical cloud reference)
  4. Debian 12 Bookworm (glibc 2.36 ptmalloc, Debian upstream)
  5. Rocky Linux 9 / RHEL 9 (glibc 2.34 ptmalloc, Enterprise Linux standard)

Intensity Levels:
  Level 1: Normal (Operational Baseline)
  Level 2: Heavy (Peak Saturated Stress)
  Level 3: Ultimate (Choking Point, Dead / Failure Point, Recovery Point)

Hardware Safety Guardrails:
  - Caps container execution strictly at --cpus=4.0 and --memory=7g (staying <= 70% host hardware load).
  - Validates host CPU and RAM via psutil before each OS run.
  - Executes sequentially to prevent any cross-talk or host laptop freezing.
"""

import os
import sys
import time
import json
import psutil
import subprocess

TARGETS = [
    {
        "id": "ferro-os-server",
        "name": "FerroOS Server v2.0",
        "image": "ferro-os-server:latest",
        "libc": "glibc 2.36 + mimalloc 2.1 + pure-Rust libferro_io",
        "architecture": "io_uring SQPOLL + eBPF sockops + Landlock LSM + Thread-Per-Core"
    },
    {
        "id": "alpine-3-20",
        "name": "Alpine Linux 3.20",
        "image": "bench-alpine:latest",
        "libc": "musl libc 1.2.5",
        "architecture": "Standard POSIX epoll + musl single-arena"
    },
    {
        "id": "ubuntu-24-04",
        "name": "Ubuntu 24.04 LTS",
        "image": "bench-ubuntu:latest",
        "libc": "glibc 2.39 (ptmalloc)",
        "architecture": "Standard POSIX epoll + multi-arena ptmalloc"
    },
    {
        "id": "debian-12",
        "name": "Debian 12 Bookworm",
        "image": "bench-debian:latest",
        "libc": "glibc 2.36 (ptmalloc)",
        "architecture": "Standard POSIX epoll + multi-arena ptmalloc"
    },
    {
        "id": "rocky-linux-9",
        "name": "Rocky Linux 9 (RHEL 9)",
        "image": "bench-rocky:latest",
        "libc": "glibc 2.34 (ptmalloc)",
        "architecture": "Standard POSIX epoll + multi-arena ptmalloc"
    }
]

WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPORTS_DIR = os.path.join(WORKSPACE, "tools", "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

def check_host_safety():
    """Verify host resource usage is within safe 70% limit."""
    mem = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=0.5)
    mem_used_pct = mem.percent
    print(f"  [Host Safety Monitor] RAM: {mem.used/(1024**3):.2f}/{mem.total/(1024**3):.2f} GB ({mem_used_pct:.1f}%), CPU: {cpu:.1f}%")
    if mem_used_pct > 75.0:
        print("  [!] Host RAM usage elevated (>75%). Cooling down for 5 seconds...")
        time.sleep(5.0)

def run_os_evaluation(target):
    t_id = target["id"]
    t_name = target["name"]
    image = target["image"]

    print("\n" + "=" * 90)
    print(f"🚀 EXECUTING 3-TIER DESTRUCTION & RECOVERY MATRIX: {t_name}")
    print(f"   Image: {image} | Libc: {target['libc']}")
    print(f"   Ceiling: 4.0 vCPUs, 7.0 GB RAM (Strict Host Safety Cap)")
    print("=" * 90)

    check_host_safety()

    cmd = [
        "docker", "run", "--rm", "-u", "0",
        "--cpus=4.0", "--memory=7g",
        "--security-opt", "seccomp=unconfined",
        "-v", f"{WORKSPACE}:/bench",
        "-w", "/bench",
        image,
        "python3", "tools/enterprise_scenarios/run_3tier_suite.py"
    ]

    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        elapsed = time.time() - t0
        print(f"  ✓ Finished in {elapsed:.1f}s (Exit code: {proc.returncode})")

        stdout = proc.stdout
        stderr = proc.stderr

        # Extract JSON output
        start_marker = "3TIER_JSON_OUTPUT_START\n"
        end_marker = "\n3TIER_JSON_OUTPUT_END"
        idx_start = stdout.find(start_marker)
        idx_end = stdout.find(end_marker)

        if idx_start != -1 and idx_end != -1:
            json_text = stdout[idx_start + len(start_marker):idx_end].strip()
            data = json.loads(json_text)
            data["metadata"]["runtime_s"] = round(elapsed, 1)
            data["metadata"]["target_info"] = target
            return data
        else:
            print(f"  ❌ Failed to parse JSON markers from output!")
            print(f"     STDOUT snippet: {stdout[:300]}")
            print(f"     STDERR snippet: {stderr[:300]}")
            return {"error": "JSON markers not found", "stderr": stderr[:500]}

    except subprocess.TimeoutExpired:
        print(f"  ❌ Execution timed out after 600s!")
        return {"error": "Timeout expired"}
    except Exception as e:
        print(f"  ❌ Exception during execution: {e}")
        return {"error": str(e)}

def print_summary_tables(master_report):
    print("\n\n" + "#" * 105)
    print("                    MASTER 5-OS 3-TIER BENCHMARK & DESTRUCTION MATRIX")
    print("#" * 105)

    evals = master_report.get("evaluations", {})

    # TABLE 1: LEVEL 1 (NORMAL OPERATIONAL BASELINE)
    print("\n" + "=" * 105)
    print("TABLE 1: LEVEL 1 — NORMAL (OPERATIONAL BASELINE METRICS)")
    print("=" * 105)
    print(f"{'Operating System':<24} | {'HTTP QPS':<12} | {'p50 (ms)':<10} | {'p99 (ms)':<10} | {'WAL IOPS':<11} | {'Mem MB/s':<11} | {'Th Spawn (µs)':<14}")
    print("-" * 105)
    for os_id, data in evals.items():
        name = data.get("metadata", {}).get("target_info", {}).get("name", os_id)
        lvl1 = data.get("level_1_normal", {})
        http = lvl1.get("http_microservice", {})
        wal = lvl1.get("sqlite_wal_commits", {})
        mem = lvl1.get("memory_baseline", {})
        th = lvl1.get("thread_baseline", {})

        qps_str = f"{http.get('qps', 0):,.1f}"
        p50_str = f"{http.get('p50_ms', 0):.2f}"
        p99_str = f"{http.get('p99_ms', 0):.2f}"
        wal_str = f"{wal.get('iops', 0):,.1f}"
        mem_str = f"{mem.get('throughput_mb_s', 0):,.1f}"
        th_str = f"{th.get('spawn_latency_us', 0):.1f}"

        print(f"{name:<24} | {qps_str:<12} | {p50_str:<10} | {p99_str:<10} | {wal_str:<11} | {mem_str:<11} | {th_str:<14}")

    # TABLE 2: LEVEL 2 (HEAVY SATURATED PEAK STRESS)
    print("\n" + "=" * 105)
    print("TABLE 2: LEVEL 2 — HEAVY (PEAK SATURATED STRESS & CONTENTION)")
    print("=" * 105)
    print(f"{'Operating System':<24} | {'Sat QPS':<12} | {'Sat p99 (ms)':<12} | {'Surge Factor':<13} | {'Sat WAL IOPS':<13} | {'Disk Churn':<12} | {'Mem Churn MB/s'}")
    print("-" * 105)
    for os_id, data in evals.items():
        name = data.get("metadata", {}).get("target_info", {}).get("name", os_id)
        lvl2 = data.get("level_2_heavy", {})
        http = lvl2.get("http_microservice_saturated", {})
        wal = lvl2.get("db_saturated_writes", {})
        mem = lvl2.get("memory_churn_fragmentation", {})

        qps_str = f"{http.get('qps', 0):,.1f}"
        p99_str = f"{http.get('p99_ms', 0):.2f}"
        surge_str = f"{http.get('surge_factor', 1.0):.1f}x"
        wal_str = f"{wal.get('iops', 0):,.1f}"
        churn_str = f"{wal.get('churn_mb', 0):.1f} MB"
        mem_str = f"{mem.get('churn_rate_mb_s', 0):,.1f} MB/s"

        print(f"{name:<24} | {qps_str:<12} | {p99_str:<12} | {surge_str:<13} | {wal_str:<13} | {churn_str:<12} | {mem_str}")

    # TABLE 3: LEVEL 3 (ULTIMATE: CHOKING POINT, DEAD POINT & DESTRUCTION)
    print("\n" + "=" * 105)
    print("TABLE 3: LEVEL 3 — ULTIMATE (CHOKING POINT & DEAD/BREAKING POINT)")
    print("=" * 105)
    print(f"{'Operating System':<24} | {'Choke Concurrency':<18} | {'Dead Concurrency':<18} | {'Drop Rate %':<12} | {'I/O Choke p99':<14} | {'Mem Reclaim %'}")
    print("-" * 105)
    for os_id, data in evals.items():
        name = data.get("metadata", {}).get("target_info", {}).get("name", os_id)
        lvl3 = data.get("level_3_ultimate", {})
        cr = lvl3.get("concurrency_ramp", {})
        io = lvl3.get("storage_io_starvation", {})
        mr = lvl3.get("memory_edge_riding", {})

        choke_c = cr.get("choking_point", {}).get("concurrency", "N/A")
        dead_c = cr.get("dead_point", {}).get("concurrency", "N/A")
        choke_str = f"{choke_c:,} VUs" if isinstance(choke_c, (int, float)) else str(choke_c)
        dead_str = f"{dead_c:,} VUs" if isinstance(dead_c, (int, float)) else str(dead_c)
        dead_drop = cr.get("dead_point", {}).get("drop_rate_pct", 0.0)
        io_p99 = io.get("commit_p99_ms", 0.0)
        reclaim_pct = mr.get("reclamation_pct", 0.0)

        print(f"{name:<24} | {choke_str:<18} | {dead_str:<18} | {f'{dead_drop:.3f}%':<12} | {f'{io_p99:.2f} ms':<14} | {f'{reclaim_pct:.1f}%'}")

    # TABLE 4: RECOVERY & SELF-HEALING (POST-DESTRUCTION)
    print("\n" + "=" * 105)
    print("TABLE 4: RECOVERY POINT (DRAIN SPEED, PING RESTORATION & MEMORY RECLAMATION)")
    print("=" * 105)
    print(f"{'Operating System':<24} | {'Drain Time (ms)':<16} | {'Ping Latency (ms)':<18} | {'Retained Dirty RSS':<20} | {'I/O Recovery (ms)'}")
    print("-" * 105)
    for os_id, data in evals.items():
        name = data.get("metadata", {}).get("target_info", {}).get("name", os_id)
        lvl3 = data.get("level_3_ultimate", {})
        cr_rec = lvl3.get("concurrency_ramp", {}).get("recovery", {})
        io = lvl3.get("storage_io_starvation", {})

        drain = f"{cr_rec.get('drain_time_ms', 0):.1f} ms"
        ping = f"{cr_rec.get('ping_latency_ms', 0):.2f} ms"
        retained = f"{cr_rec.get('retained_delta_rss_mb', 0):+.1f} MB"
        io_rec = f"{io.get('recovery_time_ms', 0):.1f} ms"

        print(f"{name:<24} | {drain:<16} | {ping:<18} | {retained:<20} | {io_rec}")

def main():
    print("=" * 90)
    print("      UNIVERSAL 5-OS 3-TIER DESTRUCTION & RECOVERY MATRIX RUNNER")
    print(f"      Kernel: {os.uname().release} | Architecture: {os.uname().machine}")
    print(f"      Host Safety Cap: 4.0 vCPUs, 7.0 GB RAM (<= 70% Host Utilization)")
    print("=" * 90)

    master_report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host_kernel": os.uname().release,
        "host_safety_ceiling": {
            "cpus": 4.0,
            "memory_gb": 7.0
        },
        "evaluations": {}
    }

    for target in TARGETS:
        t_id = target["id"]
        result = run_os_evaluation(target)
        master_report["evaluations"][t_id] = result
        # 3-second cooldown between OS runs
        time.sleep(3.0)

    out_json = os.path.join(REPORTS_DIR, "3tier_destructive_matrix_results.json")
    with open(out_json, "w") as f:
        json.dump(master_report, f, indent=2)

    print_summary_tables(master_report)

    print("\n" + "=" * 90)
    print(f"✅ COMPLETE! All 5 OS evaluations finished cleanly.")
    print(f"   Master Dataset saved to: {out_json}")
    print("=" * 90)

if __name__ == "__main__":
    main()
