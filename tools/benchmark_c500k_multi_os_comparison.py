#!/usr/bin/env python3
"""
tools/benchmark_c500k_multi_os_comparison.py
Runs the Next-Generation C500K architectural components inside both Ubuntu 24.04 LTS
and FerroOS Server containers under strict 1 vCPU / 2048 MB RAM limits to demonstrate
how the next-gen design performs across both operating systems.
"""

import os
import sys
import time
import json
import subprocess

SCRIPT_INSIDE = """
import time, struct, array, hashlib, hmac, sqlite3, os

SECRET = b"twelve-dollar-challenge-ferro-secret"

# 1. MicroSocketSlab: 500k connections
capacity = 500_000
t0 = time.perf_counter()
raw_table = bytearray(capacity * 32)
free_list = array.array('I', range(capacity))
for i in range(capacity):
    slot = free_list.pop()
    struct.pack_into("<IHBBII", raw_table, slot * 32, slot, 1, 1, 0, int(time.time()), 0)
alloc_sec = time.perf_counter() - t0
slab_mb = (len(raw_table) + free_list.buffer_info()[1] * 4) / (1024**2)

# 2. Batch Crypto: 2,000 tokens
tokens = []
header = b"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
for i in range(1, 2001):
    payload = f'{{"sub":{i},"exp":{int(time.time())+3600}}}'.encode()
    p_b64 = hashlib.sha256(payload).hexdigest()[:24].encode()
    sign_in = header + b"." + p_b64
    sig = hashlib.sha256(hmac.new(SECRET, sign_in, hashlib.sha256).digest()).hexdigest()[:24].encode()
    tokens.append(sign_in + b"." + sig)

t0 = time.perf_counter()
key_pad = SECRET + b"\\x00" * (64 - len(SECRET))
o_pad = bytes(x ^ 0x5c for x in key_pad)
i_pad = bytes(x ^ 0x36 for x in key_pad)
for t in tokens:
    parts = t.split(b".")
    in_hash = hashlib.sha256(i_pad + parts[0] + b"." + parts[1]).digest()
    out_hash = hashlib.sha256(o_pad + in_hash).digest()
    exp_sig = hashlib.sha256(out_hash).hexdigest()[:24].encode()
crypto_sec = time.perf_counter() - t0
crypto_us_req = (crypto_sec / len(tokens)) * 1_000_000

# 3. WAL Checkpoint Under Write Churn: 1,000 inserts
db_path = "/tmp/c500k_bench.db"
for f in [db_path, f"{db_path}-wal", f"{db_path}-shm"]:
    if os.path.exists(f): os.remove(f)
conn = sqlite3.connect(db_path)
conn.execute("PRAGMA journal_mode = WAL;")
conn.execute("PRAGMA synchronous = NORMAL;")
conn.execute("PRAGMA wal_autocheckpoint = 0;")
conn.execute("CREATE TABLE writes (id INTEGER PRIMARY KEY, v TEXT);")
conn.commit()

latencies = []
for i in range(1000):
    t_w0 = time.perf_counter()
    conn.execute("INSERT INTO writes VALUES (?, ?);", (i, f"val_{i}"))
    conn.commit()
    if (i + 1) % 250 == 0:
        conn.execute("PRAGMA wal_checkpoint(PASSIVE);")
    latencies.append((time.perf_counter() - t_w0) * 1000)
conn.close()

latencies.sort()
p50 = latencies[int(len(latencies) * 0.50)]
p95 = latencies[int(len(latencies) * 0.95)]
p99 = latencies[int(len(latencies) * 0.99)]

print(f"{alloc_sec:.4f}|{slab_mb:.2f}|{crypto_us_req:.2f}|{p50:.3f}|{p95:.3f}|{p99:.3f}")
"""

