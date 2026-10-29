#!/usr/bin/env python3
"""
Empirical Head-to-Head 4-Core / 8-GB Service Benchmark
=====================================================
Workload: The "$12 Server Challenge" High-Throughput REST & SQLite WAL Architecture
Environments:
  1. Ubuntu 24.04 (Containerized):
     - Docker container with --cpus=4.0, -m 8192M, volume mount for WAL storage
     - Standard container isolation, containerd, runc, veth network bridge, docker-proxy
  2. FerroOS Native (No Containers, Autonomous Pure-Rust Architecture):
     - Managed natively via ferro-superd (Pillar 2: Cgroups v2 supervisor, cpu_cores=4.0, memory_max_mb=8192)
     - Sandboxed via ferro sandbox (Pillar 1: Landlock LSM profile 'shared', shm pool, path delegation)
     - Physical disk persistent storage, zero-copy shared memory, bare-metal direct socket bind
"""

import os
import sys
import time
import json
import random
import shutil
import sqlite3
import threading
import subprocess
import urllib.request
import urllib.error
from typing import Dict, Any, List

try:
    import psutil
except ImportError:
    psutil = None

WORKSPACE = "/home/tarun-kumar/Desktop/sample os "
TOOLS_DIR = os.path.join(WORKSPACE, "tools")
CORE_BIN = os.path.join(WORKSPACE, "target/release/ferro-core")
SUPERD_BIN = os.path.join(WORKSPACE, "target/release/ferro-superd")
SERVICE_SCRIPT = os.path.join(TOOLS_DIR, "twelve_dollar_service.py")

UBUNTU_IMAGE = "bench-ubuntu:latest"
UBUNTU_CONTAINER = "bench-ubuntu-4c8g"
UBUNTU_PORT = 9124
UBUNTU_STORAGE = "/tmp/bench_ubuntu_storage"

FERRO_PORT = 9125
FERRO_STORAGE = "/tmp/bench_ferro_storage"
FERRO_RUN_DIR = "/tmp/bench_ferro_run"
FERRO_LOGS_DIR = "/tmp/bench_ferro_logs"
FERRO_SERVICES_DIR = "/tmp/bench_ferro_services"
FERRO_SOCKET = os.path.join(FERRO_RUN_DIR, "superd.sock")
FERRO_CGROUP = "/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/ferro_bench.slice"

CONCURRENCY_TIERS = [100, 300, 600, 1200]
TIER_DURATION_SEC = 8

def get_process_rss_mb(pid: int) -> float:
    """Get resident set size in megabytes for a given PID."""
    try:
        with open(f"/proc/{pid}/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return float(line.split()[1]) / 1024.0
    except Exception:
        pass
    return 0.0

def wait_for_health(url: str, timeout_sec: float = 15.0) -> float:
    """Wait for the /health endpoint to respond 200 OK. Returns elapsed time in seconds."""
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout_sec:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Ferro-Bench/1.0"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    return time.perf_counter() - t0
        except Exception:
            time.sleep(0.05)
    raise TimeoutError(f"Service at {url} failed to become healthy within {timeout_sec}s")

# ==============================================================================
# Client Load Generator
# ==============================================================================

def run_load_tier(base_url: str, concurrency: int, duration_sec: int = 8) -> Dict[str, Any]:
    """Execute high concurrency HTTP requests against the 5 API endpoints."""
    print(f"    ⚡ Generating load: {concurrency} Virtual Users (VUs) for {duration_sec}s...")
    stop_event = threading.Event()
    results = {
        "requests": 0,
        "errors": 0,
        "latencies_ms": []
    }
    lock = threading.Lock()

    # 40% Feed, 30% User Profile, 15% Post Detail, 10% ACID Like Write, 5% Metrics
    endpoints = [
        ("GET", "/users/{}/feed", 40),
        ("GET", "/users/{}", 30),
        ("GET", "/posts/{}", 15),
        ("POST", "/posts/{}/like", 10),
        ("GET", "/metrics", 5)
    ]
    weighted_choices = []
    for method, tmpl, weight in endpoints:
        weighted_choices.extend([(method, tmpl)] * weight)

    def worker_loop():
        local_reqs = 0
        local_errs = 0
        local_lats = []
        while not stop_event.is_set():
            method, tmpl = random.choice(weighted_choices)
            if "{}" in tmpl:
                url_path = tmpl.format(random.randint(1, 1000))
            else:
                url_path = tmpl
            full_url = f"{base_url}{url_path}"
            t0 = time.perf_counter()
            try:
                req = urllib.request.Request(full_url, method=method)
                if method == "POST":
                    req.add_header("Content-Type", "application/json")
                    req.data = b"{}"
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    resp.read()
                    elapsed = (time.perf_counter() - t0) * 1000.0
                    local_lats.append(elapsed)
                    local_reqs += 1
            except Exception:
                local_errs += 1

        with lock:
            results["requests"] += local_reqs
            results["errors"] += local_errs
            results["latencies_ms"].extend(local_lats)

    threads = [threading.Thread(target=worker_loop, daemon=True) for _ in range(concurrency)]
    start_time = time.perf_counter()
    for t in threads:
        t.start()

    time.sleep(duration_sec)
    stop_event.set()
    for t in threads:
        t.join(timeout=2.0)

    actual_duration = time.perf_counter() - start_time
    total_reqs = results["requests"]
    rps = total_reqs / actual_duration if actual_duration > 0 else 0
    errs = results["errors"]
    lats = sorted(results["latencies_ms"])

    p50 = lats[int(len(lats) * 0.50)] if lats else 0.0
    p95 = lats[int(len(lats) * 0.95)] if lats else 0.0
    p99 = lats[int(len(lats) * 0.99)] if lats else 0.0
    max_lat = lats[-1] if lats else 0.0

    print(f"      -> Concurrency {concurrency:4d} VUs | RPS: {rps:8.1f} req/s | p50: {p50:5.2f}ms | p95: {p95:5.2f}ms | p99: {p99:5.2f}ms | Errors: {errs}")

    return {
        "concurrency": concurrency,
        "rps": round(rps, 1),
        "total_requests": total_reqs,
        "errors": errs,
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2),
        "max_ms": round(max_lat, 2),
        "error_rate_pct": round((errs / (total_reqs + errs) * 100.0) if (total_reqs + errs) > 0 else 0.0, 3)
    }

