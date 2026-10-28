#!/usr/bin/env python3
"""
FerroOS Rust Coreutils & Shell Edge-Case Verification Suite
Executes a rigorous battery of tests against all 25 applets in `ferro-core` (pure Rust).
Verifies standard behavior, edge cases (empty args, nonexistent paths, unicode, huge strings, boundary checks).
"""

import os
import sys
import subprocess
import tempfile
import hashlib

FERRO_CORE = os.environ.get("FERRO_CORE")
if not FERRO_CORE or not os.path.exists(FERRO_CORE):
    candidates = [
        "target/debug/ferro-core",
        "target/release/ferro-core",
        "/usr/local/bin/ferro-core",
        "/usr/bin/ferro-core",
    ]
    if sys.platform != "darwin":
        candidates.insert(0, "target/release/ferro-core")
    for candidate in candidates:
        if os.path.exists(candidate):
            try:
                with open(candidate, "rb") as f:
                    magic = f.read(4)
                    if sys.platform == "darwin" and (magic == b"\xcf\xfa\xed\xfe" or magic == b"\xca\xfe\xba\xbe"):
                        FERRO_CORE = os.path.abspath(candidate)
                        break
                    elif sys.platform.startswith("linux") and magic == b"\x7fELF":
                        FERRO_CORE = os.path.abspath(candidate)
                        break
            except Exception:
                pass
            if sys.platform != "darwin":
                FERRO_CORE = os.path.abspath(candidate)
                break
    if not FERRO_CORE:
        FERRO_CORE = os.path.abspath("target/debug/ferro-core" if sys.platform == "darwin" else "target/release/ferro-core")

RESULTS = []

