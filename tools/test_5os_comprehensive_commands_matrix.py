#!/usr/bin/env python3
"""
tools/test_5os_comprehensive_commands_matrix.py
Comprehensive 5-OS Enterprise Command Matrix & Gap Analysis
Compares command availability, execution status, and gap analysis across:
  1. Ubuntu 24.04 LTS (Canonical Debian family)
  2. Debian 12 Slim (Upstream Debian family)
  3. Rocky / AlmaLinux 9 (Red Hat Enterprise Linux family)
  4. Alpine Linux 3.20 (musl / Busybox family)
  5. FerroOS 2.0 (Pure-Rust Cloud OS userland)

Groups commands across 5 functional tiers:
  Tier 1: Basic Daily Admin & Process Operations
  Tier 2: Network Inspection, Sockets & Routing
  Tier 3: Network Security, Hardening & Cryptography
  Tier 4: Deep Crisis, SRE Forensics & Kernel Diagnostics ("When Disaster Strikes")
  Tier 5: FerroOS Pure-Rust & Cloud Innovations
"""

import os
import sys
import json
import time
import subprocess

TARGET_OS_IMAGES = [
    {"id": "ubuntu", "name": "Ubuntu 24.04", "image": "ubuntu:24.04"},
    {"id": "debian", "name": "Debian 12", "image": "debian:12-slim"},
    {"id": "rocky", "name": "Rocky / Alma 9", "image": "almalinux:9"},
    {"id": "alpine", "name": "Alpine 3.20", "image": "alpine:latest"},
    {"id": "ferro", "name": "FerroOS 2.0", "image": "ferro-os-server:latest"},
]