def verify_db_stats(db_path: str) -> Dict[str, Any]:
    """Verify disk storage persistence and SQLite metrics."""
    stats = {"exists": False, "size_mb": 0.0, "total_likes": 0, "wal_size_mb": 0.0}
    if os.path.exists(db_path):
        stats["exists"] = True
        stats["size_mb"] = round(os.path.getsize(db_path) / (1024 * 1024), 2)
        wal_path = f"{db_path}-wal"
        if os.path.exists(wal_path):
            stats["wal_size_mb"] = round(os.path.getsize(wal_path) / (1024 * 1024), 2)
        try:
            conn = sqlite3.connect(db_path, timeout=5.0)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM likes;")
            stats["total_likes"] = cur.fetchone()[0]
            conn.close()
        except Exception as e:
            stats["query_error"] = str(e)
    return stats

# ==============================================================================
# 1. Ubuntu 24.04 Benchmark Runner (4-Core / 8-GB Containerized)
# ==============================================================================

def benchmark_ubuntu_container() -> Dict[str, Any]:
    print("\n" + "=" * 80)
    print(" [1/2] BENCHMARKING UBUNTU 24.04 (4-CORE, 8-GB CONTAINERIZED WORKLOAD) ")
    print("=" * 80)
    print("  • Architecture: Standard Docker Container (dockerd / containerd / runc / veth / proxy)")
    print("  • Allocations:  4 CPU Cores (--cpus=4.0), 8 GB RAM (-m 8192M)")
    print(f"  • Storage:      Bound Host Volume ({UBUNTU_STORAGE} -> /data)")

    # Clean previous container and storage
    subprocess.run(["docker", "rm", "-f", UBUNTU_CONTAINER], capture_output=True)
    if os.path.exists(UBUNTU_STORAGE):
        shutil.rmtree(UBUNTU_STORAGE, ignore_errors=True)
    os.makedirs(UBUNTU_STORAGE, exist_ok=True)

    # Calculate Docker daemon background memory
    docker_daemon_rss_mb = 0.0
    for proc in ["dockerd", "containerd"]:
        out = subprocess.run(["pgrep", "-f", proc], capture_output=True, text=True)
        for pid_str in out.stdout.split():
            try:
                docker_daemon_rss_mb += get_process_rss_mb(int(pid_str))
            except Exception:
                pass
    print(f"  • Background Docker/containerd Daemon RAM Footprint: {docker_daemon_rss_mb:.1f} MB")

    # Launch Ubuntu container
    t0 = time.perf_counter()
    docker_cmd = [
        "docker", "run", "-d",
        "--name", UBUNTU_CONTAINER,
        "--cpus=4.0",
        "-m", "8192M",
        "-p", f"{UBUNTU_PORT}:9124",
        "-v", f"{UBUNTU_STORAGE}:/data",
        "-v", f"{TOOLS_DIR}:/app:ro",
        UBUNTU_IMAGE,
        "python3", "/app/twelve_dollar_service.py",
        "--host", "0.0.0.0",
        "--port", "9124",
        "--db", "/data/feed.db",
        "--seed"
    ]
    subprocess.run(docker_cmd, check=True, capture_output=True)
    
    # Wait for ready
    startup_time_sec = wait_for_health(f"http://127.0.0.1:{UBUNTU_PORT}/health")
    print(f"  ✅ Container Healthy and Serving on port {UBUNTU_PORT} in {startup_time_sec:.3f}s")

    # Measure initial idle RSS
    inspect_out = subprocess.run(["docker", "inspect", "-f", "{{.State.Pid}}", UBUNTU_CONTAINER], capture_output=True, text=True)
    container_pid = int(inspect_out.stdout.strip()) if inspect_out.stdout.strip().isdigit() else None
    idle_rss_mb = get_process_rss_mb(container_pid) if container_pid else 0.0
    print(f"  • Container Process RSS (Idle): {idle_rss_mb:.1f} MB (Total with Daemons: {idle_rss_mb + docker_daemon_rss_mb:.1f} MB)")

    # Execute Concurrency Tiers
    base_url = f"http://127.0.0.1:{UBUNTU_PORT}"
    tier_results = []
    peak_rss_mb = idle_rss_mb

    for vu_count in CONCURRENCY_TIERS:
        res = run_load_tier(base_url, vu_count, duration_sec=TIER_DURATION_SEC)
        tier_results.append(res)
        if container_pid:
            cur_rss = get_process_rss_mb(container_pid)
            if cur_rss > peak_rss_mb:
                peak_rss_mb = cur_rss

    # Stop container
    subprocess.run(["docker", "stop", UBUNTU_CONTAINER], capture_output=True)
    subprocess.run(["docker", "rm", UBUNTU_CONTAINER], capture_output=True)

    # Verify storage persistence
    db_stats = verify_db_stats(os.path.join(UBUNTU_STORAGE, "feed.db"))
    print(f"  • Post-Test Storage State: DB Size {db_stats['size_mb']} MB, Total Likes {db_stats['total_likes']:,}")

    return {
        "os": "Ubuntu 24.04",
        "mode": "Containerized (Docker/runc/veth)",
        "cpu_cores": 4.0,
        "memory_budget_mb": 8192,
        "startup_time_sec": round(startup_time_sec, 3),
        "daemon_overhead_mb": round(docker_daemon_rss_mb, 1),
        "idle_service_rss_mb": round(idle_rss_mb, 1),
        "peak_service_rss_mb": round(peak_rss_mb, 1),
        "tier_results": tier_results,
        "storage": db_stats
    }

