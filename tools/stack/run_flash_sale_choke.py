#!/usr/bin/env python3
"""
tools/stack/run_flash_sale_choke.py
High-End 4 vCPU / 6 GB RAM Flash Sale & Multi-Modal Choke-to-Failure Benchmark.

Evaluates FerroOS Server v2.0 vs Ubuntu Server 24.04 LTS:
- Hardware Spec: 4 vCPUs (--cpuset-cpus=2,3,4,5) / 6 GB RAM (--memory=6g)
- Storage Envelope: AWS EBS gp3 (125 MB/s, 3,000 IOPS via cgroups v2)
- Multi-Modal Workload:
  1. Hot Flash Sale Catalog Queries
  2. 256 KB Binary Image Reads & HTTP Streaming
  3. High-Contention Atomic Row-Lock Flash Purchases (All VUs hammering SKU #1)
  4. Content Likes & Reaction Counters
  5. 256 KB Binary Image Uploads to Disk (Intense Page Dirtying & Storage Choke)
- Stampede Scale: Ramping up to 1,000 concurrent Virtual Users
"""

import os
import sys
import time
import json
import shutil
import subprocess

STACK_DIR = os.path.abspath(os.path.dirname(__file__))
BASE_DIR = os.path.abspath(os.path.join(STACK_DIR, "..", ".."))
REPORTS_DIR = os.path.join(BASE_DIR, "reports", "flash_sale_choke")
FLASH_DATA_DIR = os.path.join(STACK_DIR, "flash_data")
K6_BIN = os.path.join(BASE_DIR, "tools", "k6")
K6_SCRIPT = os.path.join(STACK_DIR, "flash_sale_k6.js")
SERVER_SCRIPT = os.path.join(STACK_DIR, "flash_sale_server.py")
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

def clean_flash_data():
    if os.path.exists(FLASH_DATA_DIR):
        shutil.rmtree(FLASH_DATA_DIR, ignore_errors=True)
    os.makedirs(FLASH_DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(FLASH_DATA_DIR, "media_uploads"), exist_ok=True)
    os.chmod(FLASH_DATA_DIR, 0o777)

