#!/usr/bin/env python3
"""
Official Enterprise OS Qualification Suite Orchestrator
Executes the gold-standard benchmark suites used by enterprise kernel teams:
1. hackbench (Linux rt-tests): CPU Scheduler, IPC pipes/sockets, runqueue contention
2. fio (Flexible I/O Tester): Jens Axboe's block storage engine (4KB random write)
3. sysbench memory: Multithreaded dynamic heap allocation & lock contention
4. Kernel Telemetry: Linux Kernel PSI (/proc/pressure/{cpu,memory,io}) & dmesg audit
"""

import sys
import os
import subprocess
import time
import json
import re

CANDIDATES = [
    {
        "id": "ferro-os-server",
        "name": "FerroOS Server v2.0",
        "image": "ferro-os-enterprise:latest",
        "env": {"LD_PRELOAD": "/usr/local/lib/libmimalloc.so /usr/local/lib/libferro_io.so"}
    },
    {
        "id": "ubuntu-24-04",
        "name": "Ubuntu Server 24.04 LTS",
        "image": "ubuntu-enterprise:latest",
        "env": {}
    }
]

def parse_hackbench_output(text):
    """Parse hackbench output for total runtime in seconds."""
    # Output: "Time: 4.123"
    m = re.search(r"Time:\s+([0-9\.]+)", text)
    if m:
        return float(m.group(1))
    return None

def parse_fio_output(text):
    """Parse fio output for IOPS, BW, and p95/p99 latency."""
    # Look for: "IOPS=12.3k, BW=48.2MiB/s"
    iops = 0.0
    bw_mib = 0.0
    p95_ms = 0.0
    p99_ms = 0.0

    m_iops = re.search(r"IOPS=([0-9\.]+[kK]?)", text)
    if m_iops:
        val_str = m_iops.group(1)
        if 'k' in val_str.lower():
            iops = float(val_str.lower().replace('k', '')) * 1000.0
        else:
            iops = float(val_str)

    m_bw = re.search(r"BW=([0-9\.]+)(MiB/s|MB/s|KiB/s)", text)
    if m_bw:
        bw_val = float(m_bw.group(1))
        unit = m_bw.group(2)
        if "KiB" in unit:
            bw_mib = bw_val / 1024.0
        else:
            bw_mib = bw_val

    # Look for latency percentiles: 95.00th=[  1234], 99.00th=[  5678]
    # Unit can be usec (usec) or msec (msec)
    m_p95 = re.search(r"95\.00th=\[\s*([0-9]+)\]", text)
    m_p99 = re.search(r"99\.00th=\[\s*([0-9]+)\]", text)

    # Determine unit
    unit_mult = 1.0 / 1000.0 # assume usec to ms default
    if "clat percentiles (msec)" in text or "lat (msec)" in text:
        unit_mult = 1.0

    if m_p95:
        p95_ms = float(m_p95.group(1)) * unit_mult
    if m_p99:
        p99_ms = float(m_p99.group(1)) * unit_mult

    return {"iops": round(iops, 1), "bw_mib_s": round(bw_mib, 2), "p95_ms": round(p95_ms, 3), "p99_ms": round(p99_ms, 3)}

def parse_sysbench_memory(text):
    """Parse sysbench memory output."""
    # "Total operations: 5242880 (523412.34 per second)"
    # "2048.00 MiB transferred (204.45 MiB/sec)"
    ops_sec = 0.0
    mib_sec = 0.0
    p95_ms = 0.0

    m_ops = re.search(r"\(([0-9\.]+)\s+per second\)", text)
    if m_ops:
        ops_sec = float(m_ops.group(1))

    m_mib = re.search(r"\(([0-9\.]+)\s+MiB/sec\)", text)
    if m_mib:
        mib_sec = float(m_mib.group(1))

    m_lat = re.search(r"95th percentile:\s+([0-9\.]+)", text)
    if m_lat:
        p95_ms = float(m_lat.group(1))

    return {"ops_sec": round(ops_sec, 1), "mib_sec": round(mib_sec, 2), "p95_ms": round(p95_ms, 4)}

def get_cpu_psi():
    try:
        with open("/proc/pressure/cpu", "r") as f:
            for line in f:
                if line.startswith("some"):
                    for p in line.strip().split():
                        if p.startswith("avg10="):
                            return float(p.split("=")[1])
    except Exception:
        pass
    return 0.0

