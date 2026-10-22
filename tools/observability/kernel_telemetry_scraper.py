#!/usr/bin/env python3
"""
tools/observability/kernel_telemetry_scraper.py
Kernel & Memory Observability Telemetry Scraper.

Samples every 500 ms:
- /proc/vmstat: nr_dirty, nr_writeback, pgpgin, pgpgout
- /proc/pressure/io: PSI some avg10, full avg10
- /proc/pressure/cpu: PSI some avg10
- /proc/pressure/memory: PSI some avg10, full avg10

Correlates latency spikes during load tests with dirty page writeback and I/O pressure stalls.
"""

import os
import sys
import time
import json
import csv
import signal
import argparse
from typing import Dict, Any

PAGE_SIZE_KB = 4

def parse_vmstat(content: str) -> Dict[str, int]:
    metrics = {}
    for line in content.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            key, val = parts[0], parts[1]
            if key in ("nr_dirty", "nr_writeback", "nr_isolated_anon", "pgpgin", "pgpgout"):
                try: metrics[key] = int(val)
                except ValueError: pass
    return metrics

def parse_psi(content: str) -> Dict[str, float]:
    # Formats:
    # some avg10=0.00 avg60=0.00 avg300=0.00 total=0
    # full avg10=0.00 avg60=0.00 avg300=0.00 total=0
    psi = {"some_avg10": 0.0, "full_avg10": 0.0, "total_us": 0}
    for line in content.splitlines():
        parts = line.strip().split()
        if not parts: continue
        prefix = parts[0]
        for field in parts[1:]:
            if field.startswith("avg10="):
                try:
                    val = float(field.split("=")[1])
                    if prefix == "some": psi["some_avg10"] = val
                    elif prefix == "full": psi["full_avg10"] = val
                except ValueError: pass
            elif field.startswith("total="):
                try:
                    psi["total_us"] = int(field.split("=")[1])
                except ValueError: pass
    return psi

def sample_kernel(docker_container: str = None) -> Dict[str, Any]:
    vmstat_raw = ""
    psi_io_raw = ""
    psi_cpu_raw = ""
    psi_mem_raw = ""

    if docker_container:
        import subprocess
        try:
            out = subprocess.check_output(["docker", "exec", docker_container, "cat", "/proc/vmstat"], stderr=subprocess.DEVNULL).decode()
            vmstat_raw = out
        except Exception: pass
        try:
            out = subprocess.check_output(["docker", "exec", docker_container, "cat", "/proc/pressure/io"], stderr=subprocess.DEVNULL).decode()
            psi_io_raw = out
        except Exception: pass
        try:
            out = subprocess.check_output(["docker", "exec", docker_container, "cat", "/proc/pressure/cpu"], stderr=subprocess.DEVNULL).decode()
            psi_cpu_raw = out
        except Exception: pass
    else:
        # Native host Linux
        if os.path.exists("/proc/vmstat"):
            with open("/proc/vmstat", "r") as f: vmstat_raw = f.read()
        if os.path.exists("/proc/pressure/io"):
            with open("/proc/pressure/io", "r") as f: psi_io_raw = f.read()
        if os.path.exists("/proc/pressure/cpu"):
            with open("/proc/pressure/cpu", "r") as f: psi_cpu_raw = f.read()
        if os.path.exists("/proc/pressure/memory"):
            with open("/proc/pressure/memory", "r") as f: psi_mem_raw = f.read()

    vm = parse_vmstat(vmstat_raw)
    psi_io = parse_psi(psi_io_raw)
    psi_cpu = parse_psi(psi_cpu_raw)
    psi_mem = parse_psi(psi_mem_raw)

    nr_dirty = vm.get("nr_dirty", 0)
    nr_wb = vm.get("nr_writeback", 0)

    return {
        "timestamp": time.time(),
        "nr_dirty_pages": nr_dirty,
        "dirty_memory_mb": round((nr_dirty * PAGE_SIZE_KB) / 1024, 2),
        "nr_writeback_pages": nr_wb,
        "writeback_memory_mb": round((nr_wb * PAGE_SIZE_KB) / 1024, 2),
        "psi_io_some_avg10": psi_io.get("some_avg10", 0.0),
        "psi_io_full_avg10": psi_io.get("full_avg10", 0.0),
        "psi_cpu_some_avg10": psi_cpu.get("some_avg10", 0.0),
        "psi_mem_some_avg10": psi_mem.get("some_avg10", 0.0),
    }

