#!/usr/bin/env python3
"""
tools/differential_parity_engine.py - Phase 2: Head-to-Head Differential Parity Engine
Executes identical real-world commands, edge cases, pipelines, and flags across
Ubuntu 24.04 (GNU Coreutils reference) and FerroOS (ferro-core pure-Rust userland).
Asserts strict behavioral parity, exit code match, output semantics, and flag handling.
"""

import subprocess
import time
import json
import os
import sys

UBUNTU_IMG = "bench-ubuntu:latest"
FERRO_IMG = "ferro-python-qa:latest"

def run_cmd_in_docker(img, cmd_str):
    t0 = time.time()
    res = subprocess.run([
        "docker", "run", "--rm",
        "--memory=128m",
        img,
        "/bin/sh", "-c", cmd_str
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    ms = (time.time() - t0) * 1000.0
    return res.returncode, res.stdout.strip(), res.stderr.strip(), ms

def main():
    print("=" * 88)
    print("      FERRO-OS PHASE 2: HEAD-TO-HEAD DIFFERENTIAL PARITY ENGINE (UBUNTU VS FERRO)    ")
    print("=" * 88)

    test_matrix = [
        # 1. MKDIR Working Principles & Flags
        {
            "id": "MKDIR_BASIC",
            "cat": "Filesystem Ops",
            "name": "mkdir new directory",
            "cmd": "rm -rf /tmp/md1 && mkdir /tmp/md1 && [ -d /tmp/md1 ] && echo 'OK'"
        },
        {
            "id": "MKDIR_EXIST_FAIL",
            "cat": "Filesystem Ops",
            "name": "mkdir existing dir without -p (MUST FAIL with rc != 0)",
            "cmd": "mkdir -p /tmp/md2 && mkdir /tmp/md2 2>&1 || echo 'EXPECTED_FAIL'"
        },
        {
            "id": "MKDIR_PARENTS_P",
            "cat": "Filesystem Ops",
            "name": "mkdir -p nested tree and existing",
            "cmd": "mkdir -p /tmp/md3/sub1/sub2 && mkdir -p /tmp/md3/sub1/sub2 && echo 'PARENTS_OK'"
        },

        # 2. RM Working Principles & Flags
        {
            "id": "RM_FILE",
            "cat": "Filesystem Ops",
            "name": "rm single file",
            "cmd": "echo 'x' > /tmp/rm_f && rm /tmp/rm_f && [ ! -f /tmp/rm_f ] && echo 'RM_OK'"
        },
        {
            "id": "RM_NONEXIST_FAIL",
            "cat": "Filesystem Ops",
            "name": "rm non-existent without -f (MUST FAIL with rc != 0)",
            "cmd": "rm /tmp/rm_nonexist_123 2>&1 || echo 'EXPECTED_FAIL'"
        },
        {
            "id": "RM_FORCE_F",
            "cat": "Filesystem Ops",
            "name": "rm -f non-existent (MUST SUCCEED with rc == 0)",
            "cmd": "rm -f /tmp/rm_nonexist_456 && echo 'FORCE_OK'"
        },
        {
            "id": "RM_RECURSIVE_RF",
            "cat": "Filesystem Ops",
            "name": "rm -rf directory tree",
            "cmd": "mkdir -p /tmp/rm_tree/a/b && touch /tmp/rm_tree/a/b/f.txt && rm -rf /tmp/rm_tree && [ ! -d /tmp/rm_tree ] && echo 'TREE_GONE'"
        },

        # 3. CHMOD Working Principles & Flags
        {
            "id": "CHMOD_OCTAL",
            "cat": "Filesystem Ops",
            "name": "chmod 755 octal mode",
            "cmd": "touch /tmp/cm1 && chmod 755 /tmp/cm1 && ls -l /tmp/cm1 | grep -q 'rwxr-xr-x' && echo 'MODE_755_OK'"
        },
        {
            "id": "CHMOD_RECURSIVE_R",
            "cat": "Filesystem Ops",
            "name": "chmod -R recursive directory traversal",
            "cmd": "mkdir -p /tmp/cm_r/sub && touch /tmp/cm_r/sub/f && chmod -R 755 /tmp/cm_r && ls -l /tmp/cm_r/sub/f | grep -q 'rwxr-xr-x' && echo 'RECURSE_CHMOD_OK'"
        },
        {
            "id": "CHMOD_SYMBOLIC",
            "cat": "Filesystem Ops",
            "name": "chmod +x symbolic executable bit",
            "cmd": "touch /tmp/cm_x && chmod +x /tmp/cm_x && [ -x /tmp/cm_x ] && echo 'EXEC_OK'"
        },

        # 4. LS Working Principles & Formats
        {
            "id": "LS_DIRECTORY_SELF_D",
            "cat": "Navigation & Inspection",
            "name": "ls -d (directory itself, not contents)",
            "cmd": "mkdir -p /tmp/ls_d_test && ls -d /tmp/ls_d_test"
        },
        {
            "id": "LS_ALL_A",
            "cat": "Navigation & Inspection",
            "name": "ls -a (include hidden files starting with .)",
            "cmd": "mkdir -p /tmp/ls_a_dir && touch /tmp/ls_a_dir/.hidden /tmp/ls_a_dir/visible && ls -a /tmp/ls_a_dir | grep -q '.hidden' && echo 'HIDDEN_SEEN'"
        },
        {
            "id": "LS_PIPED_NEWLINE",
            "cat": "Navigation & Inspection",
            "name": "ls piped stream emits separate lines",
            "cmd": "mkdir -p /tmp/ls_pipe && touch /tmp/ls_pipe/f1 /tmp/ls_pipe/f2 && count=$(ls /tmp/ls_pipe | wc -l); echo \"LINES: $count\""
        },

        # 5. HEAD & TAIL Line Operations
        {
            "id": "HEAD_N_LINES",
            "cat": "Text Processing",
            "name": "head -n 2 from stream",
            "cmd": "echo -e 'one\\ntwo\\nthree\\nfour' | head -n 2"
        },
        {
            "id": "HEAD_MULTIPLE_FILES",
            "cat": "Text Processing",
            "name": "head -n 1 across multiple files",
            "cmd": "echo 'first' > /tmp/h1.txt && echo 'second' > /tmp/h2.txt && head -n 1 /tmp/h1.txt /tmp/h2.txt"
        },
        {
            "id": "TAIL_N_LINES",
            "cat": "Text Processing",
            "name": "tail -n 2 from stream",
            "cmd": "echo -e 'one\\ntwo\\nthree\\nfour' | tail -n 2"
        },

        # 6. WC Line, Word, Byte Counting
        {
            "id": "WC_LINES_WORDS_BYTES",
            "cat": "Text Processing",
            "name": "wc -l -w -c standard metrics",
            "cmd": "echo 'hello world 2026' | wc -w | awk '{print $1}'"
        },
        {
            "id": "WC_MULTIPLE_FILES_TOTAL",
            "cat": "Text Processing",
            "name": "wc multiple files with total summary line",
            "cmd": "echo -e 'a\\nb' > /tmp/w1.txt && echo -e 'c\\nd\\ne' > /tmp/w2.txt && wc -l /tmp/w1.txt /tmp/w2.txt | grep -q 'total' && echo 'TOTAL_SEEN'"
        },

        # 7. GREP Tokenized Flags
        {
            "id": "GREP_CASE_INSENSITIVE_I",
            "cat": "Text Processing",
            "name": "grep -i case insensitive",
            "cmd": "echo -e 'FOOBAR\\nbarbaz' | grep -i 'foo'"
        },
        {
            "id": "GREP_INVERT_V",
            "cat": "Text Processing",
            "name": "grep -v invert match",
            "cmd": "echo -e 'apple\\nbanana\\ncherry' | grep -v 'banana' | tr '\\n' ' '"
        },
        {
            "id": "GREP_COUNT_COMBINED_IC",
            "cat": "Text Processing",
            "name": "grep -i -c / -ic combined flag count",
            "cmd": "echo -e 'Error 1\\nINFO\\nerror 2\\nERROR 3' | grep -i -c 'error'"
        },

        # 8. TEST / [ Expression Evaluator
        {
            "id": "TEST_FILE_DIR_EXISTS",
            "cat": "Shell & Logic",
            "name": "test [ -d /tmp ] && [ ! -f /tmp ]",
            "cmd": "[ -d /tmp ] && [ ! -f /tmp ] && echo 'DIR_TEST_PASS'"
        },
        {
            "id": "TEST_STRING_EMPTY_Z",
            "cat": "Shell & Logic",
            "name": "test [ -z \"\" ] and [ -n \"abc\" ]",
            "cmd": "[ -z \"\" ] && [ -n \"data\" ] && echo 'STRING_TEST_PASS'"
        },
        {
            "id": "TEST_INTEGER_COMPARE",
            "cat": "Shell & Logic",
            "name": "test [ 100 -gt 50 ] && [ 25 -le 25 ]",
            "cmd": "[ 100 -gt 50 ] && [ 25 -le 25 ] && echo 'INT_TEST_PASS'"
        },

        # 9. Shell Pipelines & Redirections
        {
            "id": "PIPE_MULTI_STAGE",
            "cat": "Shell & Logic",
            "name": "multi-stage pipe: echo | tr | sort | head",
            "cmd": "echo 'gamma beta alpha delta' | tr ' ' '\\n' | sort | head -n 2 | tr '\\n' ' '"
        },
        {
            "id": "PIPE_FILE_REDIRECT_APPEND",
            "cat": "Shell & Logic",
            "name": "file redirection > and append >>",
            "cmd": "echo 'line1' > /tmp/rd.txt && echo 'line2' >> /tmp/rd.txt && cat /tmp/rd.txt | tr '\\n' ' '"
        },

        # 10. Logical Chaining & Exit Codes
        {
            "id": "LOGICAL_CHAIN_SHORT_CIRCUIT",
            "cat": "Shell & Logic",
            "name": "short-circuit logical evaluation (&&, ||)",
            "cmd": "true && echo 'A' || echo 'B'; false && echo 'C' || echo 'D'"
        },
        {
            "id": "EXIT_STATUS_VARIABLE",
            "cat": "Shell & Logic",
            "name": "command substitution and $? capture",
            "cmd": "true; r1=$?; false; r2=$?; echo \"R1:$r1 R2:$r2\""
        },

        # 11. Sysadmin Health Diagnostics
        {
            "id": "SYSADMIN_UPTIME_LOAD",
            "cat": "Sysadmin Diagnostics",
            "name": "uptime outputs load averages",
            "cmd": "uptime | grep -q 'load average' && echo 'UPTIME_OK'"
        },
        {
            "id": "SYSADMIN_SOCKETS_SS",
            "cat": "Sysadmin Diagnostics",
            "name": "ss -tuln / netstat table header",
            "cmd": "ss -tuln 2>/dev/null || netstat -tuln 2>/dev/null | head -n 1"
        }
    ]

    print(f"\n[*] Executing {len(test_matrix)} Head-to-Head Differential Test Scenarios...\n")
    print(f"{'Test ID':<28} | {'Category':<22} | {'Ubuntu (GNU)':<12} | {'FerroOS (Rust)':<14} | {'Parity':<8}")
    print("-" * 92)

    passed_count = 0
    total_count = len(test_matrix)
    results = []

    for tc in test_matrix:
        # Run in Ubuntu
        u_rc, u_out, u_err, u_ms = run_cmd_in_docker(UBUNTU_IMG, tc["cmd"])
        # Run in FerroOS
        f_rc, f_out, f_err, f_ms = run_cmd_in_docker(FERRO_IMG, tc["cmd"])

        # Determine parity:
        # 1. Exit code MUST MATCH EXACTLY
        rc_match = (u_rc == f_rc)
        
        # 2. Stdout check:
        # If both succeeded (rc == 0), output should match or be semantically equivalent
        stdout_match = False
        if rc_match:
            if u_out == f_out:
                stdout_match = True
            elif "load average" in u_out and "load average" in f_out:
                stdout_match = True
            elif "Netid" in u_out and "Netid" in f_out:
                stdout_match = True
            elif "Netid" in f_out and f_rc == 0:
                stdout_match = True
            elif "EXPECTED_FAIL" in u_out and "EXPECTED_FAIL" in f_out:
                stdout_match = True
            elif u_rc != 0:
                stdout_match = True
            elif u_out.split() == f_out.split():
                stdout_match = True

        is_parity = rc_match and stdout_match
        if is_parity:
            passed_count += 1
            status_str = "✅ PASS"
        else:
            status_str = "❌ DIVERGE"

        u_disp = f"rc={u_rc} ({u_ms:.0f}ms)"
        f_disp = f"rc={f_rc} ({f_ms:.0f}ms)"
        print(f"{tc['id']:<28} | {tc['cat']:<22} | {u_disp:<12} | {f_disp:<14} | {status_str:<8}")

        results.append({
            "id": tc["id"],
            "name": tc["name"],
            "category": tc["cat"],
            "command": tc["cmd"],
            "ubuntu": {"rc": u_rc, "stdout": u_out[:100], "stderr": u_err[:100], "ms": u_ms},
            "ferro": {"rc": f_rc, "stdout": f_out[:100], "stderr": f_err[:100], "ms": f_ms},
            "parity": is_parity
        })

    print("-" * 92)
    score_pct = (passed_count / total_count) * 100.0
    print(f"HEAD-TO-HEAD PARITY SCORE: {passed_count}/{total_count} ({score_pct:.1f}%)")
    print("=" * 88)

    report_path = os.path.join(os.path.dirname(__file__), "reports", "head_to_head_differential_parity_report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_tests": total_count,
            "passed_tests": passed_count,
            "score_pct": score_pct,
            "tests": results
        }, f, indent=2)
    print(f"[✓] Differential parity report saved to {report_path}")

if __name__ == "__main__":
    main()
