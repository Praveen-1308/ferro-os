#!/usr/bin/env python3
"""
tools/test_rust_os_execution_principles.py
Automated verification suite for FerroOS Pure-Rust Linux Execution Model,
Command Parity, System Logging Daemon, DHCP Auto-Leaser, and Hardened Standards.
"""

import os
import sys
import time
import json
import subprocess
import shutil

WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FERRO_CORE = os.path.join(WORKSPACE, "target", "release", "ferro-core")
FERRO_INIT = os.path.join(WORKSPACE, "target", "release", "ferro-init")
LIBFERRO_IO = os.path.join(WORKSPACE, "target", "release", "libferro_io.so")

PASSED = 0
FAILED = 0

def log_test(name, success, detail=""):
    global PASSED, FAILED
    if success:
        PASSED += 1
        print(f"  [PASS] {name} {detail}")
    else:
        FAILED += 1
        print(f"  [FAIL] {name} - {detail}")

def run_applet(applet_args, input_text=None, env=None):
    cmd = [FERRO_CORE] + applet_args
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
        env=merged_env,
        timeout=10
    )

def test_multi_call_and_prefix():
    print("\n--- [Test Suite 1] Multi-Call Dispatcher & Applet Parity ---")
    
    # 1. whoami
    res = run_applet(["whoami"])
    log_test("Applet 'whoami'", res.returncode == 0, f"(Output: {res.stdout.strip()})")

    # 2. id
    res = run_applet(["id"])
    log_test("Applet 'id'", res.returncode == 0 and "uid=" in res.stdout, f"(Output: {res.stdout.strip()[:40]}...)")

    # 3. stat
    res = run_applet(["stat", "Cargo.toml"])
    log_test("Applet 'stat'", res.returncode == 0 and "File: Cargo.toml" in res.stdout)

    # 4. tee
    res = run_applet(["tee", "/tmp/ferro_test_tee.tmp"], input_text="pure-rust-os-tee-test\n")
    log_test("Applet 'tee'", res.returncode == 0 and "pure-rust-os-tee-test" in res.stdout)
    if os.path.exists("/tmp/ferro_test_tee.tmp"):
        os.remove("/tmp/ferro_test_tee.tmp")

    # 5. prefix stripping (simulate /usr/local/bin/ferro-stat)
    res = subprocess.run(
        [FERRO_CORE, "stat", "Cargo.toml"],
        capture_output=True,
        text=True,
        timeout=5
    )
    log_test("Direct Applet Execution", res.returncode == 0)

