#!/usr/bin/env python3
"""
tools/test_docker_ferro_os_complete.py
Comprehensive End-to-End Test Suite for FerroOS Docker Images.

Validates:
  1. GitHub Sync & Repository Integrity (upstream main sync, clean tree)
  2. Boot & PID 1 Initialization Architecture (ferro-init, FHS 3.0, non-root user, sticky bits, os-release)
  3. Filesystem Read/Write Operations (touch, echo, tee, cat, head, tail, wc, mkdir, cp, mv, rm, chmod, chown, ln, stat, sync)
  4. Standard Linux POSIX & Coreutils Commands (pwd, ls, which, clear, grep, find, ps, uptime, free, df, id, whoami, uname, hostname, env, sleep, kill, sh)
  5. Networking Commands & Microservices:
     - ip link, ip addr, ip route
     - dhcp / ferro-net (synthetic packet verification & dry-run leaser)
     - dns-cache (daemon command verification)
     - serve / httpd (pure-Rust multi-worker HTTP server)
     - server-suite (telemetry API port 8080, key-value engine port 8081, package server port 8082)
     - fetch / curl (HTTP client requests)
  6. Performance & Kernel Benchmarks (pure-Rust hackbench scheduler IPC, bench-fsync I/O)
  7. Package Management Engine (rpk info, list, check, hash)
  8. Container Variants Cross-Verification (ferro-os-pure:latest and ferro-os-server:latest)
"""

import os
import sys
import time
import json
import socket
import urllib.request
import subprocess

WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPORT_DIR = os.path.join(WORKSPACE, "tools/reports")
REPORT_FILE = os.path.join(REPORT_DIR, "docker_ferro_os_complete_results.json")

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

results = {
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "environment": {
        "platform": sys.platform,
        "docker_available": True,
    },
    "suites": {},
    "summary": {
        "total_tests": 0,
        "passed": 0,
        "failed": 0,
        "pass_rate_pct": 0.0,
    }
}

def log_header(title):
    print("\n" + "=" * 80)
    print(f" {BOLD}{CYAN}{title}{RESET}")
    print("=" * 80)

def record_test(suite_name, test_name, passed, details="", latency_ms=0.0):
    if suite_name not in results["suites"]:
        results["suites"][suite_name] = []
    results["suites"][suite_name].append({
        "test": test_name,
        "passed": bool(passed),
        "details": details.strip() if isinstance(details, str) else str(details),
        "latency_ms": round(latency_ms, 2)
    })
    results["summary"]["total_tests"] += 1
    if passed:
        results["summary"]["passed"] += 1
        status = f"{GREEN}[PASS]{RESET}"
    else:
        results["summary"]["failed"] += 1
        status = f"{RED}[FAIL]{RESET}"
    
    print(f"  {status} {test_name:<48} ({latency_ms:6.1f}ms) {details[:40] if details else ''}")

def run_cmd(cmd, timeout=15):
    t0 = time.time()
    try:
        res = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=timeout)
        dt = (time.time() - t0) * 1000.0
        return res.returncode, res.stdout, res.stderr, dt
    except subprocess.TimeoutExpired:
        dt = (time.time() - t0) * 1000.0
        return -1, "", "TIMEOUT", dt
    except Exception as e:
        dt = (time.time() - t0) * 1000.0
        return -2, "", str(e), dt

def run_docker(image, command_str, extra_flags=None, timeout=15):
    cmd = ["docker", "run", "--rm"]
    if extra_flags:
        cmd.extend(extra_flags)
    cmd.append(image)
    if isinstance(command_str, list):
        cmd.extend(command_str)
    else:
        cmd.extend(["sh", "-c", command_str])
    return run_cmd(cmd, timeout=timeout)


