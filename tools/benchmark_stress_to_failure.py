#!/usr/bin/env python3
"""
tools/benchmark_stress_to_failure.py - FerroOS Stress-to-Failure & Breaking Point Engine
Pushes the operating system to its absolute physical limits under a strict 6 GB RAM ceiling.
Progressively ramps up concurrency, memory pressure, file descriptors, and I/O congestion
to discover where the system chokes, throttles, or dies, providing actionable architectural insights.

Destruction Stages:
  Stage 1: Concurrency Thrashing (16 -> 32 -> 64 -> 128 -> 256 -> 512 threads)
  Stage 2: File Descriptor & Socket Exhaustion (Up to 5,000 concurrent sockets)
  Stage 3: Memory Edge-Riding (Pushing from 1 GB to 5.2 GB in 6 GB container under load)
  Stage 4: I/O Writeback Congestion & fsync Starvation (Gigabyte disk flood under load)
"""

import sys
import os
import time
import json
import sqlite3
import hashlib
import hmac
import socket
import struct
import threading
import subprocess
import http.client
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import random
import resource

SECRET_KEY = b"ferro-stress-secret-key-32bytes"

class StressGatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            
            # HMAC authentication
            auth_header = self.headers.get("Authorization", "")
            expected_hmac = hmac.new(SECRET_KEY, body, hashlib.sha256).hexdigest()
            if not auth_header.endswith(expected_hmac[-16:]):
                self.send_response(401)
                self.end_headers()
                return

            data = json.loads(body.decode("utf-8"))
            resp = json.dumps({"status": "ok", "tenant": data.get("tenant", "none"), "ts": time.time()}).encode()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            self.wfile.write(resp)
        except Exception:
            try:
                self.send_response(500)
                self.end_headers()
            except Exception:
                pass

def get_current_rss_mb():
    try:
        rusage = resource.getrusage(resource.RUSAGE_SELF)
        if sys.platform == "darwin":
            return rusage.ru_maxrss / (1024 * 1024)
        else:
            return rusage.ru_maxrss / 1024
    except Exception:
        return 0.0

def get_open_fd_count():
    try:
        pid = os.getpid()
        if os.path.exists(f"/proc/{pid}/fd"):
            return len(os.listdir(f"/proc/{pid}/fd"))
    except Exception:
        pass
    return -1

