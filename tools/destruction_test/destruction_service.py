#!/usr/bin/env python3
"""
tools/destruction_test/destruction_service.py
High-Load Enterprise Service Designed for Continuous Ramp-to-Destruction Evaluation.

Workload Characteristics:
- ACID Transactional Writes to SQLite WAL (inventory decrement + audit log flush)
- Dynamic Memory Churn (128 KB heap buffers allocated and transformed per write)
- Read Cache Simulation
- Strict Liveness Probe (/healthz)
"""

import os
import sys
import time
import json
import sqlite3
import asyncio
from typing import Dict, Any

PORT = int(os.environ.get("PORT", "10000"))
HOST = os.environ.get("HOST", "0.0.0.0")
DB_PATH = os.environ.get("SQLITE_PATH", "/tmp/destruction_test.db")
MAX_IN_FLIGHT = int(os.environ.get("MAX_IN_FLIGHT", "128"))

class DestructionService:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.conn = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self.conn.execute("PRAGMA synchronous = NORMAL;")
        self.conn.execute("PRAGMA cache_size = -32000;")
        self.conn.execute("PRAGMA mmap_size = 134217728;")
        self.conn.execute("PRAGMA busy_timeout = 3000;")
        
        # Init schema
        self.conn.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, sku TEXT, stock INTEGER, price INTEGER);")
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM products;")
        if cur.fetchone()[0] < 1000:
            cur.execute("BEGIN;")
            for i in range(1, 1001):
                cur.execute("INSERT OR REPLACE INTO products (id, sku, stock, price) VALUES (?, ?, ?, ?);",
                            (i, f"SKU-{i:05d}", 1000000, 1999 + (i % 5000)))
            cur.execute("COMMIT;")
            
        self.sem = asyncio.Semaphore(MAX_IN_FLIGHT)
        audit_path = os.path.join(os.path.dirname(db_path), "destruction_audit.wal")
        self.audit_fd = os.open(audit_path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o666)
        self.audit_blob = os.urandom(65536) # 64 KB block

    def read_product(self, prod_id: int):
        cur = self.conn.cursor()
        cur.execute("SELECT id, sku, stock, price FROM products WHERE id = ?;", (prod_id,))
        row = cur.fetchone()
        if row:
            return {"id": row[0], "sku": row[1], "stock": row[2], "price": row[3]}
        return {"error": "not found"}

    def write_order(self, prod_id: int):
        # 1. Heap churn: allocate and transform 128 KB buffer
        buf = bytearray(os.urandom(131072))
        for i in range(0, 1024, 64):
            buf[i] ^= 0x5A
            
        # 2. Disk writeback injection: append 64 KB to audit log
        os.write(self.audit_fd, self.audit_blob)
        
        # 3. Database lock & WAL commit
        cur = self.conn.cursor()
        cur.execute("BEGIN IMMEDIATE;")
        cur.execute("UPDATE products SET stock = stock - 1 WHERE id = ?;", (prod_id,))
        cur.execute("COMMIT;")
        
        return {"status": "ordered", "prod_id": prod_id, "checksum": len(buf)}

service = None

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    global service
    try:
        req_line = await asyncio.wait_for(reader.readline(), timeout=3.0)
        if not req_line:
            writer.close()
            return
            
        parts = req_line.decode("latin1", errors="ignore").split()
        if len(parts) < 2:
            writer.close()
            return
            
        method, path = parts[0], parts[1]
        
        # Drain headers
        content_length = 0
        while True:
            header_line = await asyncio.wait_for(reader.readline(), timeout=2.0)
            if not header_line or header_line == b"\r\n":
                break
            line_str = header_line.decode("latin1", errors="ignore").lower()
            if line_str.startswith("content-length:"):
                try:
                    content_length = int(line_str.split(":")[1].strip())
                except Exception:
                    pass

        if content_length > 0:
            await asyncio.wait_for(reader.readexactly(content_length), timeout=2.0)

        # Route
        status_code = "200 OK"
        body = b"{}"
        
        if path == "/healthz":
            body = b'{"status":"ok"}'
        elif path.startswith("/api/read"):
            prod_id = 1
            if "?id=" in path:
                try:
                    prod_id = int(path.split("?id=")[1].split("&")[0])
                except Exception:
                    prod_id = 1
            res = service.read_product(prod_id)
            body = json.dumps(res).encode("utf-8")
        elif path.startswith("/api/write") or path.startswith("/api/order"):
            prod_id = 1
            if "?id=" in path:
                try:
                    prod_id = int(path.split("?id=")[1].split("&")[0])
                except Exception:
                    prod_id = 1
            res = service.write_order(prod_id)
            body = json.dumps(res).encode("utf-8")
        else:
            status_code = "404 Not Found"
            body = b'{"error":"not_found"}'
            
        resp = (
            f"HTTP/1.1 {status_code}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: keep-alive\r\n\r\n"
        ).encode("utf-8") + body
        
        writer.write(resp)
        await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def main():
    global service
    service = DestructionService(DB_PATH)
    server = await asyncio.start_server(handle_client, HOST, PORT, backlog=16384)
    print(f"[*] Destruction Service listening on {HOST}:{PORT} (DB: {DB_PATH})...")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
