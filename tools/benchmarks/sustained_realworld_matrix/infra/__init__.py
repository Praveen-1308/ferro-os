"""
tools/benchmarks/sustained_realworld_matrix/infra/__init__.py

Milestone 1 Infrastructure Package:
- 3-Container Topology & Lifecycle: ContainerManager, SlotId, SlotConfig, SLOT_DEFINITIONS
- Host Resource Preservation: HostResourceWatchdog, HostWatchdogSummary
- Strict Execution & Pipefail: StrictExecutionRunner, CommandResult, run_strict_pipe, run_strict_command, execute_with_pipefail
"""

from .container_manager import (
    SlotId,
    SlotConfig,
    SLOT_DEFINITIONS,
    NETWORK_NAME,
    NETWORK_SUBNET,
    NETWORK_GATEWAY,
    ContainerInstance,
    ExecResult,
    ContainerManager,
)

from .host_watchdog import (
    HostResourceWatchdog,
    HostWatchdogSummary,
    DEFAULT_SAMPLE_INTERVAL_S,
    DEFAULT_MIN_SAFE_RAM_GB,
    DEFAULT_ABORT_THRESHOLD_RAM_GB,
    DEFAULT_MIN_CPU_IDLE_PCT,
)

from .strict_runner import (
    CommandResult,
    StrictExecutionRunner,
    run_strict_pipe,
    run_strict_command,
    execute_with_pipefail,
    classify_exit_code,
)

__all__ = [
    # Container Manager
    "SlotId",
    "SlotConfig",
    "SLOT_DEFINITIONS",
    "NETWORK_NAME",
    "NETWORK_SUBNET",
    "NETWORK_GATEWAY",
    "ContainerInstance",
    "ExecResult",
    "ContainerManager",
    # Host Watchdog
    "HostResourceWatchdog",
    "HostWatchdogSummary",
    "DEFAULT_SAMPLE_INTERVAL_S",
    "DEFAULT_MIN_SAFE_RAM_GB",
    "DEFAULT_ABORT_THRESHOLD_RAM_GB",
    "DEFAULT_MIN_CPU_IDLE_PCT",
    # Strict Runner
    "CommandResult",
    "StrictExecutionRunner",
    "run_strict_pipe",
    "run_strict_command",
    "execute_with_pipefail",
    "classify_exit_code",
]
