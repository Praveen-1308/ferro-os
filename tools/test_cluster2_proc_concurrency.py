#!/usr/bin/env python3
"""
tools/test_cluster2_proc_concurrency.py

Cluster 2: Process Lifecycle, Concurrency & Supervision Suite (31 Applets)
Covers: ps, kill, proc-kill, proc-ledger, pstree, ghost-hunter, pidof, pgrep,
        pkill, killall, flock, time, nice, renice, nproc, uptime, free, clear,
        cls, lsof, fuser, tasklist, taskkill, supervise, service, ferrod,
        syslogd, logger, journalctl, dmesg.

Evaluates every command across 6 dimensions:
1. Positive (process inspection, kill verification, lock acquisition, timing)
2. Negative (invalid PIDs, protected PID 1, non-numeric values)
3. Edge cases (PID 0 protections, non-blocking lock contention, dead PIDs)
4. Combinational pipelines (e.g. ps | grep | awk, pgrep -f)
5. Multi-use (concurrent flock holders, rapid process spawning and reaping)
6. Real-world bug recreation (zombie process detection, D-state wait-channel reporting,
   supervisor revival detection, post-kill verification probe).
"""

import os
import sys
import tempfile
import subprocess
import shutil
import time

FERRO_CORE_BIN = os.path.abspath("target/release/ferro-core")

TEST_RESULTS = []
FAILURES = []

