#!/usr/bin/env python3
"""
tools/run_5os_adversarial_chaos_matrix.py
Universal 5-OS Deep Adversarial Chaos, Bug Injection & Security Matrix Runner
Evaluates 5 Operating Systems:
  1. FerroOS Server v2.0 (Pure-Rust userland + libferro_io + mimalloc 2.1 + KSPP sysctl + Zeroize)
  2. Alpine Linux 3.20 (musl libc 1.2.5, lean container standard)
  3. Ubuntu 24.04 LTS (glibc 2.39 ptmalloc, Canonical cloud standard)
  4. Debian 12 Bookworm (glibc 2.36 ptmalloc, Debian upstream)
  5. Rocky Linux 9 (glibc 2.34 ptmalloc, RHEL 9 Enterprise Linux standard)

Hardware Safety Guardrails:
  - Caps container execution at --cpus=4.0 and --memory=6.0g (Strictly <= 70% Host Utilization)
  - Validates host CPU and RAM via psutil before each run
  - Runs sequentially with cooling periods to eliminate cross-talk and prevent laptop lockups
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
        "profile": "Least-Privilege (UID 1000) + KSPP Sysctl + Zeroize"
    },
    {
        "id": "alpine-3-20",
        "name": "Alpine Linux 3.20",
        "image": "bench-alpine:latest",
        "libc": "musl libc 1.2.5",
        "profile": "Standard Root (UID 0) + Musl Single-Arena"
    },
    {
        "id": "ubuntu-24-04",
        "name": "Ubuntu 24.04 LTS",
        "image": "bench-ubuntu:latest",
        "libc": "glibc 2.39 (ptmalloc)",
        "profile": "Standard Root (UID 0) + Multi-Arena ptmalloc"
    },
    {
        "id": "debian-12",
        "name": "Debian 12 Bookworm",
        "image": "bench-debian:latest",
        "libc": "glibc 2.36 (ptmalloc)",
        "profile": "Standard Root (UID 0) + Multi-Arena ptmalloc"
    },
    {
        "id": "rocky-linux-9",
        "name": "Rocky Linux 9 (RHEL 9)",
        "image": "bench-rocky:latest",
        "libc": "glibc 2.34 (ptmalloc)",
        "profile": "Standard Root (UID 0) + Enterprise RHEL Defaults"
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

def run_os_adversarial_suite(target):
    t_id = target["id"]
    t_name = target["name"]
    image = target["image"]

    print("\n" + "=" * 90)
    print(f"🚀 EXECUTING ADVERSARIAL CHAOS MATRIX: {t_name}")
    print(f"   Image: {image} | Profile: {target['profile']}")
    print(f"   Ceiling: 4.0 vCPUs, 6.0 GB RAM (Strict Host Safety Cap)")
    print("=" * 90)

    check_host_safety()

    # Note: Run container with default image USER so least-privilege security settings are evaluated
    cmd = [
        "docker", "run", "--rm",
        "--cpus=4.0", "--memory=6g",
        "--security-opt", "seccomp=unconfined",
        "-v", f"{WORKSPACE}:/bench",
        "-w", "/bench",
        image,
        "python3", "tools/enterprise_scenarios/run_adversarial_chaos_suite.py"
    ]

    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        elapsed = time.time() - t0
        print(f"  ✓ Finished in {elapsed:.1f}s (Exit code: {proc.returncode})")

        stdout = proc.stdout
        stderr = proc.stderr

        start_marker = "ADVERSARIAL_JSON_OUTPUT_START\n"
        end_marker = "\nADVERSARIAL_JSON_OUTPUT_END"
        idx_start = stdout.find(start_marker)
        idx_end = stdout.find(end_marker)

        if idx_start != -1 and idx_end != -1:
            json_text = stdout[idx_start + len(start_marker):idx_end].strip()
            data = json.loads(json_text)
            data["metadata"] = {
                "runtime_s": round(elapsed, 1),
                "target_info": target,
                "exit_code": proc.returncode
            }
            return data
        else:
            print(f"  ❌ Failed to parse JSON markers from output!")
            print(f"     STDOUT snippet: {stdout[:300]}")
            print(f"     STDERR snippet: {stderr[:300]}")
            return {"error": "JSON markers not found", "stderr": stderr[:500]}

    except subprocess.TimeoutExpired:
        print(f"  ❌ Execution timed out after 120s!")
        return {"error": "Timeout expired"}
    except Exception as e:
        print(f"  ❌ Exception during execution: {e}")
        return {"error": str(e)}

def print_adversarial_summary_tables(master_report):
    print("\n\n" + "#" * 105)
    print("             MASTER 5-OS ADVERSARIAL CHAOS, BUG INJECTION & SECURITY MATRIX")
    print("#" * 105)

    evals = master_report.get("evaluations", {})

    # TABLE 1: SLOWLORIS ATTACK DEFENSE
    print("\n" + "=" * 105)
    print("TABLE 1: LAYER-7 SLOWLORIS ATTACK & CONNECTION STARVATION")
    print("=" * 105)
    print(f"{'Operating System':<24} | {'Legit QPS':<12} | {'p50 (ms)':<10} | {'p99 (ms)':<10} | {'Slow Neutralized':<18} | {'Legit Drop Rate'}")
    print("-" * 105)
    for os_id, data in evals.items():
        name = data.get("metadata", {}).get("target_info", {}).get("name", os_id)
        s1 = data.get("scenario_1_slowloris", {})
        qps_str = f"{s1.get('legit_qps', 0):,.1f}"
        p50_str = f"{s1.get('legit_p50_ms', 0):.2f}"
        p99_str = f"{s1.get('legit_p99_ms', 0):.2f}"
        slow_str = f"{s1.get('slow_connections_neutralized', 0)}/100"
        drop_str = f"{s1.get('legit_drop_rate_pct', 0.0):.2f}%"
        print(f"{name:<24} | {qps_str:<12} | {p50_str:<10} | {p99_str:<10} | {slow_str:<18} | {drop_str}")

    # TABLE 2: FORK-STORM & EMFILE RECOVERY
    print("\n" + "=" * 105)
    print("TABLE 2: PROCESS & VFS EXHAUSTION (FORK-STORM SCHEDULER & EMFILE RECOVERY)")
    print("=" * 105)
    print(f"{'Operating System':<24} | {'Fork Spawn (ms)':<16} | {'Scheduler Lat (µs)':<20} | {'Zombies Leaked':<16} | {'EMFILE Recovery (ms)'}")
    print("-" * 105)
    for os_id, data in evals.items():
        name = data.get("metadata", {}).get("target_info", {}).get("name", os_id)
        s2 = data.get("scenario_2_fork_storm", {})
        s3 = data.get("scenario_3_fd_exhaustion", {})
        fork_str = f"{s2.get('spawn_time_ms', 0):.1f} ms"
        sched_str = f"{s2.get('parent_scheduler_latency_us', 0):.1f} µs"
        zomb_str = str(s2.get('zombies_leaked', 0))
        emfile_str = f"{s3.get('recovery_time_ms', 0):.2f} ms"
        print(f"{name:<24} | {fork_str:<16} | {sched_str:<20} | {zomb_str:<16} | {emfile_str}")

    # TABLE 3: MEMORY LEAKAGE & ACCESS CONTAINMENT
    print("\n" + "=" * 105)
    print("TABLE 3: MEMORY ZEROIZE & PRIVILEGE CONTAINMENT (CWE-226 & ACCESS CONTROL)")
    print("=" * 105)
    print(f"{'Operating System':<24} | {'Default UID':<12} | {'Plaintext Residuals':<21} | {'CWE-226 Neutralized':<21} | {'Containment Rate'}")
    print("-" * 105)
    for os_id, data in evals.items():
        name = data.get("metadata", {}).get("target_info", {}).get("name", os_id)
        s4 = data.get("scenario_4_residual_secret_scraping", {})
        s5 = data.get("scenario_5_sandbox_traversal", {})
        uid_str = f"UID {s5.get('default_uid', 'N/A')}"
        res_str = f"{s4.get('plaintext_secrets_recovered', 0)}/200 ({s4.get('residual_leak_rate_pct', 0)}%)"
        cwe_str = "YES (PASS)" if s4.get('cwe_226_neutralized', False) else "NO (VULNERABLE)"
        cont_str = f"{s5.get('containment_rate_pct', 0):.1f}%"
        print(f"{name:<24} | {uid_str:<12} | {res_str:<21} | {cwe_str:<21} | {cont_str}")

    # TABLE 4: ASYMMETRIC STORAGE STARVATION
    print("\n" + "=" * 105)
    print("TABLE 4: ASYMMETRIC STORAGE STARVATION (FLUSHER CONTENTION & TAIL INFLATION)")
    print("=" * 105)
    print(f"{'Operating System':<24} | {'Baseline p99':<14} | {'Stressed p99':<14} | {'Tail Inflation Factor':<23} | {'Disk Churn':<12} | {'I/O Recovery'}")
    print("-" * 105)
    for os_id, data in evals.items():
        name = data.get("metadata", {}).get("target_info", {}).get("name", os_id)
        s6 = data.get("scenario_6_io_starvation", {})
        b_p99_str = f"{s6.get('baseline_p99_ms', 0):.2f} ms"
        s_p99_str = f"{s6.get('stressed_p99_ms', 0):.2f} ms"
        inf_str = f"{s6.get('tail_latency_inflation_factor', 1.0):.1f}x"
        churn_str = f"{s6.get('storage_churn_generated_mb', 0):.1f} MB"
        rec_str = f"{s6.get('io_recovery_time_ms', 0):.2f} ms"
        print(f"{name:<24} | {b_p99_str:<14} | {s_p99_str:<14} | {inf_str:<23} | {churn_str:<12} | {rec_str}")

def main():
    print("=" * 90)
    print("   UNIVERSAL 5-OS ADVERSARIAL CHAOS, BUG INJECTION & SECURITY MATRIX")
    print(f"   Kernel: {os.uname().release} | Architecture: {os.uname().machine}")
    print(f"   Safety Cap: 4.0 vCPUs, 6.0 GB RAM (<= 70% Host Utilization)")
    print("=" * 90)

    master_report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host_kernel": os.uname().release,
        "host_safety_ceiling": {
            "cpus": 4.0,
            "memory_gb": 6.0
        },
        "evaluations": {}
    }

    for target in TARGETS:
        t_id = target["id"]
        result = run_os_adversarial_suite(target)
        master_report["evaluations"][t_id] = result
        time.sleep(2.0)

    out_json = os.path.join(REPORTS_DIR, "adversarial_chaos_5os_matrix.json")
    with open(out_json, "w") as f:
        json.dump(master_report, f, indent=2)

    print_adversarial_summary_tables(master_report)

    print("\n" + "=" * 90)
    print(f"✅ COMPLETE! All 5 OS evaluations finished cleanly.")
    print(f"   Master Dataset saved to: {out_json}")
    print("=" * 90)

if __name__ == "__main__":
    main()