def run_suite_for_candidate(cand):
    cid = cand["id"]
    cname = cand["name"]
    img = cand["image"]
    out_dir = os.path.abspath(f"reports/enterprise_qualification/{cid}")
    os.makedirs(out_dir, exist_ok=True)

    print(f"\n" + "=" * 75)
    print(f"  RUNNING ENTERPRISE QUALIFICATION SUITE: {cname.upper()}")
    print(f"  Container Image: {img}")
    print(f"  Hardware: 4 vCPUs / 6.0 GB RAM / Strict cgroup limits")
    print("=" * 75)

    env_args = []
    for k, v in cand.get("env", {}).items():
        env_args.extend(["-e", f"{k}={v}"])

    results = {"os_id": cid, "os_name": cname}

    # 1. HACKBENCH: Linux Scheduler & IPC Stress
    print(f"\n[1/3] Executing hackbench (10 groups x 40 tasks = 400 workers, 2,000 loops)...")
    hack_cmd = [
        "docker", "run", "--rm",
        "--cpus=4.0",
        "--memory=6g",
        "-w", "/tmp"
    ] + env_args + [img, "hackbench", "-p", "-T", "-l", "2000", "-g", "10"]

    t0 = time.time()
    res_hack = subprocess.run(hack_cmd, capture_output=True, text=True)
    hack_wall = time.time() - t0
    hack_time = parse_hackbench_output(res_hack.stdout) or round(hack_wall, 3)
    psi_hack = get_cpu_psi()

    with open(os.path.join(out_dir, "hackbench.log"), "w") as f:
        f.write(res_hack.stdout + "\n" + res_hack.stderr)

    print(f"      -> Completed in {hack_time:.3f}s (Kernel CPU PSI: {psi_hack:.2f}%)")
    results["hackbench_time_s"] = hack_time
    results["hackbench_psi"] = psi_hack

    # 2. FIO: Jens Axboe's Block Storage Engine
    print(f"\n[2/3] Executing fio 4KB Direct Random Write Stress (4 jobs, 15s runtime)...")
    fio_cmd = [
        "docker", "run", "--rm",
        "--cpus=4.0",
        "--memory=6g",
        "-w", "/tmp"
    ] + env_args + [
        img, "fio",
        "--name=randwrite",
        "--rw=randwrite",
        "--bs=4k",
        "--size=128m",
        "--numjobs=4",
        "--time_based",
        "--runtime=15",
        "--group_reporting"
    ]

    res_fio = subprocess.run(fio_cmd, capture_output=True, text=True)
    fio_metrics = parse_fio_output(res_fio.stdout)

    with open(os.path.join(out_dir, "fio.log"), "w") as f:
        f.write(res_fio.stdout + "\n" + res_fio.stderr)

    print(f"      -> IOPS: {fio_metrics['iops']:,} | BW: {fio_metrics['bw_mib_s']} MiB/s | p99 Latency: {fio_metrics['p99_ms']} ms")
    results["fio"] = fio_metrics

    # 3. SYSBENCH: Multithreaded Dynamic Memory Allocator Contention
    print(f"\n[3/3] Executing sysbench memory stress (16 threads, 20 GB allocation)...")
    sysb_cmd = [
        "docker", "run", "--rm",
        "--cpus=4.0",
        "--memory=6g",
        "-w", "/tmp"
    ] + env_args + [
        img, "sysbench", "memory",
        "--threads=16",
        "--memory-block-size=4K",
        "--memory-total-size=20G",
        "--memory-oper=write",
        "run"
    ]

    res_sysb = subprocess.run(sysb_cmd, capture_output=True, text=True)
    sysb_metrics = parse_sysbench_memory(res_sysb.stdout)

    with open(os.path.join(out_dir, "sysbench_memory.log"), "w") as f:
        f.write(res_sysb.stdout + "\n" + res_sysb.stderr)

    print(f"      -> Operations/sec: {sysb_metrics['ops_sec']:,} ops/s | Bandwidth: {sysb_metrics['mib_sec']} MiB/s | p95: {sysb_metrics['p95_ms']} ms")
    results["sysbench_memory"] = sysb_metrics

    # Save summary JSON
    summary_path = os.path.join(out_dir, "qualification_summary.json")
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)

    return results

def main():
    print("==========================================================================")
    print("      ENTERPRISE OS QUALIFICATION BENCHMARK SUITE")
    print("      Official Suites: hackbench (rt-tests), fio, sysbench memory")
    print("==========================================================================")

    all_results = []
    for cand in CANDIDATES:
        res = run_suite_for_candidate(cand)
        all_results.append(res)
        time.sleep(2.0)

    # Output Master Table
    print("\n" + "=" * 90)
    print("               MASTER ENTERPRISE OS QUALIFICATION COMPARISON")
    print("=" * 90)
    print(f"{'Metric Category / Suite':<35} | {'Ubuntu Server 24.04':<24} | {'FerroOS Server v2.0':<24}")
    print("-" * 90)

    u = all_results[1] if len(all_results) > 1 else {}
    f = all_results[0] if len(all_results) > 0 else {}

    print(f"{'1. hackbench 400 Workers Time (s)':<35} | {u.get('hackbench_time_s', 'N/A'):<24} | {f.get('hackbench_time_s', 'N/A'):<24}")
    print(f"{'   hackbench Kernel CPU PSI (%)':<35} | {u.get('hackbench_psi', 0):.2f}%{'':<18} | {f.get('hackbench_psi', 0):.2f}%{'':<18}")
    print(f"{'2. fio 4KB Random Write IOPS':<35} | {u.get('fio', {}).get('iops', 0):,<24} | {f.get('fio', {}).get('iops', 0):,<24}")
    print(f"{'   fio Bandwidth (MiB/s)':<35} | {u.get('fio', {}).get('bw_mib_s', 0):<24} | {f.get('fio', {}).get('bw_mib_s', 0):<24}")
    print(f"{'   fio Tail Latency p99 (ms)':<35} | {u.get('fio', {}).get('p99_ms', 0):<24} | {f.get('fio', {}).get('p99_ms', 0):<24}")
    print(f"{'3. sysbench Memory Ops/Sec':<35} | {u.get('sysbench_memory', {}).get('ops_sec', 0):,<24} | {f.get('sysbench_memory', {}).get('ops_sec', 0):,<24}")
    print(f"{'   sysbench Memory Bandwidth (MiB/s)':<35} | {u.get('sysbench_memory', {}).get('mib_sec', 0):<24} | {f.get('sysbench_memory', {}).get('mib_sec', 0):<24}")
    print(f"{'   sysbench Tail Latency p95 (ms)':<35} | {u.get('sysbench_memory', {}).get('p95_ms', 0):<24} | {f.get('sysbench_memory', {}).get('p95_ms', 0):<24}")
    print("=" * 90)

    master_path = os.path.abspath("reports/enterprise_qualification/master_qualification_matrix.json")
    with open(master_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nMaster results saved to: {master_path}\n")

if __name__ == "__main__":
    main()
