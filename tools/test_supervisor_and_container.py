#!/usr/bin/env python3
"""
Test Suite: FerroOS Next-Gen Subsystems (ferro-superd & ferrocage)
Validates:
1. ferro-superd service supervision, cgroups, health, and `ferro service` CLI commands.
2. ferrocage pure-Rust container execution, ps, inspect, logs, stop, rm commands.
"""

import os
import sys
import time
import json
import subprocess
import signal

def log(msg, status="INFO"):
    colors = {
        "INFO": "\033[1;34m[*]\033[0m",
        "PASS": "\033[1;32m[✓]\033[0m",
        "FAIL": "\033[1;31m[✗]\033[0m"
    }
    print(f"{colors.get(status, '[*]')} {msg}")

def run_cmd(cmd, check=True):
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed (rc={res.returncode}): {cmd}\nStdout: {res.stdout}\nStderr: {res.stderr}")
    return res

def test_supervisor():
    log("Testing Pillar 2: ferro-superd & ferro service...", "INFO")
    
    superd_bin = os.path.abspath("target/release/ferro-superd")
    core_bin = os.path.abspath("target/release/ferro-core")

    is_root = (hasattr(os, "geteuid") and os.geteuid() == 0)
    services_dir = "/etc/ferro/services" if is_root else "/tmp/ferro_test_services"
    logs_dir = "/var/log/ferro" if is_root else "/tmp/ferro_test_logs"
    run_dir = "/run/ferro" if is_root else "/tmp/ferro_test_run"
    socket_path = os.path.join(run_dir, "superd.sock")

    os.environ["FERRO_SERVICES_DIR"] = services_dir
    os.environ["FERRO_LOGS_DIR"] = logs_dir
    os.environ["FERRO_SOCKET_PATH"] = socket_path

    os.makedirs(services_dir, exist_ok=True)
    os.makedirs(logs_dir, exist_ok=True)
    os.makedirs(run_dir, exist_ok=True)

    # Clean up old socket if present
    if os.path.exists(socket_path):
        os.remove(socket_path)

    # Create test service manifest
    manifest = """
[service]
name = "qa-worker"
description = "QA Diagnostic Background Daemon"
command = ["/bin/sh", "-c", "while true; do echo 'qa-worker heartbeat'; sleep 1; done"]
working_dir = "/tmp"

[restart]
policy = "always"
max_retries = 3
backoff_ms = 500

[cgroups]
memory_max_mb = 128
cpu_weight = 100
pids_max = 20

[health]
check_interval_sec = 2
check_command = ["/bin/true"]
timeout_sec = 1
restart_on_unhealthy = false
"""
    manifest_path = os.path.join(services_dir, "qa-worker.toml")
    with open(manifest_path, "w") as f:
        f.write(manifest)

    # Launch ferro-superd in background
    superd_proc = subprocess.Popen([superd_bin], env=os.environ, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(1.0) # wait for socket bind

    try:
        assert os.path.exists(socket_path), f"IPC socket {socket_path} was not created"
        log(f"IPC socket successfully bound at {socket_path}", "PASS")

        # 1. Test ferro service list
        res = run_cmd(f'"{core_bin}" service list')
        assert "qa-worker" in res.stdout, "qa-worker not found in list output"
        log("ferro service list: found active qa-worker", "PASS")

        # 2. Test ferro service status
        res = run_cmd(f'"{core_bin}" service status qa-worker')
        assert "Active: running" in res.stdout or "Main PID:" in res.stdout, f"Unexpected status: {res.stdout}"
        log("ferro service status: verified active running status", "PASS")

        # 3. Test ferro service status --format json
        res = run_cmd(f'"{core_bin}" service status qa-worker json')
        data = json.loads(res.stdout)
        assert data.get("status") == "ok" and data.get("service") == "qa-worker", f"Invalid json status: {data}"
        log("ferro service status (JSON): valid JSON RPC payload returned", "PASS")

        # 4. Test ferro service stop
        res = run_cmd(f'"{core_bin}" service stop qa-worker')
        assert "Stopped service 'qa-worker'" in res.stdout, f"Stop failed: {res.stdout}"
        res_stat = run_cmd(f'"{core_bin}" service status qa-worker', check=False)
        assert res_stat.returncode == 3 or "Active: stopped" in res_stat.stdout, "Service was not stopped"
        log("ferro service stop: service cleanly stopped (rc=3 / inactive)", "PASS")

        # 5. Test ferro service start
        res = run_cmd(f'"{core_bin}" service start qa-worker')
        assert "Started service 'qa-worker'" in res.stdout, f"Start failed: {res.stdout}"
        log("ferro service start: service successfully resumed", "PASS")

        # 6. Test ferro service logs
        time.sleep(1.2)
        res = run_cmd(f'"{core_bin}" service logs qa-worker -n 10')
        assert "heartbeat" in res.stdout or "spawned" in res.stdout, f"Logs missing heartbeat: {res.stdout}"
        log("ferro service logs: captured ring-buffer log entries", "PASS")

    finally:
        superd_proc.terminate()
        superd_proc.wait(timeout=2)
        if os.path.exists(socket_path):
            os.remove(socket_path)
        if os.path.exists(manifest_path):
            os.remove(manifest_path)

def test_ferrocage():
    log("Testing Pillar 3: ferrocage micro-container engine...", "INFO")
    
    cage_bin = os.path.abspath("target/release/ferrocage")

    is_root = (hasattr(os, "geteuid") and os.geteuid() == 0)
    cage_state_dir = "/var/lib/ferrocage/containers" if is_root else "/tmp/ferrocage_test_state"
    if not is_root:
        cage_logs_dir = "/tmp/ferrocage_test_state/logs"
        os.environ["FERROCAGE_STATE_DIR"] = cage_state_dir
        os.environ["FERROCAGE_LOGS_DIR"] = cage_logs_dir
        os.makedirs(cage_state_dir, exist_ok=True)
        os.makedirs(cage_logs_dir, exist_ok=True)

    # 1. Run detached micro-container
    res = run_cmd(f'"{cage_bin}" run -d --name c1-test --memory 64M alpine /bin/sh -c \'sleep 8\'')
    cid = res.stdout.strip()
    assert len(cid) == 12, f"Expected 12-char container ID, got: '{cid}'"
    log(f"ferrocage run -d: container spawned with ID {cid}", "PASS")

    try:
        # 2. Test ferrocage ps
        res = run_cmd(f'"{cage_bin}" ps')
        assert cid in res.stdout or "c1-test" in res.stdout, f"Container {cid} not in ps table:\n{res.stdout}"
        log("ferrocage ps: container active in process table", "PASS")

        # 3. Test ferrocage ps --format=json
        res = run_cmd(f'"{cage_bin}" ps --format=json')
        containers = json.loads(res.stdout)
        assert any(c.get("id") == cid for c in containers), f"Container {cid} not found in json ps: {containers}"
        log("ferrocage ps (JSON): container verified in structured JSON array", "PASS")

        # 4. Test ferrocage inspect
        res = run_cmd(f'"{cage_bin}" inspect {cid}')
        state = json.loads(res.stdout)
        assert state.get("id") == cid and state.get("name") == "c1-test", f"Inspect error: {state}"
        assert state.get("memory_max_bytes") == 64 * 1024 * 1024, "Memory limit mismatch"
        log("ferrocage inspect: verified configuration and cgroup limit (64M)", "PASS")

        # 5. Test ferrocage stop
        res = run_cmd(f'"{cage_bin}" stop {cid}')
        assert cid in res.stdout, f"Stop failed: {res.stdout}"
        res_ps = run_cmd(f'"{cage_bin}" ps')
        assert cid not in res_ps.stdout, "Container should not appear in running ps"
        log("ferrocage stop: container stopped successfully", "PASS")

        # 6. Test ferrocage rm
        res = run_cmd(f'"{cage_bin}" rm {cid}')
        assert cid in res.stdout, f"Rm failed: {res.stdout}"
        assert not os.path.exists(f"{cage_state_dir}/{cid}"), "Container state dir not removed"
        log("ferrocage rm: container metadata and storage cleaned up", "PASS")

    finally:
        # Cleanup if still exists
        run_cmd(f'"{cage_bin}" rm -f {cid}', check=False)

if __name__ == "__main__":
    print("=" * 80)
    print("  FERRO-OS NEXT-GEN ARCHITECTURE VALIDATION (SUPERVISOR & CONTAINER)  ")
    print("=" * 80)
    try:
        test_supervisor()
        test_ferrocage()
        print("\n" + "=" * 80)
        log("ALL PILLAR 2 & PILLAR 3 VALIDATION TESTS PASSED (100% SUCCESS)", "PASS")
        print("=" * 80)
    except Exception as e:
        log(f"Test failure: {e}", "FAIL")
        sys.exit(1)