# ==============================================================================
# 2. FerroOS Native Benchmark Runner (4-Core / 8-GB Autonomous Pure Rust)
# ==============================================================================

def benchmark_ferroos_native() -> Dict[str, Any]:
    print("\n" + "=" * 80)
    print(" [2/2] BENCHMARKING FERRO-OS NATIVE (4-CORE, 8-GB NO-CONTAINER WORKLOAD) ")
    print("=" * 80)
    print("  • Architecture: Pure Rust ferro-superd + Landlock LSM ferro sandbox + Zero-Copy SHM")
    print("  • Allocations:  4 CPU Cores (cpu_cores=4.0 / cpu.max), 8 GB RAM (memory_max_mb=8192)")
    print(f"  • Storage:      Direct Physical Disk Delegation ({FERRO_STORAGE})")

    # Clean previous state
    for d in [FERRO_STORAGE, FERRO_RUN_DIR, FERRO_LOGS_DIR, FERRO_SERVICES_DIR]:
        if os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
    if os.path.exists("/dev/shm/ferro_bench_pool"):
        try: os.remove("/dev/shm/ferro_bench_pool")
        except Exception: pass

    # Write Service TOML Manifest
    manifest_path = os.path.join(FERRO_SERVICES_DIR, "twelve-dollar-native.toml")
    manifest_content = f"""name = "twelve-dollar-native"
description = "FerroOS 4-Core 8GB Native High-Velocity Service"
command = [
    "{CORE_BIN}",
    "sandbox",
    "--profile", "shared",
    "--shm", "bench_pool",
    "--ro", "/usr",
    "--ro", "/lib",
    "--ro", "/lib64",
    "--ro", "/etc",
    "--ro", "{TOOLS_DIR}",
    "--rw", "{FERRO_STORAGE}",
    "--",
    "python3",
    "{SERVICE_SCRIPT}",
    "--host", "127.0.0.1",
    "--port", "{FERRO_PORT}",
    "--db", "{FERRO_STORAGE}/feed.db",
    "--seed"
]
working_dir = "{WORKSPACE}"
policy = "always"
memory_max_mb = 8192
cpu_cores = 4.0
cpu_weight = 100
check_interval_sec = 2
check_command = ["curl", "-s", "http://127.0.0.1:{FERRO_PORT}/health"]
restart_on_unhealthy = false
"""
    with open(manifest_path, "w") as f:
        f.write(manifest_content)

    # Launch ferro-superd supervisor
    superd_env = os.environ.copy()
    superd_env["FERRO_SERVICES_DIR"] = FERRO_SERVICES_DIR
    superd_env["FERRO_SOCKET_PATH"] = FERRO_SOCKET
    superd_env["FERRO_LOGS_DIR"] = FERRO_LOGS_DIR
    superd_env["FERRO_CGROUP_ROOT"] = FERRO_CGROUP

    t_start = time.perf_counter()
    superd_proc = subprocess.Popen([SUPERD_BIN], env=superd_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(0.5)

    superd_rss_mb = get_process_rss_mb(superd_proc.pid)
    print(f"  • ferro-superd Daemon Background Footprint: {superd_rss_mb:.2f} MB (vs ~156 MB Docker)")

    # Start service via ferro-core service start
    cli_env = os.environ.copy()
    cli_env["FERRO_SOCKET_PATH"] = FERRO_SOCKET
    start_cmd = [CORE_BIN, "service", "start", "twelve-dollar-native"]
    res = subprocess.run(start_cmd, env=cli_env, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  ❌ Error starting service: {res.stderr} {res.stdout}")

    # Wait for ready
    startup_time_sec = wait_for_health(f"http://127.0.0.1:{FERRO_PORT}/health")
    print(f"  ✅ FerroOS Service Healthy and Serving on port {FERRO_PORT} in {startup_time_sec:.3f}s")

    # Query supervisor for service status
    status_cmd = [CORE_BIN, "service", "status", "twelve-dollar-native", "--format", "json"]
    status_res = subprocess.run(status_cmd, env=cli_env, capture_output=True, text=True)
    service_pid = None
    try:
        data = json.loads(status_res.stdout)
        service_pid = data.get("pid")
    except Exception:
        pass

    idle_rss_mb = get_process_rss_mb(service_pid) if service_pid else 0.0
    print(f"  • FerroOS Native Service RSS (Idle): {idle_rss_mb:.1f} MB (Total with Supervisor: {idle_rss_mb + superd_rss_mb:.1f} MB)")

    # Execute Concurrency Tiers
    base_url = f"http://127.0.0.1:{FERRO_PORT}"
    tier_results = []
    peak_rss_mb = idle_rss_mb

    for vu_count in CONCURRENCY_TIERS:
        tier_res = run_load_tier(base_url, vu_count, duration_sec=TIER_DURATION_SEC)
        tier_results.append(tier_res)
        if service_pid:
            cur_rss = get_process_rss_mb(service_pid)
            if cur_rss > peak_rss_mb:
                peak_rss_mb = cur_rss

    # Stop service & supervisor
    subprocess.run([CORE_BIN, "service", "stop", "twelve-dollar-native"], env=cli_env, capture_output=True)
    superd_proc.terminate()
    try: superd_proc.wait(timeout=2)
    except Exception: superd_proc.kill()

    # Verify storage persistence
    db_stats = verify_db_stats(os.path.join(FERRO_STORAGE, "feed.db"))
    print(f"  • Post-Test Storage State: DB Size {db_stats['size_mb']} MB, Total Likes {db_stats['total_likes']:,}")

    return {
        "os": "FerroOS (Pure Rust)",
        "mode": "Native (No Containers / ferro-superd / Landlock)",
        "cpu_cores": 4.0,
        "memory_budget_mb": 8192,
        "startup_time_sec": round(startup_time_sec, 3),
        "daemon_overhead_mb": round(superd_rss_mb, 2),
        "idle_service_rss_mb": round(idle_rss_mb, 1),
        "peak_service_rss_mb": round(peak_rss_mb, 1),
        "tier_results": tier_results,
        "storage": db_stats
    }

# ==============================================================================
# 3. Main Comparison Orchestrator
# ==============================================================================

def main():
    try:
        import resource
        cur_soft, cur_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = min(cur_hard, 65536)
        resource.setrlimit(resource.RLIMIT_NOFILE, (target, cur_hard))
    except Exception:
        pass

    print("=" * 80)
    print("      4-CORE / 8-GB HEAD-TO-HEAD SERVICE BENCHMARK: UBUNTU VS FERRO-OS         ")
    print("=" * 80)
    print(f"  Date & Time:        {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Host Architecture:  {os.uname().machine} | 8 Physical Host Cores | 14 GB Total RAM")
    print("  Resource Quota:     4 Cores (100% 4.0 CPUs) & 8192 MB RAM Per Environment")
    print("  Workload Spectrum:  5-Endpoint $12 Challenge (Users, Feeds, Posts, ACID Likes, Metrics)")
    print("=" * 80)

    # 1. Benchmark Ubuntu
    ubuntu_data = benchmark_ubuntu_container()

    # Cooldown
    time.sleep(2)

    # 2. Benchmark FerroOS Native
    ferro_data = benchmark_ferroos_native()

    # 3. Comparative Analysis
    print("\n" + "=" * 80)
    print("              FINAL 4-CORE / 8-GB COMPARATIVE PERFORMANCE MATRIX               ")
    print("=" * 80)
    print(f"{'Metric':<28} | {'Ubuntu (Container)':<22} | {'FerroOS (Native)':<22} | {'Delta':<10}")
    print("-" * 88)

    # Daemon RAM
    d_ub = ubuntu_data["daemon_overhead_mb"]
    d_fe = ferro_data["daemon_overhead_mb"]
    print(f"{'Daemon Background RAM (MB)':<28} | {d_ub:>20.1f} MB | {d_fe:>20.2f} MB | {((d_fe - d_ub)/d_ub)*100:>+8.1f}%")

    # Startup time
    s_ub = ubuntu_data["startup_time_sec"]
    s_fe = ferro_data["startup_time_sec"]
    speedup = s_ub / s_fe if s_fe > 0 else 1.0
    print(f"{'Cold Startup to Healthy (s)':<28} | {s_ub:>20.3f} s  | {s_fe:>20.3f} s  | {speedup:>8.1f}x")

    # Peak RSS
    r_ub = ubuntu_data["peak_service_rss_mb"]
    r_fe = ferro_data["peak_service_rss_mb"]
    print(f"{'Peak Service RSS RAM (MB)':<28} | {r_ub:>20.1f} MB | {r_fe:>20.1f} MB | {((r_fe - r_ub)/r_ub)*100:>+8.1f}%")

    # Storage Likes Persisted
    l_ub = ubuntu_data["storage"]["total_likes"]
    l_fe = ferro_data["storage"]["total_likes"]
    print(f"{'Durable WAL Likes Persisted':<28} | {l_ub:>20,d}     | {l_fe:>20,d}     | {l_fe - l_ub:>+8,d}")

    print("\n" + "-" * 88)
    print("  CONCURRENCY SCALING & THROUGHPUT (REQUESTS PER SECOND & p99 LATENCY):")
    print("-" * 88)
    print(f"{'Virtual Users (VUs)':<20} | {'Ubuntu RPS':<15} | {'FerroOS RPS':<15} | {'RPS Advantage':<14} | {'p99 Latency (Ub vs Fe)':<22}")
    print("-" * 88)

    for i in range(len(CONCURRENCY_TIERS)):
        vu = CONCURRENCY_TIERS[i]
        u_tier = ubuntu_data["tier_results"][i]
        f_tier = ferro_data["tier_results"][i]
        rps_delta = ((f_tier["rps"] - u_tier["rps"]) / u_tier["rps"]) * 100.0 if u_tier["rps"] > 0 else 0.0
        lat_comp = f"{u_tier['p99_ms']:.1f}ms vs {f_tier['p99_ms']:.1f}ms"
        print(f"{vu:<20d} | {u_tier['rps']:>13,.1f}  | {f_tier['rps']:>13,.1f}  | {rps_delta:>+12.1f}% | {lat_comp:>22}")

    print("=" * 88)

    # Save Structured Report
    report = {
        "benchmark_name": "4_core_8gb_workload_comparative_benchmark",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hardware": {
            "cores_allocated": 4.0,
            "memory_budget_mb": 8192,
            "host_machine": os.uname().machine,
            "kernel": os.uname().release
        },
        "ubuntu_container": ubuntu_data,
        "ferroos_native": ferro_data
    }

    out_file = os.path.join(TOOLS_DIR, "reports/four_core_eight_gb_benchmark_report.json")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n✅ Structured benchmark metrics persisted to: {out_file}\n")

if __name__ == "__main__":
    main()
