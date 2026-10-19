#!/usr/bin/env python3
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

URL = "http://localhost:8088/health"
TOTAL_REQUESTS = 1000
CONCURRENCY = 20

def send_request(idx):
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(URL, timeout=5) as resp:
            data = resp.read()
            lat = (time.perf_counter() - t0) * 1000.0
            return True, lat
    except Exception as e:
        lat = (time.perf_counter() - t0) * 1000.0
        return False, lat

def main():
    print("======================================================================")
    print("      FERRO-OS PURE RUST HTTP SERVER HIGH-CONCURRENCY BENCHMARK       ")
    print("======================================================================")
    print(f"Target:       {URL}")
    print(f"Requests:     {TOTAL_REQUESTS}")
    print(f"Concurrency:  {CONCURRENCY} parallel threads")
    print("Dispatching load...")

    t_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        results = list(executor.map(send_request, range(TOTAL_REQUESTS)))
    t_end = time.perf_counter()

    elapsed = t_end - t_start
    success = sum(1 for s, _ in results if s)
    latencies = [l for _, l in results]
    latencies.sort()

    throughput = TOTAL_REQUESTS / elapsed
    avg_lat = sum(latencies) / len(latencies)
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]

    print("\n--- Pure Rust Server Performance Results ---")
    print(f"Total Requests:      {TOTAL_REQUESTS}")
    print(f"Successful Requests: {success} ({success/TOTAL_REQUESTS*100:.2f}%)")
    print(f"Total Test Time:     {elapsed:.4f} seconds")
    print(f"Throughput:          {throughput:.2f} requests/sec")
    print(f"Average Latency:     {avg_lat:.2f} ms")
    print(f"Median Latency (p50):{p50:.2f} ms")
    print(f"95th Percentile(p95):{p95:.2f} ms")
    print(f"99th Percentile(p99):{p99:.2f} ms")
    print("======================================================================")

if __name__ == "__main__":
    main()
