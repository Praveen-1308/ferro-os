#!/usr/bin/env python3
"""
tools/benchmarks/sustained_realworld_matrix/tests/test_harness.py
Opaque-box test harness, specifications, interface contracts, and validation logic
for the Sustained Real-World Benchmark Matrix project.
"""

import os
import sys
import json
import math
import hmac
import hashlib
import base64
import time
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple, Set


# ==============================================================================
# FEATURE 1 & 2: TARGET OS FLEET SPECIFICATIONS
# ==============================================================================

VALID_OS_TARGETS = {
    "ferro-server": {
        "name": "FerroOS Server v2.0",
        "category": "Pure-Rust Userland",
        "init": "ferro-init",
        "libc": "None (Pure Rust syscall interface)",
        "allocator": "libmimalloc.so.2",
        "io_engine": "libferro_io.so (POSIX/io_uring acceleration)",
        "security": "Landlock sandbox",
        "expected_shell": "/usr/bin/bash",
    },
    "bench-ubuntu": {
        "name": "Ubuntu 24.04 LTS Noble Numbat",
        "category": "Cloud Standard",
        "init": "systemd",
        "libc": "glibc 2.39",
        "allocator": "ptmalloc3",
        "expected_shell": "/bin/bash",
    },
    "bench-debian": {
        "name": "Debian 12 Bookworm",
        "category": "Enterprise Upstream",
        "init": "systemd",
        "libc": "glibc 2.36",
        "allocator": "ptmalloc3",
        "expected_shell": "/bin/bash",
    },
    "bench-rocky": {
        "name": "Rocky Linux 9",
        "category": "RHEL 9 Binary Compatible",
        "init": "systemd",
        "libc": "glibc 2.34",
        "allocator": "ptmalloc3",
        "expected_shell": "/bin/bash",
    },
    "almalinux:9": {
        "name": "AlmaLinux 9",
        "category": "RHEL 9 Binary Compatible",
        "init": "systemd",
        "libc": "glibc 2.34",
        "allocator": "ptmalloc3",
        "expected_shell": "/bin/bash",
    },
    "bench-alpine": {
        "name": "Alpine Linux 3.20",
        "category": "Hyper-Minimal Container",
        "init": "BusyBox init / OpenRC",
        "libc": "musl libc 1.2.5",
        "allocator": "musl allocator",
        "expected_shell": "/bin/sh",
        "exact_base": "alpine:3.20",
    },
    "amazonlinux:2023": {
        "name": "Amazon Linux 2023",
        "category": "AWS Cloud Production",
        "init": "systemd",
        "libc": "glibc 2.34",
        "allocator": "ptmalloc3",
        "expected_shell": "/bin/bash",
    },
}

def validate_os_target(target_id: str) -> Tuple[bool, Optional[str]]:
    """Validates that target_id belongs to the 7 required OS distributions."""
    if not isinstance(target_id, str):
        return False, "Target OS identifier must be a string."
    if target_id not in VALID_OS_TARGETS:
        return False, f"Unknown OS target: {target_id}. Must be one of: {list(VALID_OS_TARGETS.keys())}"
    return True, None

def validate_alpine_image_alignment(image_ref: str) -> Tuple[bool, Optional[str]]:
    """Enforces that Alpine image is strictly alpine:3.20 (musl 1.2.5) and not alpine:latest."""
    if not isinstance(image_ref, str) or not image_ref.strip():
        return False, "Image reference cannot be empty."
    clean_ref = image_ref.strip().lower()
    if "latest" in clean_ref:
        return False, "Alpine image must NOT use ':latest' tag; must pin to 3.20."
    if "3.20" not in clean_ref:
        return False, f"Alpine image must be version 3.20, got: {image_ref}"
    return True, None

def validate_ferro_command_safety(command: str) -> Tuple[bool, Optional[str]]:
    """Enforces that commands inside FerroOS invoke /usr/bin/bash or python3 directly, avoiding applet shell loops."""
    if not isinstance(command, str) or not command.strip():
        return False, "Command cannot be empty."
    cmd = command.strip()
    if cmd.startswith("sh ") or cmd == "sh" or cmd.startswith("/bin/sh"):
        return False, "FerroOS commands must invoke /usr/bin/bash or python3 directly to avoid busybox applet shell loops."
    if not (cmd.startswith("/usr/bin/bash") or cmd.startswith("bash") or cmd.startswith("python3") or cmd.startswith("/usr/bin/python3")):
        return False, f"Safe invocation requires bash or python3 entrypoint, got: {cmd[:30]}"
    return True, None


