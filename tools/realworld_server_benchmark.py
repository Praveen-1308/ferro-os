#!/usr/bin/env python3
"""
Real-World Enterprise Server Benchmark Suite
Measures actual production workloads across operating systems:
1. Enterprise SQL ACID Transactions & Analytics (WAL mode, 8-thread worker pool)
2. High-Concurrency REST Microservice (Multi-threaded HTTP keep-alive)
3. Deeply Nested JSON Schema Parsing & Mutation (e-commerce catalog)
4. Multi-Threaded Cryptographic HMAC & SHA-256 Auth Pipeline
5. Multi-Threaded Memory Allocator (Local Batching & Cross-Thread Remote Free)
"""

import os
import sys
import time
import json
import sqlite3
import hashlib
import hmac
import threading
import subprocess
import urllib.request
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

RESULTS = {}

# =====================================================================
# 1. Enterprise SQL ACID Transactions & Analytics Workload
# =====================================================================
def run_benchmark_sql():
    print("[1/5] Running Real-World SQL Enterprise Database Workload (10k ACID Txs)...")
    db_file = "/tmp/realworld_bench.db"
    for f in [db_file, db_file + "-wal", db_file + "-shm"]:
        if os.path.exists(f):
            try: os.remove(f)
            except Exception: pass
    
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode = WAL;")
    cur.execute("PRAGMA synchronous = NORMAL;")
    cur.execute("PRAGMA cache_size = -64000;") # 64MB cache
    cur.execute("PRAGMA temp_store = MEMORY;")
    cur.execute("PRAGMA mmap_size = 268435456;") # 256MB mmap
    
    cur.execute("""
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY,
            account_number TEXT UNIQUE NOT NULL,
            balance REAL NOT NULL,
            tier TEXT NOT NULL
        );
    """)
    cur.execute("""
        CREATE TABLE transactions (
            tx_id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            timestamp REAL NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        );
    """)
    cur.execute("CREATE INDEX idx_tx_account ON transactions(account_id);")
    
    # Seed 500 enterprise accounts
    accounts = [(i, f"ACC-{i:06d}", 100000.0 + i, "ENTERPRISE" if i % 5 == 0 else "STANDARD") for i in range(1, 501)]
    cur.executemany("INSERT INTO accounts VALUES (?, ?, ?, ?)", accounts)
    conn.commit()
    conn.close()
    
    total_txs = 10000
    concurrency = 8
    tx_per_worker = total_txs // concurrency
    latencies = [[] for _ in range(concurrency)]
    
    def worker(wid):
        c = sqlite3.connect(db_file, timeout=30.0)
        cr = c.cursor()
        cr.execute("PRAGMA synchronous = NORMAL;")
        cr.execute("PRAGMA mmap_size = 268435456;")
        for i in range(tx_per_worker):
            t0 = time.perf_counter()
            acc_id = ((wid * 1000 + i) % 500) + 1
            amt = 150.0 + (i % 25)
            cr.execute("BEGIN IMMEDIATE;")
            cr.execute("INSERT INTO transactions (account_id, amount, timestamp) VALUES (?, ?, ?)", (acc_id, amt, time.time()))
            cr.execute("UPDATE accounts SET balance = balance + ? WHERE id = ?", (amt, acc_id))
            c.commit()
            # Verification read
            cr.execute("SELECT balance FROM accounts WHERE id = ?", (acc_id,))
            _ = cr.fetchone()
            latencies[wid].append((time.perf_counter() - t0) * 1000)
        c.close()

    t_start = time.perf_counter()
    threads = [threading.Thread(target=worker, args=(w,)) for w in range(concurrency)]
    for t in threads: t.start()
    for t in threads: t.join()
    t_end = time.perf_counter()
    
    duration = t_end - t_start
    all_lats = [lat for w_l in latencies for lat in w_l]
    all_lats.sort()
    tps = len(all_lats) / duration if duration > 0 else 0
    p95 = all_lats[int(len(all_lats) * 0.95)] if all_lats else 0
    
    # Complex join query
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    t0_an = time.perf_counter()
    cur.execute("""
        SELECT a.tier, COUNT(t.tx_id), SUM(t.amount), AVG(t.amount), AVG(a.balance)
        FROM accounts a JOIN transactions t ON a.id = t.account_id
        GROUP BY a.tier;
    """)
    _ = cur.fetchall()
    an_time_ms = (time.perf_counter() - t0_an) * 1000
    conn.close()
    
    for f in [db_file, db_file + "-wal", db_file + "-shm"]:
        if os.path.exists(f):
            try: os.remove(f)
            except Exception: pass

    RESULTS["sql_tps"] = round(tps, 2)
    RESULTS["sql_duration_s"] = round(duration, 3)
    RESULTS["sql_p95_ms"] = round(p95, 2)
    RESULTS["sql_analytics_ms"] = round(an_time_ms, 2)
    print(f"  -> SQL Result: {tps:.1f} TPS, Duration: {duration:.3f}s, p95: {p95:.2f}ms, Analytics: {an_time_ms:.2f}ms")