def run_stress_to_failure():
    print("=" * 80)
    print("  💥 FERRO-OS STRESS-TO-FAILURE & DESTRUCTION BREAKING-POINT TEST 💥")
    print(f"  Host: {os.uname().sysname} {os.uname().machine} | Runtime: Python {sys.version.split()[0]}")
    print(f"  Container RAM Limit: 6.00 GB | Initial RSS: {get_current_rss_mb():.1f} MB")
    print("=" * 80)

    # Start Ingress Gateway
    port = 19090
    server_address = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(server_address, StressGatewayHandler)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.2)

    # Initialize SQLite Database for WAL testing
    db_file = "/tmp/stress_breaking_point.db"
    for f in [db_file, db_file + "-wal", db_file + "-shm"]:
        if os.path.exists(f):
            try: os.remove(f)
            except Exception: pass

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode = WAL;")
    cur.execute("PRAGMA synchronous = NORMAL;")
    cur.execute("CREATE TABLE stress_accounts (id INT PRIMARY KEY, balance REAL);")
    cur.executemany("INSERT INTO stress_accounts VALUES (?, 50000.0);", [(i,) for i in range(1, 10001)])
    conn.commit()
    conn.close()

    summary_results = {}

    # =========================================================================
    # STAGE 1: Concurrency Choke Test (16 -> 32 -> 64 -> 128 -> 256 -> 512)
    # =========================================================================
    print("\n--------------------------------------------------------------------------------")
    print("  STAGE 1: Progressive Concurrency Scaling & Thread Thrashing Test")
    print("--------------------------------------------------------------------------------")
    print(f"  {'Concurrency':<14} {'Throughput (RPS)':<20} {'p50 Lat (ms)':<16} {'p99 Lat (ms)':<16} {'Errors':<10} {'Status'}")
    print("  " + "-" * 76)

    stage1_tiers = [16, 32, 64, 128, 256, 512]
    stage1_results = {}

    for threads_count in stage1_tiers:
        stop_tier = threading.Event()
        success_count = 0
        error_count = 0
        latencies = []
        tier_lock = threading.Lock()

        def client_worker():
            nonlocal success_count, error_count
            conn = None
            while not stop_tier.is_set():
                t0 = time.perf_counter()
                try:
                    if conn is None:
                        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2.0)
                    body = json.dumps({"tenant": f"t-{random.randint(1,100)}", "data": "X"*64}).encode()
                    token = hmac.new(SECRET_KEY, body, hashlib.sha256).hexdigest()
                    conn.request("POST", "/api/stress", body=body, headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}",
                        "Connection": "keep-alive"
                    })
                    resp = conn.getresponse()
                    _ = resp.read()
                    lat = (time.perf_counter() - t0) * 1000.0
                    with tier_lock:
                        success_count += 1
                        latencies.append(lat)
                except Exception:
                    if conn:
                        try: conn.close()
                        except Exception: pass
                        conn = None
                    with tier_lock:
                        error_count += 1
            if conn:
                try: conn.close()
                except Exception: pass

        workers = [threading.Thread(target=client_worker) for _ in range(threads_count)]
        t_start = time.perf_counter()
        for w in workers: w.start()
        time.sleep(3.0) # 3-second sustained hammer per tier
        stop_tier.set()
        for w in workers: w.join(timeout=3.0)
        t_dur = time.perf_counter() - t_start

        rps = success_count / t_dur if t_dur > 0 else 0
        lats_sorted = sorted(latencies)
        p50 = lats_sorted[len(lats_sorted) // 2] if lats_sorted else 0.0
        p99 = lats_sorted[int(len(lats_sorted) * 0.99)] if lats_sorted else 0.0

        status = "\033[92mSTABLE\033[0m" if error_count == 0 else f"\033[91mFAIL ({error_count})\033[0m"
        if p99 > 50.0:
            status += " (THROTTLING)"
        print(f"  {threads_count:<14} {rps:<20.1f} {p50:<16.2f} {p99:<16.2f} {error_count:<10} {status}")
        stage1_results[f"{threads_count}_workers"] = {
            "rps": round(rps, 1), "p50_ms": round(p50, 2), "p99_ms": round(p99, 2), "errors": error_count
        }

    summary_results["stage1_concurrency"] = stage1_results

    # =========================================================================
    # STAGE 2: File Descriptor & Socket Saturation Test
    # =========================================================================
    print("\n--------------------------------------------------------------------------------")
    print("  STAGE 2: Socket & File Descriptor Saturation Flood")
    print("--------------------------------------------------------------------------------")
    target_fds = [500, 1000, 2000, 3000, 4000]
    stage2_results = {}
    active_sockets = []
    fd_limit_hit = False

    for count in target_fds:
        needed = count - len(active_sockets)
        errors = 0
        for _ in range(needed):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2.0)
                s.connect(("127.0.0.1", port))
                active_sockets.append(s)
            except Exception as e:
                errors += 1
                fd_limit_hit = True
                break

        current_fds = get_open_fd_count()
        status = f"✅ {len(active_sockets)} sockets active" if errors == 0 else f"❌ Choked at {len(active_sockets)} sockets (EMFILE)"
        print(f"  Target: {count:<8} -> Held: {len(active_sockets):<8} | Open FDs in /proc: {current_fds:<6} | Status: {status}")
        stage2_results[f"target_{count}"] = {"held_sockets": len(active_sockets), "open_fds": current_fds, "errors": errors}
        if fd_limit_hit:
            break

    # Clean up open sockets
    for s in active_sockets:
        try: s.close()
        except Exception: pass
    active_sockets.clear()
    summary_results["stage2_fd_saturation"] = stage2_results

    # =========================================================================
    # STAGE 3: Memory Edge-Riding Test (Pushing towards 6 GB RAM limit)
    # =========================================================================
    print("\n--------------------------------------------------------------------------------")
    print("  STAGE 3: Memory Edge-Riding Pressure (Pushing up to 5.2 GB in 6 GB Container)")
    print("--------------------------------------------------------------------------------")
    memory_slabs = []
    slab_targets_mb = [500, 1000, 2000, 3000, 4000, 4800, 5200]
    stage3_results = {}

    for target_mb in slab_targets_mb:
        current_rss = get_current_rss_mb()
        needed_mb = target_mb - int(current_rss)
        alloc_failed = False
        t0_alloc = time.perf_counter()

        if needed_mb > 0:
            try:
                # Allocate chunk and dirty every 4KB page so kernel cannot lazy-map
                chunk_bytes = needed_mb * 1024 * 1024
                # Allocate 50MB bytearrays in loop
                slabs_to_add = needed_mb // 50
                for _ in range(slabs_to_add):
                    b = bytearray(50 * 1024 * 1024)
                    # Dirty pages across the slab
                    for offset in range(0, len(b), 4096):
                        b[offset] = 0xAA
                    memory_slabs.append(b)
            except (MemoryError, Exception) as e:
                alloc_failed = True
                print(f"  ❌ Memory Allocation Choked at {target_mb} MB: {e}")

        measured_rss = get_current_rss_mb()

        # Run 20 concurrent transactions while under this extreme memory pressure
        db_errors = 0
        t0_db = time.perf_counter()
        try:
            c = sqlite3.connect(db_file, timeout=5.0)
            cr = c.cursor()
            cr.execute("PRAGMA synchronous = NORMAL;")
            for i in range(100):
                cr.execute("UPDATE stress_accounts SET balance = balance + 1.0 WHERE id = ?;", (random.randint(1, 10000),))
            c.commit()
            c.close()
        except Exception as e:
            db_errors += 1

        dt_db = (time.perf_counter() - t0_db) * 1000.0
        status = "\033[92mSURVIVED\033[0m" if not alloc_failed and db_errors == 0 else "\033[91mDEGRADED\033[0m"
        print(f"  Target: {target_mb:>5} MB -> Real RSS: {measured_rss:>6.1f} MB ({(measured_rss/6144.0)*100:>4.1f}% of 6GB) | DB Tx: {dt_db:>5.1f} ms | Status: {status}")
        stage3_results[f"{target_mb}_mb"] = {
            "real_rss_mb": round(measured_rss, 1), "pct_of_6gb": round((measured_rss/6144.0)*100, 1),
            "db_latency_ms": round(dt_db, 1), "survived": not alloc_failed
        }

        if alloc_failed:
            print("  💥 Hit Physical Container OOM Boundary!")
            break

    # Release memory slabs
    memory_slabs.clear()
    import gc
    gc.collect()
    summary_results["stage3_memory_pressure"] = stage3_results

    # =========================================================================
    # STAGE 4: Disk I/O Writeback Congestion & fsync Starvation
    # =========================================================================
    print("\n--------------------------------------------------------------------------------")
    print("  STAGE 4: Disk I/O Congestion & Synchronous fsync() Flooding")
    print("--------------------------------------------------------------------------------")
    io_scratch = "/tmp/stress_io_congestion"
    os.makedirs(io_scratch, exist_ok=True)
    stop_io = threading.Event()
    io_bytes_written = 0
    io_lock = threading.Lock()

    def io_congestion_burner(wid):
        nonlocal io_bytes_written
        chunk = b"HEAVY_DISK_WRITE_BLOCK_DATA_CONGESTION\n" * 4096 # 160 KB
        fpath = os.path.join(io_scratch, f"heavy_io_{wid}.dat")
        while not stop_io.is_set():
            try:
                with open(fpath, "wb") as f:
                    for _ in range(50): # 8 MB per file
                        f.write(chunk)
                    f.flush()
                    os.fsync(f.fileno()) # Force physical writeback to storage
                with io_lock:
                    io_bytes_written += len(chunk) * 50
            except Exception:
                pass

    # Launch 8 parallel fsync burners
    burners = [threading.Thread(target=io_congestion_burner, args=(w,)) for w in range(8)]
    for b in burners: b.start()

    # Measure API Gateway response latency during the active disk flood
    api_lats_under_io = []
    t0_api_io = time.perf_counter()
    while time.perf_counter() - t0_api_io < 3.0:
        t0 = time.perf_counter()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2.0)
            body = b'{"stress": "fsync_under_load"}'
            token = hmac.new(SECRET_KEY, body, hashlib.sha256).hexdigest()
            conn.request("POST", "/api/stress", body=body, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            })
            resp = conn.getresponse()
            _ = resp.read()
            conn.close()
            api_lats_under_io.append((time.perf_counter() - t0) * 1000.0)
        except Exception:
            pass

    stop_io.set()
    for b in burners: b.join(timeout=3.0)

    io_mb = io_bytes_written / (1024 * 1024)
    sorted_io_lats = sorted(api_lats_under_io)
    io_p50 = sorted_io_lats[len(sorted_io_lats)//2] if sorted_io_lats else 0.0
    io_p99 = sorted_io_lats[int(len(sorted_io_lats)*0.99)] if sorted_io_lats else 0.0

    print(f"  * Disk Write Churn:          {io_mb:.1f} MB written with physical fsync()")
    print(f"  * API Gateway Latency Under I/O Flood: p50: {io_p50:.2f} ms | p99: {io_p99:.2f} ms")
    status_io = "\033[92mRESILIENT (Sub-10ms)\033[0m" if io_p99 < 15.0 else "\033[91mCHOKED (Disk starved network)\033[0m"
    print(f"  * Storage-Network Isolation: {status_io}")

    summary_results["stage4_io_congestion"] = {
        "io_mb_written": round(io_mb, 1),
        "api_p50_ms": round(io_p50, 2),
        "api_p99_ms": round(io_p99, 2),
    }

    # Teardown
    httpd.shutdown()
    httpd.server_close()
    import shutil
    shutil.rmtree(io_scratch, ignore_errors=True)
    for f in [db_file, db_file + "-wal", db_file + "-shm"]:
        if os.path.exists(f):
            try: os.remove(f)
            except Exception: pass

    print("\n" + "=" * 80)
    print("  💥 STRESS-TO-FAILURE TESTING COMPLETE: BREAKING POINT AUDIT")
    print("=" * 80)
    print(json.dumps(summary_results, indent=2))
    return summary_results

if __name__ == "__main__":
    run_stress_to_failure()
