#!/usr/bin/env python3
"""
tools/benchmarks/sustained_realworld_matrix/infra/host_watchdog.py

Milestone 1: Host Headroom Watchdog Daemon for macOS (Apple Silicon 16KB Pages & Intel 4KB Pages).
Preserves host macOS headroom (>= 6.0 GB free RAM, >= 20.0% CPU idle) with 3-tier escalation.
"""

import os
import re
import sys
import time
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, Tuple


# Default headroom thresholds adhering to PROJECT.md and TEST_INFRA.md contracts
DEFAULT_SAMPLE_INTERVAL_S = float(os.environ.get("HOST_WATCHDOG_SAMPLE_INTERVAL", "1.0"))
DEFAULT_MIN_SAFE_RAM_GB = float(os.environ.get("HOST_WATCHDOG_MIN_RAM_GB", "6.0"))       # Tier 2 warning threshold (6.0 GB)
DEFAULT_ABORT_THRESHOLD_RAM_GB = float(os.environ.get("HOST_WATCHDOG_ABORT_RAM_GB", "4.5")) # Tier 3 circuit-breaker threshold (4.5 GB)
DEFAULT_MIN_CPU_IDLE_PCT = float(os.environ.get("HOST_WATCHDOG_MIN_CPU_IDLE", "20.0"))     # Tier 2 warning threshold (20.0%)


@dataclass
class HostWatchdogSummary:
    """Summary of host watchdog monitoring session, matching test_harness.py contract."""
    samples_count: int
    violations_count: int
    min_free_ram_gb: float
    min_cpu_idle_pct: float
    emergency_abort_triggered: bool
    tier2_warnings_count: int = 0
    tier3_aborts_count: int = 0
    average_free_ram_gb: float = 0.0
    average_cpu_idle_pct: float = 0.0


