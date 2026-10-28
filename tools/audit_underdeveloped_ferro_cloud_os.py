#!/usr/bin/env python3
"""
tools/audit_underdeveloped_ferro_cloud_os.py - Comprehensive Real-World Cloud OS Operations & Gap Audit
Executes 25 real-world daily sysadmin tasks, shell scripts, text pipelines, developer operations,
and diagnostic checks on FerroOS vs Ubuntu Server vs Alpine Linux to identify underdeveloped parts.
"""

import subprocess
import time
import json
import os
import sys

def run_in_container(image, cmd_str):
    """Executes a command inside a fresh container and returns (returncode, stdout, stderr, latency_ms)"""
    t0 = time.time()
    docker_cmd = [
        "docker", "run", "--rm",
        "--memory=128m",
        image,
        "/bin/sh", "-c", cmd_str
    ]
    res = subprocess.run(docker_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    latency_ms = (time.time() - t0) * 1000.0
    return res.returncode, res.stdout.strip(), res.stderr.strip(), latency_ms

def main():
    print("=" * 84)
    print("      FERRO-OS CLOUD OPERATIONS & UNDERDEVELOPED SUBSYSTEM AUDIT        ")
    print("================================================================================")

    # Images under test
    images = {
        "FerroOS": "ferro-python-qa:latest",
        "Ubuntu": "bench-ubuntu:latest",
        "Alpine": "alpine:latest"
    }

    # Test Suite: Real daily sysadmin & cloud operations
    test_cases = [
        # Category A: Shell Syntax & Script Grammar
        {
            "id": "A1_VAR_EXPANSION",
            "cat": "Shell Grammar",
            "name": "Variable & Default Value Expansion",
            "cmd": "FOO=bar; echo \"VAL: $FOO\"; echo \"DEFAULT: ${UNSET_VAR:-default_val}\""
        },
        {
            "id": "A2_CMD_SUBSTITUTION",
            "cat": "Shell Grammar",
            "name": "Command Substitution $(...) and Exit Status $?",
            "cmd": "OUT=$(uname -s); echo \"OS: $OUT\"; true; echo \"RC: $?\""
        },
        {
            "id": "A3_LOGICAL_CHAINING",
            "cat": "Shell Grammar",
            "name": "Logical AND/OR Chaining (&&, ||)",
            "cmd": "echo 1 && echo 2 || echo 3; false && echo 4 || echo 5"
        },
        {
            "id": "A4_LOOP_SYNTAX",
            "cat": "Shell Grammar",
            "name": "For Loop Iteration (for x in a b c; do ... done)",
            "cmd": "for x in alpha beta gamma; do echo \"ITEM: $x\"; done"
        },
        {
            "id": "A5_IF_TEST_SYNTAX",
            "cat": "Shell Grammar",
            "name": "Conditional If-Then-Else with [ -d ... ]",
            "cmd": "if [ -d /tmp ]; then echo 'TMP_EXISTS'; else echo 'NO_TMP'; fi"
        },
        {
            "id": "A6_MULTI_PIPE_REDIRECT",
            "cat": "Shell Grammar",
            "name": "Multi-stage Pipe and Redirection (| and >)",
            "cmd": "echo -e 'zebra\\napple\\nbanana' | grep -v 'apple' | sort > /tmp/test_sort.txt; cat /tmp/test_sort.txt"
        },

        # Category B: Text Processing & Pipelines
        {
            "id": "B1_GREP_FLAGS",
            "cat": "Text Processing",
            "name": "Grep Flags (-i, -v, -c, -n)",
            "cmd": "echo -e 'Error: 404\\nINFO: 200\\nerror: 500' | grep -i -c 'error'"
        },
        {
            "id": "B2_FIND_COMMAND",
            "cat": "Text Processing",
            "name": "Find Command with -name and -type",
            "cmd": "find /etc -name '*.conf' 2>/dev/null | head -n 3"
        },
        {
            "id": "B3_SED_STREAM_EDITOR",
            "cat": "Text Processing",
            "name": "Sed Stream Editor (sed 's/foo/bar/g')",
            "cmd": "echo 'Hello World 2026' | sed 's/World/Cloud/g'"
        },
        {
            "id": "B4_AWK_COLUMN_PARSER",
            "cat": "Text Processing",
            "name": "Awk Column Parser (awk '{print $1, $3}')",
            "cmd": "echo 'root 1000 0.0' | awk '{print \"USER:\" $1, \"PID:\" $2}'"
        },
        {
            "id": "B5_HEAD_TAIL_FLAGS",
            "cat": "Text Processing",
            "name": "Head/Tail with Numeric Lines (-n 2)",
            "cmd": "echo -e 'line1\\nline2\\nline3\\nline4' | tail -n 2"
        },
        {
            "id": "B6_WC_COUNTS",
            "cat": "Text Processing",
            "name": "Word Count Flags (wc -l, wc -w)",
            "cmd": "echo -e 'one two\\nthree four five' | wc -w"
        },
        {
            "id": "B7_TAR_GZIP",
            "cat": "Text Processing",
            "name": "Archive Creation (tar -czf and tar -xzf)",
            "cmd": "mkdir -p /tmp/arch && echo 'hello' > /tmp/arch/f.txt && tar -czf /tmp/test.tar.gz -C /tmp arch && tar -tzf /tmp/test.tar.gz"
        },

        # Category C: Daily Sysadmin & Health Checks
        {
            "id": "C1_MEMORY_FREE",
            "cat": "Sysadmin & Health",
            "name": "Memory Telemetry (free -m or free)",
            "cmd": "free"
        },
        {
            "id": "C2_DISK_DF",
            "cat": "Sysadmin & Health",
            "name": "Disk Free Space (df -h or df)",
            "cmd": "df -h 2>/dev/null || df"
        },
        {
            "id": "C3_PROCESS_PS",
            "cat": "Sysadmin & Health",
            "name": "Process Table (ps -ef or ps aux or ps)",
            "cmd": "ps aux 2>/dev/null || ps -ef 2>/dev/null || ps"
        },
        {
            "id": "C4_UPTIME_LOAD",
            "cat": "Sysadmin & Health",
            "name": "Uptime and System Load",
            "cmd": "uptime"
        },
        {
            "id": "C5_NETWORK_IFCONFIG_IP",
            "cat": "Sysadmin & Health",
            "name": "Network Interface Listing (ip addr or ifconfig)",
            "cmd": "ip addr 2>/dev/null || ip a 2>/dev/null || ifconfig 2>/dev/null"
        },
        {
            "id": "C6_SOCKET_INSPECTION",
            "cat": "Sysadmin & Health",
            "name": "Active Socket Inspection (ss -tulpn or netstat)",
            "cmd": "ss -tulpn 2>/dev/null || netstat -tulpn 2>/dev/null || cat /proc/net/tcp | head -n 3"
        },
        {
            "id": "C7_CURL_FETCH",
            "cat": "Sysadmin & Health",
            "name": "HTTP Fetch Tool (curl or fetch)",
            "cmd": "curl -sI https://www.google.com 2>/dev/null | head -n 2 || fetch -s https://www.google.com | head -n 2"
        },

        # Category D: Developer Tools & Runtime Ecosystem
        {
            "id": "D1_PYTHON_RUNTIME",
            "cat": "Developer Runtime",
            "name": "Python 3 Runtime & Version",
            "cmd": "python3 --version"
        },
        {
            "id": "D2_SQLITE_DATABASE",
            "cat": "Developer Runtime",
            "name": "SQLite 3 Database CLI & In-Memory Table",
            "cmd": "sqlite3 :memory: 'CREATE TABLE t(x); INSERT INTO t VALUES(\"DB_OK\"); SELECT * FROM t;'"
        },
        {
            "id": "D3_C_COMPILER",
            "cat": "Developer Runtime",
            "name": "C Compiler (gcc, clang, or tcc)",
            "cmd": "gcc --version 2>/dev/null || clang --version 2>/dev/null || tcc -v 2>/dev/null || echo 'NO_C_COMPILER'"
        },
        {
            "id": "D4_MAKE_BUILD_TOOL",
            "cat": "Developer Runtime",
            "name": "Make Build Automation Tool",
            "cmd": "make --version 2>/dev/null || echo 'NO_MAKE'"
        },
        {
            "id": "D5_GIT_VCS",
            "cat": "Developer Runtime",
            "name": "Git Version Control CLI",
            "cmd": "git --version 2>/dev/null || echo 'NO_GIT'"
        }
    ]

    results = {}
    for os_name, img_tag in images.items():
        print(f"\n[*] Running 25 Daily Operations on {os_name} ({img_tag})...")
        os_results = []
        for tc in test_cases:
            rc, stdout, stderr, ms = run_in_container(img_tag, tc["cmd"])
            passed = (rc == 0) and not ("NO_C_COMPILER" in stdout or "NO_MAKE" in stdout or "NO_GIT" in stdout)
            status = "PASS" if passed else "FAIL"
            
            # Identify specific reason
            err_summary = ""
            if not passed:
                if "not found" in stderr.lower() or "not found" in stdout.lower() or "NO_" in stdout:
                    err_summary = "Missing Utility"
                elif "unknown" in stderr.lower() or "syntax" in stderr.lower():
                    err_summary = "Syntax/Flag Unsupported"
                else:
                    err_summary = stderr[:60] if stderr else f"Exit {rc}"

            os_results.append({
                "id": tc["id"],
                "category": tc["cat"],
                "name": tc["name"],
                "command": tc["cmd"],
                "status": status,
                "rc": rc,
                "stdout_sample": stdout[:120].replace("\n", " "),
                "stderr_sample": stderr[:120].replace("\n", " "),
                "latency_ms": round(ms, 1),
                "error_reason": err_summary
            })
            print(f"   [{status:<4}] {tc['name']:<42} ({ms:.1f}ms) {err_summary}")
        results[os_name] = os_results

    # Summary table
    print("\n" + "=" * 84)
    print("📊 25-OPERATION COMPARATIVE MATRIX: FERRO-OS VS UBUNTU VS ALPINE")
    print("=" * 84)
    print(f"{'Category':<16} | {'Test Operation':<36} | {'FerroOS':<10} | {'Ubuntu':<10} | {'Alpine':<10}")
    print("-" * 84)

    for i, tc in enumerate(test_cases):
        f_st = results["FerroOS"][i]["status"]
        u_st = results["Ubuntu"][i]["status"]
        a_st = results["Alpine"][i]["status"]
        f_sym = "✅ PASS" if f_st == "PASS" else "❌ FAIL"
        u_sym = "✅ PASS" if u_st == "PASS" else "❌ FAIL"
        a_sym = "✅ PASS" if a_st == "PASS" else "❌ FAIL"
        print(f"{tc['cat']:<16} | {tc['name']:<36} | {f_sym:<10} | {u_sym:<10} | {a_sym:<10}")

    # Totals
    f_total = sum(1 for r in results["FerroOS"] if r["status"] == "PASS")
    u_total = sum(1 for r in results["Ubuntu"] if r["status"] == "PASS")
    a_total = sum(1 for r in results["Alpine"] if r["status"] == "PASS")

    print("-" * 84)
    print(f"{'OVERALL SCORE':<16} | {'Total Passed Out of 25 Operations':<36} | {f_total}/25 ({f_total*4}%) | {u_total}/25 ({u_total*4}%) | {a_total}/25 ({a_total*4}%)")
    print("=" * 84)

    # Output detailed report to JSON
    report_path = "tools/reports/cloud_operations_underdeveloped_parts_report.json"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[✓] Saved detailed comparative audit to {report_path}")

if __name__ == "__main__":
    main()