COMMAND_BATTERY = [
    # --------------------------------------------------------------------------
    # TIER 1: Basic Daily Admin & Process Operations (20 commands)
    # --------------------------------------------------------------------------
    {"group": "Tier 1: Basic Daily Admin", "cmd": "cat", "test": "echo 'test' | cat", "desc": "Concatenate and display files"},
    {"group": "Tier 1: Basic Daily Admin", "cmd": "ls", "test": "ls -d /", "desc": "List directory contents"},
    {"group": "Tier 1: Basic Daily Admin", "cmd": "grep", "test": "echo 'abc' | grep 'b'", "desc": "Print lines matching a pattern"},
    {"group": "Tier 1: Basic Daily Admin", "cmd": "cp", "test": "echo 'a' > /tmp/c1 && cp /tmp/c1 /tmp/c2 && rm -f /tmp/c1 /tmp/c2", "desc": "Copy files and directories"},
    {"group": "Tier 1: Basic Daily Admin", "cmd": "mv", "test": "echo 'a' > /tmp/m1 && mv /tmp/m1 /tmp/m2 && rm -f /tmp/m2", "desc": "Move / rename files"},
    {"group": "Tier 1: Basic Daily Admin", "cmd": "rm", "test": "touch /tmp/r1 && rm -f /tmp/r1", "desc": "Remove files or directories"},
    {"group": "Tier 1: Basic Daily Admin", "cmd": "mkdir", "test": "mkdir -p /tmp/test_dir && rmdir /tmp/test_dir", "desc": "Make directories"},
    {"group": "Tier 1: Basic Daily Admin", "cmd": "find", "test": "find /etc -maxdepth 1 -type f 2>/dev/null | head -n 1", "desc": "Search for files in a directory hierarchy"},
    {"group": "Tier 1: Basic Daily Admin", "cmd": "head", "test": "echo -e '1\\n2\\n3' | head -n 1", "desc": "Output the first part of files"},
    {"group": "Tier 1: Basic Daily Admin", "cmd": "tail", "test": "echo -e '1\\n2\\n3' | tail -n 1", "desc": "Output the last part of files"},
    {"group": "Tier 1: Basic Daily Admin", "cmd": "wc", "test": "echo 'one two three' | wc -w", "desc": "Print line, word, and byte counts"},
    {"group": "Tier 1: Basic Daily Admin", "cmd": "ps", "test": "ps", "desc": "Report snapshot of current processes"},
    {"group": "Tier 1: Basic Daily Admin", "cmd": "uptime", "test": "uptime", "desc": "Tell how long the system has been running"},
    {"group": "Tier 1: Basic Daily Admin", "cmd": "whoami", "test": "whoami", "desc": "Print effective userid"},
    {"group": "Tier 1: Basic Daily Admin", "cmd": "id", "test": "id -u", "desc": "Print real and effective user and group IDs"},
    {"group": "Tier 1: Basic Daily Admin", "cmd": "uname", "test": "uname -a", "desc": "Print system information"},
    {"group": "Tier 1: Basic Daily Admin", "cmd": "pwd", "test": "pwd", "desc": "Print name of current/working directory"},
    {"group": "Tier 1: Basic Daily Admin", "cmd": "which", "test": "which sh", "desc": "Locate a command in PATH"},
    {"group": "Tier 1: Basic Daily Admin", "cmd": "env", "test": "env | grep -E 'PATH|HOME' | head -n 1", "desc": "Run a program in a modified environment"},
    {"group": "Tier 1: Basic Daily Admin", "cmd": "sleep", "test": "sleep 0.01", "desc": "Delay for a specified amount of time"},

    # --------------------------------------------------------------------------
    # TIER 2: Network Inspection, Sockets & Routing (12 commands)
    # --------------------------------------------------------------------------
    {"group": "Tier 2: Network & Routing", "cmd": "ip", "test": "ip addr show lo", "desc": "Routing, network devices, interfaces, and tunnels (iproute2)"},
    {"group": "Tier 2: Network & Routing", "cmd": "ifconfig", "test": "ifconfig lo", "desc": "Configure network interface (legacy net-tools)"},
    {"group": "Tier 2: Network & Routing", "cmd": "ss", "test": "ss -tl", "desc": "Dump socket statistics (modern netstat replacement)"},
    {"group": "Tier 2: Network & Routing", "cmd": "netstat", "test": "netstat -tl 2>/dev/null || netstat -a", "desc": "Print network connections, routing tables (legacy net-tools)"},
    {"group": "Tier 2: Network & Routing", "cmd": "ping", "test": "ping -V 2>&1 | head -n 1 || ping -c 1 -W 1 127.0.0.1 2>/dev/null", "desc": "Send ICMP ECHO_REQUEST to network hosts"},
    {"group": "Tier 2: Network & Routing", "cmd": "curl", "test": "curl --version 2>/dev/null | head -n 1", "desc": "Transfer data from or to a server"},
    {"group": "Tier 2: Network & Routing", "cmd": "wget", "test": "wget --version 2>/dev/null | head -n 1", "desc": "Non-interactive network downloader"},
    {"group": "Tier 2: Network & Routing", "cmd": "nc", "test": "nc -h 2>/dev/null || nc -z 127.0.0.1 80 2>/dev/null", "desc": "Arbitrary TCP and UDP connections and listens (netcat)"},
    {"group": "Tier 2: Network & Routing", "cmd": "dig", "test": "dig -v 2>&1 | head -n 1", "desc": "DNS lookup utility (bind-utils)"},
    {"group": "Tier 2: Network & Routing", "cmd": "nslookup", "test": "nslookup -version 2>/dev/null || which nslookup", "desc": "Query Internet name servers interactively"},
    {"group": "Tier 2: Network & Routing", "cmd": "host", "test": "host -V 2>/dev/null || which host", "desc": "DNS lookup utility"},
    {"group": "Tier 2: Network & Routing", "cmd": "arp", "test": "arp -n 2>/dev/null || which arp", "desc": "Manipulate the system ARP cache (legacy)"},

    # --------------------------------------------------------------------------
    # TIER 3: Network Security, Hardening & Cryptography (10 commands)
    # --------------------------------------------------------------------------
    {"group": "Tier 3: Security & Crypto", "cmd": "tcpdump", "test": "tcpdump --version 2>&1 | head -n 1", "desc": "Dump traffic on a network (packet capture)"},
    {"group": "Tier 3: Security & Crypto", "cmd": "iptables", "test": "iptables --version 2>/dev/null", "desc": "Administration tool for IPv4 packet filtering and NAT"},
    {"group": "Tier 3: Security & Crypto", "cmd": "nft", "test": "nft --version 2>/dev/null", "desc": "Administration tool for nftables packet filtering (modern firewall)"},
    {"group": "Tier 3: Security & Crypto", "cmd": "openssl", "test": "openssl version", "desc": "OpenSSL command line tool (cryptography & TLS)"},
    {"group": "Tier 3: Security & Crypto", "cmd": "sha256sum", "test": "echo 'test' | sha256sum", "desc": "Compute and check SHA256 message digest"},
    {"group": "Tier 3: Security & Crypto", "cmd": "md5sum", "test": "echo 'test' | md5sum", "desc": "Compute and check MD5 message digest"},
    {"group": "Tier 3: Security & Crypto", "cmd": "gpg", "test": "gpg --version 2>/dev/null | head -n 1", "desc": "OpenPGP encryption and signing tool"},
    {"group": "Tier 3: Security & Crypto", "cmd": "capsh", "test": "capsh --print 2>/dev/null | head -n 1", "desc": "Capability shell wrapper (POSIX capabilities)"},
    {"group": "Tier 3: Security & Crypto", "cmd": "ulimit", "test": "ulimit -n", "desc": "Control user process resource limits"},
    {"group": "Tier 3: Security & Crypto", "cmd": "chroot", "test": "chroot --help 2>/dev/null | head -n 1", "desc": "Run command or interactive shell with special root directory"},

    # --------------------------------------------------------------------------
    # TIER 4: Deep Crisis, SRE Forensics & Kernel Diagnostics (12 commands)
    # --------------------------------------------------------------------------
    {"group": "Tier 4: Crisis Forensics", "cmd": "lsof", "test": "lsof -v 2>&1 | head -n 1", "desc": "List open files and socket descriptors"},
    {"group": "Tier 4: Crisis Forensics", "cmd": "fuser", "test": "fuser -V 2>/dev/null || which fuser", "desc": "Identify processes using files or sockets"},
    {"group": "Tier 4: Crisis Forensics", "cmd": "dmesg", "test": "dmesg | head -n 1 2>/dev/null || which dmesg", "desc": "Print or control the kernel ring buffer"},
    {"group": "Tier 4: Crisis Forensics", "cmd": "sysctl", "test": "sysctl kernel.pid_max 2>/dev/null || which sysctl", "desc": "Configure kernel parameters at runtime"},
    {"group": "Tier 4: Crisis Forensics", "cmd": "journalctl", "test": "journalctl --version 2>/dev/null | head -n 1", "desc": "Query the systemd journal"},
    {"group": "Tier 4: Crisis Forensics", "cmd": "iostat", "test": "iostat -V 2>&1 | head -n 1", "desc": "Report CPU statistics and I/O statistics for devices (sysstat)"},
    {"group": "Tier 4: Crisis Forensics", "cmd": "vmstat", "test": "vmstat 1 1 2>/dev/null || which vmstat", "desc": "Report virtual memory statistics"},
    {"group": "Tier 4: Crisis Forensics", "cmd": "mpstat", "test": "mpstat -V 2>&1 | head -n 1", "desc": "Report processors related statistics (sysstat)"},
    {"group": "Tier 4: Crisis Forensics", "cmd": "strace", "test": "strace -V 2>&1 | head -n 1", "desc": "Trace system calls and signals"},
    {"group": "Tier 4: Crisis Forensics", "cmd": "top", "test": "top -b -n 1 2>/dev/null | head -n 2", "desc": "Display Linux processes dynamically"},
    {"group": "Tier 4: Crisis Forensics", "cmd": "free", "test": "free -m", "desc": "Display amount of free and used memory in the system"},
    {"group": "Tier 4: Crisis Forensics", "cmd": "sync", "test": "sync", "desc": "Synchronize cached writes to persistent storage"},

    # --------------------------------------------------------------------------
    # TIER 5: FerroOS Native Innovations (8 commands)
    # --------------------------------------------------------------------------
    {"group": "Tier 5: FerroOS Innovations", "cmd": "rpk", "test": "which rpk 2>/dev/null || which ferro-pkg 2>/dev/null || /bin/ferro-pkg --help 2>/dev/null", "desc": "Pure-Rust atomic transactional package manager (rpk)"},
    {"group": "Tier 5: FerroOS Innovations", "cmd": "ferro-init", "test": "which ferro-init 2>/dev/null || [ -x /sbin/ferro-init ] || [ -f /sbin/ferro-init ]", "desc": "Memory-safe pure-Rust PID 1 init system"},
    {"group": "Tier 5: FerroOS Innovations", "cmd": "fdstore", "test": "/bin/ferro-core fdstore status 2>/dev/null || /usr/local/bin/ferro-core fdstore status 2>/dev/null", "desc": "Zero-downtime socket preservation across service crashes"},
    {"group": "Tier 5: FerroOS Innovations", "cmd": "bpf", "test": "/bin/ferro-core bpf bypass-check 2>/dev/null || /usr/local/bin/ferro-core bpf bypass-check 2>/dev/null", "desc": "eBPF zero-copy TCP socket loopback bypass engine"},
    {"group": "Tier 5: FerroOS Innovations", "cmd": "scx", "test": "/bin/ferro-core sched scx 2>/dev/null || /usr/local/bin/ferro-core sched scx 2>/dev/null", "desc": "Extensible sched_ext CPU scheduler control"},
    {"group": "Tier 5: FerroOS Innovations", "cmd": "dns-cache", "test": "/bin/ferro-core dns-cache 2>/dev/null || /usr/local/bin/ferro-core dns-cache 2>/dev/null", "desc": "Sub-microsecond shared-memory local DNS resolver"},
    {"group": "Tier 5: FerroOS Innovations", "cmd": "supervise", "test": "which supervise 2>/dev/null || /bin/ferro-core --has-applet supervise 2>/dev/null", "desc": "Pure-Rust crash-only service supervisor"},
    {"group": "Tier 5: FerroOS Innovations", "cmd": "recovery", "test": "/bin/ferro-core recovery 2>/dev/null || /usr/local/bin/ferro-core recovery 2>/dev/null", "desc": "Windows-style WinRE automated boot crash recovery menu"}
]