# ==============================================================================
# FEATURE 4 & 5: 3-CONTAINER TOPOLOGY & NETWORK ISOLATION
# ==============================================================================

MAX_TOTAL_CPUS = 5.0
MAX_TOTAL_RAM_GB = 10.0

SLOT_LIMITS = {
    "slot_a": {
        "cpus": 2.0,
        "memory_gb": 4.0,
        "memory_swap_gb": 4.0,
        "scratch_storage_gb": 15.0,
    },
    "slot_b": {
        "cpus": 2.0,
        "memory_gb": 4.0,
        "memory_swap_gb": 4.0,
        "scratch_storage_gb": 15.0,
    },
    "slot_c": {
        "cpus": 1.0,
        "memory_gb": 2.0,
        "memory_swap_gb": 2.0,
        "scratch_storage_gb": 5.0,
    },
}

NETWORK_SPEC = {
    "network_name": "realworld_matrix_net",
    "subnet": "172.30.0.0/16",
    "gateway": "172.30.0.1",
    "driver": "bridge",
}

def validate_topology_allocation(slots: Dict[str, Dict[str, float]]) -> Tuple[bool, Optional[str]]:
    """Validates that slot configurations conform to envelope and individual limits."""
    total_cpus = 0.0
    total_ram = 0.0
    for slot_name in ["slot_a", "slot_b", "slot_c"]:
        if slot_name not in slots:
            return False, f"Missing required slot configuration: {slot_name}"
        cfg = slots[slot_name]
        cpus = cfg.get("cpus", 0.0)
        ram = cfg.get("memory_gb", 0.0)
        if cpus <= 0.0 or ram <= 0.0:
            return False, f"Slot {slot_name} has invalid non-positive resources: cpus={cpus}, ram={ram}"
        spec = SLOT_LIMITS[slot_name]
        if cpus > spec["cpus"]:
            return False, f"Slot {slot_name} exceeds CPU limit: {cpus} > {spec['cpus']}"
        if ram > spec["memory_gb"]:
            return False, f"Slot {slot_name} exceeds RAM limit: {ram} > {spec['memory_gb']}"
        total_cpus += cpus
        total_ram += ram

    if round(total_cpus, 2) > MAX_TOTAL_CPUS:
        return False, f"Total CPU allocation {total_cpus} exceeds cap of {MAX_TOTAL_CPUS} vCPUs"
    if round(total_ram, 2) > MAX_TOTAL_RAM_GB:
        return False, f"Total RAM allocation {total_ram} GB exceeds cap of {MAX_TOTAL_RAM_GB} GB"
    return True, None

def validate_network_isolation(network_config: Dict[str, str]) -> Tuple[bool, Optional[str]]:
    """Validates Docker bridge network isolation specification."""
    if network_config.get("network_name") != NETWORK_SPEC["network_name"]:
        return False, f"Network name must be {NETWORK_SPEC['network_name']}, got {network_config.get('network_name')}"
    if network_config.get("subnet") != NETWORK_SPEC["subnet"]:
        return False, f"Network subnet must be {NETWORK_SPEC['subnet']}, got {network_config.get('subnet')}"
    if network_config.get("driver") != NETWORK_SPEC["driver"]:
        return False, f"Network driver must be bridge, got {network_config.get('driver')}"
    return True, None


# ==============================================================================
# FEATURE 6 & 7: HOST HEADROOM SAFEGUARD & PIPEFAIL ENFORCEMENT
# ==============================================================================

MIN_SAFE_HOST_RAM_GB = 6.0
EMERGENCY_ABORT_RAM_GB = 4.5
MIN_SAFE_CPU_IDLE_PCT = 20.0

@dataclass
class HostWatchdogSummary:
    samples_count: int
    violations_count: int
    min_free_ram_gb: float
    min_cpu_idle_pct: float
    emergency_abort_triggered: bool

