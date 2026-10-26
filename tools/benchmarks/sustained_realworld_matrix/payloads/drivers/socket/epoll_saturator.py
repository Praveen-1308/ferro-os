"""
tools/benchmarks/sustained_realworld_matrix/payloads/drivers/socket/epoll_saturator.py
Floods 100,000 ready signals/sec across thousands of open sockets to saturate SUT epoll queue.
"""

import socket
import select
import argparse
from typing import List


def run_epoll_saturator(target_host: str, target_port: int, num_sockets: int = 5000, event_rate: int = 100000, duration_s: int = 10):
    sockets: List[socket.socket] = []
    print(f"[*] Connecting {num_sockets} sockets to {target_host}:{target_port}...")

    for _ in range(num_sockets):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect((target_host, target_port))
            sockets.append(s)
        except Exception:
            break

    print(f"[+] Connected {len(sockets)} sockets; pulsing ready bytes...")
    elapsed = 0.0
    while elapsed < duration_s and sockets:
        for s in sockets:
            try:
                s.send(b"\x01")
            except Exception:
                pass
        select.select([], [], [], 0.05)
        elapsed += 0.05

    for s in sockets:
        try:
            s.close()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="172.30.0.10")
    parser.add_argument("--port", type=int, default=9994)
    parser.add_argument("--sockets", type=int, default=5000)
    parser.add_argument("--event-rate", type=int, default=100000)
    parser.add_argument("--duration", type=int, default=10)
    args = parser.parse_args()

    run_epoll_saturator(args.host, args.port, args.sockets, args.event_rate, args.duration)