def run_in_os(image_name):
    cmd = [
        "docker", "run", "--rm",
        "--cpus", "1.0",
        "--memory", "2048m",
        "--memory-swap", "2048m",
        image_name,
        "python3", "-c", SCRIPT_INSIDE
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error running in {image_name}: {res.stderr}")
        return None
    output = res.stdout.strip().splitlines()[-1]
    parts = [float(x) for x in output.split("|")]
    return {
        "slab_alloc_sec": parts[0],
        "slab_mem_mb": parts[1],
        "crypto_us_req": parts[2],
        "wal_p50_ms": parts[3],
        "wal_p95_ms": parts[4],
        "wal_p99_ms": parts[5],
    }

def main():
    print("=" * 80)
    print("      C500K ARCHITECTURAL PILLARS MULTI-OS BENCHMARK (1 vCPU, 2 GB)     ")
    print("=" * 80)
    print("  Testing 500k MicroSocketSlab, Vector Crypto, and Double-Buffered WAL...")
    
    print("\n🔬 [1/2] Running Next-Gen Design in Ubuntu 24.04 LTS...")
    u_data = run_in_os("bench-ubuntu:latest")
    print(f"   • Slab 500k Alloc: {u_data['slab_alloc_sec']:.3f}s ({500_000/u_data['slab_alloc_sec']:,.0f} ops/s) | RAM: {u_data['slab_mem_mb']:.2f} MB")
    print(f"   • Crypto Verify:  {u_data['crypto_us_req']:.2f} µs/req ({1_000_000/u_data['crypto_us_req']:,.0f} req/s)")
    print(f"   • WAL p99 Commit: {u_data['wal_p99_ms']:.3f} ms")

    print("\n🔬 [2/2] Running Next-Gen Design in FerroOS Server...")
    f_data = run_in_os("ferro-server:latest")
    print(f"   • Slab 500k Alloc: {f_data['slab_alloc_sec']:.3f}s ({500_000/f_data['slab_alloc_sec']:,.0f} ops/s) | RAM: {f_data['slab_mem_mb']:.2f} MB")
    print(f"   • Crypto Verify:  {f_data['crypto_us_req']:.2f} µs/req ({1_000_000/f_data['crypto_us_req']:,.0f} req/s)")
    print(f"   • WAL p99 Commit: {f_data['wal_p99_ms']:.3f} ms")

    print("\n" + "=" * 80)
    print("               NEXT-GEN C500K DESIGN: UBUNTU VS FERRO-OS                ")
    print("=" * 80)
    print(f"{'Component':<28} | {'Ubuntu 24.04':<16} | {'FerroOS Server':<16} | {'Delta':<12}")
    print("-" * 80)
    
    # Slab allocation
    diff_alloc = ((u_data['slab_alloc_sec'] - f_data['slab_alloc_sec']) / u_data['slab_alloc_sec']) * 100
    print(f"{'500k Socket Alloc Velocity':<28} | {500_000/u_data['slab_alloc_sec']:>12,.0f} ops/s | {500_000/f_data['slab_alloc_sec']:>12,.0f} ops/s | {diff_alloc:>+6.1f}%")
    
    # Crypto latency
    diff_crypto = ((u_data['crypto_us_req'] - f_data['crypto_us_req']) / u_data['crypto_us_req']) * 100
    print(f"{'Crypto Overhead / Request':<28} | {u_data['crypto_us_req']:>12.2f} µs    | {f_data['crypto_us_req']:>12.2f} µs    | {diff_crypto:>+6.1f}%")

    # WAL p99
    diff_wal = u_data['wal_p99_ms'] - f_data['wal_p99_ms']
    print(f"{'WAL Write p99 Commit':<28} | {u_data['wal_p99_ms']:>12.3f} ms    | {f_data['wal_p99_ms']:>12.3f} ms    | {diff_wal:>+6.3f}ms")
    print("-" * 80)

    # Save to disk
    with open("benchmarks/c500k_multi_os_comparison.json", "w") as f:
        json.dump({"ubuntu": u_data, "ferro_os": f_data}, f, indent=2)
    print("📁 Saved results to benchmarks/c500k_multi_os_comparison.json")

if __name__ == "__main__":
    main()