class HostResourceWatchdog:
    """Opaque-box reference model for macOS host headroom watchdog daemon."""
    def __init__(self, sample_interval_s: float = 1.0):
        self.sample_interval_s = sample_interval_s
        self.samples: List[Dict[str, float]] = []
        self.violations_count = 0
        self.emergency_abort = False
        self._running = False

    def record_sample(self, free_ram_gb: float, cpu_idle_pct: float) -> bool:
        """Records a sample. Returns False if emergency abort triggered."""
        self.samples.append({"free_ram_gb": free_ram_gb, "cpu_idle_pct": cpu_idle_pct})
        if free_ram_gb < EMERGENCY_ABORT_RAM_GB:
            self.violations_count += 1
            self.emergency_abort = True
            return False
        if free_ram_gb < MIN_SAFE_HOST_RAM_GB or cpu_idle_pct < MIN_SAFE_CPU_IDLE_PCT:
            self.violations_count += 1
        return True

    def get_summary(self) -> HostWatchdogSummary:
        if not self.samples:
            return HostWatchdogSummary(0, 0, 0.0, 0.0, False)
        min_ram = min(s["free_ram_gb"] for s in self.samples)
        min_cpu = min(s["cpu_idle_pct"] for s in self.samples)
        return HostWatchdogSummary(
            samples_count=len(self.samples),
            violations_count=self.violations_count,
            min_free_ram_gb=round(min_ram, 2),
            min_cpu_idle_pct=round(min_cpu, 1),
            emergency_abort_triggered=self.emergency_abort,
        )

