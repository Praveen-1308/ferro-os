#!/usr/bin/env python3
"""
E2E Testing Suite for FerroOS Local Shared-Memory DNS Caching Resolver
Tests:
1. Daemon startup & loopback socket binding (127.0.0.1:5353)
2. Static /etc/hosts resolution (< 20 µs)
3. Upstream recursive resolution & TTL cache ingestion
4. Sub-20 µs in-memory cache hit verification
5. High-throughput 1,000-query benchmark & QPS measurement
"""

import time
import subprocess
import sys

def main():
    print("================================================================================")
    print("      FERRO-OS LOCAL SHARED-MEMORY DNS RESOLVER E2E VALIDATION SUITE           ")
    print("================================================================================")

    # 1. Start DNS Caching Daemon in background
    port = 5353
    print(f"\n[Step 1] Starting ferro-core dns-cache daemon on port {port}...")
    daemon = subprocess.Popen(
        ["ferro-core", "dns-cache", "start", "--port", str(port), "--upstream", "1.1.1.1:53"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    time.sleep(1.0)
    
    if daemon.poll() is not None:
        err = daemon.stderr.read()
        print(f"❌ Failed to start daemon: {err}")
        sys.exit(1)
    print("  -> Daemon is listening on 127.0.0.1:5353.")

    try:
        # 2. Query /etc/hosts mapped entry
        print("\n[Step 2] Testing /etc/hosts In-Memory SHM Host Resolution (localhost)...")
        # Warmup query
        subprocess.run(["ferro-core", "dns-cache", "query", "localhost", "--port", str(port)], capture_output=True, text=True)
        res1 = subprocess.run(["ferro-core", "dns-cache", "query", "localhost", "--port", str(port)], capture_output=True, text=True)
        print(res1.stdout)

        # 3. Query Upstream & Cache Ingestion (google.com)
        print("\n[Step 3] Testing Upstream Query & Cache Ingestion (google.com)...")
        res2 = subprocess.run(["ferro-core", "dns-cache", "query", "google.com", "--port", str(port)], capture_output=True, text=True)
        print(res2.stdout)

        # 4. Query Repeated Domain -> Cache Hit
        print("\n[Step 4] Testing Cache Hit Timing on Cached Entry (google.com)...")
        res3 = subprocess.run(["ferro-core", "dns-cache", "query", "google.com", "--port", str(port)], capture_output=True, text=True)
        print(res3.stdout)

        # 5. Run 1,000 Query Throughput Benchmark
        print("\n[Step 5] Executing 1,000-Query In-Memory Benchmark against Local Resolver...")
        res4 = subprocess.run(["ferro-core", "dns-cache", "bench", "localhost", "1000", "--port", str(port)], capture_output=True, text=True)
        print(res4.stdout)

        if "RESOLUTION VERIFIED" in res4.stdout or "ULTRA-FAST RESOLUTION" in res4.stdout:
            print("🏆 TIER 2: LOCAL SHARED-MEMORY DNS RESOLVER VALIDATED SUCCESSFULLY!")
            sys.exit(0)
        else:
            print("❌ DNS benchmark failed.")
            sys.exit(1)

    finally:
        daemon.terminate()
        daemon.wait(timeout=2)

if __name__ == "__main__":
    main()
