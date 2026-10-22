#!/usr/bin/env python3
"""
tools/stack/flash_sale_server.py
High-End Multi-Modal Flash Sale & Media Streaming Microservice.
Designed for 4 vCPU / 6-8 GB RAM Cloud Server Ceilings.

Endpoints:
1. GET  /flash-sale/catalog   - Hot catalog query with real-time stock levels
2. POST /flash-sale/buy       - High-contention atomic row-lock inventory purchase
3. POST /content/:id/like     - High-frequency atomic counter increment
4. POST /media/images         - 256 KB binary image upload to disk (dirty page stress)
5. GET  /media/images/:id     - 256 KB binary image streaming (send buffer & page cache stress)
6. GET  /healthz              - Liveness & Readiness probe
"""

import os
import sys
import time
import json
import sqlite3
import asyncio
from typing import Dict, Any

DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "flash_sale.db")
UPLOADS_DIR = os.path.join(DATA_DIR, "media_uploads")
PORT = int(os.environ.get("PORT", "3000"))
HOST = os.environ.get("HOST", "0.0.0.0")
MAX_IN_FLIGHT = int(os.environ.get("MAX_IN_FLIGHT", "128"))

# Pre-generate 64 KB synthetic JPEG image payload for fast serving & writeback
IMAGE_BLOB_SIZE = 65536 # 64 KB
SYNTHETIC_IMAGE_BLOB = b"\xFF\xD8\xFF\xE0\x00\x10JFIF" + os.urandom(IMAGE_BLOB_SIZE - 9) + b"\xFF\xD9"