def execute_with_pipefail(command: str) -> Tuple[int, str, str]:
    """Executes a command with strict pipefail semantics and returns (exit_code, stdout, stderr)."""
    full_cmd = f"set -eo pipefail; {command}"
    proc = subprocess.run(
        ["/bin/bash", "-c", full_cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return proc.returncode, proc.stdout, proc.stderr


# ==============================================================================
# FEATURE 8 TO 13: 65 PRODUCTION SCENARIOS CATALOG
# ==============================================================================

SCENARIO_COUNTS_BY_CATEGORY = {
    "web_microservices": 15,
    "databases_state_engines": 12,
    "high_churn_io_media": 10,
    "queueing_telemetry_streaming": 10,
    "incident_radar_faults": 10,
    "deadzone_hardware_extremes": 8,
}
TOTAL_SCENARIOS_COUNT = sum(SCENARIO_COUNTS_BY_CATEGORY.values())  # 65

def build_reference_scenario_catalog() -> Dict[str, Dict[str, Any]]:
    """Builds the canonical registry of 65 production scenarios conforming to R1."""
    scenarios = {}
    
    # Category 1: Web & Microservices (15)
    web_names = [
        ("SCEN-WEB-01", "FastAPI Async JSON Serialization", "HTTP/1.1", 8000, 5.0),
        ("SCEN-WEB-02", "Express.js High Churn REST Endpoints", "HTTP/1.1", 3000, 8.0),
        ("SCEN-WEB-03", "Go Chi Lightweight HTTP Gateway", "HTTP/1.1", 8080, 2.0),
        ("SCEN-WEB-04", "Rust Axum Multi-Core Microservice", "HTTP/1.1", 8081, 1.0),
        ("SCEN-WEB-05", "Nginx Reverse Proxy & Keep-Alive Pooling", "HTTP/1.1", 80, 3.0),
        ("SCEN-WEB-06", "Nginx TLS Handshake Session Resumption", "HTTPS", 443, 10.0),
        ("SCEN-WEB-07", "GraphQL Nested Entity Resolution", "HTTP/1.1", 4000, 15.0),
        ("SCEN-WEB-08", "Django WSGI Synchronous Worker Turnover", "HTTP/1.1", 8000, 20.0),
        ("SCEN-WEB-09", "HTTP/2 Multiplexed Stream Saturation", "HTTP/2", 8443, 4.0),
        ("SCEN-WEB-10", "gRPC Protobuf Bi-Directional Streaming", "HTTP/2-gRPC", 50051, 2.5),
        ("SCEN-WEB-11", "Server-Sent Events (SSE) Fan-Out (5,000 clients)", "HTTP/1.1-SSE", 8082, 5.0),
        ("SCEN-WEB-12", "WebSocket Full-Duplex Real-Time Churn", "WS", 8083, 3.0),
        ("SCEN-WEB-13", "Resilience4j / Envoy Circuit Breaker Trips", "HTTP/1.1", 8084, 5.0),
        ("SCEN-WEB-14", "OAuth2 JWT Cryptographic Token Validation", "HTTP/1.1", 8085, 2.0),
        ("SCEN-WEB-15", "Rate Limiter Leaky Bucket Throttling", "HTTP/1.1", 8086, 1.5),
    ]
    for s_id, s_name, proto, port, sla in web_names:
        scenarios[s_id] = {
            "id": s_id, "name": s_name, "category": "web_microservices",
            "protocol": proto, "target_port": port, "sla_p95_ms": sla
        }

    # Category 2: Databases & State Engines (12)
    db_names = [
        ("SCEN-DB-01", "PostgreSQL TPC-B Transaction Ingestion", "PGSQL", 5432, 12.0),
        ("SCEN-DB-02", "SQLite WAL High-Concurrency Concurrent Read-Writes", "Embedded-WAL", 0, 4.0),
        ("SCEN-DB-03", "Redis 7 Pipelined GET/SET Cache Operations", "RESP", 6379, 1.0),
        ("SCEN-DB-04", "Redis BGSAVE Copy-on-Write Memory Pressure", "RESP", 6379, 15.0),
        ("SCEN-DB-05", "Valkey High-Throughput Cluster Sharding", "RESP", 6380, 1.2),
        ("SCEN-DB-06", "PgBouncer Connection Multiplexing (5,000 clients)", "PGSQL", 6432, 8.0),
        ("SCEN-DB-07", "SQLite FTS5 BM25 Full-Text Search Queries", "Embedded-FTS5", 0, 5.0),
        ("SCEN-DB-08", "PostgreSQL Lock Contention & Deadlock Detection", "PGSQL", 5432, 25.0),
        ("SCEN-DB-09", "PostgreSQL MVCC Table Bloat & Auto-VACUUM", "PGSQL", 5432, 30.0),
        ("SCEN-DB-10", "Redis Sorted Sets (ZSET) Leaderboard Ingestion", "RESP", 6379, 2.0),
        ("SCEN-DB-11", "Key-Value Range Scans under Continuous Writes", "KV", 7000, 6.0),
        ("SCEN-DB-12", "Connection Pool Exhaustion & Queue Backpressure", "HTTP-DB", 8090, 20.0),
    ]
    for s_id, s_name, proto, port, sla in db_names:
        scenarios[s_id] = {
            "id": s_id, "name": s_name, "category": "databases_state_engines",
            "protocol": proto, "target_port": port, "sla_p95_ms": sla
        }

    # Category 3: High-Churn I/O & Media (10)
    io_names = [
        ("SCEN-IO-01", "Multipart File Upload (1 MB - 25 MB chunks)", "HTTP-Multipart", 9000, 50.0),
        ("SCEN-IO-02", "Linux sendfile(2) Zero-Copy Kernel Transfer", "TCP-Raw", 9001, 5.0),
        ("SCEN-IO-03", "MinIO S3 Compatible Object Storage Benchmark", "S3-REST", 9002, 35.0),
        ("SCEN-IO-04", "Maildir 100,000 Small File Inode Churn", "VFS", 0, 10.0),
        ("SCEN-IO-05", "fdatasync Saturation & Disk Write Barriers", "POSIX-IO", 0, 45.0),
        ("SCEN-IO-06", "FIO Direct I/O (O_DIRECT) Kernel Bypass", "FIO-Direct", 0, 8.0),
        ("SCEN-IO-07", "libvips SIMD Multithreaded Image Transcoding", "CPU-SIMD", 0, 60.0),
        ("SCEN-IO-08", "mmap Shared Memory Concurrent Updates", "POSIX-mmap", 0, 1.5),
        ("SCEN-IO-09", "Disk Queue Saturation & Block I/O Throttling", "BlockIO", 0, 40.0),
        ("SCEN-IO-10", "Temporary File Churn & Directory Re-indexing", "POSIX-tmp", 0, 12.0),
    ]
    for s_id, s_name, proto, port, sla in io_names:
        scenarios[s_id] = {
            "id": s_id, "name": s_name, "category": "high_churn_io_media",
            "protocol": proto, "target_port": port, "sla_p95_ms": sla
        }

    # Category 4: Queueing, Telemetry & Streaming (10)
    q_names = [
        ("SCEN-Q-01", "RabbitMQ AMQP 0-9-1 Topic Exchange Fanout", "AMQP", 5672, 10.0),
        ("SCEN-Q-02", "NATS Core Pub/Sub High-Velocity Routing", "NATS", 4222, 1.0),
        ("SCEN-Q-03", "ZeroMQ PUSH/PULL Lock-Free Socket Pipeline", "ZMQ-TCP", 5555, 0.8),
        ("SCEN-Q-04", "Prometheus 10,000 Metrics/Sec Pull Scrapes", "HTTP-Prom", 9090, 15.0),
        ("SCEN-Q-05", "Vector High-Throughput JSON Log Ingestion", "TCP-Syslog", 9514, 5.0),
        ("SCEN-Q-06", "OpenTelemetry Distributed Span Ingestion", "gRPC-OTel", 4317, 8.0),
        ("SCEN-Q-07", "StatsD UDP High-Rate Metric Aggregation", "UDP", 8125, 1.0),
        ("SCEN-Q-08", "Kafka-compatible Streaming Partition Writes", "Kafka-Wire", 9092, 12.0),
        ("SCEN-Q-09", "Backpressure Event Streaming Flow Control", "TCP-Stream", 7777, 6.0),
        ("SCEN-Q-10", "Message Priority Re-ordering under Contention", "AMQP-Pri", 5673, 14.0),
    ]
    for s_id, s_name, proto, port, sla in q_names:
        scenarios[s_id] = {
            "id": s_id, "name": s_name, "category": "queueing_telemetry_streaming",
            "protocol": proto, "target_port": port, "sla_p95_ms": sla
        }

    # Category 5: Incident Radar & Fault Injection (10)
    flt_names = [
        ("SCEN-FLT-01", "TCP TIME_WAIT Ephemeral Port Exhaustion", "TCP-Churn", 8881, 10.0),
        ("SCEN-FLT-02", "Gradual Memory Leak (5 MB/sec) & Allocator Behavior", "HTTP-Leak", 8882, 12.0),
        ("SCEN-FLT-03", "Unclosed File Descriptor Leak (ulimit ceiling)", "POSIX-FD", 8883, 15.0),
        ("SCEN-FLT-04", "SIGKILL Worker Process Instant Termination & Restart", "Signal-Crash", 8884, 100.0),
        ("SCEN-FLT-05", "Zombie Process Reaping & PID Table Saturation", "Fork-Reap", 0, 20.0),
        ("SCEN-FLT-06", "Slowloris Attack Slow-Header Connection Starvation", "HTTP-Slow", 8886, 25.0),
        ("SCEN-FLT-07", "TCP Zero-Window Client Flow-Control Freeze", "TCP-Window", 8887, 30.0),
        ("SCEN-FLT-08", "Packet Corruption & Bit-Flip Checksum Rejection", "TCP-Corrupt", 8888, 15.0),
        ("SCEN-FLT-09", "Unix Domain Socket File Descriptors Unlinking", "AF_UNIX", 0, 5.0),
        ("SCEN-FLT-10", "Cascading Worker Thread Deadlock and Timeout", "Thread-Lock", 8890, 50.0),
    ]
    for s_id, s_name, proto, port, sla in flt_names:
        scenarios[s_id] = {
            "id": s_id, "name": s_name, "category": "incident_radar_faults",
            "protocol": proto, "target_port": port, "sla_p95_ms": sla
        }

    # Category 6: Deadzone & Hardware Extremes (8)
    dzn_names = [
        ("SCEN-DZN-01", "Cgroup OOM 4 GB Memory Ceiling Hard Enforcement", "OOM-Ceiling", 9991, 50.0),
        ("SCEN-DZN-02", "10,000 Concurrent Open Network Sockets", "C10K-FD", 9992, 10.0),
        ("SCEN-DZN-03", "Hackbench Context-Switch Scheduler Storm", "Context-Storm", 0, 20.0),
        ("SCEN-DZN-04", "Epoll Event Queue Saturation (100k events)", "epoll-sat", 9994, 5.0),
        ("SCEN-DZN-05", "cgroup io.max Block I/O Severe Throttling", "IO-Throttle", 0, 80.0),
        ("SCEN-DZN-06", "Fork Bomb Mitigation (pids.max boundary)", "PID-Bomb", 0, 30.0),
        ("SCEN-DZN-07", "Extreme Inode Depletion on Scratch Storage", "Inode-Limit", 0, 40.0),
        ("SCEN-DZN-08", "Raw Socket SYN Flood Defense (SYN Cookies)", "SYN-Flood", 9998, 15.0),
    ]
    for s_id, s_name, proto, port, sla in dzn_names:
        scenarios[s_id] = {
            "id": s_id, "name": s_name, "category": "deadzone_hardware_extremes",
            "protocol": proto, "target_port": port, "sla_p95_ms": sla
        }

    return scenarios


# ==============================================================================
# FEATURE 14 & 15: 0% SYNTHETIC PAYLOAD ENGINE & SLOT C GENERATOR
# ==============================================================================

def verify_zero_synthetic_payload(code_or_data: Any) -> Tuple[bool, Optional[str]]:
    """Detects and rejects mock sleep or synthetic math loops."""
    if isinstance(code_or_data, str):
        content = code_or_data.lower()
        if "time.sleep" in content or "mock" in content or "synthetic_loop" in content:
            return False, "Synthetic mock sleep or dummy loop detected in payload code."
        if "math.sin" in content and "for _ in range(1000000)" in content:
            return False, "Synthetic math loop detected."
    return True, None

def validate_sqlite_binary_header(db_bytes: bytes) -> bool:
    """Verifies that bytes begin with genuine SQLite 3 database header."""
    return db_bytes.startswith(b"SQLite format 3\x00")

def validate_jpeg_binary_header(img_bytes: bytes) -> bool:
    """Verifies that bytes begin with valid JPEG SOI marker."""
    return img_bytes.startswith(b"\xff\xd8\xff")

def validate_png_binary_header(img_bytes: bytes) -> bool:
    """Verifies that bytes begin with valid PNG signature."""
    return img_bytes.startswith(b"\x89PNG\r\n\x1a\n")

def generate_valid_jwt(secret: str, claims: Dict[str, Any]) -> str:
    """Generates an authentic RFC 7519 HMAC-SHA256 JWT."""
    header = {"alg": "HS256", "typ": "JWT"}
    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    signing_input = f"{h_b64}.{p_b64}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{h_b64}.{p_b64}.{sig_b64}"

def verify_valid_jwt(token: str, secret: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Cryptographically verifies an RFC 7519 JWT."""
    parts = token.split(".")
    if len(parts) != 3:
        return False, None
    h_b64, p_b64, sig_b64 = parts
    signing_input = f"{h_b64}.{p_b64}".encode()
    expected_sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    # Padding recovery
    pad = len(sig_b64) % 4
    if pad: sig_b64 += "=" * (4 - pad)
    try:
        actual_sig = base64.urlsafe_b64decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return False, None
        pad_p = len(p_b64) % 4
        if pad_p: p_b64 += "=" * (4 - pad_p)
        payload = json.loads(base64.urlsafe_b64decode(p_b64).decode())
        return True, payload
    except Exception:
        return False, None


# ==============================================================================
# FEATURE 16, 17 & 18: STRESS LADDER, CROSSOVER SWAPPER & VARIANCE GATE
# ==============================================================================

STRESS_LADDER_PHASES = [
    {"phase": 1, "name": "Baseline & Cold Start", "start_s": 0, "end_s": 60, "vus": "10-50"},
    {"phase": 2, "name": "Healthy Steady State", "start_s": 60, "end_s": 120, "vus": "200"},
    {"phase": 3, "name": "High Concurrency", "start_s": 120, "end_s": 180, "vus": "1000-5000"},
    {"phase": 4, "name": "Choking & Contention", "start_s": 180, "end_s": 240, "vus": "Saturated"},
    {"phase": 5, "name": "Fault Injection & Chaos", "start_s": 240, "end_s": 280, "vus": "Chaos"},
    {"phase": 6, "name": "Deadzone Boundary", "start_s": 280, "end_s": 300, "vus": "OOM-Limit"},
]

def calculate_crossover_variance_pct(metric_a: float, metric_b: float) -> float:
    """
    Computes mathematical relative variance between Slot A and Slot B runs:
    Delta = |M_A - M_B| / (0.5 * (M_A + M_B)) * 100%
    """
    if metric_a < 0 or metric_b < 0:
        raise ValueError("Metrics must be non-negative.")
    avg = 0.5 * (metric_a + metric_b)
    if avg == 0.0:
        return 0.0
    return (abs(metric_a - metric_b) / avg) * 100.0

def evaluate_placement_bias_gate(variance_pct: float) -> bool:
    """Returns True if variance < 2.5%, False otherwise."""
    return variance_pct < 2.50


# ==============================================================================
# FEATURE 19 TO 25: TELEMETRY SCHEMA, CHARTS & SCORECARD
# ==============================================================================

REQUIRED_TELEMETRY_RECORD_FIELDS = {
    "second", "traffic", "latency_ms", "cpu", "memory",
    "scheduler", "sockets", "host_headroom"
}

def validate_telemetry_dataset(dataset: List[Dict[str, Any]], expected_seconds: int = 300) -> Tuple[bool, Optional[str]]:
    """Validates that a telemetry dataset conforms to the second-by-second schema."""
    if not isinstance(dataset, list):
        return False, "Telemetry dataset must be a list."
    if len(dataset) != expected_seconds:
        return False, f"Expected {expected_seconds} second records, found {len(dataset)}."
    
    for idx, rec in enumerate(dataset):
        missing = REQUIRED_TELEMETRY_RECORD_FIELDS - set(rec.keys())
        if missing:
            return False, f"Record {idx+1} is missing required fields: {missing}"
        if rec["second"] != idx + 1:
            return False, f"Record at index {idx} has invalid second: {rec['second']}, expected {idx+1}"
        
        # Validate ranges
        lat = rec["latency_ms"]
        for k, v in lat.items():
            if not isinstance(v, (int, float)) or math.isnan(v) or math.isinf(v):
                return False, f"Record {idx+1} has NaN, Inf, or non-numeric in latency: {k}={v}"
        if lat["p50"] < 0 or lat["p95"] < lat["p50"] or lat["max"] < lat["p95"]:
            return False, f"Record {idx+1} has invalid non-monotonic latencies: {lat}"
        
        mem = rec["memory"]
        if mem["rss_mb"] < 0:
            return False, f"Record {idx+1} has negative memory RSS: {mem['rss_mb']}"
            
    return True, None

def evaluate_business_scorecard(metrics: Dict[str, Any]) -> str:
    """
    Evaluates 4-tier color-coded business qualification rating:
    - 🟢 Good/Superior: Enterprise-grade stability, sub-millisecond p99, zero unexpected drops.
    - 🟡 Acceptable: Compliant with standard enterprise SLAs (p99 <= 10ms), minor latency drift.
    - 🟠 Poor: Elevated latency tails (> 50ms), excessive memory fragmentation, or heavy throttling.
    - 🔴 Business Unacceptable: Process segfaults, silent data corruption, unrecovered deadlocks, or OOM crash.
    """
    segfaults = metrics.get("segfaults", 0)
    data_corruptions = metrics.get("data_corruptions", 0)
    unrecovered_deadlocks = metrics.get("unrecovered_deadlocks", 0)
    premature_oom = metrics.get("premature_oom", False)

    if segfaults > 0 or data_corruptions > 0 or unrecovered_deadlocks > 0 or premature_oom:
        return "🔴 Business Unacceptable"
    
    p99_latency_ms = metrics.get("p99_latency_ms", 0.0)
    unexpected_drops = metrics.get("unexpected_drops", 0)
    throttling_events = metrics.get("throttling_events", 0)

    if p99_latency_ms <= 1.0 and unexpected_drops == 0 and throttling_events == 0:
        return "🟢 Good / Superior"
    elif p99_latency_ms <= 10.0 and unexpected_drops <= 5:
        return "🟡 Acceptable"
    elif p99_latency_ms > 50.0 or throttling_events > 100 or unexpected_drops > 50:
        return "🟠 Poor"
    else:
        return "🟡 Acceptable"
