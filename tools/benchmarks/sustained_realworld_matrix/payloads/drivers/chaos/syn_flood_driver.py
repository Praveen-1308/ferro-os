"""
tools/benchmarks/sustained_realworld_matrix/payloads/drivers/chaos/syn_flood_driver.py
High-rate TCP connection attempt generator testing kernel listen backlog & SYN cookies defense.
"""

import socket
import argparse


def run_syn_flood(target_host: str, target_port: int, rate: int = 10000, duration_s: int = 10):
    print(f"[*] Blasting TCP connection attempts to {target_host}:{target_port} at target rate {rate}...")
    count = 0

    for i in range(rate):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setblocking(False)
            s.connect_ex((target_host, target_port))
            s.close()
            count += 1
        except Exception:
            pass

    print(f"[+] Completed {count} SYN bursts.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-ip", default="172.30.0.10")
    parser.add_argument("--port", type=int, default=9998)
    parser.add_argument("--rate", type=int, default=10000)
    args = parser.parse_args()

    run_syn_flood(args.target_ip, args.port, args.rate)