# =====================================================================
# 2. Real-World High-Concurrency HTTP REST Microservice Workload
# =====================================================================
class MicroserviceHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        req = json.loads(post_data.decode('utf-8'))
        resp = {
            "status": "PROCESSED",
            "request_id": req.get("id"),
            "computed_hash": hashlib.sha256(str(req.get("id")).encode()).hexdigest()[:16],
            "server_time": time.time()
        }
        resp_bytes = json.dumps(resp).encode('utf-8')
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp_bytes)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(resp_bytes)
        
    def log_message(self, format, *args):
        pass

def run_benchmark_http():
    print("[2/5] Running High-Concurrency Web Microservice Workload (2,000 requests, 16 workers)...")
    server_address = ('127.0.0.1', 9199)
    httpd = ThreadingHTTPServer(server_address, MicroserviceHandler)
    server_thread = threading.Thread(target=httpd.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    time.sleep(0.5)
    
    total_reqs = 2000
    concurrency = 16
    req_per_thread = total_reqs // concurrency
    thread_lats = [[] for _ in range(concurrency)]
    
    def client_worker(wid):
        url = "http://127.0.0.1:9199/api/process"
        for i in range(req_per_thread):
            t0 = time.perf_counter()
            req_id = wid * 1000 + i
            payload = json.dumps({"id": req_id, "action": "CALCULATE_DISCOUNT", "items": [10, 20, 30]}).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json', 'Connection': 'close'}, method='POST')
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    assert response.status == 200
                    _ = response.read()
                thread_lats[wid].append((time.perf_counter() - t0) * 1000)
            except Exception as e:
                pass

    t_start = time.perf_counter()
    clients = [threading.Thread(target=client_worker, args=(w,)) for w in range(concurrency)]
    for c in clients: c.start()
    for c in clients: c.join()
    t_end = time.perf_counter()
    
    httpd.shutdown()
    httpd.server_close()
    
    duration = t_end - t_start
    all_lats = [lat for w_l in thread_lats for lat in w_l]
    all_lats.sort()
    rps = len(all_lats) / duration if duration > 0 else 0
    p95 = all_lats[int(len(all_lats) * 0.95)] if all_lats else 0
    p99 = all_lats[int(len(all_lats) * 0.99)] if all_lats else 0
    mean_lat = sum(all_lats) / len(all_lats) if all_lats else 0
    
    RESULTS["http_rps"] = round(rps, 2)
    RESULTS["http_duration_s"] = round(duration, 3)
    RESULTS["http_mean_lat_ms"] = round(mean_lat, 2)
    RESULTS["http_p99_ms"] = round(p99, 2)
    print(f"  -> HTTP Result: {rps:.1f} RPS, Duration: {duration:.3f}s, Mean Latency: {mean_lat:.2f}ms, p99: {p99:.2f}ms")

# =====================================================================
# 3. Real-World JSON Serialization, Schema Validation & Mutation
# =====================================================================
def run_benchmark_json():
    print("[3/5] Running Real-World JSON Schema & Payload Processing (50,000 catalog orders)...")
    template_order = {
        "order_id": "ORD-998234-X",
        "customer": {"id": 10482, "name": "Jane Enterprise", "email": "jane@corp.internal", "tier": "VIP"},
        "items": [
            {"sku": "SKU-APPLE-01", "name": "Enterprise Server Node", "quantity": 4, "unit_price": 2499.50},
            {"sku": "SKU-MEM-64GB", "name": "DDR5 ECC 64GB RDIMM", "quantity": 16, "unit_price": 189.99},
            {"sku": "SKU-NVME-4TB", "name": "NVMe PCIe 5.0 4TB SSD", "quantity": 8, "unit_price": 349.00}
        ],
        "shipping": {"address": "100 Enterprise Way", "city": "San Francisco", "zip": "94105", "method": "EXPRESS_OVERNIGHT"},
        "payment": {"method": "CORPORATE_INVOICE", "terms": "NET30", "approved": True}
    }
    
    count = 50000
    json_bytes = json.dumps(template_order).encode('utf-8')
    
    t0 = time.perf_counter()
    for i in range(count):
        # Deserialization
        obj = json.loads(json_bytes)
        # Business logic mutation & validation
        subtotal = sum(item["quantity"] * item["unit_price"] for item in obj["items"])
        tax = subtotal * 0.0825
        total = subtotal + tax
        obj["totals"] = {"subtotal": subtotal, "tax": tax, "total": total}
        obj["order_id"] = f"ORD-{i:07d}"
        obj["status"] = "VALIDATED"
        # Re-serialization
        _ = json.dumps(obj)
    t_end = time.perf_counter()
    
    duration = t_end - t0
    ops_per_sec = count / duration if duration > 0 else 0
    
    RESULTS["json_ops_per_sec"] = round(ops_per_sec, 2)
    RESULTS["json_duration_s"] = round(duration, 3)
    print(f"  -> JSON Result: {ops_per_sec:.1f} docs/sec, Duration: {duration:.3f}s")

# =====================================================================
# 4. Real-World Multi-Threaded Cryptographic Pipeline (SHA-256 + HMAC)
# =====================================================================
def run_benchmark_crypto():
    print("[4/5] Running Multi-Threaded Cryptographic Auth Pipeline (500 MB across 8 threads)...")
    total_bytes = 500 * 1024 * 1024
    num_threads = 8
    bytes_per_thread = total_bytes // num_threads
    chunk_size = 64 * 1024
    secret_key = b"ferro-enterprise-secret-signature-key-2026"
    sample_chunk = b"X" * chunk_size
    
    def crypto_worker():
        chunks = bytes_per_thread // chunk_size
        for _ in range(chunks):
            # Compute SHA-256 digest
            sha = hashlib.sha256(sample_chunk).digest()
            # Compute HMAC-SHA256 signature
            _ = hmac.new(secret_key, sha, hashlib.sha256).digest()

    t0 = time.perf_counter()
    threads = [threading.Thread(target=crypto_worker) for _ in range(num_threads)]
    for t in threads: t.start()
    for t in threads: t.join()
    t_end = time.perf_counter()
    
    duration = t_end - t0
    throughput_mb = (total_bytes / (1024 * 1024)) / duration if duration > 0 else 0
    
    RESULTS["crypto_throughput_mbs"] = round(throughput_mb, 2)
    RESULTS["crypto_duration_s"] = round(duration, 3)
    print(f"  -> Crypto Result: {throughput_mb:.1f} MB/s, Duration: {duration:.3f}s")

# =====================================================================
# 5. Multi-Threaded Memory Allocator (Local Batching & Remote Free)
# =====================================================================
def run_benchmark_memory():
    print("[5/5] Running Multi-Threaded Memory Allocator Stress (Local Multi-Thread + Remote-Free)...")
    
    # Test A: Pure Multi-Thread Local Batch Allocation (8 threads, 1.6M ops)
    src_local = "/bench/tools/benchmark_allocator.c"
    bin_local = "/tmp/bench_alloc_local"
    subprocess.check_call(f"gcc -O3 -pthread {src_local} -o {bin_local}", shell=True)
    out_local = subprocess.check_output(bin_local, shell=True).decode('utf-8')
    
    ops_local = 0.0
    ns_local = 0.0
    for line in out_local.splitlines():
        if "Allocation Throughput:" in line:
            ops_local = float(line.split("Allocation Throughput:")[1].split("ops/sec")[0].replace(",", "").strip())
        if "Avg Op Latency:" in line:
            ns_local = float(line.split("Avg Op Latency:")[1].split("ns")[0].strip())
            
    # Test B: Producer-Consumer Remote Free (1M ops cross-thread)
    src_remote = "/bench/tools/benchmark_remote_free.c"
    bin_remote = "/tmp/bench_alloc_remote"
    subprocess.check_call(f"gcc -O3 -pthread {src_remote} -o {bin_remote}", shell=True)
    out_remote = subprocess.check_output(bin_remote, shell=True).decode('utf-8')
    
    ops_remote = 0.0
    ns_remote = 0.0
    for line in out_remote.splitlines():
        if "Remote Free Throughput:" in line:
            ops_remote = float(line.split("Remote Free Throughput:")[1].split("ops/sec")[0].replace(",", "").strip())
        if "Average Latency:" in line:
            ns_remote = float(line.split("Average Latency:")[1].split("ns")[0].strip())

    RESULTS["mem_local_ops_sec"] = round(ops_local, 2)
    RESULTS["mem_local_ns_op"] = round(ns_local, 2)
    RESULTS["mem_remote_ops_sec"] = round(ops_remote, 2)
    RESULTS["mem_remote_ns_op"] = round(ns_remote, 2)
    print(f"  -> Local Alloc: {ops_local:,.0f} ops/sec ({ns_local:.2f} ns/op)")
    print(f"  -> Remote Free: {ops_remote:,.0f} ops/sec ({ns_remote:.2f} ns/op)")

def main():
    print("=" * 70)
    print(f"STARTING REAL-WORLD ENTERPRISE BENCHMARK ON: {os.uname().sysname} {os.uname().release}")
    print("=" * 70)
    
    run_benchmark_sql()
    run_benchmark_http()
    run_benchmark_json()
    run_benchmark_crypto()
    run_benchmark_memory()
    
    print("\n" + "=" * 70)
    print("FINAL BENCHMARK JSON RESULTS:")
    print(json.dumps(RESULTS, indent=2))
    print("=" * 70)

if __name__ == "__main__":
    main()
