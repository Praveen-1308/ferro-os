#!/usr/bin/env python3
"""
tools/run_5os_operational_crises_matrix.py
Runs the Fortune 500 Operational Crises empirical suite (Scenarios 028 to 032) across all 5 operating systems:
1. FerroOS Server v2.0 (Pure-Rust userland + libferro_io + mimalloc)
2. Ubuntu 24.04 LTS
3. Alpine Linux 3.20
4. Rocky Linux 9 (RHEL 9)
5. Debian 12 Bookworm

All tests executed with zero synthetic mocks inside identical cgroups (2 vCPUs, 6 GB RAM).
"""

import os
import sys
import json
import time
import subprocess

TARGETS = [
    {
        "id": "ferro-os-server",
        "name": "FerroOS Server v2.0",
        "image": "ferro-os-server:latest",
    },
    {
        "id": "ubuntu-24-04",
        "name": "Ubuntu 24.04 LTS",
        "image": "bench-ubuntu:latest",
    },
    {
        "id": "alpine-3-20",
        "name": "Alpine Linux 3.20",
        "image": "bench-alpine:latest",
    },
    {
        "id": "rocky-linux-9",
        "name": "Rocky Linux 9 (RHEL 9)",
        "image": "bench-rocky:latest",
    },
    {
        "id": "debian-12",
        "name": "Debian 12 Bookworm",
        "image": "bench-debian:latest",
    },
]

def run_suite_for_target(target):
    print("\n" + "=" * 80)
    print(f" EVALUATING OPERATIONAL CRISES: {target['name']} ({target['image']})")
    print("=" * 80)

    cmd = [
        "docker", "run", "--rm",
        "--cpus=2.0",
        "--memory=6g",
        "--security-opt", "seccomp=unconfined",
        "-v", f"{os.getcwd()}:/work",
        "-w", "/work",
        target["image"],
        "python3", "tools/enterprise_scenarios/run_operational_crises_suite.py"
    ]

    t0 = time.perf_counter()
    res = subprocess.run(cmd, capture_output=True, text=True)
    duration = time.perf_counter() - t0

    if res.returncode != 0:
        print(f"[-] Execution failed (code {res.returncode}):")
        print(res.stderr[:500])
        return {"error": f"Failed (code {res.returncode})", "stderr": res.stderr}

    print(f"[+] Execution completed in {duration:.2f} s")
    
    # Read output json
    result_path = "reports/enterprise_scenarios/operational_crises_results.json"
    if os.path.exists(result_path):
        with open(result_path, "r") as f:
            data = json.load(f)
        return {"duration_s": round(duration, 2), "results": data}
    else:
        return {"duration_s": round(duration, 2), "error": "Missing output JSON"}

def main():
    print("*" * 80)
    print("   UNIVERSAL 5-OS FORTUNE 500 OPERATIONAL CRISES EMPIRICAL MATRIX")
    print("*" * 80)

    master_results = {}
    for target in TARGETS:
        master_results[target["id"]] = {
            "metadata": target,
            "data": run_suite_for_target(target)
        }

    out_file = "tools/reports/operational_crises_5os_empirical_results.json"
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(master_results, f, indent=2)

    print("\n" + "*" * 80)
    print(f" Master Empirical Results written to: {out_file}")
    print("*" * 80)

if __name__ == "__main__":
    main()
