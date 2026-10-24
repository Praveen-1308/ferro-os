import subprocess
import json
import time
import os

cwd = os.getcwd()
targets = [
    ("Ubuntu 24.04", "bench-ubuntu:latest"),
    ("Debian 12", "bench-debian:latest"),
    ("FerroOS Server", "ferro-os-server:latest")
]

results = {}

for name, image in targets:
    print(f"\n==================================================")
    print(f"  RUNNING 12 SCENARIOS ON: {name} ({image})")
    print(f"==================================================")
    cmd = [
        "docker", "run", "--rm",
        "--cpus=2.0", "--memory=6g",
        "-v", f"{cwd}:/bench",
        "-w", "/bench",
        image,
        "python3", "tools/benchmark_12_scenarios.py"
    ]
    t0 = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - t0
    print(f"Completed in {elapsed:.1f}s, Return code: {res.returncode}")
    
    out = res.stdout
    if "FINAL 12-SCENARIO JSON OUTPUT:" in out:
        json_part = out.split("FINAL 12-SCENARIO JSON OUTPUT:")[1].split("=" * 75)[0].strip()
        try:
            data = json.loads(json_part)
            results[name] = data
            print(f"Successfully collected metrics for {name}")
        except Exception as e:
            print(f"JSON parse error for {name}: {e}")
    else:
        print(f"Failed to find JSON marker in output for {name}")
        print("Stdout snippet:\n", out[:500], "\nStderr:\n", res.stderr[:500])

with open("tools/reports/empirical_3os_12scenarios_comparison.json", "w") as f:
    json.dump(results, f, indent=2)

print("\nDone! Saved to tools/reports/empirical_3os_12scenarios_comparison.json")