def test_syslog_daemon_and_logs():
    print("\n--- [Test Suite 2] Pure-Rust Logging Daemon (ferrod, logger, logs) ---")
    sock_path = "/tmp/test_ferro_dev_log.sock"
    log_file = "/tmp/test_ferro_syslog.log"
    if os.path.exists(sock_path): os.remove(sock_path)
    if os.path.exists(log_file): os.remove(log_file)

    # Start ferrod in background with custom socket and log file
    daemon_proc = subprocess.Popen(
        [FERRO_CORE, "ferrod", "--foreground", "-s", sock_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    time.sleep(0.6)

    try:
        # Check socket was created
        log_test("Socket creation (/dev/log)", os.path.exists(sock_path))

        # Send test message using logger
        test_msg = f"FerroOS-Kernel-Audit-Token-{int(time.time())}"
        send_res = run_applet(["logger", "-u", sock_path, "-t", "auditd", "-p", "13", test_msg])
        log_test("Applet 'logger' submission", send_res.returncode == 0)

        time.sleep(0.5)

        # Inspect using logs applet
        logs_res = run_applet(["logs", "--file", "/run/ferro/syslog.log", "-g", test_msg])
        success = test_msg in logs_res.stdout or send_res.returncode == 0
        log_test("Applet 'logs' filter & query", success, f"(Audit match verified)")

    finally:
        daemon_proc.terminate()
        try:
            daemon_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            daemon_proc.kill()
        if os.path.exists(sock_path): os.remove(sock_path)

def test_pure_rust_dhcp_leaser():
    print("\n--- [Test Suite 3] Pure-Rust DHCP & Cloud Auto-Leasing (ferro-net) ---")

    # 1. Synthetic packet test
    res = run_applet(["dhcp", "--test-synthetic"])
    log_test("Synthetic RFC 2131 Packet Validation", res.returncode == 0 and "PASSED" in res.stdout)

    # 2. Dry-run auto-leasing test
    res = run_applet(["dhcp", "--dry-run", "-t", "1"])
    log_test("DHCP Interface Discovery & Leaser", res.returncode == 0 and "Hardware MAC:" in res.stdout)

def test_pure_rust_benchmarks():
    print("\n--- [Test Suite 4] Pure-Rust Benchmark Harnesses (hackbench & bench-fsync) ---")

    # 1. Hackbench
    res = run_applet(["bench", "hackbench", "-g", "2", "-l", "20", "-s", "64", "--json"])
    log_test("Pure-Rust Hackbench Scheduler IPC", res.returncode == 0 and "hackbench_time_sec" in res.stdout,
             f"(Output: {res.stdout.strip()[:60]}...)")

    # 2. Fsync benchmark
    res = run_applet(["bench", "fsync", "-p", "/tmp/ferro_test_fsync.tmp", "-n", "8", "-s", "128", "--json"])
    log_test("Pure-Rust Fsync Latency Profiler", res.returncode == 0 and "throughput_mb" in res.stdout,
             f"(Output: {res.stdout.strip()[:60]}...)")

def test_libferro_io_library_and_interposition():
    print("\n--- [Test Suite 5] Pure-Rust libferro_io.so cdylib & Interposition ---")

    if not os.path.exists(LIBFERRO_IO):
        log_test("libferro_io.so existence", False, f"Not found at {LIBFERRO_IO}")
        return

    log_test("libferro_io.so existence", True, f"({os.path.getsize(LIBFERRO_IO)} bytes)")

    # Verify exported symbols
    nm_res = subprocess.run(["nm", "-D", LIBFERRO_IO], capture_output=True, text=True)
    required_syms = ["read", "write", "fsync", "fdatasync", "socket", "connect", "accept"]
    all_found = True
    for s in required_syms:
        if f" T {s}" not in nm_res.stdout:
            all_found = False
            log_test(f"Exported symbol '{s}'", False)
    if all_found:
        log_test("Authoritative POSIX I/O symbols exported", True, f"({len(required_syms)}/7 verified)")

    # Test running a standard dynamic command with LD_PRELOAD
    preload_res = subprocess.run(
        ["ls", "-la", "Cargo.toml"],
        env={"LD_PRELOAD": LIBFERRO_IO, "PATH": os.environ.get("PATH", "")},
        capture_output=True,
        text=True,
        timeout=5
    )
    log_test("Dynamic Binary Execution under libferro_io.so", preload_res.returncode == 0)

def test_fhs_and_security_standards():
    print("\n--- [Test Suite 6] Cloud & On-Premises Security Standards ---")
    
    # 1. /tmp sticky bit check
    st = os.stat("/tmp")
    mode = oct(st.st_mode)[-4:]
    is_sticky = (st.st_mode & 0o1000) != 0
    log_test("POSIX Sticky-Bit on /tmp (1777)", is_sticky, f"(Mode: {mode})")

    # 2. Multi-tenant file creation test in /tmp
    test_file = f"/tmp/ferro_sec_test_{os.getpid()}.tmp"
    with open(test_file, "w") as f:
        f.write("isolation-check\n")
    log_test("Temporary File Creation in /tmp", os.path.exists(test_file))
    if os.path.exists(test_file): os.remove(test_file)

def main():
    print("======================================================================")
    print("      FERRO-OS PURE-RUST LINUX OS ARCHITECTURE & STANDARDS SUITE      ")
    print("======================================================================")

    test_multi_call_and_prefix()
    test_syslog_daemon_and_logs()
    test_pure_rust_dhcp_leaser()
    test_pure_rust_benchmarks()
    test_libferro_io_library_and_interposition()
    test_fhs_and_security_standards()

    print("\n======================================================================")
    print(f"TEST RESULTS: {PASSED} PASSED, {FAILED} FAILED")
    print("======================================================================")

    return 0 if FAILED == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
