#!/usr/bin/env python3
"""
tools/choke_server.py - High-Concurrency Twelve Dollar Challenge API Server
Built exclusively on standard library (asyncio, sqlite3, json, time) to run
identically inside both Ubuntu 24.04 and FerroOS containers without external wheels.
"""

import os
import sys
import time
import json
import sqlite3
import asyncio
import signal

DB_PATH = os.environ.get("SQLITE_PATH", "/tmp/choke_feed.db")
PORT = int(os.environ.get("PORT", "9200"))
HOST = os.environ.get("HOST", "0.0.0.0")

# Setup SQLite Database if not present
def init_db(path):
    conn = sqlite3.connect(path, timeout=10.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA cache_size = -64000;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA mmap_size = 268435456;")
    conn.execute("PRAGMA busy_timeout = 5000;")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            followers_count INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            likes_count INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            created_at REAL NOT NULL,
            UNIQUE(user_id, post_id)
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_user ON posts(user_id, created_at DESC);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_likes_post ON likes(post_id);")

    # Check if seeded
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM users;")
    count = cur.fetchone()[0]
    if count < 5000:
        print("🌱 Seeding 5,000 users and 25,000 posts for choke test...")
        conn.execute("BEGIN TRANSACTION;")
        now = time.time()
        users = [(i, f"user_{i}", f"Coder {i}", (i * 7) % 500, now - (i * 10)) for i in range(1, 5001)]
        conn.executemany("INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?, ?);", users)

        posts = [(i, (i % 5000) + 1, f"Post #{i} testing $12 challenge limits", (i * 3) % 50, now - (i * 5)) for i in range(1, 25001)]
        conn.executemany("INSERT OR REPLACE INTO posts VALUES (?, ?, ?, ?, ?);", posts)

        likes = []
        for i in range(1, 20000):
            likes.append((i, (i % 5000) + 1, (i % 25000) + 1, now))
        conn.executemany("INSERT OR IGNORE INTO likes (id, user_id, post_id, created_at) VALUES (?, ?, ?, ?);", likes)
        conn.execute("COMMIT;")
        print("✅ Seeding complete.")
    conn.close()

class ChokeServer:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self.conn.execute("PRAGMA synchronous = NORMAL;")
        self.conn.execute("PRAGMA cache_size = -64000;")
        self.conn.execute("PRAGMA temp_store = MEMORY;")
        self.conn.execute("PRAGMA mmap_size = 268435456;")
        self.conn.execute("PRAGMA busy_timeout = 5000;")

    def handle_request(self, method, path, body):
        cur = self.conn.cursor()
        t0 = time.perf_counter()

        # 1. GET /feed (Global Feed)
        if method == "GET" and path == "/feed":
            try:
                cur.execute("""
                    SELECT p.id, p.content, p.likes_count, p.created_at, u.username
                    FROM posts p JOIN users u ON p.user_id = u.id
                    ORDER BY p.created_at DESC, p.id DESC LIMIT 20;
                """)
                rows = cur.fetchall()
                feed = [{"id": r[0], "content": r[1], "likes": r[2], "created_at": r[3], "author": r[4]} for r in rows]
                return 200, {"feed": feed, "count": len(feed)}
            except Exception as e:
                return 500, {"error": str(e)}

        # 1b. GET /users/:id/feed
        elif method == "GET" and path.startswith("/users/") and path.endswith("/feed"):
            try:
                user_id = int(path.split("/")[2])
                cur.execute("""
                    SELECT p.id, p.content, p.likes_count, p.created_at, u.username
                    FROM posts p JOIN users u ON p.user_id = u.id
                    WHERE p.user_id = ?
                    ORDER BY p.created_at DESC LIMIT 20;
                """, (user_id,))
                rows = cur.fetchall()
                feed = [{"id": r[0], "content": r[1], "likes": r[2], "created_at": r[3], "author": r[4]} for r in rows]
                return 200, {"user_id": user_id, "feed": feed, "count": len(feed)}
            except Exception as e:
                return 400, {"error": str(e)}

        # 2. GET /users/:id
        elif method == "GET" and path.startswith("/users/"):
            try:
                user_id = int(path.split("/")[2])
                cur.execute("SELECT id, username, display_name, followers_count, created_at FROM users WHERE id = ?", (user_id,))
                row = cur.fetchone()
                if row:
                    return 200, {"id": row[0], "username": row[1], "display_name": row[2], "followers": row[3], "created_at": row[4]}
                return 404, {"error": "User not found"}
            except Exception as e:
                return 400, {"error": str(e)}

        # 3. GET /posts/:id
        elif method == "GET" and path.startswith("/posts/") and not path.endswith("/like"):
            try:
                post_id = int(path.split("/")[2])
                cur.execute("SELECT p.id, p.content, p.likes_count, p.created_at, u.username FROM posts p JOIN users u ON p.user_id = u.id WHERE p.id = ?", (post_id,))
                row = cur.fetchone()
                if row:
                    return 200, {"id": row[0], "content": row[1], "likes": row[2], "created_at": row[3], "author": row[4]}
                return 404, {"error": "Post not found"}
            except Exception as e:
                return 400, {"error": str(e)}

        # 4. POST /posts/:id/like (ACID Transaction)
        elif method == "POST" and path.startswith("/posts/") and path.endswith("/like"):
            try:
                post_id = int(path.split("/")[2])
                user_id = (post_id % 5000) + 1
                now = time.time()
                cur.execute("BEGIN IMMEDIATE;")
                cur.execute("INSERT OR IGNORE INTO likes (user_id, post_id, created_at) VALUES (?, ?, ?);", (user_id, post_id, now))
                cur.execute("UPDATE posts SET likes_count = likes_count + 1 WHERE id = ?;", (post_id,))
                cur.execute("COMMIT;")
                return 200, {"status": "liked", "post_id": post_id}
            except Exception as e:
                cur.execute("ROLLBACK;")
                return 500, {"error": str(e)}

        # 4b. POST /posts (ACID Create Post)
        elif method == "POST" and path == "/posts":
            try:
                now = time.time()
                cur.execute("BEGIN IMMEDIATE;")
                cur.execute("INSERT INTO posts (user_id, content, likes_count, created_at) VALUES (?, ?, 0, ?);", (1, "New post testing choke capacity", now))
                new_id = cur.lastrowid
                cur.execute("COMMIT;")
                return 201, {"status": "created", "post_id": new_id}
            except Exception as e:
                cur.execute("ROLLBACK;")
                return 500, {"error": str(e)}
        elif method == "GET" and path == "/metrics":
            try:
                cur.execute("SELECT id, likes_count, content FROM posts ORDER BY likes_count DESC LIMIT 5;")
                trending = [{"id": r[0], "likes": r[1], "content": r[2][:30]} for r in cur.fetchall()]
                return 200, {"trending": trending}
            except Exception as e:
                return 500, {"error": str(e)}

        return 404, {"error": "Not found"}

    async def client_handler(self, reader, writer):
        buffer = b""
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                line_str = line.decode("latin1").strip()
                if not line_str:
                    continue

                parts = line_str.split()
                if len(parts) < 2:
                    break
                method, path = parts[0], parts[1]

                content_len = 0
                close_connection = False

                while True:
                    hdr_line = await reader.readline()
                    if not hdr_line or hdr_line == b"\r\n" or hdr_line == b"\n":
                        break
                    hdr_lower = hdr_line.lower()
                    if hdr_lower.startswith(b"content-length:"):
                        content_len = int(hdr_line.split(b":", 1)[1].strip())
                    elif hdr_lower.startswith(b"connection:") and b"close" in hdr_lower:
                        close_connection = True

                body = b""
                if content_len > 0:
                    body = await reader.readexactly(content_len)

                status_code, resp_obj = self.handle_request(method, path, body)
                payload = json.dumps(resp_obj).encode("utf-8")
                
                conn_header = b"Connection: close\r\n" if close_connection else b"Connection: keep-alive\r\n"
                status_text = b"200 OK" if status_code == 200 else (b"404 Not Found" if status_code == 404 else b"500 Internal Error")
                header = (
                    b"HTTP/1.1 " + status_text + b"\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Content-Length: " + str(len(payload)).encode() + b"\r\n"
                    + conn_header +
                    b"\r\n"
                )
                writer.write(header + payload)
                await writer.drain()

                if close_connection:
                    break

        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

async def main():
    init_db(DB_PATH)
    server_app = ChokeServer(DB_PATH)
    server = await asyncio.start_server(server_app.client_handler, HOST, PORT, backlog=8192)
    print(f"🚀 [ChokeServer] Listening on {HOST}:{PORT} (DB: {DB_PATH})...", flush=True)
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
