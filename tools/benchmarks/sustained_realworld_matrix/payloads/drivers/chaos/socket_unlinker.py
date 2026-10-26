"""
tools/benchmarks/sustained_realworld_matrix/payloads/drivers/chaos/socket_unlinker.py
Unlinks active Unix Domain Socket from filesystem to test automatic re-bind recovery.
"""

import os
import select
import argparse


def unlink_socket(socket_path: str, delay_s: float = 5.0):
    print(f"[*] Awaiting {delay_s}s before unlinking {socket_path}...")
    select.select([], [], [], delay_s)
    if os.path.exists(socket_path):
        try:
            os.unlink(socket_path)
            print(f"[+] Successfully unlinked socket: {socket_path}")
        except Exception as e:
            print(f"[-] Failed to unlink {socket_path}: {e}")
    else:
        print(f"[-] Socket path {socket_path} does not exist.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket-path", default="/tmp/matrix_ipc.sock")
    parser.add_argument("--unlink-second", type=float, default=5.0)
    args = parser.parse_args()

    unlink_socket(args.socket_path, args.unlink_second)