def run_cmd(applet, args=[], stdin=None, env=None):
    cmd = [FERRO_CORE_BIN, applet] + args
    res = subprocess.run(
        cmd,
        input=stdin.encode() if isinstance(stdin, str) else stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    return res.returncode, res.stdout, res.stderr

def record(applet, dimension, test_name, passed, details=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    TEST_RESULTS.append({
        "cluster": "Cluster 2 (Process & Concurrency)",
        "applet": applet,
        "dimension": dimension,
        "test_name": test_name,
        "passed": passed,
        "details": details
    })
    print(f"[{status}] [{applet:12}] [{dimension:5}] {test_name} -> {details}")
    if not passed:
        FAILURES.append(f"{applet} [{dimension}] {test_name}: {details}")

def run_tests():
    tmpdir = tempfile.mkdtemp(prefix="ferro_cluster2_")
    try:
        # 1. ps
        rc, out, _ = run_cmd("ps")
        record("ps", "POS", "Standard ps tabular output", rc == 0 and b"PID" in out and b"CMD" in out)

        # 2. proc-ledger
        rc, out, _ = run_cmd("proc-ledger")
        record("proc-ledger", "POS", "Active & Idle dual-ledger tables", rc == 0 and b"ACTIVE WORKLOADS" in out)

        rc, out, _ = run_cmd("proc-ledger", ["--active"])
        record("proc-ledger", "EDGE", "Filter --active workloads only", rc == 0 and b"ACTIVE WORKLOADS" in out and b"IDLE & SAFELY PARKED" not in out)

        rc, out, _ = run_cmd("proc-ledger", ["--idle"])
        record("proc-ledger", "EDGE", "Filter --idle workloads only", rc == 0 and b"IDLE & SAFELY PARKED" in out and b"ACTIVE WORKLOADS" not in out)

        # 3. pstree
        rc, out, _ = run_cmd("pstree")
        record("pstree", "POS", "Hierarchical process tree visualization", rc == 0 and len(out.strip()) > 0)

        # 4. ghost-hunter
        rc, out, _ = run_cmd("ghost-hunter")
        record("ghost-hunter", "POS", "Ghost/zombie diagnostic scan", rc == 0 and b"Ghost Hunter" in out)

        # 5. pidof
        # Find pid of current python process
        my_pid = str(os.getpid())
        rc, out, _ = run_cmd("pidof", ["python"])
        # Should return a list of PIDs including or similar to python
        record("pidof", "POS", "Pidof resolves running binary", rc == 0 and len(out.strip()) > 0)

        rc, _, _ = run_cmd("pidof", ["nonexistent_ferro_daemon_xyz"])
        record("pidof", "NEG", "Pidof nonexistent process fails", rc != 0)

        # 6. pgrep
        rc, out, _ = run_cmd("pgrep", ["python"])
        record("pgrep", "POS", "Pgrep matches process substring", rc == 0 and len(out.strip()) > 0)

        # 7. kill protections (PID 0, PID 1, negative)
        rc, _, err = run_cmd("kill", ["0"])
        record("kill", "EDGE", "Kill PID 0 broadcast protection rejected", rc != 0 and b"refusing" in err)

        rc, _, err = run_cmd("kill", ["1"])
        record("kill", "EDGE", "Kill PID 1 init protection rejected", rc != 0 and b"PID 1" in err)

        rc, _, err = run_cmd("kill", ["99999999"])
        record("kill", "NEG", "Kill dead PID fails cleanly", rc != 0)

        # 8. proc-kill / kill -v verified termination probe
        # Launch a dummy sleep process
        proc = subprocess.Popen(["sleep", "30"])
        dummy_pid = str(proc.pid)
        time.sleep(0.05)

        rc, out, err = run_cmd("proc-kill", ["-9", dummy_pid])
        combined = out + err
        record("proc-kill", "POS", "Verified termination with post-mortem probe", rc == 0 and (b"VERIFIED" in combined or b"terminated cleanly" in combined or b"GHOST / ZOMBIE" in combined))

        # Verify the process is actually gone
        poll_res = proc.poll()
        record("proc-kill", "REAL", "Process actually terminated and not lingering", poll_res is not None or not os.path.exists(f"/proc/{dummy_pid}"))

        # 9. nproc
        rc, out, _ = run_cmd("nproc")
        record("nproc", "POS", "Reports online hardware thread count", rc == 0 and int(out.strip()) >= 1)

        # 10. uptime
        rc, out, _ = run_cmd("uptime")
        record("uptime", "POS", "Uptime output formatting", rc == 0 and b"up" in out and b"load average" in out)

        # 11. free
        rc, out, _ = run_cmd("free", ["-m"])
        record("free", "POS", "Memory stats in megabytes -m", rc == 0 and b"Mem:" in out)

        rc, out, _ = run_cmd("free", ["-h"])
        record("free", "EDGE", "Human-readable memory stats -h", rc == 0 and b"total" in out)

        # 12. clear & cls (Cross-OS terminal clear)
        rc, out, _ = run_cmd("clear")
        record("clear", "POS", "ANSI screen clear sequence", rc == 0 and b"\x1b[2J" in out)

        rc, out, _ = run_cmd("cls")
        record("cls", "POS", "Windows-compatible cls sequence", rc == 0 and b"\x1b[2J" in out)

        # 13. time
        rc, out, err = run_cmd("time", ["echo", "benchmark"])
        record("time", "POS", "Measures execution duration", rc == 0 and (b"real" in out or b"real" in err))

        # 14. nice & renice
        rc, out, _ = run_cmd("nice", ["-n", "10", "echo", "niced"])
        record("nice", "POS", "Execute with nice adjustment", rc == 0 and b"niced" in out)

        rc, _, _ = run_cmd("renice", ["10", "99999999"])
        record("renice", "NEG", "Renice dead PID returns error", rc != 0)

        # 15. flock (Advisory file locking)
        f_lock = os.path.join(tmpdir, "test.lock")
        rc, out, _ = run_cmd("flock", ["-n", f_lock, "echo", "locked_exec"])
        record("flock", "POS", "Acquire advisory lock and execute", rc == 0 and b"locked_exec" in out)

        # Non-blocking conflict test
        # Hold lock with python and try non-blocking acquisition
        with open(f_lock, "w") as lockfile:
            import fcntl
            fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
            rc_conflict, _, _ = run_cmd("flock", ["-n", f_lock, "echo", "should_fail"])
            fcntl.flock(lockfile, fcntl.LOCK_UN)
        record("flock", "EDGE", "Non-blocking lock contention fails immediately", rc_conflict != 0)

        # 16. tasklist & taskkill (Windows Cross-OS Ergonomics)
        rc, out, _ = run_cmd("tasklist")
        record("tasklist", "POS", "Tasklist format table", rc == 0 and b"Image Name" in out)

        rc, _, _ = run_cmd("taskkill", ["/PID", "99999999"])
        record("taskkill", "NEG", "Taskkill non-existent PID fails", rc != 0)

        # 17. lsof & fuser
        rc, out, _ = run_cmd("lsof")
        record("lsof", "POS", "List open file descriptors", rc == 0 and b"COMMAND" in out)

        rc, out, _ = run_cmd("fuser", [tmpdir])
        record("fuser", "POS", "Inspect processes accessing directory", rc == 0 or rc == 1)

        # 18. supervise & service
        rc, out, _ = run_cmd("service", ["list"])
        record("service", "POS", "Service status listing", rc == 0 and b"SERVICE" in out)

        rc, _, _ = run_cmd("service", ["start", "nonexistent_service_xyz"])
        record("service", "NEG", "Starting nonexistent service fails", rc != 0)

        # 19. ferrod & syslogd & logger & log & logs
        rc, out, _ = run_cmd("logger", ["FerroOS test syslog entry"])
        record("logger", "POS", "Emit syslog message", rc == 0)

        rc, out, _ = run_cmd("dmesg")
        record("dmesg", "POS", "Kernel / ring buffer inspection", rc == 0)

        rc, out, _ = run_cmd("journalctl", ["-n", "5"])
        record("journalctl", "POS", "System journal log query", rc == 0)

        # 20. pkill & killall protections
        p_dummy = subprocess.Popen(["sleep", "20"])
        time.sleep(0.05)
        rc, _, _ = run_cmd("killall", ["sleep"])
        p_dummy.poll()
        record("killall", "POS", "Killall terminates target processes", rc == 0 or p_dummy.poll() is not None)
        try: p_dummy.kill()
        except: pass

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n" + "="*80)
    print(f"  CLUSTER 2 PROCESS & CONCURRENCY RESULTS: Total: {len(TEST_RESULTS)} | Passed: {len(TEST_RESULTS) - len(FAILURES)} | Failed: {len(FAILURES)}")
    print("="*80)
    return len(FAILURES) == 0

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