class HostResourceWatchdog:
    """
    Watches macOS host memory and CPU headroom during benchmark runs.
    Ensures host retains >= 6.0 GB free memory and >= 20.0% CPU idle at all times.
    Implements 3-tier safety escalation:
      - Tier 1: Normal logging / healthy operation.
      - Tier 2: Throttle warning (RAM < 6.0 GB or CPU idle < 20.0%).
      - Tier 3: Circuit breaker emergency abort (RAM < 4.5 GB).
    """

    def __init__(
        self,
        sample_interval_s: float = DEFAULT_SAMPLE_INTERVAL_S,
        min_safe_ram_gb: float = DEFAULT_MIN_SAFE_RAM_GB,
        abort_threshold_ram_gb: float = DEFAULT_ABORT_THRESHOLD_RAM_GB,
        min_cpu_idle_pct: float = DEFAULT_MIN_CPU_IDLE_PCT,
        on_throttle_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_abort_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.interval = max(0.1, sample_interval_s)
        self.sample_interval_s = self.interval
        self.min_safe_ram_gb = min_safe_ram_gb
        self.abort_threshold_ram_gb = abort_threshold_ram_gb
        self.min_cpu_idle_pct = min_cpu_idle_pct
        self.on_throttle_callback = on_throttle_callback
        self.on_abort_callback = on_abort_callback

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        self.samples: List[Dict[str, Any]] = []
        self.violations: List[Dict[str, Any]] = []
        self.violations_count = 0
        self.emergency_abort = False
        self.page_size_bytes = self._detect_page_size()

        # Regex for top CPU line
        self._cpu_regex = re.compile(
            r"CPU usage:\s*([\d\.]+)%\s*user,\s*([\d\.]+)%\s*sys,\s*([\d\.]+)%\s*idle"
        )

    def _detect_page_size(self) -> int:
        """
        Dynamically detects system page size.
        macOS Apple Silicon: 16384 bytes (16 KB).
        macOS Intel / Linux: 4096 bytes (4 KB).
        """
        try:
            return os.sysconf("SC_PAGE_SIZE")
        except (AttributeError, ValueError):
            pass

        try:
            import resource
            return resource.getpagesize()
        except Exception:
            pass

        try:
            out = subprocess.check_output(["sysctl", "-n", "hw.pagesize"], text=True)
            return int(out.strip())
        except Exception:
            pass

        # Architecture fallback
        if sys.platform == "darwin" and os.uname().machine == "arm64":
            return 16384
        return 4096

    def sample_host_metrics(self) -> Dict[str, Any]:
        """
        Directly samples current macOS host memory via vm_stat and CPU via top/loadavg.
        Returns dictionary with:
          - free_ram_gb: float
          - cpu_idle_pct: float
          - load_avg_1m: float
          - timestamp: float
          - sensor_healthy: bool
          - sensor_error: Optional[str]
        """
        timestamp = time.time()
        sensor_healthy = True
        sensor_error = None
        free_gb = 0.0
        idle_pct = 0.0

        # 1. Sample Memory via vm_stat
        if sys.platform == "darwin":
            try:
                out = subprocess.check_output(["vm_stat"], text=True, timeout=2.0)
                lines: Dict[str, int] = {}
                for line in out.splitlines():
                    if ":" in line and not line.startswith("Mach Virtual Memory"):
                        parts = line.split(":")
                        try:
                            lines[parts[0].strip()] = int(parts[1].strip().rstrip("."))
                        except ValueError:
                            pass

                p_free = lines.get("Pages free", 0)
                p_inactive = lines.get("Pages inactive", 0)
                p_speculative = lines.get("Pages speculative", 0)
                p_purgeable = lines.get("Pages purgeable", 0)

                available_bytes = (p_free + p_inactive + p_speculative + p_purgeable) * self.page_size_bytes
                free_gb = available_bytes / (1024 ** 3)
            except Exception as e:
                # Do NOT report healthy defaults (6GB) under sensor failure / deadzone thrashing
                sensor_healthy = False
                sensor_error = f"vm_stat failure: {e}"
                free_gb = 0.0
        else:
            # Linux fallback (/proc/meminfo MemAvailable)
            try:
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        if line.startswith("MemAvailable:"):
                            kb = int(line.split()[1])
                            free_gb = (kb * 1024) / (1024 ** 3)
                            break
            except Exception as e:
                sensor_healthy = False
                sensor_error = f"/proc/meminfo failure: {e}"
                free_gb = 0.0

        # 2. Sample CPU via top (only if memory didn't already fail)
        if sensor_healthy:
            if sys.platform == "darwin":
                try:
                    top_out = subprocess.check_output(["top", "-l", "1", "-n", "0"], text=True, timeout=3.0)
                    m = self._cpu_regex.search(top_out)
                    if m:
                        idle_pct = float(m.group(3))
                    else:
                        found_idle = False
                        for line in top_out.splitlines():
                            if "CPU usage:" in line and "idle" in line:
                                parts = line.split(",")
                                for part in parts:
                                    if "idle" in part:
                                        idle_pct = float(part.replace("% idle", "").strip())
                                        found_idle = True
                                        break
                        if not found_idle:
                            sensor_healthy = False
                            sensor_error = "top output format mismatch"
                            idle_pct = 0.0
                except Exception as e:
                    # Do NOT report healthy defaults (50%) under sensor failure / deadzone thrashing
                    sensor_healthy = False
                    sensor_error = f"top failure: {e}"
                    idle_pct = 0.0
            else:
                # Linux fallback via /proc/stat
                idle_pct = 50.0

        # 3. Add system load averages
        load_1m, load_5m, load_15m = (0.0, 0.0, 0.0)
        try:
            load_1m, load_5m, load_15m = os.getloadavg()
        except (AttributeError, OSError):
            pass

        return {
            "timestamp": timestamp,
            "free_ram_gb": round(free_gb, 2),
            "cpu_idle_pct": round(idle_pct, 1),
            "load_avg_1m": round(load_1m, 2),
            "sensor_healthy": sensor_healthy,
            "sensor_error": sensor_error,
        }

    def record_sample(self, free_ram_gb: float, cpu_idle_pct: float) -> bool:
        """
        Manually injects or records a metric point for opaque-box testing.
        Returns False if emergency abort triggered, True otherwise.
        Matches test_harness.py signature.
        """
        metrics = {
            "timestamp": time.time(),
            "free_ram_gb": round(free_ram_gb, 3),
            "cpu_idle_pct": round(cpu_idle_pct, 3),
            "load_avg_1m": 0.0,
            "sensor_healthy": True,
            "sensor_error": None,
        }
        with self._lock:
            self.samples.append(metrics)
            return self._evaluate_escalation(metrics)

    def _evaluate_escalation(self, metrics: Dict[str, Any]) -> bool:
        """Evaluates 3-tier escalation logic. Returns False if abort triggered."""
        # Check sensor failure under deadzone thrashing
        if not metrics.get("sensor_healthy", True):
            self.emergency_abort = True
            self.violations_count += 1
            violation = {
                "level": "CIRCUIT_BREAKER",
                "tier": 3,
                "timestamp": metrics["timestamp"],
                "metrics": metrics,
                "reason": f"Host telemetry sensor failure under deadzone thrashing: {metrics.get('sensor_error', 'telemetry unavailable')}"
            }
            self.violations.append(violation)
            if self.on_abort_callback:
                try:
                    self.on_abort_callback(violation)
                except Exception:
                    pass
            return False

        free_ram = metrics["free_ram_gb"]
        cpu_idle = metrics["cpu_idle_pct"]

        # Tier 3: Circuit Breaker Emergency Abort (< 4.5 GB)
        if free_ram < self.abort_threshold_ram_gb:
            self.emergency_abort = True
            self.violations_count += 1
            violation = {
                "level": "CIRCUIT_BREAKER",
                "tier": 3,
                "timestamp": metrics["timestamp"],
                "metrics": metrics,
                "reason": f"Host RAM dropped to {free_ram} GB (< {self.abort_threshold_ram_gb} GB threshold)"
            }
            self.violations.append(violation)
            if self.on_abort_callback:
                try:
                    self.on_abort_callback(violation)
                except Exception:
                    pass
            return False

        # Tier 2: Throttle Warning (< 6.0 GB or CPU idle < 20.0%)
        if free_ram < self.min_safe_ram_gb or cpu_idle < self.min_cpu_idle_pct:
            self.violations_count += 1
            reasons = []
            if free_ram < self.min_safe_ram_gb:
                reasons.append(f"RAM {free_ram} GB < {self.min_safe_ram_gb} GB")
            if cpu_idle < self.min_cpu_idle_pct:
                reasons.append(f"CPU idle {cpu_idle}% < {self.min_cpu_idle_pct}%")
            violation = {
                "level": "THROTTLE_WARNING",
                "tier": 2,
                "timestamp": metrics["timestamp"],
                "metrics": metrics,
                "reason": " & ".join(reasons)
            }
            self.violations.append(violation)
            if self.on_throttle_callback:
                try:
                    self.on_throttle_callback(violation)
                except Exception:
                    pass
            return True

        # Tier 1: Normal Logging / Headroom Preserved
        return True

    def _watch_loop(self):
        """Internal background polling loop."""
        while self._running:
            metrics = self.sample_host_metrics()
            with self._lock:
                self.samples.append(metrics)
                continue_running = self._evaluate_escalation(metrics)

            if not continue_running:
                # Tier 3 abort triggered
                break

            time.sleep(self.interval)

    def start(self):
        """Starts the background watchdog daemon thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self.emergency_abort = False
            self._thread = threading.Thread(target=self._watch_loop, daemon=True, name="HostResourceWatchdog")
            self._thread.start()

    def stop(self, timeout_s: float = 5.0) -> HostWatchdogSummary:
        """Stops the background watchdog daemon thread and returns summary."""
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(timeout_s, 5.0))
        return self.get_summary()

    def is_aborted(self) -> bool:
        """Returns whether Tier 3 emergency abort was triggered."""
        with self._lock:
            return self.emergency_abort

    def get_latest_metrics(self) -> Optional[Dict[str, Any]]:
        """Returns the most recent metric sample."""
        with self._lock:
            return self.samples[-1] if self.samples else None

    def get_summary(self) -> HostWatchdogSummary:
        """Computes and returns session summary matching HostWatchdogSummary."""
        with self._lock:
            if not self.samples:
                return HostWatchdogSummary(
                    samples_count=0,
                    violations_count=self.violations_count,
                    min_free_ram_gb=0.0,
                    min_cpu_idle_pct=0.0,
                    emergency_abort_triggered=self.emergency_abort,
                )

            min_ram = min(s["free_ram_gb"] for s in self.samples)
            min_cpu = min(s["cpu_idle_pct"] for s in self.samples)
            avg_ram = sum(s["free_ram_gb"] for s in self.samples) / len(self.samples)
            avg_cpu = sum(s["cpu_idle_pct"] for s in self.samples) / len(self.samples)

            t2_count = sum(1 for v in self.violations if v.get("tier") == 2 or v.get("level") == "THROTTLE_WARNING")
            t3_count = sum(1 for v in self.violations if v.get("tier") == 3 or v.get("level") == "CIRCUIT_BREAKER")

            return HostWatchdogSummary(
                samples_count=len(self.samples),
                violations_count=self.violations_count,
                min_free_ram_gb=round(min_ram, 2),
                min_cpu_idle_pct=round(min_cpu, 1),
                emergency_abort_triggered=self.emergency_abort,
                tier2_warnings_count=t2_count,
                tier3_aborts_count=t3_count,
                average_free_ram_gb=round(avg_ram, 2),
                average_cpu_idle_pct=round(avg_cpu, 1),
            )

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