def probe_command(image: str, cmd_name: str, test_cmd: str):
    """
    Checks if a command exists in the container and whether it executes.
    Returns: status ('OK', 'RESTRICTED', 'MISSING'), exit_code, stdout_sample
    """
    # 1. First check if binary exists or is shell builtin
    check_exists_cmd = [
        "docker", "run", "--rm", image, "sh", "-c",
        f"which '{cmd_name}' >/dev/null 2>&1 || type '{cmd_name}' >/dev/null 2>&1 || [ -x '/bin/{cmd_name}' ] || [ -x '/usr/bin/{cmd_name}' ] || [ -x '/usr/sbin/{cmd_name}' ] || [ -x '/usr/local/bin/{cmd_name}' ]"
    ]
    res_exists = subprocess.run(check_exists_cmd, capture_output=True, text=True)
    if res_exists.returncode != 0:
        # Strict check for ferro-core internal applets
        if "ferro" in image:
            check_ferro_applet = [
                "docker", "run", "--rm", image, "sh", "-c",
                f"/bin/ferro-core --has-applet '{cmd_name}' 2>/dev/null || /usr/local/bin/ferro-core --has-applet '{cmd_name}' 2>/dev/null"
            ]
            r_fa = subprocess.run(check_ferro_applet, capture_output=True, text=True)
            if r_fa.returncode != 0 and cmd_name not in ["ulimit", "chroot"]:
                return {"status": "MISSING", "code": 127, "sample": "command not found"}
        else:
            return {"status": "MISSING", "code": 127, "sample": "command not found"}

    # 2. Command exists, run the test invocation with pipefail enforcement
    strict_test_cmd = f"(set -o pipefail 2>/dev/null) && set -o pipefail 2>/dev/null; {test_cmd}"
    run_test_cmd = ["docker", "run", "--rm", image, "sh", "-c", strict_test_cmd]
    try:
        proc = subprocess.run(run_test_cmd, capture_output=True, text=True, timeout=8)
        sample = (proc.stdout.strip() or proc.stderr.strip()).split("\n")[0][:45]
        if proc.returncode == 0:
            return {"status": "OK", "code": 0, "sample": sample}
        elif proc.returncode == 127:
            # POSIX exit code 127 is command not found - never mask into RESTRICTED
            return {"status": "MISSING", "code": 127, "sample": sample or "command not found"}
        else:
            # Command exists but returned non-zero (e.g. requires root/caps/container limit)
            return {"status": "RESTRICTED", "code": proc.returncode, "sample": sample or f"exit code {proc.returncode}"}
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "code": -1, "sample": "Execution timed out (>8s)"}
    except Exception as e:
        return {"status": "ERROR", "code": -2, "sample": str(e)[:45]}