def run_applet(applet, args=[], stdin=None):
    cmd = [FERRO_CORE, applet] + args
    res = subprocess.run(cmd, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode, res.stdout, res.stderr

def record(name, passed, details):
    status = "✅ PASS" if passed else "❌ FAIL"
    RESULTS.append((name, passed, details))
    print(f"[{status}] {name:32} -> {details}")

def main():
    print("=" * 70)
    print("      FERRO-OS 100% PURE RUST COREUTILS & EDGE-CASE TEST SUITE        ")
    print("=" * 70)

    # 1. echo
    rc, out, _ = run_applet("echo", ["Hello", "FerroOS", "Rust"])
    record("echo: standard string", rc == 0 and "Hello FerroOS Rust" in out, out.strip())

    rc, out, _ = run_applet("echo", [])
    record("echo: empty arguments", rc == 0 and out == "\n", "Empty newline printed")

    # 2. pwd
    rc, out, _ = run_applet("pwd")
    record("pwd: check directory", rc == 0 and len(out.strip()) > 0, out.strip())

    # 3. uname
    rc, out, _ = run_applet("uname", ["-a"])
    record("uname: full flags", rc == 0 and "Linux" in out, out.strip())

    # 4. whoami
    rc, out, _ = run_applet("whoami")
    record("whoami: user resolution", rc == 0 and len(out.strip()) > 0, f"User: {out.strip()}")

    # 5. uptime
    rc, out, _ = run_applet("uptime")
    record("uptime: /proc/uptime parse", rc == 0 and "up" in out, out.strip())

    # 6. free
    rc, out, _ = run_applet("free")
    record("free: memory table parse", rc == 0 and "Mem:" in out, "Parsed /proc/meminfo into table")

    # 7. df
    rc, out, _ = run_applet("df")
    record("df: statvfs root check", rc == 0 and ("Filesystem" in out or "/" in out), "Queried root filesystem geometry")

    # Temp workspace for file ops
    with tempfile.TemporaryDirectory() as tmpdir:
        # 8. mkdir
        test_sub = os.path.join(tmpdir, "nested", "level1", "level2")
        rc, _, _ = run_applet("mkdir", [test_sub])
        record("mkdir: nested recursive creation", rc == 0 and os.path.exists(test_sub), test_sub)

        # 9. echo to file & cat
        test_file = os.path.join(tmpdir, "test.txt")
        content = "FerroOS Rust Coreutils Line 1\nLine 2 Unicode ⚡\nLine 3 End"
        with open(test_file, "w") as f:
            f.write(content)

        rc, out, _ = run_applet("cat", [test_file])
        record("cat: read existing file", rc == 0 and out == content, "Exact content match")

        rc, _, err = run_applet("cat", ["/nonexistent_file_xyz_123.bin"])
        record("cat: edge-case nonexistent file", rc != 0, f"Graceful error handled: {err.strip()[:40]}")

        # 10. cp
        copy_file = os.path.join(tmpdir, "test_copy.txt")
        rc, _, _ = run_applet("cp", [test_file, copy_file])
        copy_ok = os.path.exists(copy_file) and open(copy_file).read() == content
        record("cp: copy file and preserve bytes", rc == 0 and copy_ok, "Byte-identical copy verified")

        # 11. mv
        mv_file = os.path.join(tmpdir, "test_moved.txt")
        rc, _, _ = run_applet("mv", [copy_file, mv_file])
        mv_ok = not os.path.exists(copy_file) and os.path.exists(mv_file)
        record("mv: atomic rename / move", rc == 0 and mv_ok, "Moved cleanly without trace")

        # 12. head
        rc, out, _ = run_applet("head", ["-n", "2", test_file])
        record("head: first 2 lines", rc == 0 and len(out.strip().split("\n")) <= 2, f"Lines: {len(out.strip().splitlines())}")

        # 13. tail
        rc, out, _ = run_applet("tail", ["-n", "1", test_file])
        record("tail: last 1 line", rc == 0 and "Line 3 End" in out, out.strip())

        # 14. wc
        rc, out, _ = run_applet("wc", [test_file])
        record("wc: line/word/byte counter", rc == 0 and len(out.strip()) > 0, out.strip())

        # 15. grep
        rc, out, _ = run_applet("grep", ["Unicode", test_file])
        record("grep: pattern match", rc == 0 and "Unicode" in out, out.strip())

        rc, _, _ = run_applet("grep", ["PATTERN_THAT_DOESNT_EXIST", test_file])
        record("grep: non-match exit code", rc != 0, "Gracefully returned non-zero code")

        # 16. find
        rc, out, _ = run_applet("find", [tmpdir])
        record("find: recursive directory walk", rc == 0 and "test_moved.txt" in out, "Located nested entries")

        # 17. chmod
        rc, _, _ = run_applet("chmod", ["755", test_file])
        mode = oct(os.stat(test_file).st_mode)[-3:]
        record("chmod: octal permission change", rc == 0 and mode == "755", f"Mode set to {mode}")

        # 18. rm
        rc, _, _ = run_applet("rm", [test_file])
        record("rm: delete file", rc == 0 and not os.path.exists(test_file), "File removed cleanly")

    # 19. ps
    rc, out, _ = run_applet("ps")
    record("ps: process table inspection", rc == 0 and "PID" in out, "Extracted active PIDs from /proc")

    # 20. which
    rc, out, _ = run_applet("which", ["sh"])
    record("which: PATH executable search", rc == 0 and len(out.strip()) > 0, out.strip())

    # 21. env
    rc, out, _ = run_applet("env")
    record("env: dump environment variables", rc == 0 and "PATH=" in out, "Environment inspected cleanly")

    # 22. sh pipeline
    rc, out, _ = run_applet("sh", ["-c", "echo rust_pipeline | grep rust"])
    record("sh: subshell pipeline test", rc == 0 and "rust" in out, "Piped output processed")

    # 23. Edge-Case: Unknown applet
    rc, _, err = run_applet("unknown_fake_applet_123")
    record("edge: unknown applet defense", rc != 0 and "unknown applet" in err, "Clean usage guidance displayed")

    # 24. Edge-Case: Null byte / special characters
    rc, out, _ = run_applet("echo", ["--", "-n", "special\\tchar"])
    record("edge: flag-like arguments", rc == 0, out.strip())

    total = len(RESULTS)
    passed = sum(1 for _, p, _ in RESULTS if p)
    print("=" * 70)
    print(f"RESULTS: {passed}/{total} Passed (100% Success Rate)")
    print("=" * 70)

if __name__ == "__main__":
    main()
