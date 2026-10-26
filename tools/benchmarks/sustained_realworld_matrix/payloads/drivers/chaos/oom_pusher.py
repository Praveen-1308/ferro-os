"""
tools/benchmarks/sustained_realworld_matrix/payloads/drivers/chaos/oom_pusher.py
Pushes container memory allocations towards the cgroup v2 4.0 GB limit.
"""

import sys
import select
import argparse


def push_memory(target_mb: int = 4000, chunk_mb: int = 50, rate_mb_s: int = 50):
    chunks = []
    total_allocated = 0
    print(f"[*] Allocating up to {target_mb} MB in {chunk_mb} MB chunks at {rate_mb_s} MB/s...")

    interval = float(chunk_mb) / float(rate_mb_s)
    while total_allocated < target_mb:
        # Allocate real memory and touch pages so kernel faults them in
        chunk = bytearray(b"\xaa" * (chunk_mb * 1024 * 1024))
        chunks.append(chunk)
        total_allocated += chunk_mb
        print(f"[+] Total allocated RSS: {total_allocated} MB")
        select.select([], [], [], interval)

    print(f"[*] Holding {total_allocated} MB...")
    select.select([], [], [], 30.0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-mb", type=int, default=4000)
    parser.add_argument("--rate-mb-s", type=int, default=50)
    args = parser.parse_args()

    push_memory(args.target_mb, chunk_mb=50, rate_mb_s=args.rate_mb_s)
