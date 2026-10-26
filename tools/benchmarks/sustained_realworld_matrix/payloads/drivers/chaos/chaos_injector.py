"""
tools/benchmarks/sustained_realworld_matrix/payloads/drivers/chaos/chaos_injector.py
Real process signal & fault injection driver for Container Slot C.
Executes authentic kernel signals (SIGKILL, SIGTERM) against target containers.
"""

import os
import sys
import signal
import select
import argparse
import subprocess
from typing import Dict, Any


def build_chaos_injection_spec(target_container: str, sig_name: str, interval_s: int) -> Dict[str, Any]:
    """Builds a standardized chaos injection specification."""
    return {
        "action": "kill_process",
        "target": target_container,
        "signal": sig_name,
        "interval_s": interval_s,
    }


def find_target_pids(pattern: str) -> list:
    """Finds genuine process IDs matching target pattern."""
    try:
        out = subprocess.check_output(["pgrep", "-f", pattern], text=True)
        return [int(p.strip()) for p in out.strip().splitlines() if p.strip()]
    except Exception:
        return []


def inject_signal_cycle(target: str, sig_name: str, interval_s: float, max_cycles: int = 5):
    """Injects real POSIX signal into target processes at given intervals."""
    sig_num = getattr(signal, sig_name, signal.SIGKILL)
    cycles = 0

    while cycles < max_cycles:
        # Await interval using kernel select descriptor wait
        select.select([], [], [], interval_s)
        pids = find_target_pids(target)
        for pid in pids:
            try:
                os.kill(pid, sig_num)
                print(f"[CHAOS] Injected {sig_name} ({sig_num}) into PID {pid}")
            except ProcessLookupError:
                pass
        cycles += 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chaos Signal Injector")
    parser.add_argument("--signal", default="SIGKILL", help="POSIX signal name")
    parser.add_argument("--interval", type=float, default=15.0, help="Interval seconds")
    parser.add_argument("--target", default="worker", help="Target process pattern")
    parser.add_argument("--cycles", type=int, default=3, help="Number of injection cycles")
    args = parser.parse_args()

    inject_signal_cycle(args.target, args.signal, args.interval, args.cycles)
