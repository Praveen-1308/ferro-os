#!/usr/bin/env python3
"""
tools/benchmarks/sustained_realworld_matrix/infra/container_manager.py

Orchestrates the 3-container topology, resource limits, bridge networking,
scratch volumes, and lifecycle management for the Sustained Real-World Benchmark Matrix.

Topology Specifications:
- Container Slot A (SUT 1): cpus=2.0, memory=4g, memory-swap=4g, scratch=15GB, IP=172.30.0.10, internal_port=8080
- Container Slot B (SUT 2): cpus=2.0, memory=4g, memory-swap=4g, scratch=15GB, IP=172.30.0.11, internal_port=8080
- Container Slot C (Traffic/Validator): cpus=1.0, memory=2g, memory-swap=2g, scratch=5GB, IP=172.30.0.20, internal_port=9090
Total Docker Envelope: 5.0 vCPUs, 10.0 GB RAM (Preserving >= 5 cores & >= 6 GB RAM on macOS).
"""

import os
import sys
import time
import signal
import atexit
import subprocess
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any


class SlotId(str, Enum):
    SLOT_A = "slot_a"
    SLOT_B = "slot_b"
    SLOT_C = "slot_c"


@dataclass(frozen=True)
class SlotConfig:
    slot_id: SlotId
    container_name: str
    cpus: float
    memory: str
    memory_swap: str
    scratch_volume: Optional[str]
    scratch_mount_path: str
    scratch_limit_bytes: int
    static_ip: str
    internal_port: int
    nofile_limit: int = 65536


SLOT_DEFINITIONS: Dict[SlotId, SlotConfig] = {
    SlotId.SLOT_A: SlotConfig(
        slot_id=SlotId.SLOT_A,
        container_name="matrix-slot-a",
        cpus=2.0,
        memory="4g",
        memory_swap="4g",
        scratch_volume="matrix-scratch-slot-a",
        scratch_mount_path="/scratch",
        scratch_limit_bytes=15 * 1024 * 1024 * 1024,  # 15 GB
        static_ip="172.30.0.10",
        internal_port=8080,
    ),
    SlotId.SLOT_B: SlotConfig(
        slot_id=SlotId.SLOT_B,
        container_name="matrix-slot-b",
        cpus=2.0,
        memory="4g",
        memory_swap="4g",
        scratch_volume="matrix-scratch-slot-b",
        scratch_mount_path="/scratch",
        scratch_limit_bytes=15 * 1024 * 1024 * 1024,  # 15 GB
        static_ip="172.30.0.11",
        internal_port=8080,
    ),
    SlotId.SLOT_C: SlotConfig(
        slot_id=SlotId.SLOT_C,
        container_name="matrix-slot-c",
        cpus=1.0,
        memory="2g",
        memory_swap="2g",
        scratch_volume="matrix-scratch-slot-c",
        scratch_mount_path="/scratch",
        scratch_limit_bytes=5 * 1024 * 1024 * 1024,   # 5 GB
        static_ip="172.30.0.20",
        internal_port=9090,
    ),
}

NETWORK_NAME = "realworld_matrix_net"
NETWORK_SUBNET = "172.30.0.0/16"
NETWORK_GATEWAY = "172.30.0.1"

FERRO_ALLOWED_PREFIXES = ("/usr/bin/bash", "bash", "python3", "/usr/bin/python3")

def validate_ferro_command_safety(command: Optional[List[str]] = None, entrypoint: Optional[str] = None) -> None:
    """
    Enforces that FerroOS invocations strictly use affirmative whitelist of shells:
    /usr/bin/bash, bash, python3, /usr/bin/python3.
    Rejects applet shell loops, /bin/sh, /usr/bin/sh, ash, busybox, dash.
    """
    if entrypoint:
        ep = entrypoint.strip()
        if not any(ep == p or ep.startswith(p + " ") for p in FERRO_ALLOWED_PREFIXES):
            raise ValueError("FerroOS must invoke /usr/bin/bash or python3 directly, avoiding applet shell loops.")

    if command:
        cmd_str = " ".join(command).strip()
        if not entrypoint:
            if not any(cmd_str == p or cmd_str.startswith(p + " ") for p in FERRO_ALLOWED_PREFIXES):
                raise ValueError("FerroOS must invoke /usr/bin/bash or python3 directly, avoiding applet shell loops.")
        else:
            first = command[0].strip() if command else ""
            if first in ("sh", "/bin/sh", "/usr/bin/sh", "ash", "/bin/ash", "dash", "busybox"):
                raise ValueError("FerroOS must invoke /usr/bin/bash or python3 directly, avoiding applet shell loops.")


