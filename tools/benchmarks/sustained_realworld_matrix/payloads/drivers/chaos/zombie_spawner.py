"""
tools/benchmarks/sustained_realworld_matrix/payloads/drivers/chaos/zombie_spawner.py
Subshell spawner creating short-lived child processes that exit without waitpid(),
generating zombie processes to evaluate init reaper performance.
"""

import os
import sys
import select
import argparse


def spawn_zombies(count: int = 500, hold_s: float = 10.0):
    pids = []
    print(f"[*] Spawning {count} child processes without waitpid()...")

    for _ in range(count):
        try:
            pid = os.fork()
            if pid == 0:
                os._exit(0)
            else:
                pids.append(pid)
        except Exception:
            break

    print(f"[+] Spawned {len(pids)} defunct children; holding for init reaper...")
    select.select([], [], [], hold_s)

    # Clean up any remaining zombies
    for pid in pids:
        try:
            os.waitpid(pid, os.WNOHANG)
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fork-rate", type=int, default=500)
    parser.add_argument("--duration", type=float, default=10.0)
    args = parser.parse_args()

    spawn_zombies(args.fork_rate, args.duration)