def run_scraper(output_csv: str, interval_ms: int = 500, container: str = None, duration_s: float = None):
    fieldnames = [
        "timestamp", "seconds_elapsed", "nr_dirty_pages", "dirty_memory_mb",
        "nr_writeback_pages", "writeback_memory_mb",
        "psi_io_some_avg10", "psi_io_full_avg10", "psi_cpu_some_avg10", "psi_mem_some_avg10"
    ]
    
    csv_file = open(output_csv, "w", newline="")
    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
    writer.writeheader()

    t_start = time.perf_counter()
    stop_flag = False

    def sig_handler(sig, frame):
        nonlocal stop_flag
        stop_flag = True

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    print(f"📡 [Observability] Started Kernel Telemetry Scraper -> {output_csv} (Interval: {interval_ms}ms)")
    sample_count = 0

    try:
        while not stop_flag:
            now_elapsed = round(time.perf_counter() - t_start, 2)
            if duration_s and now_elapsed >= duration_s:
                break

            data = sample_kernel(docker_container=container)
            data["seconds_elapsed"] = now_elapsed
            writer.writerow(data)
            csv_file.flush()
            sample_count += 1
            time.sleep(interval_ms / 1000.0)
    finally:
        csv_file.close()
        print(f"📡 [Observability] Completed Scraper: {sample_count} samples collected in {round(time.perf_counter() - t_start, 2)}s.")

def analyze_telemetry(csv_path: str):
    if not os.path.exists(csv_path):
        print(f"File not found: {csv_path}")
        return

    with open(csv_path, "r") as f:
        reader = list(csv.DictReader(f))

    if not reader:
        print("No samples in telemetry file.")
        return

    max_dirty_mb = max(float(r["dirty_memory_mb"]) for r in reader)
    max_wb_mb = max(float(r["writeback_memory_mb"]) for r in reader)
    max_psi_io = max(float(r["psi_io_some_avg10"]) for r in reader)
    max_psi_cpu = max(float(r["psi_cpu_some_avg10"]) for r in reader)

    print("\n" + "=" * 80)
    print("      KERNEL OBSERVABILITY & PRESSURE STALL (PSI) AUDIT REPORT        ")
    print("=" * 80)
    print(f"  • Total Samples:           {len(reader)}")
    print(f"  • Peak Dirty Memory:       {max_dirty_mb:.2f} MB")
    print(f"  • Peak Active Writeback:   {max_wb_mb:.2f} MB")
    print(f"  • Max I/O Pressure (PSI):  {max_psi_io:.2f}% stall")
    print(f"  • Max CPU Pressure (PSI):  {max_psi_cpu:.2f}% stall")
    print("-" * 80)

    # Detect stall correlation
    stall_events = [r for r in reader if float(r["psi_io_some_avg10"]) > 0.0 or float(r["dirty_memory_mb"]) > 50.0]
    if stall_events:
        print("⚠️ Detected Hardware / Kernel Contention Events:")
        for ev in stall_events[:5]:
            print(f"  [@ {ev['seconds_elapsed']}s] Dirty: {ev['dirty_memory_mb']} MB | Writeback: {ev['writeback_memory_mb']} MB | PSI I/O: {ev['psi_io_some_avg10']}%")
    else:
        print("🟢 Clean Run: Zero I/O Pressure Stalls or Uncontrolled Page Backlogs detected.")
    print("=" * 80)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kernel Telemetry Scraper")
    parser.add_argument("--output", "-o", default="tools/observability/telemetry.csv", help="Output CSV path")
    parser.add_argument("--interval", "-i", type=int, default=500, help="Sampling interval in ms")
    parser.add_argument("--duration", "-d", type=float, default=None, help="Duration in seconds")
    parser.add_argument("--container", "-c", default=None, help="Docker container name to inspect")
    parser.add_argument("--analyze", "-a", action="store_true", help="Analyze an existing CSV")

    args = parser.parse_args()
    if args.analyze:
        analyze_telemetry(args.output)
    else:
        run_scraper(args.output, args.interval, args.container, args.duration)
