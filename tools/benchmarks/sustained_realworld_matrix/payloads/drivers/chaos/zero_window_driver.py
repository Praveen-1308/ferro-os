"""
tools/benchmarks/sustained_realworld_matrix/payloads/drivers/chaos/zero_window_driver.py
TCP Zero-Window flow control freeze driver.
Reads initial bytes, stops draining socket, and causes OS TCP receive buffer to fill up.
"""

import socket
import select
import argparse
from typing import List


def run_zero_window(target_host: str, target_port: int, num_clients: int = 100, duration_s: int = 60):
    sockets: List[socket.socket] = []
    print(f"[*] Connecting {num_clients} Zero-Window clients to {target_host}:{target_port}...")

    for i in range(num_clients):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Restrict receive buffer to minimal size to force zero-window quickly
            s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2048)
            s.connect((target_host, target_port))
            s.send(b"GET /stream_large HTTP/1.1\r\nHost: matrix-sut\r\n\r\n")
            # Read first chunk
            s.recv(1024)
            sockets.append(s)
        except Exception:
            pass

    print(f"[+] Holding {len(sockets)} TCP sockets with zero read drain...")
    # Kernel will advertise win 0 when socket receive buffer is full
    select.select([], [], [], float(duration_s))

    for s in sockets:
        try:
            s.close()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="172.30.0.10")
    parser.add_argument("--port", type=int, default=8887)
    parser.add_argument("--clients", type=int, default=100)
    parser.add_argument("--duration", type=int, default=60)
    args = parser.parse_args()

    run_zero_window(args.host, args.port, args.clients, args.duration)
