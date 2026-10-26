"""
tools/benchmarks/sustained_realworld_matrix/payloads/drivers/chaos/fork_bomb_bounded.py
Bounded recursive process forker testing cgroup pids.max ceiling (2048 pids).
"""

import os
import sys
import select
import argparse


def bounded_fork(ceiling: int = 2048):
    pids = []
    print(f"[*] Forking bounded processes up to ceiling={ceiling}...")

    try:
        while len(pids) < ceiling:
            pid = os.fork()
            if pid == 0:
                # Child process waits for parent signal then exits
                select.select([], [], [], 30.0)
                os._exit(0)
            else:
                pids.append(pid)
    except BlockingIOError:
        print(f"[+] Reached kernel / cgroup pids limit at {len(pids)} processes (EAGAIN).")
    except OSError as e:
        print(f"[+] Fork blocked as expected: {e} at count {len(pids)}")

    print(f"[+] Reaping {len(pids)} child processes...")
    for pid in pids:
        try:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
        except Exception:
            pass
    print("[+] All children reaped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ceiling", type=int, default=2048)
    args = parser.parse_args()

    bounded_fork(args.ceiling)
