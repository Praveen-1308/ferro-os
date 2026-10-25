#!/usr/bin/env python3
"""
tools/execute_one_to_one_e2e.py
One-to-One Direct Command & Real-World Scenario Execution Engine
Runs actual commands against the live FerroOS container (ferro-server),
capturing exact inputs, exact stdout/stderr, exit codes, and timestamps.
"""

import subprocess
import time
import json
import os

LOG_RECORDS = []

def run_e2e_command(step_id: str, scenario: str, description: str, cmd_str: str):
    print(f"[{step_id}] ({scenario}) Running: {cmd_str}")
    t0 = time.perf_counter()
    full_cmd = ["docker", "exec", "ferro-server", "sh", "-c", cmd_str]
    proc = subprocess.run(full_cmd, capture_output=True, text=True)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    record = {
        "step_id": step_id,
        "scenario": scenario,
        "description": description,
        "command": cmd_str,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "elapsed_ms": round(elapsed_ms, 2),
        "status": "SUCCESS" if proc.returncode == 0 else "FAILURE"
    }
    LOG_RECORDS.append(record)
    print(f"    -> Code: {proc.returncode} | Time: {elapsed_ms:.1f}ms | Out: {proc.stdout.strip().splitlines()[:2]}")
    return record

def main():
    print("=" * 80)
    print("  FERRO-OS ONE-TO-ONE LIVE COMMAND & SCENARIO EXECUTION")
    print("=" * 80)

    # =========================================================================
    # SCENARIO A: Daily Developer & Sysadmin Operations
    # =========================================================================
    run_e2e_command("A1", "Daily Operations", "Print current working directory", "pwd")
    run_e2e_command("A2", "Daily Operations", "Verify effective user identity", "whoami")
    run_e2e_command("A3", "Daily Operations", "Verify numerical UID and GID", "id")
    run_e2e_command("A4", "Daily Operations", "Kernel release and architecture", "uname -a")
    run_e2e_command("A5", "Daily Operations", "System uptime and load averages", "/bin/ferro-core uptime")
    run_e2e_command("A6", "Daily Operations", "Create nested directory structure", "mkdir -p /tmp/ferro_work/logs /tmp/ferro_work/data && ls -la /tmp/ferro_work")
    run_e2e_command("A7", "Daily Operations", "Write application log file", "echo '[2026-10-25 21:05:01] INFO Service started on port 8080' > /tmp/ferro_work/logs/app.log && cat /tmp/ferro_work/logs/app.log")
    run_e2e_command("A8", "Daily Operations", "Append simulated error logs", "echo '[2026-10-25 21:05:02] ERROR Connection timeout upstream' >> /tmp/ferro_work/logs/app.log && echo '[2026-10-25 21:05:03] INFO Retrying connection' >> /tmp/ferro_work/logs/app.log")
    run_e2e_command("A9", "Daily Operations", "Filter log patterns with grep", "grep 'ERROR' /tmp/ferro_work/logs/app.log")
    run_e2e_command("A10", "Daily Operations", "Display first line with head", "head -n 1 /tmp/ferro_work/logs/app.log")
    run_e2e_command("A11", "Daily Operations", "Display last line with tail", "tail -n 1 /tmp/ferro_work/logs/app.log")
    run_e2e_command("A12", "Daily Operations", "Count total lines using ferro-core wc", "/bin/ferro-core wc -l /tmp/ferro_work/logs/app.log")
    run_e2e_command("A13", "Daily Operations", "Inspect inode and file attributes", "stat /tmp/ferro_work/logs/app.log")
    run_e2e_command("A14", "Daily Operations", "Enforce read-only permissions", "chmod 444 /tmp/ferro_work/logs/app.log && ls -l /tmp/ferro_work/logs/app.log")
    run_e2e_command("A15", "Daily Operations", "Restore write permissions and cleanup", "chmod 644 /tmp/ferro_work/logs/app.log && rm -rf /tmp/ferro_work && ls -d /tmp/ferro_work 2>&1 || true")
    run_e2e_command("A16", "Daily Operations", "Inspect active process table via ferro-core", "/bin/ferro-core ps")
    run_e2e_command("A17", "Daily Operations", "Inspect physical memory pools via ferro-core", "/bin/ferro-core free")

    # =========================================================================
    # SCENARIO B: Network & Socket Incident Response (Real Active Listeners)
    # =========================================================================
    run_e2e_command("B1", "Network Forensics", "Inspect network interfaces & IP routing", "/bin/ferro-core ip addr")
    run_e2e_command("B2", "Network Forensics", "Inspect loopback interface details", "ifconfig lo 2>/dev/null || ip addr show lo")
    run_e2e_command("B3", "Network Forensics", "Audit active TCP listening ports and PIDs", "netstat -tulpn")
    run_e2e_command("B4", "Network Forensics", "Verify network loopback socket connectivity", "ping -c 2 127.0.0.1 2>/dev/null || python3 -c \"import socket; s=socket.socket(); s.connect(('127.0.0.1', 8080)); print('TCP handshake to 127.0.0.1:8080 successful'); s.close()\"")
    run_e2e_command("B5", "Network Forensics", "Execute HTTP request against live microservice port 8080", "python3 -c \"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/api/status').read().decode()[:80])\"")
    run_e2e_command("B6", "Network Forensics", "Execute key-value store write on live service port 8081", "python3 -c \"import urllib.request, json; req = urllib.request.Request('http://127.0.0.1:8081/set', data=json.dumps({'key': 'e2e_test', 'value': 'success'}).encode(), headers={'Content-Type': 'application/json'}); print(urllib.request.urlopen(req).read().decode())\"")
    run_e2e_command("B7", "Network Forensics", "Execute key-value store read on live service port 8081", "python3 -c \"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8081/get?key=e2e_test').read().decode())\"")
    run_e2e_command("B8", "Network Forensics", "Query DNS resolver for localhost mapping", "python3 -c \"import socket; print('Resolved localhost:', socket.gethostbyname('localhost'))\"")

    # =========================================================================
    # SCENARIO C: Storage Saturation, File Descriptors & Dirty Pages
    # =========================================================================
    run_e2e_command("C1", "Storage Choke", "Report filesystem disk capacity and mount points", "df -h /")
    run_e2e_command("C2", "Storage Choke", "Spawn background writer and hold active file descriptor", "python3 -c \"import os, time; f=open('/tmp/dirty_pressure.dat', 'wb'); f.write(os.urandom(1024*1024*2)); f.flush(); time.sleep(1); f.close(); print('2MB written and closed')\"")
    run_e2e_command("C3", "Storage Choke", "Inspect file size and allocated blocks", "stat /tmp/dirty_pressure.dat")
    run_e2e_command("C4", "Storage Choke", "Execute kernel sync to flush dirty buffers to disk", "sync")
    run_e2e_command("C5", "Storage Choke", "Compute cryptographic SHA256 digest of stored block", "sha256sum /tmp/dirty_pressure.dat")
    run_e2e_command("C6", "Storage Choke", "Remove test block and verify storage reclamation", "rm -f /tmp/dirty_pressure.dat && ls /tmp/dirty_pressure.dat 2>&1 || true")

    # =========================================================================
    # SCENARIO D: Security Hardening & Privilege Sandboxing
    # =========================================================================
    run_e2e_command("D1", "Security Audit", "Verify process open file descriptor limits (ulimit -n)", "ulimit -n")
    run_e2e_command("D2", "Security Audit", "Verify system-wide max file limit (ulimit -a)", "ulimit -a")
    run_e2e_command("D3", "Security Audit", "Verify OpenSSL cryptographic engine version", "openssl version")
    run_e2e_command("D4", "Security Audit", "Verify MD5 digest generation", "echo 'security-audit-payload' | md5sum")
    run_e2e_command("D5", "Security Audit", "Verify /tmp sticky bit security standard (1777)", "stat -c '%a %n' /tmp")
    run_e2e_command("D6", "Security Audit", "Verify non-root file ownership protection", "id -u ferro && touch /tmp/ferro_secure && ls -l /tmp/ferro_secure && rm -f /tmp/ferro_secure")

    # =========================================================================
    # SCENARIO E: FerroOS Native Cloud Innovations
    # =========================================================================
    run_e2e_command("E1", "FerroOS Innovations", "Query native rpk (ferro-pkg) package database", "/bin/ferro-pkg list")
    run_e2e_command("E2", "FerroOS Innovations", "Inspect zero-downtime socket handover interface (fdstore)", "/bin/ferro-core fdstore status")
    run_e2e_command("E3", "FerroOS Innovations", "Probe eBPF socket loopback bypass capabilities", "/bin/ferro-core bpf status")
    run_e2e_command("E4", "FerroOS Innovations", "Query local shared-memory DNS table", "/bin/ferro-core dns-cache query localhost")
    run_e2e_command("E5", "FerroOS Innovations", "Inspect WinRE boot crash recovery status", "/bin/ferro-core recovery status")

    out_file = os.path.join(os.path.dirname(__file__), "reports", "one_to_one_e2e_execution_log.json")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(LOG_RECORDS, f, indent=2)
    print(f"\n[+] Execution log saved to: {out_file} ({len(LOG_RECORDS)} steps completed)")

if __name__ == "__main__":
    main()
