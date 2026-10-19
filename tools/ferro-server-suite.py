#!/usr/bin/env python3
"""
FerroOS Multi-Service Production Server Suite
Runs three concurrent server microservices on distinct ports:
1. Port 8080: Hardware Telemetry & REST API Service
2. Port 8081: In-Memory Key-Value Cache & State Storage Engine
3. Port 8082: Static File & Package Distribution Service
"""

import os
import sys
import time
import json
import threading
import psutil
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ==============================================================================
# SERVER 1: REST API & Telemetry Service (Port 8080)
# ==============================================================================
class TelemetryAPIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            vm = psutil.virtual_memory()
            data = {
                "server": "FerroOS Telemetry Microservice",
                "os": "FerroOS 64-Bit Hybrid",
                "kernel": os.uname().release,
                "arch": os.uname().machine,
                "cores": psutil.cpu_count(logical=True),
                "ram_total_mb": round(vm.total / (1024**2), 2),
                "ram_used_mb": round(vm.used / (1024**2), 2),
                "ram_percent": vm.percent,
                "active_processes": len(list(psutil.process_iter())),
                "timestamp": time.time()
            }
            self.send_json(200, data)
        elif parsed.path == "/api/health":
            self.send_json(200, {"status": "HEALTHY", "uptime_sec": time.time() - START_TIME})
        else:
            self.send_json(404, {"error": "Endpoint not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/echo":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                payload = json.loads(body)
                self.send_json(200, {"echo": payload, "received_at": time.time()})
            except Exception as e:
                self.send_json(400, {"error": "Invalid JSON", "details": str(e)})
        else:
            self.send_json(404, {"error": "Endpoint not found"})

    def send_json(self, code, data):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass # Suppress noisy stdout logs during benchmarks

# ==============================================================================
# SERVER 2: Key-Value In-Memory Storage Engine (Port 8081)
# ==============================================================================
KV_STORE = {}
KV_LOCK = threading.Lock()

class KeyValueHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/get":
            qs = parse_qs(parsed.query)
            key = qs.get("key", [None])[0]
            with KV_LOCK:
                if key and key in KV_STORE:
                    self.send_json(200, {"key": key, "value": KV_STORE[key]})
                else:
                    self.send_json(404, {"error": f"Key '{key}' not found"})
        elif parsed.path == "/keys":
            with KV_LOCK:
                self.send_json(200, {"total_keys": len(KV_STORE), "keys": list(KV_STORE.keys())})
        elif parsed.path == "/health":
            self.send_json(200, {"status": "KV_RUNNING", "entries": len(KV_STORE)})
        else:
            self.send_json(404, {"error": "Endpoint not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/set":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                key = data.get("key")
                val = data.get("value")
                if not key:
                    self.send_json(400, {"error": "Missing key in payload"})
                    return
                with KV_LOCK:
                    KV_STORE[key] = val
                self.send_json(200, {"status": "STORED", "key": key, "value": val})
            except Exception as e:
                self.send_json(400, {"error": "Malformed request", "details": str(e)})
        else:
            self.send_json(404, {"error": "Endpoint not found"})

    def send_json(self, code, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass

# ==============================================================================
# SERVER 3: Static Asset & Package Repository Service (Port 8082)
# ==============================================================================
STATIC_ROOT = "/tmp/ferro_static_repo"
os.makedirs(STATIC_ROOT, exist_ok=True)
with open(f"{STATIC_ROOT}/manifest.json", "w") as f:
    json.dump({
        "repository": "FerroOS Official Package Registry",
        "packages": ["ferro-core", "ferro-gui", "ferro-pkg", "firefox", "htop"],
        "architecture": "aarch64",
        "generated_at": time.time()
    }, f, indent=2)

class StaticRepoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        req_path = parsed.path.lstrip("/")
        if not req_path:
            req_path = "manifest.json"
        
        target = os.path.join(STATIC_ROOT, req_path)
        if os.path.exists(target) and os.path.isfile(target):
            with open(target, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json" if target.endswith(".json") else "text/plain")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            body = b'{"error": "Asset not found"}'
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, format, *args):
        pass

# ==============================================================================
# Supervisor Entrypoint
# ==============================================================================
START_TIME = time.time()

def run_server(server_class, handler_class, port, name):
    server = server_class(("0.0.0.0", port), handler_class)
    print(f"[{name}] Listening on http://0.0.0.0:{port}")
    server.serve_forever()

if __name__ == "__main__":
    print("=================================================================")
    print("        FERRO-OS MULTI-SERVICE SERVER WORKLOAD SUPERVISOR        ")
    print("=================================================================")

    # Spawn 3 server threads
    t1 = threading.Thread(target=run_server, args=(HTTPServer, TelemetryAPIHandler, 8080, "REST API Server"), daemon=True)
    t2 = threading.Thread(target=run_server, args=(HTTPServer, KeyValueHandler, 8081, "KV Cache Server"), daemon=True)
    t3 = threading.Thread(target=run_server, args=(HTTPServer, StaticRepoHandler, 8082, "Static Asset Server"), daemon=True)

    t1.start()
    t2.start()
    t3.start()

    print("\n✅ All 3 server microservices successfully launched and bound!")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down server suite...")
