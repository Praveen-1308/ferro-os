#!/usr/bin/env python3
"""
tools/stack/enterprise_service.py
High-Performance Business Microservice for Candidate OS Evaluation.

Endpoints:
- GET  /feed          : Returns trending products and reviews
- GET  /products/:id  : Product details with associated customer reviews
- POST /orders        : ACID transactional order placement
- GET  /healthz       : Liveness / Readiness probe for Ingress
"""

import os
import sys
import time
import json
import sqlite3
import asyncio
from typing import Dict, Any

DB_PATH = os.environ.get("SQLITE_PATH", "/tmp/enterprise_seed.db")
PORT = int(os.environ.get("PORT", "3000"))
HOST = os.environ.get("HOST", "0.0.0.0")
MAX_IN_FLIGHT = int(os.environ.get("MAX_IN_FLIGHT", "64"))

class EnterpriseService:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self.conn.execute("PRAGMA synchronous = NORMAL;")
        self.conn.execute("PRAGMA cache_size = -32000;")
        self.conn.execute("PRAGMA mmap_size = 134217728;")
        self.conn.execute("PRAGMA busy_timeout = 3000;")
        self.sem = asyncio.Semaphore(MAX_IN_FLIGHT)

    def get_feed(self):
        cur = self.conn.cursor()
        cur.execute("SELECT id, sku, title, category, price_cents FROM products ORDER BY id ASC LIMIT 20;")
        rows = cur.fetchall()
        return [{"id": r[0], "sku": r[1], "title": r[2], "category": r[3], "price": r[4]} for r in rows]

    def get_product(self, prod_id):
        cur = self.conn.cursor()
        cur.execute("SELECT id, sku, title, category, price_cents, inventory_count FROM products WHERE id = ?;", (prod_id,))
        p = cur.fetchone()
        if not p: return None
        cur.execute("SELECT id, rating, comment FROM reviews WHERE product_id = ? ORDER BY id DESC LIMIT 5;", (prod_id,))
        revs = [{"id": r[0], "rating": r[1], "comment": r[2]} for r in cur.fetchall()]
        return {
            "id": p[0], "sku": p[1], "title": p[2], "category": p[3],
            "price_cents": p[4], "inventory": p[5], "reviews": revs
        }

    def place_order(self, user_id, product_id, qty=1):
        cur = self.conn.cursor()
        now = time.time()
        try:
            cur.execute("BEGIN IMMEDIATE;")
            cur.execute("SELECT price_cents, inventory_count FROM products WHERE id = ?;", (product_id,))
            p = cur.fetchone()
            if not p or p[1] < qty:
                cur.execute("ROLLBACK;")
                return None, "Out of stock or invalid product"
            price = p[0]
            total = price * qty
            cur.execute("UPDATE products SET inventory_count = inventory_count - ? WHERE id = ?;", (qty, product_id))
            cur.execute("INSERT INTO orders (user_id, total_cents, status, created_at) VALUES (?, ?, 'COMPLETED', ?);", (user_id, total, now))
            order_id = cur.lastrowid
            cur.execute("INSERT INTO order_items (order_id, product_id, quantity, price_cents) VALUES (?, ?, ?, ?);", (order_id, product_id, qty, price))
            cur.execute("COMMIT;")
            return {"order_id": order_id, "total_cents": total, "status": "COMPLETED"}, None
        except Exception as e:
            cur.execute("ROLLBACK;")
            return None, str(e)

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, service: EnterpriseService):
    try:
        data = await reader.read(4096)
        if not data:
            writer.close()
            return
        
        request_text = data.decode("utf-8", errors="ignore")
        lines = request_text.splitlines()
        if not lines:
            writer.close()
            return
        
        first_line = lines[0].split()
        if len(first_line) < 2:
            writer.close()
            return
            
        method, path = first_line[0], first_line[1]

        # Liveness check
        if path == "/healthz":
            body = b"OK\n"
            resp = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 3\r\nConnection: close\r\n\r\nOK\n"
            writer.write(resp)
            await writer.drain()
            writer.close()
            return

        # Adaptive backpressure check
        if service.sem.locked():
            resp = b"HTTP/1.1 429 Too Many Requests\r\nRetry-After: 1\r\nContent-Length: 23\r\nConnection: close\r\n\r\nRate limit: busy queue\n"
            writer.write(resp)
            await writer.drain()
            writer.close()
            return

        async with service.sem:
            if method == "GET" and path == "/feed":
                feed = service.get_feed()
                payload = json.dumps(feed).encode("utf-8")
                writer.write(f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n".encode() + payload)
            elif method == "GET" and path.startswith("/products/"):
                try:
                    p_id = int(path.split("/")[-1])
                    prod = service.get_product(p_id)
                    if prod:
                        payload = json.dumps(prod).encode("utf-8")
                        writer.write(f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n".encode() + payload)
                    else:
                        writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 9\r\nConnection: close\r\n\r\nNot Found")
                except ValueError:
                    writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 11\r\nConnection: close\r\n\r\nBad Request")
            elif method == "POST" and path == "/orders":
                # Find body
                body_idx = request_text.find("\r\n\r\n")
                body = request_text[body_idx + 4:] if body_idx != -1 else "{}"
                try:
                    req_data = json.loads(body)
                    u_id = req_data.get("user_id", 1)
                    p_id = req_data.get("product_id", 1)
                    qty = req_data.get("quantity", 1)
                    res, err = service.place_order(u_id, p_id, qty)
                    if res:
                        payload = json.dumps(res).encode("utf-8")
                        writer.write(f"HTTP/1.1 201 Created\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n".encode() + payload)
                    else:
                        payload = json.dumps({"error": err}).encode("utf-8")
                        writer.write(f"HTTP/1.1 400 Bad Request\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n".encode() + payload)
                except Exception as e:
                    writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 12\r\nConnection: close\r\n\r\nInvalid JSON")
            else:
                writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 9\r\nConnection: close\r\n\r\nNot Found")
                
            await writer.drain()
    except Exception:
        pass
    finally:
        try: writer.close()
        except Exception: pass

async def main():
    service = EnterpriseService(DB_PATH)
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, service),
        HOST, PORT, backlog=1024
    )
    print(f"🚀 [EnterpriseService] Listening on http://{HOST}:{PORT} (DB: {DB_PATH}, Max In-Flight: {MAX_IN_FLIGHT})")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