def run_target(target):
    tid = target["id"]
    tname = target["name"]
    timage = target["image"]
    tport = target["port"]

    print("\n" + "=" * 90)
    print(f"🔥 >>> [CHOKE BENCHMARK RUN] {tname} ({timage}) ...")
    print(f"    • Hardware Allocation: 4 vCPUs (Cores 2,3,4,5) | 6.0 GB RAM | EBS gp3 Limit")
    print("=" * 90)

    clean_flash_data()
    container_name = f"flash_node_{tid}"
    subprocess.run(["docker", "rm", "-f", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    docker_cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "--cpuset-cpus=2,3,4,5",
        "--memory=6g", "--memory-swap=6g",
        "--device-read-bps", "/dev/vda:131072000",
        "--device-write-bps", "/dev/vda:131072000",
        "--device-read-iops", "/dev/vda:3000",
        "--device-write-iops", "/dev/vda:3000",
        "-p", f"{tport}:3000",
        "-v", f"{FLASH_DATA_DIR}:/data",
        "-v", f"{SERVER_SCRIPT}:/app/flash_sale_server.py",
        "-e", "DATA_DIR=/data",
        "-e", "PORT=3000",
        "-e", "MAX_IN_FLIGHT=128",
        timage,
        "python3", "/app/flash_sale_server.py"
    ]

    subprocess.check_call(docker_cmd)
    time.sleep(1.5)

    # Health check
    import urllib.request
    ready = False
    for _ in range(15):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{tport}/healthz", timeout=1) as resp:
                if resp.status == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(0.5)

    if not ready:
        print("❌ Container failed health check probe! Checking logs:")
        subprocess.run(["docker", "logs", container_name])
        sys.exit(1)
    print("✅ Multi-Modal Flash Sale Service Ready: 200 OK")

    # Start Telemetry Scraper
    telemetry_csv = os.path.join(REPORTS_DIR, f"{tid}_telemetry.csv")
    scraper_proc = subprocess.Popen([
        "python3", SCRAPER_SCRIPT,
        "--output", telemetry_csv,
        "--interval", "250",
        "--container", container_name
    ])

    summary_json = os.path.join(REPORTS_DIR, f"{tid}_k6_summary.json")
    if os.path.exists(summary_json): os.remove(summary_json)

    try:
        print("\n⚡ Executing Grafana k6 Flash Sale Stampede (Ramping to 1,000 VUs)...")
        k6_cmd = [
            K6_BIN, "run",
            "-e", f"BASE_URL=http://127.0.0.1:{tport}",
            "--summary-export", summary_json,
            K6_SCRIPT
        ]
        t0 = time.perf_counter()
        k6_res = subprocess.run(k6_cmd, capture_output=True, text=True)
        elapsed = time.perf_counter() - t0
        print(k6_res.stdout)
    finally:
        scraper_proc.terminate()
        scraper_proc.wait()
        subprocess.run(["docker", "rm", "-f", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Telemetry Analysis
    subprocess.run(["python3", SCRAPER_SCRIPT, "--output", telemetry_csv, "--analyze"])

    # Parse k6 results
    with open(summary_json, "r") as f:
        k6_data = json.load(f)
    metrics = k6_data.get("metrics", {})

    def extract_trend(name):
        m = metrics.get(name, {})
        v = m.get("values", m)
        return {
            "avg": v.get("avg", 0.0),
            "med": v.get("med", 0.0),
            "p95": v.get("p(95)", 0.0),
            "p99": v.get("p(99)", v.get("p(95)", 0.0)),
            "count": v.get("count", m.get("count", 0))
        }

    return {
        "name": tname,
        "elapsed_s": round(elapsed, 1),
        "total_requests": metrics.get("http_reqs", {}).get("count", 0),
        "throughput_rps": round(metrics.get("http_reqs", {}).get("rate", 0), 1),
        "catalog_read": extract_trend("catalog_read_duration"),
        "image_stream": extract_trend("image_stream_duration"),
        "content_like": extract_trend("content_like_duration"),
        "flash_checkout": extract_trend("flash_checkout_duration"),
        "image_upload": extract_trend("image_upload_duration"),
        "overall_http": extract_trend("http_req_duration"),
        "fail_rate": round(metrics.get("http_req_failed", {}).get("value", 0.0) * 100, 2),
        "data_received_mb": round(metrics.get("data_received", {}).get("count", 0) / (1024 * 1024), 2),
        "data_sent_mb": round(metrics.get("data_sent", {}).get("count", 0) / (1024 * 1024), 2),
    }

def main():
    os.makedirs(REPORTS_DIR, exist_ok=True)
    all_results = {}

    for target in TARGETS:
        try:
            res = run_target(target)
            all_results[target["id"]] = res
        except Exception as e:
            print(f"⚠️ Error during run of {target['name']}: {e}")
            all_results[target["id"]] = {"name": target["name"], "error": str(e)}
        print("⏳ Cooldown 10s between target runs...")
        time.sleep(10)

    # Save head-to-head report
    final_json = os.path.join(REPORTS_DIR, "flash_sale_head_to_head.json")
    with open(final_json, "w") as f:
        json.dump(all_results, f, indent=2)

    # Print summary table
    print("\n" + "=" * 110)
    print("        HIGH-END 4 vCPU / 6 GB RAM FLASH SALE & MULTI-MODAL CHOKE-TO-FAILURE COMPARISON        ")
    print("=" * 110)
    print(f"{'Operational Metric':<35} | {'FerroOS Server v2.0':<34} | {'Ubuntu Server 24.04 LTS':<34}")
    print("-" * 110)
    f = all_results.get("ferro", {})
    u = all_results.get("ubuntu", {})

    print(f"{'Total Requests Served':<35} | {f.get('total_requests', 0):>25,} reqs | {u.get('total_requests', 0):>25,} reqs")
    print(f"{'Sustained Throughput':<35} | {f.get('throughput_rps', 0):>23.1f} req/s | {u.get('throughput_rps', 0):>23.1f} req/s")
    print(f"{'Total Binary Data Streamed':<35} | {f.get('data_received_mb', 0):>22.1f} MB | {u.get('data_received_mb', 0):>22.1f} MB")
    print(f"{'Total Binary Images Uploaded':<35} | {f.get('image_upload', {}).get('count', 0):>25,} imgs | {u.get('image_upload', {}).get('count', 0):>25,} imgs")
    print(f"{'Flash Checkout Transactions (p50)':<35} | {f.get('flash_checkout', {}).get('med', 0):>22.2f} ms | {u.get('flash_checkout', {}).get('med', 0):>22.2f} ms")
    print(f"{'Flash Checkout Tail (p95)':<35} | {f.get('flash_checkout', {}).get('p95', 0):>22.2f} ms | {u.get('flash_checkout', {}).get('p95', 0):>22.2f} ms")
    print(f"{'Flash Checkout Tail (p99)':<35} | {f.get('flash_checkout', {}).get('p99', 0):>22.2f} ms | {u.get('flash_checkout', {}).get('p99', 0):>22.2f} ms")
    print(f"{'Image Streaming Tail (p99)':<35} | {f.get('image_stream', {}).get('p99', 0):>22.2f} ms | {u.get('image_stream', {}).get('p99', 0):>22.2f} ms")
    print(f"{'Image Upload Tail (p99)':<35} | {f.get('image_upload', {}).get('p99', 0):>22.2f} ms | {u.get('image_upload', {}).get('p99', 0):>22.2f} ms")
    print(f"{'Error / Connection Refused Rate':<35} | {f.get('fail_rate', 0):>24.2f}% | {u.get('fail_rate', 0):>24.2f}%")
    print("=" * 110)
    print(f"✅ Full Report Saved: {final_json}")

if __name__ == "__main__":
    main()
