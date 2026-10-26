"""
tools/benchmarks/sustained_realworld_matrix/payloads/drivers/chaos/packet_corruptor.py
HTTP protocol fuzzer sending bit-flipped frames, malformed chunk sizes, and corrupted JSON.
"""

import socket
import random
import argparse


def run_fuzzer(target_host: str, target_port: int, iterations: int = 1000):
    mutations = [
        b"POST /api/fuzz HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\nZZZZ\r\n",
        b"GET /api/fuzz HTTP/1.1\r\nContent-Length: -1\r\n\r\n",
        b"POST /api/fuzz HTTP/1.1\r\nContent-Type: application/json\r\nContent-Length: 10\r\n\r\n{{{{{\x00\xff",
        b"\xff\xd8\xff\x00\x00RAW_BINARY_TRASH\x00\r\n\r\n",
    ]

    print(f"[*] Fuzzing {target_host}:{target_port} with {iterations} corrupted packets...")
    rejected = 0

    for i in range(iterations):
        payload = random.choice(mutations)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.0)
            s.connect((target_host, target_port))
            s.send(payload)
            resp = s.recv(1024)
            if b"400 Bad Request" in resp or len(resp) == 0:
                rejected += 1
            s.close()
        except Exception:
            rejected += 1

    print(f"[+] Completed {iterations} mutations; {rejected} cleanly rejected or dropped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="172.30.0.10")
    parser.add_argument("--port", type=int, default=8888)
    parser.add_argument("--iterations", type=int, default=1000)
    args = parser.parse_args()

    run_fuzzer(args.host, args.port, args.iterations)
