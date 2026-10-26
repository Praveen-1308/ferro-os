"""
tools/benchmarks/sustained_realworld_matrix/scenarios/deadzone_extremes.py
Category 6: Deadzone & Hardware Extremes (8 Scenarios: SCEN-DZN-01 to SCEN-DZN-08).
Authoritative, zero-synthetic physical and cgroup resource ceiling stress tests.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass(frozen=True)
class DeadzoneScenarioDefinition:
    id: str
    name: str
    category: str = "deadzone_hardware_extremes"
    protocol: str = "OOM-Ceiling"
    target_port: int = 9991
    sla_p95_ms: float = 50.0
    description: str = ""
    hardware_boundary: str = ""
    boundary_limit: Any = None
    driver_type: str = ""
    driver_script: str = ""
    driver_args: List[str] = field(default_factory=list)
    server_cmd: List[str] = field(default_factory=list)
    expected_exit_code: int = 0
    verification_keys: List[str] = field(
        default_factory=lambda: ["zero_synthetic", "sla_p95", "rss_stability"]
    )


DEADZONE_EXTREMES_SCENARIOS: Dict[str, DeadzoneScenarioDefinition] = {
    "SCEN-DZN-01": DeadzoneScenarioDefinition(
        id="SCEN-DZN-01",
        name="Cgroup OOM 4 GB Memory Ceiling Hard Enforcement",
        protocol="OOM-Ceiling",
        target_port=9991,
        sla_p95_ms=50.0,
        description="Pushes container memory allocations towards the strict 4,096 MB (4,294,967,296 bytes) cgroup v2 memory.max ceiling. Verifies container OOM killer triggers termination (exit code 137) while preserving host macOS headroom.",
        hardware_boundary="cgroup_memory_max_4gb",
        boundary_limit=4294967296,
        driver_type="oom_pusher",
        driver_script="payloads/drivers/chaos/oom_pusher.py",
        driver_args=["--rate-mb-s", "50", "--target-mb", "4200"],
        server_cmd=["python3", "-m", "scenarios.servers.dzn01_oom_target", "--port", "9991"],
        expected_exit_code=137,
    ),
    "SCEN-DZN-02": DeadzoneScenarioDefinition(
        id="SCEN-DZN-02",
        name="10,000 Concurrent Open Network Sockets",
        protocol="C10K-FD",
        target_port=9992,
        sla_p95_ms=10.0,
        description="High-capacity epoll server with nofile=65536. Slot C establishes and holds 10,000 live TCP connections, pulsing ping packets across sampled sockets to evaluate memory overhead and latency.",
        hardware_boundary="open_file_descriptors_10k",
        boundary_limit=10000,
        driver_type="c10k_holder",
        driver_script="payloads/drivers/socket/c10k_connector.py",
        driver_args=["--connections", "10000", "--ping-rate", "1000"],
        server_cmd=["python3", "-m", "scenarios.servers.dzn02_c10k_server", "--port", "9992"],
    ),
    "SCEN-DZN-03": DeadzoneScenarioDefinition(
        id="SCEN-DZN-03",
        name="Hackbench Context-Switch Scheduler Storm",
        protocol="Context-Storm",
        target_port=0,
        sla_p95_ms=20.0,
        description="Native compiled hackbench running 50 groups of 20 thread pairs (1,000 threads) exchanging data over POSIX pipes, driving context switches beyond 500,000/sec to stress OS kernel schedulers.",
        hardware_boundary="context_switches_500k",
        boundary_limit=500000,
        driver_type="hackbench",
        driver_script="tools/enterprise_qualification/hackbench",
        driver_args=["50", "thread", "100"],
        server_cmd=["/bin/bash", "-c", "tools/enterprise_qualification/hackbench 50 thread 100"],
    ),
    "SCEN-DZN-04": DeadzoneScenarioDefinition(
        id="SCEN-DZN-04",
        name="Epoll Event Queue Saturation (100k events)",
        protocol="epoll-sat",
        target_port=9994,
        sla_p95_ms=5.0,
        description="Epoll server configured with maxevents=100000 flooded with 1-byte ready signals across 5,000 sockets simultaneously, pushing 100,000 ready events/sec into the kernel epoll readiness list.",
        hardware_boundary="epoll_events_100k",
        boundary_limit=100000,
        driver_type="epoll_saturator",
        driver_script="payloads/drivers/socket/epoll_saturator.py",
        driver_args=["--sockets", "5000", "--event-rate", "100000"],
        server_cmd=["python3", "-m", "scenarios.servers.dzn04_epoll_server", "--port", "9994"],
    ),
    "SCEN-DZN-05": DeadzoneScenarioDefinition(
        id="SCEN-DZN-05",
        name="cgroup io.max Block I/O Severe Throttling",
        protocol="IO-Throttle",
        target_port=0,
        sla_p95_ms=80.0,
        description="FIO block write harness writing 200 MB/s of 64 KB blocks to scratch NVMe under cgroup v2 io.max throttle (wbps=52428800 = 50 MB/s limit), evaluating PSI stall spikes.",
        hardware_boundary="cgroup_io_max_50mb",
        boundary_limit=52428800,
        driver_type="fio",
        driver_script="payloads/drivers/fio/io_max_throttle.fio",
        driver_args=["--direct=1", "--bs=64k", "--iodepth=64"],
        server_cmd=["fio", "payloads/drivers/fio/io_max_throttle.fio"],
    ),
    "SCEN-DZN-06": DeadzoneScenarioDefinition(
        id="SCEN-DZN-06",
        name="Fork Bomb Mitigation (pids.max boundary)",
        protocol="PID-Bomb",
        target_port=0,
        sla_p95_ms=30.0,
        description="Bounded recursive process forker pushing against container cgroup pids.max=2048 limit. When limit is reached, fork() returns EAGAIN while init process and container remain stable.",
        hardware_boundary="cgroup_pids_max_2048",
        boundary_limit=2048,
        driver_type="fork_bomb",
        driver_script="payloads/drivers/chaos/fork_bomb_bounded.py",
        driver_args=["--target-pids", "4000", "--ceiling", "2048"],
        server_cmd=["python3", "payloads/drivers/chaos/fork_bomb_bounded.py"],
    ),
    "SCEN-DZN-07": DeadzoneScenarioDefinition(
        id="SCEN-DZN-07",
        name="Extreme Inode Depletion on Scratch Storage",
        protocol="Inode-Limit",
        target_port=0,
        sla_p95_ms=40.0,
        description="Creates 500,000 small files in hashed directories on /scratch to deplete filesystem inodes and stress kernel VFS dentry slab allocation and dcache eviction algorithms.",
        hardware_boundary="vfs_inodes_500k",
        boundary_limit=500000,
        driver_type="inode_depleter",
        driver_script="payloads/drivers/vfs/inode_depleter.py",
        driver_args=["--mount", "/scratch", "--count", "500000"],
        server_cmd=["python3", "payloads/drivers/vfs/inode_depleter.py", "--mount", "/scratch", "--count", "500000"],
    ),
    "SCEN-DZN-08": DeadzoneScenarioDefinition(
        id="SCEN-DZN-08",
        name="Raw Socket SYN Flood Defense (SYN Cookies)",
        protocol="SYN-Flood",
        target_port=9998,
        sla_p95_ms=15.0,
        description="Raw socket blaster streaming 100,000 SYNs/sec to target port with backlog=128. Kernel overflows listen queue and activates tcp_syncookies; verifies legitimate client connections succeed.",
        hardware_boundary="tcp_syncookies_activation",
        boundary_limit=100000,
        driver_type="syn_flood",
        driver_script="payloads/drivers/chaos/syn_flood_driver.py",
        driver_args=["--target-ip", "172.30.0.10", "--port", "9998", "--rate", "100000"],
        server_cmd=["python3", "-m", "scenarios.servers.dzn08_syn_cookie_target", "--port", "9998"],
    ),
}


def get_deadzone_scenarios() -> Dict[str, Dict[str, Any]]:
    """Returns the reference dictionary of all 8 Deadzone & Hardware Extremes scenarios."""
    return {
        s.id: {
            "id": s.id,
            "name": s.name,
            "category": s.category,
            "protocol": s.protocol,
            "target_port": s.target_port,
            "sla_p95_ms": s.sla_p95_ms,
        }
        for s in DEADZONE_EXTREMES_SCENARIOS.values()
    }
