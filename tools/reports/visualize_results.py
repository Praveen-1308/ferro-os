#!/usr/bin/env python3
"""
FerroOS Phase 3: Visual Results & ASCII Outcome Bar Generator
Outputs neutral, objective outcome bars comparing performance metrics across all 15 operating systems
without rankings or bias.
"""

import os
import sys
import json

BOLD = "\033[1m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

def render_bar(val, max_val, bar_width=35):
    ratio = min(1.0, max(0.0, val / max_val)) if max_val > 0 else 0
    filled = int(round(ratio * bar_width))
    return "█" * filled + " " * (bar_width - filled)

def render_inverted_bar(val, max_val, bar_width=35):
    # For latency: smaller is better
    if val <= 0:
        return " " * bar_width
    score = max_val / max(val, 1.0)
    # normalize
    ratio = min(1.0, score / (max_val / 10.0))
    filled = int(round(ratio * bar_width))
    return "█" * filled + " " * (bar_width - filled)

def main():
    json_path = os.path.join(os.path.dirname(__file__), "master_matrix.json")
    if not os.path.exists(json_path):
        json_path = "tools/reports/master_matrix.json"

    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found. Run tools/devastating_chaos_matrix.py first.")
        sys.exit(1)

    with open(json_path, "r") as f:
        data = json.load(f)

    platforms = data.get("platforms", [])

    print(f"\n{BOLD}{CYAN}================================================================================{RESET}")
    print(f"{BOLD}{CYAN}        15-OPERATING-SYSTEM EMPIRICAL OUTCOME DISTRIBUTION BARS                 {RESET}")
    print(f"{BOLD}{CYAN}================================================================================{RESET}\n")

    # 1. HTTP Throughput Outcome Bars
    print(f"{BOLD}[1. HTTP Microservice Max Throughput (Req/Sec) — Higher is Better]{RESET}\n")
    max_http = max(p["http_rps"] for p in platforms)
    for p in platforms:
        bar = render_bar(p["http_rps"], max_http, 36)
        print(f"  {p['name']:<24} | {bar} ({p['http_rps']:>8,.1f} req/s)")
    print("  " + " " * 24 + " +" + "-" * 38)
    print("  " + " " * 24 + "  0        10k       20k       30k       40k\n")

    # 2. Tail Latency (p99) Outcome Bars
    print(f"{BOLD}[2. HTTP Tail Latency p99 (Milliseconds) — Lower is Better]{RESET}\n")
    max_lat = 2000.0
    for p in platforms:
        # Show normalized bar (capped at 2000ms)
        ratio = min(1.0, p["p99_ms"] / max_lat)
        filled = max(1, int(round(ratio * 36)))
        bar = "█" * filled + " " * (36 - filled)
        print(f"  {p['name']:<24} | {bar} ({p['p99_ms']:>8.2f} ms)")
    print("  " + " " * 24 + " +" + "-" * 38)
    print("  " + " " * 24 + "  0ms      500ms     1000ms    1500ms    2000ms\n")

    # 3. DNS Concurrency QPS
    print(f"{BOLD}[3. Local DNS Query Concurrency (16,000 Concurrent Workers) — Higher is Better]{RESET}\n")
    max_dns = max(p["dns_qps"] for p in platforms)
    for p in platforms:
        bar = render_bar(p["dns_qps"], max_dns, 36)
        print(f"  {p['name']:<24} | {bar} ({p['dns_qps']:>8,.0f} QPS)")
    print("  " + " " * 24 + " +" + "-" * 38)
    print("  " + " " * 24 + "  0        25k       50k       75k       100k\n")

    # 4. Allocator Contention Hammer
    print(f"{BOLD}[4. Multi-Threaded Allocator Contention (128 Threads) — Higher is Better]{RESET}\n")
    max_alloc = 5000.0
    for p in platforms:
        bar = render_bar(p["alloc_ops_sec"], max_alloc, 36)
        print(f"  {p['name']:<24} | {bar} ({p['alloc_ops_sec']:>5,} ops/s)")
    print("  " + " " * 24 + " +" + "-" * 38)
    print("  " + " " * 24 + "  0        1,250     2,500     3,750     5,000\n")

    print(f"{BOLD}{GREEN}✅ Visual outcome bars successfully rendered.{RESET}\n")

if __name__ == "__main__":
    main()
