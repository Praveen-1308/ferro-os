"""
tools/benchmarks/sustained_realworld_matrix/scenarios/incident_faults.py
Category 5: Incident Radar & Engineering Faults (10 Scenarios: SCEN-FLT-01 to SCEN-FLT-10).
Authoritative, zero-synthetic incident simulations: socket exhaustion, memory leaks, FD limits, SIGKILL recovery.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass(frozen=True)
class FaultScenarioDefinition:
    id: str
    name: str
    category: str = "incident_radar_faults"
    protocol: str = "TCP-Churn"
    target_port: int = 8881
    sla_p95_ms: float = 10.0
    description: str = ""
    fault_type: str = ""
    fault_trigger_second: int = 240
    driver_type: str = "k6"
    driver_script: str = ""
    driver_args: List[str] = field(default_factory=list)
    server_cmd: List[str] = field(default_factory=list)
    expected_exit_code: int = 0
    verification_keys: List[str] = field(
        default_factory=lambda: ["zero_synthetic", "sla_p95", "rss_stability"]
    )


INCIDENT_FAULTS_SCENARIOS: Dict[str, FaultScenarioDefinition] = {
    "SCEN-FLT-01": FaultScenarioDefinition(
        id="SCEN-FLT-01",
        name="TCP TIME_WAIT Ephemeral Port Exhaustion",
        protocol="TCP-Churn",
        target_port=8881,
        sla_p95_ms=10.0,
        description="HTTP server with Connection: close and zero SO_LINGER actively closing sockets. Slot C blasts 2,000 conns/sec across ephemeral ports (32768-60999) evaluating tcp_tw_reuse.",
        fault_type="time_wait_exhaustion",
        driver_type="k6",
        driver_script="payloads/drivers/k6/time_wait_churn.js",
        driver_args=["--vus", "2000", "--duration", "300s"],
        server_cmd=["python3", "-m", "scenarios.servers.flt01_time_wait_server", "--port", "8881"],
    ),
    "SCEN-FLT-02": FaultScenarioDefinition(
        id="SCEN-FLT-02",
        name="Gradual Memory Leak (5 MB/sec) & Allocator Behavior",
        protocol="HTTP-Leak",
        target_port=8882,
        sla_p95_ms=12.0,
        description="HTTP service retaining uncollected chunk allocations in a ring buffer on every request (5 MB/s leak rate). Tracks memory fragmentation, RSS drift, and supervisor memory warning.",
        fault_type="heap_leak",
        driver_type="wrk2",
        driver_script="payloads/drivers/wrk2/leak_client.lua",
        driver_args=["-t4", "-c100", "-d300s", "-R1000", "--latency"],
        server_cmd=["python3", "-m", "scenarios.servers.flt02_leak_server", "--port", "8882", "--leak-rate-mb", "5"],
    ),
    "SCEN-FLT-03": FaultScenarioDefinition(
        id="SCEN-FLT-03",
        name="Unclosed File Descriptor Leak (ulimit ceiling)",
        protocol="POSIX-FD",
        target_port=8883,
        sla_p95_ms=15.0,
        description="HTTP service leaking socket handles or scratch file descriptors on error code paths until hitting the 10,000 FD ceiling (EMFILE). Verifies event loop doesn't spin at 100% CPU.",
        fault_type="fd_leak",
        driver_type="k6",
        driver_script="payloads/drivers/k6/fd_leak_trigger.js",
        driver_args=["--vus", "300", "--duration", "300s"],
        server_cmd=["python3", "-m", "scenarios.servers.flt03_fd_leak_server", "--port", "8883"],
    ),
    "SCEN-FLT-04": FaultScenarioDefinition(
        id="SCEN-FLT-04",
        name="SIGKILL Worker Process Instant Termination & Restart",
        protocol="Signal-Crash",
        target_port=8884,
        sla_p95_ms=100.0,
        description="Supervised multi-worker HTTP server under live 2,000 QPS load subjected to periodic SIGKILL worker termination (kill -9). Measures supervisor detection speed and process restart latency.",
        fault_type="sigkill_injection",
        fault_trigger_second=245,
        driver_type="chaos_injector",
        driver_script="payloads/drivers/chaos/chaos_injector.py",
        driver_args=["--signal", "SIGKILL", "--interval", "15", "--target", "worker"],
        server_cmd=["python3", "-m", "scenarios.servers.flt04_supervised_server", "--port", "8884"],
        expected_exit_code=137,
    ),
    "SCEN-FLT-05": FaultScenarioDefinition(
        id="SCEN-FLT-05",
        name="Zombie Process Reaping & PID Table Saturation",
        protocol="Fork-Reap",
        target_port=0,
        sla_p95_ms=20.0,
        description="Subshell worker spawner executing short-lived tasks that exit immediately without waitpid(). Evaluates PID 1 init reaper performance and PID table saturation defenses.",
        fault_type="zombie_accumulation",
        driver_type="zombie_spawner",
        driver_script="payloads/drivers/chaos/zombie_spawner.py",
        driver_args=["--fork-rate", "500", "--duration", "300"],
        server_cmd=["python3", "-m", "scenarios.servers.flt05_zombie_service"],
    ),
    "SCEN-FLT-06": FaultScenarioDefinition(
        id="SCEN-FLT-06",
        name="Slowloris Attack Slow-Header Connection Starvation",
        protocol="HTTP-Slow",
        target_port=8886,
        sla_p95_ms=25.0,
        description="Slowloris driver opening 1,500 connections dripping 1 header byte every 5 seconds, attempting to hold connection pools open while legitimate traffic measures p95 latency.",
        fault_type="slowloris",
        driver_type="slowloris",
        driver_script="payloads/drivers/chaos/slowloris_driver.py",
        driver_args=["--connections", "1500", "--delay", "5.0"],
        server_cmd=["python3", "-m", "scenarios.servers.flt06_slowloris_target", "--port", "8886"],
    ),
    "SCEN-FLT-07": FaultScenarioDefinition(
        id="SCEN-FLT-07",
        name="TCP Zero-Window Client Flow-Control Freeze",
        protocol="TCP-Window",
        target_port=8887,
        sla_p95_ms=30.0,
        description="Streaming HTTP server sending 10 MB payloads. Malicious client reads 64 KB then advertises win 0, testing kernel SO_SNDBUF saturation, persist timers, and backpressure isolation.",
        fault_type="zero_window",
        driver_type="zero_window",
        driver_script="payloads/drivers/chaos/zero_window_driver.py",
        driver_args=["--clients", "300", "--window", "0"],
        server_cmd=["python3", "-m", "scenarios.servers.flt07_stream_server", "--port", "8887"],
    ),
    "SCEN-FLT-08": FaultScenarioDefinition(
        id="SCEN-FLT-08",
        name="Packet Corruption & Bit-Flip Checksum Rejection",
        protocol="TCP-Corrupt",
        target_port=8888,
        sla_p95_ms=15.0,
        description="HTTP protocol parser service subjected to stream fuzzer sending malformed chunk sizes, bit-flipped frames, and 1,000-deep JSON. Verifies clean HTTP 400 rejection and 0 segfaults.",
        fault_type="fuzzing_corruption",
        driver_type="packet_corruptor",
        driver_script="payloads/drivers/chaos/packet_corruptor.py",
        driver_args=["--corrupt-rate", "0.3", "--rate", "2000"],
        server_cmd=["python3", "-m", "scenarios.servers.flt08_parser_server", "--port", "8888"],
    ),
    "SCEN-FLT-09": FaultScenarioDefinition(
        id="SCEN-FLT-09",
        name="Unix Domain Socket File Descriptors Unlinking",
        protocol="AF_UNIX",
        target_port=0,
        sla_p95_ms=5.0,
        description="IPC server communicating over /tmp/matrix_ipc.sock at 5,000 msgs/sec subjected to sudden unlink('/tmp/matrix_ipc.sock') at t=265s. Measures automatic socket re-binding and connection recovery.",
        fault_type="socket_unlinking",
        driver_type="socket_unlinker",
        driver_script="payloads/drivers/chaos/socket_unlinker.py",
        driver_args=["--socket-path", "/tmp/matrix_ipc.sock", "--unlink-second", "265"],
        server_cmd=["python3", "-m", "scenarios.servers.flt09_unix_socket_server", "--socket", "/tmp/matrix_ipc.sock"],
    ),
    "SCEN-FLT-10": FaultScenarioDefinition(
        id="SCEN-FLT-10",
        name="Cascading Worker Thread Deadlock and Timeout",
        protocol="Thread-Lock",
        target_port=8890,
        sla_p95_ms=50.0,
        description="Multithreaded service with interdependent locks (Account A <-> Account B) subjected to inverted transfer requests. Tests pthread_mutex_timedlock, deadlock timeout, and 504 gateway response.",
        fault_type="lock_contention",
        driver_type="wrk2",
        driver_script="payloads/drivers/wrk2/inverted_transfers.lua",
        driver_args=["-t8", "-c500", "-d300s", "-R2000", "--latency"],
        server_cmd=["python3", "-m", "scenarios.servers.flt10_deadlock_service", "--port", "8890", "--lock-timeout-ms", "200"],
    ),
}


def get_incident_faults_scenarios() -> Dict[str, Dict[str, Any]]:
    """Returns the reference dictionary of all 10 Incident Radar & Fault Injection scenarios."""
    return {
        s.id: {
            "id": s.id,
            "name": s.name,
            "category": s.category,
            "protocol": s.protocol,
            "target_port": s.target_port,
            "sla_p95_ms": s.sla_p95_ms,
        }
        for s in INCIDENT_FAULTS_SCENARIOS.values()
    }