@dataclass
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float

    @property
    def is_success(self) -> bool:
        return self.exit_code == 0


@dataclass
class ContainerInstance:
    slot_id: SlotId
    container_name: str
    container_id: str
    image: str
    ip_address: str
    dns_name: str
    port: int
    started_at: float


class ContainerManager:
    """
    Manages the lifecycle of the 3-container topology, isolated bridge network,
    cgroup limits, scratch volumes, and teardown.
    """

    def __init__(self, network_name: str = NETWORK_NAME, auto_cleanup: bool = True):
        self.network_name = network_name
        self.auto_cleanup = auto_cleanup
        self.active_containers: Dict[SlotId, ContainerInstance] = {}
        self._emergency_cleaned = False

        if self.auto_cleanup:
            atexit.register(self.emergency_cleanup)
            try:
                signal.signal(signal.SIGINT, self._handle_signal)
                signal.signal(signal.SIGTERM, self._handle_signal)
            except (ValueError, AttributeError):
                # May fail if running outside main thread
                pass

    def _handle_signal(self, signum, frame):
        print(f"\n[ContainerManager] Caught signal {signum}. Executing emergency cleanup...")
        self.emergency_cleanup()
        sys.exit(128 + signum)

    def __enter__(self):
        self.ensure_network()
        self.preflight_cleanup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.teardown(remove_network=False, remove_volumes=True)

    # --------------------------------------------------------------------------
    # Network Management
    # --------------------------------------------------------------------------
    def ensure_network(self) -> None:
        """Idempotently ensures realworld_matrix_net exists with 172.30.0.0/16 and heals subnet drift."""
        check = subprocess.run(
            ["docker", "network", "inspect", self.network_name, "--format", "{{(index .IPAM.Config 0).Subnet}}"],
            capture_output=True,
            text=True
        )
        if check.returncode == 0:
            current_subnet = check.stdout.strip()
            if current_subnet == NETWORK_SUBNET:
                return
            # Subnet has drifted from specification! Recreate to heal drift
            self.remove_network()

        cmd = [
            "docker", "network", "create",
            "--driver", "bridge",
            "--subnet", NETWORK_SUBNET,
            "--gateway", NETWORK_GATEWAY,
            "--opt", "com.docker.network.bridge.name=br-matrix",
            "--label", "project=sustained_realworld_matrix",
            self.network_name,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Failed to create bridge network {self.network_name}: {res.stderr}")

    def remove_network(self) -> None:
        """Removes the bridge network if it exists."""
        subprocess.run(
            ["docker", "network", "rm", self.network_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    # --------------------------------------------------------------------------
    # Scratch Volume Management
    # --------------------------------------------------------------------------
    def ensure_scratch_volume(self, slot_id: SlotId) -> str:
        """Creates or validates the dedicated scratch volume for a slot."""
        cfg = SLOT_DEFINITIONS[slot_id]
        if not cfg.scratch_volume:
            return ""
        subprocess.run(
            ["docker", "volume", "create", cfg.scratch_volume],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        return cfg.scratch_volume

    def wipe_scratch_volume(self, slot_id: SlotId) -> None:
        """
        Atomically recreates the named volume to ensure 100% clean filesystem
        metadata and eliminate stale inodes or journal buffers.
        """
        cfg = SLOT_DEFINITIONS[slot_id]
        if not cfg.scratch_volume:
            return

        # Ensure container is stopped before volume wipe
        self.stop_slot(slot_id)

        rm_res = subprocess.run(
            ["docker", "volume", "rm", "-f", cfg.scratch_volume],
            capture_output=True,
            text=True
        )
        if rm_res.returncode != 0:
            err_msg = rm_res.stderr.strip() or f"exit code {rm_res.returncode}"
            raise RuntimeError(f"Failed to wipe scratch volume {cfg.scratch_volume}: {err_msg}")

        create_res = subprocess.run(
            ["docker", "volume", "create", cfg.scratch_volume],
            capture_output=True,
            text=True
        )
        if create_res.returncode != 0:
            err_msg = create_res.stderr.strip() or f"exit code {create_res.returncode}"
            raise RuntimeError(f"Failed to create scratch volume {cfg.scratch_volume}: {err_msg}")

    def get_scratch_usage_bytes(self, slot_id: SlotId) -> int:
        """Samples current bytes used in /scratch via df -B1."""
        cfg = SLOT_DEFINITIONS[slot_id]
        if slot_id not in self.active_containers:
            return 0
        try:
            res = self.exec_in_slot(slot_id, ["df", "-B1", cfg.scratch_mount_path])
            if res.exit_code != 0:
                return 0
            lines = res.stdout.strip().splitlines()
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 3:
                    return int(parts[2])
        except Exception:
            pass
        return 0

    # --------------------------------------------------------------------------
    # Container Lifecycle Management
    # --------------------------------------------------------------------------
    def preflight_cleanup(self) -> None:
        """Forcibly removes any lingering containers or volumes from prior runs."""
        for cfg in SLOT_DEFINITIONS.values():
            subprocess.run(["docker", "rm", "-f", cfg.container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if cfg.scratch_volume:
                subprocess.run(["docker", "volume", "rm", "-f", cfg.scratch_volume], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def start_slot(
        self,
        slot_id: SlotId,
        image: str,
        command: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        entrypoint: Optional[str] = None,
        wait_ready: bool = True,
        ready_timeout_s: float = 20.0,
    ) -> ContainerInstance:
        """
        Launches a container in the specified slot with strict cgroup limits,
        bridge networking, static IP, and scratch volume mount.
        """
        self.ensure_network()
        cfg = SLOT_DEFINITIONS[slot_id]

        # Cleanup existing slot container if present
        self.stop_slot(slot_id)
        self.ensure_scratch_volume(slot_id)

        docker_cmd = [
            "docker", "run", "-d",
            "--name", cfg.container_name,
            "--network", self.network_name,
            "--ip", cfg.static_ip,
            f"--cpus={cfg.cpus:.1f}",
            f"--memory={cfg.memory}",
            f"--memory-swap={cfg.memory_swap}",
            f"--ulimit=nofile={cfg.nofile_limit}:{cfg.nofile_limit}",
            "--label", f"slot={cfg.slot_id.value}",
            "--label", "project=sustained_realworld_matrix",
        ]

        if cfg.scratch_volume:
            docker_cmd.extend(["-v", f"{cfg.scratch_volume}:{cfg.scratch_mount_path}"])

        # Environment variables
        merged_env = {
            "SLOT_ID": cfg.slot_id.value,
            "CONTAINER_NAME": cfg.container_name,
            "PORT": str(cfg.internal_port),
        }
        if env:
            merged_env.update(env)
        for k, v in merged_env.items():
            docker_cmd.extend(["-e", f"{k}={v}"])

        # Resolve image aliases if needed
        resolved_image = image
        if resolved_image in ("ferro-server", "ferro-server:latest"):
            chk = subprocess.run(["docker", "image", "inspect", resolved_image], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if chk.returncode != 0:
                resolved_image = "ferro-os-server:latest"

        # FerroOS bash safety enforcement with affirmative whitelist
        if "ferro" in image.lower() or "ferro" in resolved_image.lower():
            validate_ferro_command_safety(command=command, entrypoint=entrypoint)

        if entrypoint:
            docker_cmd.extend(["--entrypoint", entrypoint])

        docker_cmd.append(resolved_image)
        if command:
            docker_cmd.extend(command)

        start_time = time.time()
        res = subprocess.run(docker_cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Failed to start container in {slot_id.value}: {res.stderr}")

        container_id = res.stdout.strip()
        instance = ContainerInstance(
            slot_id=slot_id,
            container_name=cfg.container_name,
            container_id=container_id,
            image=image,
            ip_address=cfg.static_ip,
            dns_name=cfg.container_name,
            port=cfg.internal_port,
            started_at=start_time,
        )
        self.active_containers[slot_id] = instance

        if wait_ready:
            self.wait_for_container_alive(slot_id, timeout_s=ready_timeout_s)

        return instance

    def wait_for_container_alive(self, slot_id: SlotId, timeout_s: float = 15.0) -> bool:
        """Polls until the container is running or timeout expires."""
        cfg = SLOT_DEFINITIONS[slot_id]
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            res = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", cfg.container_name],
                capture_output=True,
                text=True
            )
            if res.returncode == 0 and res.stdout.strip() == "true":
                return True
            time.sleep(0.2)
        raise TimeoutError(f"Container {cfg.container_name} in {slot_id.value} failed to reach running state within {timeout_s}s.")

    def stop_slot(self, slot_id: SlotId, timeout_s: int = 2) -> None:
        """Gracefully stops and removes a container in the specified slot."""
        cfg = SLOT_DEFINITIONS[slot_id]
        subprocess.run(["docker", "stop", "-t", str(timeout_s), cfg.container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["docker", "rm", "-f", cfg.container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.active_containers.pop(slot_id, None)

    def stop_all(self, timeout_s: int = 2) -> None:
        """Stops all active containers across Slots A, B, and C."""
        for slot_id in list(SLOT_DEFINITIONS.keys()):
            self.stop_slot(slot_id, timeout_s=timeout_s)

    def exec_in_slot(
        self,
        slot_id: SlotId,
        cmd: List[str],
        workdir: Optional[str] = None,
        timeout_s: float = 300.0
    ) -> ExecResult:
        """Executes a command inside the slot container with raw exit code preservation."""
        cfg = SLOT_DEFINITIONS[slot_id]

        # Enforce affirmative whitelist validation if slot is running FerroOS
        inst = self.active_containers.get(slot_id)
        image_name = inst.image if inst else ""
        if not image_name:
            try:
                res = subprocess.run(["docker", "inspect", "-f", "{{.Config.Image}}", cfg.container_name], capture_output=True, text=True)
                if res.returncode == 0:
                    image_name = res.stdout.strip()
            except Exception:
                pass

        if "ferro" in image_name.lower():
            validate_ferro_command_safety(command=cmd, entrypoint=None)

        exec_cmd = ["docker", "exec"]
        if workdir:
            exec_cmd.extend(["-w", workdir])
        exec_cmd.append(cfg.container_name)
        exec_cmd.extend(cmd)

        t0 = time.time()
        try:
            res = subprocess.run(
                exec_cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s
            )
            return ExecResult(
                exit_code=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
                duration_s=round(time.time() - t0, 3),
            )
        except subprocess.TimeoutExpired:
            return ExecResult(
                exit_code=143,  # SIGTERM equivalent
                stdout="",
                stderr=f"Command execution timed out after {timeout_s}s",
                duration_s=round(time.time() - t0, 3),
            )

    # --------------------------------------------------------------------------
    # Symmetric Crossover Swapping Support
    # --------------------------------------------------------------------------
    def prepare_crossover_run(
        self,
        direct: bool,
        os_x_image: str,
        os_y_image: str,
        sut_command: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[ContainerInstance, ContainerInstance]:
        """
        Orchestrates symmetric crossover container placement:
        - Direct run: Slot A = OS X, Slot B = OS Y
        - Swapped run: Slot A = OS Y, Slot B = OS X
        """
        if direct:
            img_a = os_x_image
            img_b = os_y_image
        else:
            img_a = os_y_image
            img_b = os_x_image

        inst_a = self.start_slot(SlotId.SLOT_A, image=img_a, command=sut_command, env=env)
        inst_b = self.start_slot(SlotId.SLOT_B, image=img_b, command=sut_command, env=env)
        return inst_a, inst_b

    def inter_run_cooldown_and_wipe(self, cooldown_s: float = 15.0) -> None:
        """
        Executes inter-run reset between forward and swapped phases:
        1. Gracefully stops SUT containers.
        2. Wipes both scratch volumes (recreating them fresh).
        3. Waits for TCP TIME_WAIT socket drainage and host RAM stabilization.
        """
        self.stop_slot(SlotId.SLOT_A)
        self.stop_slot(SlotId.SLOT_B)
        self.wipe_scratch_volume(SlotId.SLOT_A)
        self.wipe_scratch_volume(SlotId.SLOT_B)
        time.sleep(cooldown_s)

    # --------------------------------------------------------------------------
    # Teardown & Emergency Cleanup
    # --------------------------------------------------------------------------
    def teardown(self, remove_network: bool = False, remove_volumes: bool = True) -> None:
        """Full teardown of all containers, volumes, and optionally the network."""
        self.stop_all()
        if remove_volumes:
            for cfg in SLOT_DEFINITIONS.values():
                if cfg.scratch_volume:
                    subprocess.run(["docker", "volume", "rm", "-f", cfg.scratch_volume], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if remove_network:
            self.remove_network()

    def emergency_cleanup(self) -> None:
        """Idempotent fail-safe cleanup registered with atexit and signal handlers."""
        if self._emergency_cleaned:
            return
        self._emergency_cleaned = True
        try:
            for cfg in SLOT_DEFINITIONS.values():
                subprocess.run(["docker", "rm", "-f", cfg.container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if cfg.scratch_volume:
                    subprocess.run(["docker", "volume", "rm", "-f", cfg.scratch_volume], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
