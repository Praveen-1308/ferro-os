"""
tools/benchmarks/sustained_realworld_matrix/payloads/drivers/socket/c10k_connector.py
Slot C driver establishing and holding up to 10,000 live TCP connections against SUT.
"""

import socket
import select
import argparse
from typing import List


def run_c10k(target_host: str, target_port: int, target_conns: int = 10000, duration_s: int = 60):
    sockets: List[socket.socket] = []
    print(f"[*] Establishing up to {target_conns} TCP sockets to {target_host}:{target_port}...")

    for i in range(target_conns):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect((target_host, target_port))
            sockets.append(s)
            if len(sockets) % 1000 == 0:
                print(f"[+] Connected {len(sockets)} sockets...")
        except Exception as e:
            print(f"[-] Stopped at {len(sockets)} connections: {e}")
            break

    print(f"[+] Holding {len(sockets)} active connections for {duration_s}s...")
    select.select([], [], [], float(duration_s))

    for s in sockets:
        try:
            s.close()
        except Exception:
            pass
    print("[+] All sockets closed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="172.30.0.10")
    parser.add_argument("--port", type=int, default=9992)
    parser.add_argument("--connections", type=int, default=10000)
    parser.add_argument("--duration", type=int, default=60)
    args = parser.parse_args()

    run_c10k(args.host, args.port, args.connections, args.duration)