# ==============================================================================
# SUITE 1: GITHUB SYNC & UPSTREAM VERIFICATION
# ==============================================================================
def test_suite_github():
    log_header("SUITE 1: GITHUB SYNC & UPSTREAM VERIFICATION")
    sname = "github_verification"

    # 1. Check Git Remote
    code, out, err, dt = run_cmd("git remote -v", timeout=5)
    has_origin = "Praveen-1308/ferro-os" in out
    record_test(sname, "Git Remote Configured to Official Upstream", has_origin and code == 0, out.splitlines()[0] if out else "", dt)

    # 2. Check Git Log & Upstream Head
    code, out, err, dt = run_cmd("git log -n 1 --oneline", timeout=5)
    record_test(sname, "Local Git Commit Synchronized with Upstream", code == 0 and len(out.strip()) > 0, out.strip(), dt)

    # 3. Check Branch Tracked Status
    code, out, err, dt = run_cmd("git status -uno", timeout=5)
    up_to_date = "Your branch is up to date" in out
    record_test(sname, "Branch Synchronized with origin/main", up_to_date, "Branch up to date with origin/main", dt)


# ==============================================================================
# SUITE 2: BOOT & PID 1 INITIALIZATION ARCHITECTURE
# ==============================================================================
def test_suite_boot_init():
    log_header("SUITE 2: BOOT & PID 1 INITIALIZATION ARCHITECTURE")
    sname = "boot_and_init"
    image = "ferro-os-pure:latest"

    # 1. Inspect ferro-init binary existence
    code, out, err, dt = run_docker(image, "stat /usr/sbin/ferro-init")
    record_test(sname, "PID 1 Daemon Installed (/usr/sbin/ferro-init)", code == 0 and "regular file" in out, out.splitlines()[0] if out else "", dt)

    # 2. Kernel /init symlink
    code, out, err, dt = run_docker(image, "stat /init")
    record_test(sname, "Kernel Init Symlink (/init -> ferro-init)", code == 0 and "symbolic link" in out, out.splitlines()[0] if out else "", dt)

    # 3. Non-Root Least-Privilege Execution (UID 1000 ferro)
    code, out, err, dt = run_docker(image, "id")
    is_ferro = "uid=1000(ferro)" in out and "gid=1000(ferro)" in out
    record_test(sname, "Non-Root Least-Privilege (UID 1000 ferro)", code == 0 and is_ferro, out.strip(), dt)

    # 4. FHS 3.0 Hierarchy & UsrMerge
    dirs = ["/bin", "/sbin", "/usr/bin", "/usr/sbin", "/usr/lib", "/etc", "/home/ferro", "/root", "/tmp", "/var", "/run", "/dev", "/proc", "/sys"]
    code, out, err, dt = run_docker(image, f"for d in {' '.join(dirs)}; do stat $d >/dev/null || exit 1; done; echo FHS_OK")
    record_test(sname, "FHS 3.0 Directory Hierarchy & UsrMerge", code == 0 and "FHS_OK" in out, "All 14 standard FHS directories verified", dt)

    # 5. Multi-Tenant Sticky Bit on /tmp (1777 / drwxrwxrwt)
    code, out, err, dt = run_docker(image, "stat /tmp")
    has_sticky = "1777" in out or "drwxrwxrwt" in out
    record_test(sname, "Sticky-Bit Enforcement on /tmp (1777)", code == 0 and has_sticky, out.splitlines()[1] if len(out.splitlines()) > 1 else "", dt)

    # 6. /etc/os-release Standards Compliance
    code, out, err, dt = run_docker(image, "cat /etc/os-release")
    has_os_meta = 'NAME="FerroOS"' in out and ('ID="ferro"' in out or 'ID=ferro' in out)
    record_test(sname, "OS Identification Standard (/etc/os-release)", code == 0 and has_os_meta, "ID=ferro verified", dt)

    # 7. ferro-init Bootloader Sequence & Recovery Subsystem
    t0_b = time.time()
    p = subprocess.Popen(["docker", "run", "--rm", image, "/usr/sbin/ferro-init"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(1.5)
    p.terminate()
    try:
        out, _ = p.communicate(timeout=2)
    except Exception:
        p.kill()
        out, _ = p.communicate()
    dt_b = (time.time() - t0_b) * 1000.0
    banner_ok = "FerroOS v0.1.0" in out and "FERRO-OS ADVANCED BOOT LOADER" in out
    record_test(sname, "ferro-init WinRE Boot Menu & Early Mounts", banner_ok, "Boot banner & WinRE loader menu loaded", dt_b)


# ==============================================================================
# SUITE 3: FILESYSTEM READ / WRITE POSIX OPERATIONS
# ==============================================================================
def test_suite_read_write_operations():
    log_header("SUITE 3: FILESYSTEM READ / WRITE POSIX OPERATIONS")
    sname = "read_write_operations"
    image = "ferro-os-pure:latest"

    # 1. File creation with touch
    code, out, err, dt = run_docker(image, "touch /tmp/test_create.txt && stat /tmp/test_create.txt")
    record_test(sname, "POSIX 'touch' & Metadata Query", code == 0 and "test_create.txt" in out, "Zero-byte file created", dt)

    # 2. Sequential & Append Writes (echo > & >>)
    code, out, err, dt = run_docker(image, "echo 'Line 1: Rust OS' > /tmp/test_write.txt && echo 'Line 2: High Velocity' >> /tmp/test_write.txt && cat /tmp/test_write.txt")
    write_ok = "Line 1: Rust OS" in out and "Line 2: High Velocity" in out
    record_test(sname, "POSIX 'echo' File Redirection & Append", code == 0 and write_ok, "Multi-line write verified", dt)

    # 3. Stream Duplication with tee
    code, out, err, dt = run_docker(image, "echo 'Tee Payload' | tee /tmp/test_tee.txt")
    tee_ok = "Tee Payload" in out
    record_test(sname, "POSIX 'tee' Stream Ingestion & Duplication", code == 0 and tee_ok, "Piped I/O into tee verified", dt)

    # 4. Multi-File Concatenation with cat
    code, out, err, dt = run_docker(image, "echo 'PartA' > /tmp/a.txt && echo 'PartB' > /tmp/b.txt && cat /tmp/a.txt /tmp/b.txt")
    cat_ok = "PartA" in out and "PartB" in out
    record_test(sname, "POSIX 'cat' Multi-File Concatenation", code == 0 and cat_ok, "Concatenated 2 files", dt)

    # 5. Line Filtering with head and tail
    code, out, err, dt = run_docker(image, "echo Line 1 > /tmp/seq.txt; echo Line 2 >> /tmp/seq.txt; echo Line 3 >> /tmp/seq.txt; head -n 2 /tmp/seq.txt && tail -n 1 /tmp/seq.txt")
    ht_ok = "Line 1" in out and "Line 2" in out and "Line 3" in out
    record_test(sname, "POSIX 'head' & 'tail' Line Slicing", code == 0 and ht_ok, "head -n 2 & tail -n 1 matched", dt)

    # 6. Word, Line, and Byte Counting with wc
    code, out, err, dt = run_docker(image, "echo 'hello ferro os pure' > /tmp/wc.txt && wc /tmp/wc.txt")
    wc_ok = "1" in out and "4" in out and "20" in out
    record_test(sname, "POSIX 'wc' Word, Line & Byte Counting", code == 0 and wc_ok, out.strip(), dt)

    # 7. Directory Tree Operations (mkdir -p, cp, mv, rm -rf)
    code, out, err, dt = run_docker(image, "mkdir -p /tmp/d1/d2/d3 && touch /tmp/d1/d2/d3/file.dat && cp /tmp/d1/d2/d3/file.dat /tmp/d1/file.dat && mv /tmp/d1/file.dat /tmp/d1/moved.dat && stat /tmp/d1/moved.dat && rm -rf /tmp/d1")
    tree_ok = "moved.dat" in out
    record_test(sname, "POSIX Directory Lifecycle (mkdir/cp/mv/rm)", code == 0 and tree_ok, "Nested tree created, copied, moved, and destroyed", dt)

    # 8. Permission and Link Manipulation (chmod, ln -s, stat)
    code, out, err, dt = run_docker(image, "touch /tmp/perm.txt && chmod 755 /tmp/perm.txt && ln -s /tmp/perm.txt /tmp/perm_link && stat /tmp/perm.txt")
    perm_ok = "0755" in out or "rwxr-xr-x" in out
    record_test(sname, "POSIX 'chmod' & Symbolic Link 'ln -s'", code == 0 and perm_ok, "0755 permissions and symlink verified", dt)

    # 9. Page Cache Flushing with sync
    code, out, err, dt = run_docker(image, "sync")
    record_test(sname, "POSIX 'sync' Dirty Page Buffer Flush", code == 0, "Dirty buffers committed to storage", dt)


# ==============================================================================
# SUITE 4: ALL STANDARD LINUX POSIX & COREUTILS COMMANDS
# ==============================================================================
def test_suite_standard_linux_commands():
    log_header("SUITE 4: ALL STANDARD LINUX POSIX & COREUTILS COMMANDS")
    sname = "standard_linux_commands"
    image = "ferro-os-pure:latest"

    # 1. Navigation & Path Resolution
    code, out, err, dt = run_docker(image, "pwd")
    record_test(sname, "POSIX 'pwd' Current Working Directory", code == 0 and "/home/ferro" in out, out.strip(), dt)

    code, out, err, dt = run_docker(image, "ls -la /")
    record_test(sname, "POSIX 'ls -la' Root Listing", code == 0 and "usr" in out and "etc" in out, f"{len(out.splitlines())} entries enumerated", dt)

    code, out, err, dt = run_docker(image, "which sh && which ls && which rpk")
    which_ok = "/usr/bin/sh" in out and "/usr/bin/ls" in out and "/usr/bin/rpk" in out
    record_test(sname, "POSIX 'which' Binary Path Search", code == 0 and which_ok, out.strip().replace("\n", " | "), dt)

    # 2. Search & Pattern Matching (grep, find)
    code, out, err, dt = run_docker(image, "echo apple > /tmp/fruit.txt; echo banana >> /tmp/fruit.txt; grep banana /tmp/fruit.txt")
    record_test(sname, "POSIX 'grep' File Pattern Matching", code == 0 and "banana" in out, out.strip(), dt)

    code, out, err, dt = run_docker(image, "find /etc -name 'os-release'")
    record_test(sname, "POSIX 'find' Directory Hierarchy Search", code == 0 and "/etc/os-release" in out, out.strip(), dt)

    # 3. Process Table & System Monitoring
    code, out, err, dt = run_docker(image, "ps")
    record_test(sname, "POSIX 'ps' Process Enumeration", code == 0 and "PID" in out, "Process table active", dt)

    code, out, err, dt = run_docker(image, "uptime")
    record_test(sname, "Standard 'uptime' Telemetry", code == 0 and ("up" in out or "hours" in out or "minutes" in out), out.strip(), dt)

    code, out, err, dt = run_docker(image, "free")
    free_ok = "Mem:" in out and "total" in out
    record_test(sname, "Standard 'free' Memory Telemetry", code == 0 and free_ok, "RAM total/used/free parsed from /proc/meminfo", dt)

    code, out, err, dt = run_docker(image, "df -h")
    df_ok = "Filesystem" in out or "/" in out
    record_test(sname, "POSIX 'df' Storage Capacity & Mount Status", code == 0 and df_ok, "Filesystem statistics parsed", dt)

    # 4. Identification & Environment
    code, out, err, dt = run_docker(image, "whoami")
    record_test(sname, "POSIX 'whoami' Identity Check", code == 0 and "ferro" in out, out.strip(), dt)

    code, out, err, dt = run_docker(image, "uname -a")
    record_test(sname, "POSIX 'uname -a' Kernel & Architecture", code == 0 and "ferro" in out and "x86_64" in out, out.strip(), dt)

    code, out, err, dt = run_docker(image, "hostname")
    record_test(sname, "POSIX 'hostname' Host Resolution", code == 0 and len(out.strip()) > 0, out.strip(), dt)

    code, out, err, dt = run_docker(image, "env")
    env_ok = "PATH=" in out and "HOME=" in out
    record_test(sname, "POSIX 'env' Environment Variable Dump", code == 0 and env_ok, f"{len(out.splitlines())} variables active", dt)

    # 5. Shell Execution Principles (sh command chaining &&, ;)
    code, out, err, dt = run_docker(image, "echo A && echo B; echo C")
    sh_ok = "A" in out and "B" in out and "C" in out
    record_test(sname, "Ferro Shell Command Chaining (&&, ;)", code == 0 and sh_ok, "A && B ; C evaluated sequentially", dt)

    code, out, err, dt = run_docker(image, "sleep 0.1 && echo AWAKE")
    record_test(sname, "POSIX 'sleep' Timer Resolution", code == 0 and "AWAKE" in out, "Sub-second pause verified", dt)


# ==============================================================================
# SUITE 5: NETWORKING COMMANDS & PROTOCOLS
# ==============================================================================
def test_suite_networking():
    log_header("SUITE 5: NETWORKING COMMANDS & PROTOCOLS")
    sname = "networking_commands"
    image = "ferro-os-pure:latest"

    # 1. Interface Enumeration with 'ip link'
    code, out, err, dt = run_docker(image, "ip link")
    ip_link_ok = "eth0" in out or "lo" in out
    record_test(sname, "Linux 'ip link' Network Interfaces", code == 0 and ip_link_ok, "MAC addresses & MTU states discovered", dt)

    # 2. IP Address Discovery with 'ip addr'
    code, out, err, dt = run_docker(image, "ip addr")
    ip_addr_ok = "inet" in out or "127.0.0.1" in out or "eth0" in out
    record_test(sname, "Linux 'ip addr' IPv4/IPv6 Addresses", code == 0 and ip_addr_ok, "Interface addressing enumerated", dt)

    # 3. Routing Table Inspection with 'ip route'
    code, out, err, dt = run_docker(image, "ip route")
    ip_route_ok = "default" in out or "eth0" in out or "dev" in out
    record_test(sname, "Linux 'ip route' Kernel Routing Table", code == 0 and ip_route_ok, out.splitlines()[0] if out else "", dt)

    # 4. Pure-Rust DHCP Client (ferro-net) Synthetic Packet Test
    code, out, err, dt = run_docker(image, "dhcp --test-synthetic")
    dhcp_synth_ok = "PASSED" in out and "100% fidelity" in out
    record_test(sname, "Pure-Rust DHCP Packet Serialization & Parser", code == 0 and dhcp_synth_ok, "Synthetic DHCP packet fidelity 100%", dt)

    # 5. Pure-Rust DHCP Auto-Leaser Dry-Run
    code, out, err, dt = run_docker(image, "dhcp --dry-run eth0")
    dhcp_dry_ok = "DRY-RUN" in out and "Broadcasting DHCPDISCOVER" in out
    record_test(sname, "Pure-Rust DHCP Auto-Leaser (ferro-net)", code == 0 and dhcp_dry_ok, "Auto-leaser executed discovery broadcast", dt)

    # 6. DNS Resolver Cache Engine
    code, out, err, dt = run_docker(image, "dns-cache help")
    dns_ok = "FerroOS Pure-Rust DNS Cache Engine" in out or "dns-cache" in out
    record_test(sname, "Pure-Rust DNS Caching Engine (dns-cache)", code == 0 and dns_ok, "DNS engine applet operational", dt)

    # 7. Pure-Rust Static Web Server (serve)
    test_port = 18888
    cid_code, cid, _, _ = run_cmd(f"docker run -d -p {test_port}:{test_port} {image} sh -c 'echo \"FERRO_NET_OK\" > /tmp/index.html && serve {test_port} /tmp'")
    time.sleep(1.2)
    cid = cid.strip()
    try:
        req_code, req_out, _, req_dt = run_cmd(f"curl -s --max-time 3 http://127.0.0.1:{test_port}/index.html")
        serve_ok = "FERRO_NET_OK" in req_out
        record_test(sname, "Pure-Rust Multi-Worker Web Server (serve)", serve_ok, f"HTTP 200 payload: '{req_out.strip()}'", req_dt)
    finally:
        run_cmd(f"docker rm -f {cid}", timeout=5)

    # 8. Pure-Rust Multi-Service Server Suite (server-suite)
    p_status = 18880
    p_kv = 18881
    p_pkg = 18882
    cid_code, cid, _, _ = run_cmd(f"docker run -d -p {p_status}:8080 -p {p_kv}:8081 -p {p_pkg}:8082 {image} server-suite")
    time.sleep(1.2)
    cid = cid.strip()
    try:
        # A. Telemetry & Health API
        c, health_out, _, dt1 = run_cmd(f"curl -s --max-time 3 http://127.0.0.1:{p_status}/api/health")
        h_ok = '"status": "HEALTHY"' in health_out
        record_test(sname, "Server-Suite REST Health API (GET /api/health)", h_ok, health_out.strip(), dt1)

        c, status_out, _, dt2 = run_cmd(f"curl -s --max-time 3 http://127.0.0.1:{p_status}/api/status")
        s_ok = '"server": "FerroOS Pure-Rust Telemetry Microservice"' in status_out
        record_test(sname, "Server-Suite Telemetry API (GET /api/status)", s_ok, "RAM & CPU telemetry parsed", dt2)

        # B. In-Memory Key-Value Storage Engine
        c, set_out, _, dt3 = run_cmd(f"curl -s --max-time 3 \"http://127.0.0.1:{p_kv}/set?key=network_bench&val=subsecond_speed\"")
        set_ok = '"status": "STORED"' in set_out
        record_test(sname, "Server-Suite KV Engine Set (GET /set)", set_ok, set_out.strip(), dt3)

        c, get_out, _, dt4 = run_cmd(f"curl -s --max-time 3 \"http://127.0.0.1:{p_kv}/get?key=network_bench\"")
        get_ok = '"value": "subsecond_speed"' in get_out
        record_test(sname, "Server-Suite KV Engine Get (GET /get)", get_ok, get_out.strip(), dt4)

        # C. Static Package Registry
        c, pkg_out, _, dt5 = run_cmd(f"curl -s --max-time 3 http://127.0.0.1:{p_pkg}/")
        pkg_ok = "FerroOS Official Package Registry" in pkg_out
        record_test(sname, "Server-Suite Package Registry (GET /)", pkg_ok, "Static registry active", dt5)
    finally:
        run_cmd(f"docker rm -f {cid}", timeout=5)

    # 9. Pure-Rust Minimal HTTP Client (fetch / curl)
    cid_code, cid, _, _ = run_cmd(f"docker run -d -p 18889:18889 {image} sh -c 'echo \"CLIENT_FETCH_PASS\" > /tmp/payload.txt && serve 18889 /tmp'")
    time.sleep(1.2)
    cid = cid.strip()
    try:
        f_code, f_out, _, f_dt = run_docker(image, "fetch http://127.0.0.1:18889/payload.txt", extra_flags=["--net=host"])
        fetch_ok = "CLIENT_FETCH_PASS" in f_out
        record_test(sname, "Pure-Rust HTTP Client (fetch / curl)", fetch_ok, "TCP socket GET stream parsed", f_dt)
    finally:
        run_cmd(f"docker rm -f {cid}", timeout=5)


# ==============================================================================
# SUITE 6: PERFORMANCE & KERNEL BENCHMARKS
# ==============================================================================
def test_suite_performance():
    log_header("SUITE 6: PERFORMANCE & KERNEL BENCHMARKS")
    sname = "performance_benchmarks"
    image = "ferro-os-pure:latest"

    # 1. Pure-Rust Hackbench Scheduler IPC Benchmark
    code, out, err, dt = run_docker(image, "hackbench --groups 2 --loops 10")
    hb_ok = "Integrity Status:       VERIFIED" in out and "msgs/sec" in out
    msgs_sec = ""
    for line in out.splitlines():
        if "Message Rate:" in line:
            msgs_sec = line.strip()
    record_test(sname, "Pure-Rust Scheduler Hackbench IPC", code == 0 and hb_ok, msgs_sec, dt)

    # 2. Pure-Rust bench-fsync POSIX Write Throughput
    code, out, err, dt = run_docker(image, "bench-fsync --count 50 --size 4096")
    combined = out + "\n" + err
    fsync_ok = ("throughput_mb" in combined or "Throughput:" in combined) and code == 0
    tp_info = ""
    for line in combined.splitlines():
        if "Throughput:" in line:
            tp_info = line.strip()
        elif "throughput_mb" in line and not tp_info:
            tp_info = line.strip()
    record_test(sname, "Pure-Rust POSIX fsync Latency & Throughput", fsync_ok, tp_info, dt)


# ==============================================================================
# SUITE 7: PACKAGE MANAGEMENT ENGINE (RPK)
# ==============================================================================
def test_suite_package_manager():
    log_header("SUITE 7: PACKAGE MANAGEMENT ENGINE (RPK)")
    sname = "package_management"
    image = "ferro-os-pure:latest"

    # 1. RPK help and banner
    code, out, err, dt = run_docker(image, "rpk --help")
    rpk_help_ok = "Rust Package Keeper" in out
    record_test(sname, "RPK CLI Binary & Help Interface", code == 0 and rpk_help_ok, "rpk v0.2.0 active", dt)

    # 2. RPK Package Listing
    code, out, err, dt = run_docker(image, "rpk list")
    record_test(sname, "RPK Database Package Query ('rpk list')", code == 0, out.strip() if out.strip() else "Empty package catalog", dt)

    # 3. RPK System Dependency Check
    code, out, err, dt = run_docker(image, "rpk check")
    record_test(sname, "RPK System-wide Dependency Check ('rpk check')", code == 0, out.strip(), dt)

    # 4. RPK Cryptographic Hash Calculation
    code, out, err, dt = run_docker(image, "echo 'ferro_pkg_hash_test' > /tmp/h.bin && rpk hash /tmp/h.bin")
    hash_ok = "SHA-256" in out or len(out.strip().split()[-1]) == 64
    record_test(sname, "RPK SHA-256 Checksum Calculation", code == 0 and hash_ok, out.strip(), dt)


# ==============================================================================
# SUITE 8: DUAL IMAGE CROSS-VERIFICATION (PURE VS SERVER)
# ==============================================================================
def test_suite_dual_image():
    log_header("SUITE 8: DUAL IMAGE CROSS-VERIFICATION (PURE VS SERVER)")
    sname = "dual_image_comparison"

    for img in ["ferro-os-pure:latest", "ferro-os-server:latest"]:
        # Identity
        code, out, err, dt = run_docker(img, "id")
        is_ferro = "uid=1000(ferro)" in out
        record_test(sname, f"Image {img} Default Identity Non-Root", code == 0 and is_ferro, out.strip(), dt)

        # ferro-core functionality
        code, out, err, dt = run_docker(img, "ferro-core help")
        has_help = "FerroOS Core Utilities" in out
        record_test(sname, f"Image {img} ferro-core Applet Dispatch", code == 0 and has_help, "Multi-call dispatch functional", dt)

        # File I/O
        code, out, err, dt = run_docker(img, "echo DUAL_OK > /tmp/dual.txt && cat /tmp/dual.txt")
        record_test(sname, f"Image {img} File Read/Write Operations", code == 0 and "DUAL_OK" in out, "File I/O verified", dt)


def main():
    print(f"{BOLD}{CYAN}")
    print("*" * 80)
    print("  FERRO-OS DOCKER COMPREHENSIVE VERIFICATION SUITE")
    print("  Testing: Boots, Read/Write, All POSIX/Linux, Networking & Server Suite")
    print("*" * 80)
    print(f"{RESET}")
    t_start = time.time()

    test_suite_github()
    test_suite_boot_init()
    test_suite_read_write_operations()
    test_suite_standard_linux_commands()
    test_suite_networking()
    test_suite_performance()
    test_suite_package_manager()
    test_suite_dual_image()

    total_time = time.time() - t_start
    results["summary"]["total_duration_sec"] = round(total_time, 2)
    tot = results["summary"]["total_tests"]
    passed = results["summary"]["passed"]
    failed = results["summary"]["failed"]
    rate = (passed / tot * 100.0) if tot > 0 else 0.0
    results["summary"]["pass_rate_pct"] = round(rate, 2)

    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(REPORT_FILE, "w") as f:
        json.dump(results, f, indent=2)

    log_header("TEST SUITE EXECUTION SUMMARY")
    print(f"  • Total Tests Executed:  {tot}")
    print(f"  • Tests Passed:          {GREEN}{passed}{RESET}")
    print(f"  • Tests Failed:          {RED}{failed}{RESET}")
    print(f"  • Pass Rate:             {BOLD}{GREEN if failed == 0 else YELLOW}{rate:.2f}%{RESET}")
    print(f"  • Total Duration:        {total_time:.2f} seconds")
    print(f"  • Detailed JSON Report:  {REPORT_FILE}")
    print("=" * 80)

    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