def init_flash_sale_db(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA cache_size = -128000;") # 128 MB cache on 6 GB RAM
    conn.execute("PRAGMA mmap_size = 536870912;") # 512 MB mmap
    conn.execute("PRAGMA busy_timeout = 5000;")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS flash_items (
            id INTEGER PRIMARY KEY,
            sku TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            price_cents INTEGER NOT NULL,
            stock INTEGER NOT NULL,
            likes_count INTEGER NOT NULL DEFAULT 0
        );
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS flash_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            created_at REAL NOT NULL
        );
    """)

    # Populate 10 flash-sale limited-stock items
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM flash_items;")
    if cur.fetchone()[0] == 0:
        items = [
            (1, "FLASH-GPU-90", "GeForce RTX 5090 Ultra (90% Off)", 19900, 2000, 0),
            (2, "FLASH-PHONE-16", "Smartphone Pro Max 1TB", 14900, 3000, 0),
            (3, "FLASH-OLED-65", "65-inch Quantum OLED TV", 29900, 1500, 0),
            (4, "FLASH-LAPTOP-M4", "Workstation 16-Core 64GB", 39900, 1000, 0),
            (5, "FLASH-HEADSET", "Audiophile Wireless ANC", 4900, 5000, 0),
            (6, "FLASH-CAMERA-8K", "Mirrorless 8K Cinema Body", 45000, 800, 0),
            (7, "FLASH-ROUTER-W7", "Tri-Band WiFi 7 Mesh Node", 6900, 4000, 0),
            (8, "FLASH-WATCH-ULTRA", "Titanium Cellular Smartwatch", 8900, 3500, 0),
            (9, "FLASH-DRONE-PRO", "Thermal Obstacle Tracking Drone", 22000, 1200, 0),
            (10, "FLASH-CONSOLE-PRO", "Next-Gen 8K Gaming Console", 19900, 2500, 0)
        ]
        conn.executemany("INSERT INTO flash_items VALUES (?, ?, ?, ?, ?, ?);", items)
    conn.close()

class FlashSaleService:
    def __init__(self, db_path, uploads_dir):
        self.db_path = db_path
        self.uploads_dir = uploads_dir
        os.makedirs(uploads_dir, exist_ok=True)
        init_flash_sale_db(db_path)

        self.conn = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self.conn.execute("PRAGMA synchronous = NORMAL;")
        self.conn.execute("PRAGMA busy_timeout = 5000;")
        self.sem = asyncio.Semaphore(MAX_IN_FLIGHT)
        self.image_counter = 0

    def get_catalog(self):
        cur = self.conn.cursor()
        cur.execute("SELECT id, sku, name, price_cents, stock, likes_count FROM flash_items ORDER BY id ASC;")
        rows = cur.fetchall()
        return [{"id": r[0], "sku": r[1], "name": r[2], "price_cents": r[3], "stock": r[4], "likes": r[5]} for r in rows]

    def buy_flash_item(self, user_id, item_id):
        cur = self.conn.cursor()
        now = time.time()
        try:
            cur.execute("BEGIN IMMEDIATE;")
            cur.execute("SELECT stock FROM flash_items WHERE id = ?;", (item_id,))
            row = cur.fetchone()
            if not row:
                cur.execute("ROLLBACK;")
                return None, "Item not found", 404
            
            stock = row[0]
            if stock <= 0:
                # Flash replenishment: replenish 10,000 units when exhausted so high-concurrency contention persists
                cur.execute("UPDATE flash_items SET stock = stock + 10000 WHERE id = ?;", (item_id,))
                stock = 10000
                
            cur.execute("UPDATE flash_items SET stock = stock - 1 WHERE id = ?;", (item_id,))
            cur.execute("INSERT INTO flash_orders (user_id, item_id, created_at) VALUES (?, ?, ?);", (user_id, item_id, now))
            order_id = cur.lastrowid
            cur.execute("COMMIT;")
            return {"order_id": order_id, "item_id": item_id, "remaining_stock": stock - 1, "status": "CONFIRMED"}, None, 201
        except Exception as e:
            cur.execute("ROLLBACK;")
            return None, str(e), 500

    def like_item(self, item_id):
        cur = self.conn.cursor()
        try:
            cur.execute("UPDATE flash_items SET likes_count = likes_count + 1 WHERE id = ?;", (item_id,))
            return {"item_id": item_id, "status": "LIKED"}
        except Exception:
            return {"status": "ERROR"}

    def save_image(self, image_bytes):
        self.image_counter += 1
        img_id = (self.image_counter % 500) + 1
        img_path = os.path.join(self.uploads_dir, f"img_{img_id}.jpg")
        # Direct synchronous unbuffered write to drive page cache dirtying under EBS gp3
        with open(img_path, "wb") as f:
            f.write(image_bytes)
        return img_id, len(image_bytes)

    def load_image(self, img_id):
        img_path = os.path.join(self.uploads_dir, f"img_{(img_id % 500) + 1}.jpg")
        if os.path.exists(img_path):
            with open(img_path, "rb") as f:
                return f.read()
        return SYNTHETIC_IMAGE_BLOB

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, service: FlashSaleService):
    try:
        # Read HTTP headers
        header_bytes = await reader.readuntil(b"\r\n\r\n")
        header_text = header_bytes.decode("utf-8", errors="ignore")
        lines = header_text.splitlines()
        if not lines:
            writer.close()
            return
            
        first_line = lines[0].split()
        if len(first_line) < 2:
            writer.close()
            return
            
        method, path = first_line[0], first_line[1]

        # Extract Content-Length
        content_length = 0
        for l in lines[1:]:
            if l.lower().startswith("content-length:"):
                try: content_length = int(l.split(":")[1].strip())
                except ValueError: pass

        # Liveness check
        if path == "/healthz":
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 3\r\nConnection: close\r\n\r\nOK\n")
            await writer.drain()
            writer.close()
            return

        # Adaptive Backpressure
        if service.sem.locked():
            resp = b"HTTP/1.1 429 Too Many Requests\r\nRetry-After: 1\r\nContent-Length: 28\r\nConnection: close\r\n\r\nFlash Sale Queue Overloaded\n"
            writer.write(resp)
            await writer.drain()
            writer.close()
            return

        async with service.sem:
            # 1. GET /flash-sale/catalog
            if method == "GET" and path == "/flash-sale/catalog":
                catalog = service.get_catalog()
                payload = json.dumps(catalog).encode("utf-8")
                writer.write(f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n".encode() + payload)

            # 2. POST /flash-sale/buy
            elif method == "POST" and path == "/flash-sale/buy":
                body = await reader.readexactly(content_length) if content_length > 0 else b"{}"
                try:
                    data = json.loads(body.decode("utf-8", errors="ignore"))
                    u_id = data.get("user_id", 1)
                    i_id = data.get("item_id", 1)
                    res, err, status_code = service.buy_flash_item(u_id, i_id)
                    if res:
                        payload = json.dumps(res).encode("utf-8")
                        writer.write(f"HTTP/1.1 {status_code} Created\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n".encode() + payload)
                    else:
                        payload = json.dumps({"error": err}).encode("utf-8")
                        writer.write(f"HTTP/1.1 {status_code} Error\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n".encode() + payload)
                except Exception as e:
                    writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 12\r\nConnection: close\r\n\r\nInvalid JSON")

            # 3. POST /content/:id/like
            elif method == "POST" and path.startswith("/content/") and path.endswith("/like"):
                try:
                    i_id = int(path.split("/")[2])
                    res = service.like_item(i_id)
                    payload = json.dumps(res).encode("utf-8")
                    writer.write(f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n".encode() + payload)
                except Exception:
                    writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 11\r\nConnection: close\r\n\r\nBad Request")

            # 4. POST /media/images (256 KB Image Upload -> Disk)
            elif method == "POST" and path == "/media/images":
                image_bytes = await reader.readexactly(content_length) if content_length > 0 else SYNTHETIC_IMAGE_BLOB
                img_id, byte_count = service.save_image(image_bytes)
                payload = json.dumps({"image_id": img_id, "bytes_written": byte_count, "status": "STORED"}).encode("utf-8")
                writer.write(f"HTTP/1.1 201 Created\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n".encode() + payload)

            # 5. GET /media/images/:id (256 KB Image Read & Streaming)
            elif method == "GET" and path.startswith("/media/images/"):
                try:
                    img_id = int(path.split("/")[-1])
                    blob = service.load_image(img_id)
                    header = f"HTTP/1.1 200 OK\r\nContent-Type: image/jpeg\r\nContent-Length: {len(blob)}\r\nConnection: close\r\n\r\n".encode()
                    writer.write(header + blob)
                except Exception:
                    writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 9\r\nConnection: close\r\n\r\nNot Found")

            else:
                writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 9\r\nConnection: close\r\n\r\nNot Found")

            await writer.drain()
    except Exception:
        pass
    finally:
        try: writer.close()
        except Exception: pass

async def main():
    service = FlashSaleService(DB_PATH, UPLOADS_DIR)
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, service),
        HOST, PORT, backlog=2048
    )
    print(f"🔥 [FlashSaleService] Listening on http://{HOST}:{PORT} (Max In-Flight: {MAX_IN_FLIGHT}, Data: {DATA_DIR})")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
