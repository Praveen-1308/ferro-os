import sqlite3, time, multiprocessing, os

db = "/tmp/test.db"
for f in [db, db+"-wal", db+"-shm"]:
    if os.path.exists(f): 
        try: os.remove(f)
        except: pass

conn = sqlite3.connect(db)
conn.execute("PRAGMA journal_mode = WAL;")
conn.execute("CREATE VIRTUAL TABLE logs USING fts5(msg);")
for i in range(10000):
    conn.execute("INSERT INTO logs VALUES (?);", (f"hello world test {i} message error failure timeout reconnect",))
conn.commit()
conn.close()

def worker(num_queries):
    c = sqlite3.connect(db)
    cur = c.cursor()
    for _ in range(num_queries):
        cur.execute("SELECT rank, msg FROM logs WHERE logs MATCH ? ORDER BY rank LIMIT 10;", ("error",))
        _ = cur.fetchall()
    c.close()

print(f"Testing Process Scaling on SQLite {sqlite3.sqlite_version}...")
for num_procs in [1, 2, 4, 8, 16]:
    total_q = 800
    q_per = total_q // num_procs
    t0 = time.perf_counter()
    procs = [multiprocessing.Process(target=worker, args=(q_per,)) for _ in range(num_procs)]
    for p in procs: p.start()
    for p in procs: p.join()
    dt = time.perf_counter() - t0
    print(f"Processes: {num_procs:2d} | Duration: {dt:.3f}s | QPS: {(total_q/dt):.1f}")
