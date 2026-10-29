#!/usr/bin/env python3
"""
FerroOS Twelve-Dollar Challenge Service Implementation
High-concurrency Social Feed & Transactions API backed by SQLite WAL.
Designed for 4 CPU Cores & 8 GB Memory Enterprise Benchmark.
"""

import os
import sys
import time
import json
import sqlite3
import random
import argparse
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

NUM_USERS = 5000
NUM_POSTS = 25000
NUM_INITIAL_LIKES = 50000

def seed_database(db_path: str):
    """Seed SQLite database with users, posts, and likes."""
    for ext in ["", "-wal", "-shm"]:
        f = f"{db_path}{ext}"
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass

    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA journal_mode = WAL;")
    cur.execute("PRAGMA synchronous = NORMAL;")
    cur.execute("PRAGMA cache_size = -64000;")     # 64 MB Page Cache
    cur.execute("PRAGMA temp_store = MEMORY;")
    cur.execute("PRAGMA mmap_size = 268435456;")   # 256 MB MMAP
    cur.execute("PRAGMA busy_timeout = 5000;")

    cur.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            followers_count INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
        );
    """)

    cur.execute("""
        CREATE TABLE posts (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            likes_count INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)

    cur.execute("""
        CREATE TABLE likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            created_at REAL NOT NULL,
            UNIQUE(user_id, post_id)
        );
    """)

    cur.execute("CREATE INDEX idx_posts_user ON posts(user_id, created_at DESC);")
    cur.execute("CREATE INDEX idx_likes_post ON likes(post_id);")

    now = time.time()
    cur.execute("BEGIN TRANSACTION;")

    user_rows = [
        (i, f"user_{i}", f"Developer {i}", random.randint(5, 5000), now - random.randint(100, 100000))
        for i in range(1, NUM_USERS + 1)
    ]
    cur.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?);", user_rows)

    post_rows = [
        (i, random.randint(1, NUM_USERS), f"High throughput microservice transaction #{i} on 4-Core 8GB instance", random.randint(0, 100), now - random.randint(1, 50000))
        for i in range(1, NUM_POSTS + 1)
    ]
    cur.executemany("INSERT INTO posts VALUES (?, ?, ?, ?, ?);", post_rows)

    seen = set()
    like_rows = []
    while len(like_rows) < NUM_INITIAL_LIKES:
        u = random.randint(1, NUM_USERS)
        p = random.randint(1, NUM_POSTS)
        if (u, p) not in seen:
            seen.add((u, p))
            like_rows.append((u, p, now))
    cur.executemany("INSERT INTO likes (user_id, post_id, created_at) VALUES (?, ?, ?);", like_rows)

    conn.commit()
    conn.close()
    print(f"[{time.strftime('%X')}] Seeded SQLite DB ({db_path}): {NUM_USERS} users, {NUM_POSTS} posts, {NUM_INITIAL_LIKES} likes.")

class ServiceHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    _local = threading.local()
    db_path = "/tmp/feed.db"

    @classmethod
    def get_db(cls):
        if not hasattr(cls._local, "conn") or cls._local.conn is None:
            conn = sqlite3.connect(cls.db_path, timeout=10.0, check_same_thread=False)
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA cache_size = -64000;")
            conn.execute("PRAGMA mmap_size = 268435456;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            cls._local.conn = conn
        return cls._local.conn

    def do_GET(self):
        t0 = time.perf_counter()
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            self.send_json(200, {"status": "ok", "service": "twelve-dollar-service", "timestamp": time.time()}, t0)
            return

        conn = self.get_db()

        # 1. GET /users/:id
        if path.startswith("/users/") and not path.endswith("/feed"):
            try:
                user_id = int(path.split("/")[2])
                cur = conn.cursor()
                cur.execute("SELECT id, username, display_name, followers_count, created_at FROM users WHERE id = ?", (user_id,))
                row = cur.fetchone()
                if row:
                    data = {"id": row[0], "username": row[1], "display_name": row[2], "followers_count": row[3], "created_at": row[4]}
                    self.send_json(200, data, t0)
                else:
                    self.send_json(404, {"error": "User not found"}, t0)
            except Exception as e:
                self.send_json(400, {"error": str(e)}, t0)

        # 2. GET /users/:id/feed
        elif path.startswith("/users/") and path.endswith("/feed"):
            try:
                user_id = int(path.split("/")[2])
                cur = conn.cursor()
                cur.execute("""
                    SELECT p.id, p.content, p.likes_count, p.created_at, u.username, u.display_name
                    FROM posts p
                    JOIN users u ON p.user_id = u.id
                    WHERE p.user_id = ?
                    ORDER BY p.created_at DESC
                    LIMIT 20;
                """, (user_id,))
                feed = [
                    {"id": r[0], "content": r[1], "likes_count": r[2], "created_at": r[3], "author": {"username": r[4], "display_name": r[5]}}
                    for r in cur.fetchall()
                ]
                self.send_json(200, {"user_id": user_id, "feed": feed, "count": len(feed)}, t0)
            except Exception as e:
                self.send_json(400, {"error": str(e)}, t0)

        # 3. GET /posts/:id
        elif path.startswith("/posts/") and not path.endswith("/like"):
            try:
                post_id = int(path.split("/")[2])
                cur = conn.cursor()
                cur.execute("""
                    SELECT p.id, p.user_id, p.content, p.likes_count, p.created_at, u.username
                    FROM posts p
                    JOIN users u ON p.user_id = u.id
                    WHERE p.id = ?;
                """, (post_id,))
                row = cur.fetchone()
                if row:
                    data = {"id": row[0], "user_id": row[1], "content": row[2], "likes_count": row[3], "created_at": row[4], "username": row[5]}
                    self.send_json(200, data, t0)
                else:
                    self.send_json(404, {"error": "Post not found"}, t0)
            except Exception as e:
                self.send_json(400, {"error": str(e)}, t0)

        # 4. GET /metrics
        elif path == "/metrics":
            try:
                cur = conn.cursor()
                cur.execute("SELECT id, user_id, likes_count, content FROM posts ORDER BY likes_count DESC LIMIT 5;")
                trending = [{"id": r[0], "user_id": r[1], "likes": r[2], "snippet": r[3][:40]} for r in cur.fetchall()]
                cur.execute("SELECT COUNT(*) FROM likes;")
                total_likes = cur.fetchone()[0]
                self.send_json(200, {"trending": trending, "total_likes": total_likes, "engine": "WAL-SQLite3"}, t0)
            except Exception as e:
                self.send_json(500, {"error": str(e)}, t0)
        else:
            self.send_json(404, {"error": "Endpoint not found"}, t0)

    def do_POST(self):
        t0 = time.perf_counter()
        parsed = urlparse(self.path)
        path = parsed.path
        conn = self.get_db()

        # 5. POST /posts/:id/like (Atomic ACID Write to WAL)
        if path.startswith("/posts/") and path.endswith("/like"):
            try:
                post_id = int(path.split("/")[2])
                user_id = random.randint(1, NUM_USERS)
                now = time.time()
                cur = conn.cursor()

                cur.execute("INSERT OR IGNORE INTO likes (user_id, post_id, created_at) VALUES (?, ?, ?);", (user_id, post_id, now))
                cur.execute("UPDATE posts SET likes_count = likes_count + 1 WHERE id = ?;", (post_id,))
                conn.commit()

                self.send_json(200, {"status": "LIKED", "post_id": post_id, "user_id": user_id}, t0)
            except Exception as e:
                self.send_json(500, {"error": str(e)}, t0)
        else:
            self.send_json(404, {"error": "Endpoint not found"}, t0)

    def send_json(self, status_code: int, data: dict, start_time: float):
        elapsed_us = int((time.perf_counter() - start_time) * 1_000_000)
        body = json.dumps(data).encode("utf-8")
        try:
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Response-Time-Us", str(elapsed_us))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format, *args):
        # Suppress logging for benchmark throughput
        pass

def main():
    parser = argparse.ArgumentParser(description="Twelve Dollar Challenge Service")
    parser.add_argument("--host", default="0.0.0.0", help="Listen host")
    parser.add_argument("--port", type=int, default=9124, help="Listen port")
    parser.add_argument("--db", default="/tmp/feed.db", help="Path to SQLite database")
    parser.add_argument("--seed", action="store_true", help="Seed database before starting")
    args = parser.parse_args()

    ServiceHandler.db_path = args.db

    if args.seed or not os.path.exists(args.db):
        seed_database(args.db)

    server = ThreadingHTTPServer((args.host, args.port), ServiceHandler)
    server.daemon_threads = True
    print(f"[{time.strftime('%X')}] Twelve Dollar Service active on {args.host}:{args.port} (DB: {args.db})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()

if __name__ == "__main__":
    main()