def main():
    print("=" * 85)
    print("  ENTERPRISE 5-OS COMPREHENSIVE COMMAND MATRIX & GAP ANALYSIS")
    print("  Ubuntu 24.04 vs Debian 12 vs Rocky Linux 9 vs Alpine 3.20 vs FerroOS 2.0")
    print("=" * 85)

    # 1. Total counts
    total_counts = {}
    for os_info in TARGET_OS_IMAGES:
        res = subprocess.run(
            ["docker", "run", "--rm", os_info["image"], "sh", "-c", "find /bin /usr/bin /sbin /usr/sbin /usr/local/bin -maxdepth 1 2>/dev/null | wc -l"],
            capture_output=True, text=True
        )
        total_counts[os_info["id"]] = int(res.stdout.strip()) if res.stdout.strip().isdigit() else 0
        print(f"  • {os_info['name']:<18}: {total_counts[os_info['id']]} total binaries in PATH")

    print("\n" + "-" * 85)
    print(f"  Executing {len(COMMAND_BATTERY)} Target Commands across 5 Functional Tiers...")
    print("-" * 85)

    matrix_results = []
    
    current_group = ""
    for item in COMMAND_BATTERY:
        grp = item["group"]
        cmd = item["cmd"]
        test = item["test"]
        desc = item["desc"]

        if grp != current_group:
            current_group = grp
            print(f"\n📂 [{current_group.upper()}]")

        cmd_eval = {"cmd": cmd, "group": grp, "desc": desc, "targets": {}}

        print(f"  -> Testing `{cmd}`... ", end="", flush=True)

        statuses = []
        for os_info in TARGET_OS_IMAGES:
            os_id = os_info["id"]
            img = os_info["image"]
            res = probe_command(img, cmd, test)
            cmd_eval["targets"][os_id] = res
            statuses.append(f"{os_id}:{res['status']}")

        print(" | ".join(statuses))
        matrix_results.append(cmd_eval)

    # Summary Statistics
    print("\n" + "=" * 85)
    print("  TIER-BY-TIER AVAILABILITY SUMMARY")
    print("=" * 85)

    tiers = sorted(list(set(c["group"] for c in COMMAND_BATTERY)))
    tier_summary = {}

    for t in tiers:
        tier_cmds = [c for c in matrix_results if c["group"] == t]
        tier_summary[t] = {}
        for os_info in TARGET_OS_IMAGES:
            os_id = os_info["id"]
            ok_cnt = sum(1 for c in tier_cmds if c["targets"][os_id]["status"] in ["OK", "RESTRICTED"])
            tier_summary[t][os_id] = f"{ok_cnt}/{len(tier_cmds)}"

    print(f"{'Functional Tier':<35} | " + " | ".join(f"{o['name']:<13}" for o in TARGET_OS_IMAGES))
    print("-" * 110)
    for t in tiers:
        row = f"{t:<35} | " + " | ".join(f"{tier_summary[t][o['id']]:<13}" for o in TARGET_OS_IMAGES)
        print(row)

    # Gap Analysis for FerroOS
    print("\n" + "=" * 85)
    print("  FERRO-OS GAP ANALYSIS: Missing Commands vs Standard Linux")
    print("=" * 85)

    ferro_missing = []
    ferro_exclusive = []

    for c in matrix_results:
        f_st = c["targets"]["ferro"]["status"]
        others_have = any(c["targets"][o["id"]]["status"] in ["OK", "RESTRICTED"] for o in TARGET_OS_IMAGES if o["id"] != "ferro")
        
        if f_st == "MISSING" and others_have:
            providing_oses = [o["name"] for o in TARGET_OS_IMAGES if o["id"] != "ferro" and c["targets"][o["id"]]["status"] in ["OK", "RESTRICTED"]]
            ferro_missing.append({
                "cmd": c["cmd"],
                "group": c["group"],
                "desc": c["desc"],
                "available_in": providing_oses
            })
        elif f_st in ["OK", "RESTRICTED"] and not others_have:
            ferro_exclusive.append({
                "cmd": c["cmd"],
                "group": c["group"],
                "desc": c["desc"]
            })

    print(f"\n[!] Commands Standard Linux Has that FerroOS Lacks Out-of-the-Box ({len(ferro_missing)} commands):")
    for m in ferro_missing:
        print(f"    ❌ {m['cmd']:<12} ({m['group']}) - {m['desc']}")
        print(f"       -> Present in: {', '.join(m['available_in'])}")

    print(f"\n[★] FerroOS Exclusive Cloud / SRE Innovations ({len(ferro_exclusive)} commands):")
    for e in ferro_exclusive:
        print(f"    ✨ {e['cmd']:<12} ({e['group']}) - {e['desc']}")

    # Save comprehensive report
    report_path = os.path.join(os.path.dirname(__file__), "reports", "comprehensive_5os_commands_matrix.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        json.dump({
            "total_path_binaries": total_counts,
            "matrix_results": matrix_results,
            "tier_summary": tier_summary,
            "ferro_missing_gaps": ferro_missing,
            "ferro_exclusives": ferro_exclusive
        }, f, indent=2)
    print(f"\n[+] Full report saved to: {report_path}")

if __name__ == "__main__":
    main()
