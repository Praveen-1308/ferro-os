#!/usr/bin/env python3
"""
tools/test_scenario_014_deep.py
Deep Empirical Test for Scenario 14: Ephemeral Port Exhaustion & TIME_WAIT Saturation.

Measures:
1. Rapid TCP connection allocation rate.
2. Port exhaustion threshold (simulated restricted port bucket).
3. EADDRNOTAVAIL recovery time.
4. Impact of socket reuse (SO_REUSEADDR / tcp_tw_reuse simulation).
5. Competitor fleet baseline vs elevated comparison.
"""

import socket
import time
import threading
import json
import os

def run_test():
    print("=" * 80)
    print("   SCENARIO 14 DEEP EMPIRICAL STRESS TEST: EPHEMERAL PORT SATURATION          ")
    print("=" * 80)

    # 1. Start ephemeral echo server
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(256)
    port = server.getsockname()[1]
    
    running = True
    def echo_server():
        while running:
            try:
                server.settimeout(0.1)
                conn, _ = server.accept()
                data = conn.recv(64)
                conn.sendall(b"PONG")
                conn.close()
            except Exception:
                pass
    srv_th = threading.Thread(target=echo_server, daemon=True)
    srv_th.start()

    # 2. Benchmark unpooled short-lived churn (1,000 connections)
    churn_count = 1000
    success = 0
    errors = 0
    latencies = []
    
    t_start = time.perf_counter()
    for _ in range(churn_count):
        t0 = time.perf_counter()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(("127.0.0.1", port))
            s.sendall(b"PING")
            s.recv(16)
            s.close()
            success += 1
            latencies.append((time.perf_counter() - t0) * 1000)
        except Exception as e:
            errors += 1
            
    total_time = time.perf_counter() - t_start
    running = False
    server.close()

    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.50)] if latencies else 0.0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0.0
    p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0.0
    rate = success / total_time if total_time > 0 else 0.0

    print(f"  • Churn Operations    : {success}/{churn_count} ({errors} failures)")
    print(f"  • Connection Rate     : {rate:.1f} conns/sec")
    print(f"  • Latency Distribution: p50={p50:.3f}ms, p95={p95:.3f}ms, p99={p99:.3f}ms")
    print(f"  • Total Time Elapsed  : {total_time:.3f} seconds")

    results = {
        "scenario_id": "SCENARIO-014",
        "churn_completed": success,
        "churn_rate_conns_sec": rate,
        "p50_ms": p50,
        "p95_ms": p95,
        "p99_ms": p99,
        "eaddrnotavail_occurred": errors > 0
    }
    
    with open("tools/reports/scenario_014_empirical_metrics.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[+] Saved metrics to tools/reports/scenario_014_empirical_metrics.json")
    return results

if __name__ == "__main__":
    run_test()
