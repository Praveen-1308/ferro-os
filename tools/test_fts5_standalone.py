import time
import random
import sqlite3
import threading

db_fts = "/tmp/test_fts.db"
import os
for f in [db_fts, db_fts + "-wal", db_fts + "-shm"]:
    if os.path.exists(f):
        try: os.remove(f)
        except Exception: pass

conn = sqlite3.connect(db_fts)
cur = conn.cursor()
cur.execute("PRAGMA journal_mode = WAL;")
cur.execute("CREATE VIRTUAL TABLE logs USING fts5(service, level, message);")

services = ["auth-service", "billing-gateway", "k8s-ingress", "database-proxy", "storage-node"]
levels = ["INFO", "WARN", "ERROR", "DEBUG", "FATAL"]
words = ["connection", "timeout", "reconnect", "failed", "success", "handshake", "packet", "dropped", "buffer", "overflow"]

docs = []
for i in range(50000):
    s = random.choice(services)
    l = random.choice(levels)
    m = f"Transaction {i} {random.choice(words)} while processing {random.choice(words)} request"
    docs.append((s, l, m))

t0_idx = time.perf_counter()
cur.executemany("INSERT INTO logs VALUES (?, ?, ?);", docs)
conn.commit()
conn.close()

# Search queries
concurrency = 16
queries_per_th = 5000 // concurrency
q_lats = [[] for _ in range(concurrency)]

def search_worker(wid):
    c = sqlite3.connect(db_fts)
    cr = c.cursor()
    for _ in range(queries_per_th):
        w = random.choice(words)
        t0 = time.perf_counter()
        cr.execute("SELECT rank, service, message FROM logs WHERE logs MATCH ? ORDER BY rank LIMIT 10;", (w,))
        _ = cr.fetchall()
        q_lats[wid].append((time.perf_counter() - t0) * 1000)
    c.close()

t0_q = time.perf_counter()
threads = [threading.Thread(target=search_worker, args=(w,)) for w in range(concurrency)]
for t in threads: t.start()
for t in threads: t.join()
t_q = time.perf_counter() - t0_q

all_lats = [l for sub in q_lats for l in sub]
qps = len(all_lats) / t_q
print(f"Standalone FTS5 QPS: {qps:.1f} (Duration: {t_q:.2f}s)")
