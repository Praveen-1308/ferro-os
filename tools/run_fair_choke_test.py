#!/usr/bin/env python3
"""
tools/run_fair_choke_test.py - Head-to-Head Choke Test: Ubuntu 24.04 vs FerroOS
Finds the exact breaking point ("I cannot") for both operating systems under
strict $12 server hardware constraints:
  - CPU Limit:    1.0 vCPU (--cpus=1.0)
  - Memory Limit: 2.0 GB RAM (--memory=2g --memory-swap=2g, 0 swap)
  - Workload:     Social Feed REST API with SQLite WAL durably committed

Sequential execution ensures 100% fair CPU/RAM allocation without host crosstalk.
"""

import os
import sys
import time
import json
import subprocess
import urllib.request

K6_BIN = os.path.abspath("tools/k6")
LOAD_SCRIPT = os.path.abspath("tools/choke_load.js")
PORT = 9200
BASE_URL = f"http://127.0.0.1:{PORT}"

TIERS = [50, 100, 250, 500, 750, 1000, 1500, 2000, 2500, 3000]

def cleanup_container(name):
    subprocess.run(f"docker rm -f {name} >/dev/null 2>&1", shell=True)

def wait_for_server(url, timeout_sec=15):
    t0 = time.time()
    while time.time() - t0 < timeout_sec:
        try:
            with urllib.request.urlopen(f"{url}/metrics", timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False

def get_container_rss_mb(container_name):
    try:
        out = subprocess.check_output(
            f"docker stats {container_name} --no-stream --format '{{{{.MemUsage}}}}'",
            shell=True
        ).decode().strip()
        # format: 45.2MiB / 2GiB
        mem_str = out.split("/")[0].strip()
        if "GiB" in mem_str:
            return float(mem_str.replace("GiB", "").strip()) * 1024
        elif "MiB" in mem_str:
            return float(mem_str.replace("MiB", "").strip())
        elif "KiB" in mem_str:
            return float(mem_str.replace("KiB", "").strip()) / 1024
        return 0.0
    except Exception:
        return 0.0

def run_tier(vus, duration="6s"):
    k6_cmd = [
        K6_BIN, "run",
        "-e", f"BASE_URL={BASE_URL}",
        "-e", f"VUS={vus}",
        "-e", f"DURATION={duration}",
        LOAD_SCRIPT
    ]
    p = subprocess.run(k6_cmd, capture_output=True, text=True)
    out = p.stdout

    http_med = "N/A"
    http_p95 = "N/A"
    http_p99 = "N/A"
    err_rate = "0.0%"
    reqs = "0"
    pass_status = "PASS" if p.returncode == 0 else "FAIL"

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
            for part in line.split():
                if "%" in part:
                    err_rate = part
                    break
        if "http_reqs." in line:
            for part in line.split():
                if part.isdigit():
                    reqs = part
                    break

    if "✗" in out or p.returncode != 0:
        pass_status = "FAIL"

    return {
        "vus": vus,
        "requests": reqs,
        "med": http_med,
        "p95": http_p95,
        "p99": http_p99,
        "error_rate": err_rate,
        "status": pass_status
    }

def run_choke_test_for_os(os_id, os_name, image_name):
    print("\n" + "=" * 80)
    print(f"🔥 TESTING CANDIDATE: {os_name} ({image_name})")
    print("=" * 80)
    container_name = f"choke-test-{os_id}"
    cleanup_container(container_name)

    # Launch under exact $12 droplet specifications: 1 vCPU, 2 GB RAM, 0 swap
    cmd = (
        f"docker run -d --name {container_name} "
        f"--cpus=1.0 --memory=2g --memory-swap=2g "
        f"-p {PORT}:{PORT} "
        f"-v \"{os.getcwd()}\":/bench "
        f"-w /bench "
        f"{image_name} python3 tools/choke_server.py"
    )
    subprocess.check_call(cmd, shell=True)

    print(f"⏳ Waiting for {os_name} choke server on port {PORT}...")
    if not wait_for_server(BASE_URL):
        print(f"❌ Failed to reach {os_name} server within 15 seconds!")
        cleanup_container(container_name)
        return {"error": "Server failed to start"}

    print(f"✅ {os_name} is online. Beginning progressive choke tiers...")
    results = []
    choked = False
    choke_tier = None
    choke_reason = None

    for vus in TIERS:
        print(f"  👉 Concurrency Tier: {vus} Virtual Users ...", end="", flush=True)
        tier_data = run_tier(vus, duration="6s")
        rss = get_container_rss_mb(container_name)
        tier_data["rss_mb"] = round(rss, 1)

        print(f" [{tier_data['status']}] Reqs: {tier_data['requests']} | Med: {tier_data['med']} | p95: {tier_data['p95']} | Errors: {tier_data['error_rate']} | RSS: {tier_data['rss_mb']} MB")
        results.append(tier_data)

        # Check Choke Condition
        if tier_data["status"] == "FAIL" or "FAIL" in tier_data["status"]:
            choked = True
            choke_tier = vus
            try:
                err_val = float(tier_data["error_rate"].replace("%", "").strip())
            except (ValueError, AttributeError):
                err_val = 0.0
            if err_val > 1.0:
                choke_reason = f"Error rate exceeded 1% ({tier_data['error_rate']})"
            else:
                choke_reason = f"Latency breached threshold (p95: {tier_data['p95']}, p99: {tier_data['p99']})"
            print(f"\n💥 {os_name} CHOKED at {vus} VUs! Reason: {choke_reason}")
            break

    cleanup_container(container_name)
    return {
        "os_id": os_id,
        "os_name": os_name,
        "image": image_name,
        "tiers": results,
        "choked": choked,
        "choke_tier": choke_tier,
        "choke_reason": choke_reason
    }

def main():
    print("*" * 80)
    print("      FERRO-OS VS UBUNTU 24.04: $12 SERVER CHOKE-TO-FAILURE BENCHMARK         ")
    print("*" * 80)
    print("  • Target Hardware Spec: 1.0 vCPU / 2.0 GB RAM Droplet Ceiling")
    print("  • Database Engine:      SQLite (WAL mode + synchronous=NORMAL + 256MB mmap)")
    print("  • Load Generator:       Grafana k6 (High-Intensity Choke Profile)")
    print("  • Choke Condition:      p95 > 500ms, p99 > 1000ms, or Error Rate > 1.0%")
    print("*" * 80)

    # 1. Test Ubuntu 24.04 LTS
    ubuntu_results = run_choke_test_for_os("ubuntu", "Ubuntu 24.04 LTS", "bench-ubuntu:latest")

    # Short cooldown between runs
    time.sleep(2)

    # 2. Test FerroOS Dedicated Server
    ferro_results = run_choke_test_for_os("ferro", "FerroOS Dedicated Server", "ferro-os-server:latest")

    # 3. Export structured summary
    report = {
        "timestamp": time.time(),
        "hardware_profile": "1 vCPU / 2 GB RAM (No Swap)",
        "ubuntu": ubuntu_results,
        "ferro": ferro_results
    }
    os.makedirs("tools/reports", exist_ok=True)
    with open("tools/reports/choke_test_results.json", "w") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 90)
    print("             HEAD-TO-HEAD CHOKE BENCHMARK FINAL OUTCOME TABLE              ")
    print("=" * 90)
    print(f"{'Metric / Characteristic':<30} | {'Ubuntu 24.04 LTS':<25} | {'FerroOS Dedicated':<25}")
    print("-" * 90)
    u_max_vu = [t['vus'] for t in ubuntu_results['tiers'] if t['status'] == 'PASS']
    f_max_vu = [t['vus'] for t in ferro_results['tiers'] if t['status'] == 'PASS']
    u_peak_pass = u_max_vu[-1] if u_max_vu else 0
    f_peak_pass = f_max_vu[-1] if f_max_vu else 0

    u_choke = str(ubuntu_results.get("choke_tier", "None"))
    f_choke = str(ferro_results.get("choke_tier", "None"))
    u_reason = str(ubuntu_results.get("choke_reason", "N/A"))
    f_reason = str(ferro_results.get("choke_reason", "N/A"))

    print(f"{'Max Sustainable VUs (Passing)':<30} | {f'{u_peak_pass} VUs':<25} | {f'{f_peak_pass} VUs':<25}")
    print(f"{'Choke Breaking Point':<30} | {f'{u_choke} VUs':<25} | {f'{f_choke} VUs':<25}")
    print(f"{'Choke Reason':<30} | {u_reason[:25]:<25} | {f_reason[:25]:<25}")
    print("=" * 90)

if __name__ == "__main__":
    main()
