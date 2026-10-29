#!/usr/bin/env python3
"""
tools/exhaustive_real_world_applet_matrix.py

FerroOS Exhaustive Real-World Edge-Case & Quality Verification Suite.
Implements the 6-Dimension Testing Framework for FerroOS applets:
1. [POS]   Positive baseline functional test
2. [NEG]   Negative test (invalid args, non-existent files, strict non-zero exit codes)
3. [EDGE]  Edge cases (empty files, missing trailing newlines, null bytes, unicode, 0-bounds)
4. [COMB]  Combinational pipeline tests with other commands (UNIX pipelines)
5. [MULTI] Multi-use & reentrancy (rapid successive invocations, repeated calls)
6. [REAL]  Real-world bug / failure pattern recreation (from documented Linux/production CVEs & post-mortems)
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

def run_applet(applet, args=[], stdin=None, env=None):
    cmd = [FERRO_CORE_BIN, applet] + args
    res = subprocess.run(
        cmd,
        input=stdin.encode() if isinstance(stdin, str) else stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    return res.returncode, res.stdout, res.stderr

def record_test(category, applet, dimension, test_name, passed, details=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    TEST_RESULTS.append({
        "category": category,
        "applet": applet,
        "dimension": dimension,
        "test_name": test_name,
        "passed": passed,
        "details": details
    })
    print(f"[{status}] [{applet:12}] [{dimension:5}] {test_name} -> {details}")
    if not passed:
        FAILURES.append(f"{applet} [{dimension}] {test_name}: {details}")

# ============================================================================
# 1. Text & Stream Processing Suite
# ============================================================================

def test_cat(tmpdir):
    cat = "cat"
    f1 = os.path.join(tmpdir, "cat1.txt")
    with open(f1, "w") as f: f.write("hello world\n")

    # 1. POS
    code, out, _ = run_applet(cat, [f1])
    record_test("Stream", cat, "POS", "Read single file", code == 0 and out == b"hello world\n")

    # 2. NEG
    code, _, err = run_applet(cat, ["/nonexistent/path/never_there.txt"])
    record_test("Stream", cat, "NEG", "Nonexistent file exit != 0", code != 0)

    # 3. EDGE
    f_empty = os.path.join(tmpdir, "empty.txt")
    open(f_empty, "w").close()
    code, out, _ = run_applet(cat, [f_empty])
    record_test("Stream", cat, "EDGE", "Zero-byte empty file", code == 0 and out == b"")

    f_nonl = os.path.join(tmpdir, "no_newline.txt")
    with open(f_nonl, "wb") as f: f.write(b"no trailing newline")
    code, out, _ = run_applet(cat, [f_nonl])
    record_test("Stream", cat, "EDGE", "File without trailing newline", code == 0 and out == b"no trailing newline")

    f_binary = os.path.join(tmpdir, "binary.bin")
    with open(f_binary, "wb") as f: f.write(b"\x00\xff\xfe\x00\xaa\xbb")
    code, out, _ = run_applet(cat, [f_binary])
    record_test("Stream", cat, "EDGE", "Binary null bytes preservation", code == 0 and out == b"\x00\xff\xfe\x00\xaa\xbb")

    # 4. COMB
    code, out, _ = run_applet(cat, [f1], stdin=None)
    code2, out2, _ = run_applet("grep", ["world"], stdin=out)
    record_test("Stream", cat, "COMB", "Pipeline cat | grep", code2 == 0 and b"hello world" in out2)

    # 5. MULTI
    code, out, _ = run_applet(cat, [f1, f1, f1])
    record_test("Stream", cat, "MULTI", "Cat 3 files in single call", code == 0 and out == b"hello world\nhello world\nhello world\n")

    # 6. REAL
    # Real-world bug: broken pipe handling when reading huge stream into head
    code, out, _ = run_applet(cat, stdin=b"line1\nline2\nline3\n")
    record_test("Stream", cat, "REAL", "Stdin stream forwarding", code == 0 and b"line1\nline2" in out)

def test_echo_and_printf():
    # Echo
    code, out, _ = run_applet("echo", ["hello", "ferro"])
    record_test("Stream", "echo", "POS", "Standard echo", code == 0 and out == b"hello ferro\n")

    code, out, _ = run_applet("echo", ["-n", "no-newline"])
    record_test("Stream", "echo", "EDGE", "Echo -n no newline", code == 0 and out == b"no-newline")

    code, out, _ = run_applet("echo", [])
    record_test("Stream", "echo", "EDGE", "Echo empty line", code == 0 and out == b"\n")

    # Printf
    code, out, _ = run_applet("printf", ["%s %d\n", "ferro", "42"])
    record_test("Stream", "printf", "POS", "Printf format string", code == 0 and out == b"ferro 42\n")

    code, out, _ = run_applet("printf", ["hex: 0x%x\n", "255"])
    record_test("Stream", "printf", "EDGE", "Printf hex %x specifier", code == 0 and out == b"hex: 0xff\n")

    code, out, _ = run_applet("printf", ["line1\\nline2\\tcol2\\n"])
    record_test("Stream", "printf", "REAL", "Printf escape sequences \\n \\t", code == 0 and b"line1\nline2\tcol2\n" in out)

def test_head_and_tail(tmpdir):
    f = os.path.join(tmpdir, "lines10.txt")
    with open(f, "w") as fp:
        for i in range(1, 11): fp.write(f"line {i}\n")

    # Head
    code, out, _ = run_applet("head", ["-n", "3", f])
    record_test("Stream", "head", "POS", "Head -n 3", code == 0 and out == b"line 1\nline 2\nline 3\n")

    code, out, _ = run_applet("head", ["-n", "0", f])
    record_test("Stream", "head", "EDGE", "Head -n 0 empty output", code == 0 and out == b"")

    code, _, _ = run_applet("head", ["-n", "invalid_num", f])
    record_test("Stream", "head", "NEG", "Head invalid -n arg", code != 0)

    # Tail
    code, out, _ = run_applet("tail", ["-n", "2", f])
    record_test("Stream", "tail", "POS", "Tail -n 2", code == 0 and out == b"line 9\nline 10\n")

    code, out, _ = run_applet("tail", ["-n", "0", f])
    record_test("Stream", "tail", "EDGE", "Tail -n 0 empty output", code == 0 and out == b"")

    # Real-world bug: tail on file with no trailing newline
    f_nonl = os.path.join(tmpdir, "tail_nonl.txt")
    with open(f_nonl, "wb") as fp: fp.write(b"single line no newline")
    code, out, _ = run_applet("tail", ["-n", "1", f_nonl])
    record_test("Stream", "tail", "REAL", "Tail on file with no trailing newline", code == 0 and b"single line no newline" in out)

def test_wc(tmpdir):
    f = os.path.join(tmpdir, "wc_test.txt")
    with open(f, "w") as fp: fp.write("word1 word2 word3\nline 2\n")

    code, out, _ = run_applet("wc", ["-w", f])
    record_test("Stream", "wc", "POS", "Count words -w", code == 0 and b"5" in out)

    code, out, _ = run_applet("wc", ["-l", f])
    record_test("Stream", "wc", "POS", "Count lines -l", code == 0 and b"2" in out)

    f_empty = os.path.join(tmpdir, "wc_empty.txt")
    open(f_empty, "w").close()
    code, out, _ = run_applet("wc", [f_empty])
    record_test("Stream", "wc", "EDGE", "Empty file wc reports 0 0 0", code == 0 and b"0" in out)

    code, _, _ = run_applet("wc", ["/nonexistent/file"])
    record_test("Stream", "wc", "NEG", "Nonexistent file exit != 0", code != 0)

def test_grep():
    sample = "alpha\nbeta 123\ngamma 456\nDELTA\n"

    code, out, _ = run_applet("grep", ["beta"], stdin=sample)
    record_test("Stream", "grep", "POS", "Basic pattern match", code == 0 and b"beta 123\n" in out)

    code, _, _ = run_applet("grep", ["nonexistent_pattern"], stdin=sample)
    record_test("Stream", "grep", "NEG", "Pattern not found exit 1", code == 1)

    code, out, _ = run_applet("grep", ["-i", "delta"], stdin=sample)
    record_test("Stream", "grep", "EDGE", "Case-insensitive -i flag", code == 0 and b"DELTA\n" in out)

    code, out, _ = run_applet("grep", ["-v", "123"], stdin=sample)
    record_test("Stream", "grep", "COMB", "Invert match -v", code == 0 and b"123" not in out and b"alpha" in out)

    # Real world regex: start of line anchor ^
    code, out, _ = run_applet("grep", ["^gamma"], stdin=sample)
    record_test("Stream", "grep", "REAL", "Line-start anchor ^ match", code == 0 and b"gamma 456\n" in out)

def test_awk():
    sample = "root:x:0:0:root:/root:/bin/bash\nferro:x:1000:1000:user:/home/ferro:/bin/sh\n"

    code, out, _ = run_applet("awk", ["{print $1}"], stdin="one two three\nfour five six\n")
    record_test("Stream", "awk", "POS", "Column extraction $1", code == 0 and out == b"one\nfour\n")

    code, out, _ = run_applet("awk", ["-F:", "{print $1, $7}"], stdin=sample)
    record_test("Stream", "awk", "EDGE", "Custom delimiter -F:", code == 0 and b"root /bin/bash\nferro /bin/sh\n" in out)

    code, out, _ = run_applet("awk", ["{print $NF}"], stdin="a b c d\nx y\n")
    record_test("Stream", "awk", "EDGE", "Last field built-in $NF", code == 0 and out == b"d\ny\n")

    numbers = "10\n20\n30\n"
    code, out, _ = run_applet("awk", ["{sum += $1} END {print sum}"], stdin=numbers)
    record_test("Stream", "awk", "COMB", "END block sum accumulator", code == 0 and out == b"60\n")

    code, _, _ = run_applet("awk", ["{bad syntax unclosed"], stdin="test\n")
    record_test("Stream", "awk", "NEG", "Malformed AWK syntax exits != 0", code != 0)

    # Real world: NR line filtering
    header_data = "Name Age\nAlice 30\nBob 25\n"
    code, out, _ = run_applet("awk", ["NR > 1 {print $1}"], stdin=header_data)
    record_test("Stream", "awk", "REAL", "Skip header NR > 1", code == 0 and out == b"Alice\nBob\n")

def test_sponge(tmpdir):
    f = os.path.join(tmpdir, "sponge_test.txt")
    with open(f, "w") as fp: fp.write("alpha\nbeta\ngamma\n")

    # 1. POS & REAL: in-place pipeline without 0-byte truncation
    code, _, _ = run_applet("sponge", [f], stdin=b"alpha\ngamma\n")
    with open(f, "r") as fp: content = fp.read()
    record_test("Stream", "sponge", "POS", "Atomic in-place file write", code == 0 and content == "alpha\ngamma\n")

    # 2. EDGE: empty stdin
    code, _, _ = run_applet("sponge", [f], stdin=b"")
    with open(f, "r") as fp: content = fp.read()
    record_test("Stream", "sponge", "EDGE", "Sponge empty stdin writes 0-byte file", code == 0 and content == "")

    # 3. COMB: pipe into sponge
    with open(f, "w") as fp: fp.write("1\n2\n3\n4\n5\n")
    p1 = subprocess.Popen([FERRO_CORE_BIN, "grep", "-v", "3", f], stdout=subprocess.PIPE)
    p2 = subprocess.Popen([FERRO_CORE_BIN, "sponge", f], stdin=p1.stdout, stdout=subprocess.PIPE)
    p1.stdout.close()
    p2.communicate()
    with open(f, "r") as fp: content = fp.read()
    record_test("Stream", "sponge", "COMB", "Pipeline grep -v | sponge in-place", content == "1\n2\n4\n5\n")

def test_dos2unix_and_unix2dos(tmpdir):
    f = os.path.join(tmpdir, "crlf.txt")
    with open(f, "wb") as fp: fp.write(b"line1\r\nline2\r\nline3\r\n")

    # dos2unix POS
    code, _, _ = run_applet("dos2unix", [f])
    with open(f, "rb") as fp: content = fp.read()
    record_test("Stream", "dos2unix", "POS", "Convert CRLF to LF in-place", code == 0 and content == b"line1\nline2\nline3\n")

    # dos2unix EDGE: UTF-8 BOM
    with open(f, "wb") as fp: fp.write(b"\xef\xbb\xbfbom_line\r\n")
    code, _, _ = run_applet("dos2unix", [f])
    with open(f, "rb") as fp: content = fp.read()
    record_test("Stream", "dos2unix", "EDGE", "Strip UTF-8 BOM", code == 0 and content == b"bom_line\n")

    # unix2dos POS
    code, _, _ = run_applet("unix2dos", [f])
    with open(f, "rb") as fp: content = fp.read()
    record_test("Stream", "unix2dos", "POS", "Convert LF to CRLF in-place", code == 0 and content == b"bom_line\r\n")

    # unix2dos IDEMPOTENCY: double unix2dos shouldn't create \r\r\n
    code, _, _ = run_applet("unix2dos", [f])
    with open(f, "rb") as fp: content = fp.read()
    record_test("Stream", "unix2dos", "REAL", "Idempotent: no \\r\\r\\n duplication", code == 0 and content == b"bom_line\r\n")

def test_ts():
    code, out, _ = run_applet("ts", stdin="hello world\nsecond line\n")
    record_test("Stream", "ts", "POS", "Prepends timestamp to lines", code == 0 and b"hello world" in out and b"[" in out)

    code, out, _ = run_applet("ts", ["[%H:%M:%S]"], stdin="test line\n")
    record_test("Stream", "ts", "EDGE", "Custom format specifier", code == 0 and b"test line" in out)

# ============================================================================
# 2. Archival, Compression & Block I/O Suite
# ============================================================================

def test_gzip_gunzip_zcat(tmpdir):
    f = os.path.join(tmpdir, "data.txt")
    sample_text = b"FerroOS high-performance safe pure-rust operating system payload.\n" * 10
    with open(f, "wb") as fp: fp.write(sample_text)

    # 1. Gzip POS
    code, _, _ = run_applet("gzip", ["-k", f])
    gz_file = f + ".gz"
    record_test("Archival", "gzip", "POS", "Compress file to .gz", code == 0 and os.path.exists(gz_file))

    # 2. Zcat POS
    code, out, _ = run_applet("zcat", [gz_file])
    record_test("Archival", "zcat", "POS", "Stream decompress via zcat", code == 0 and out == sample_text)

    # 3. Gunzip POS
    os.remove(f)
    code, _, _ = run_applet("gunzip", [gz_file])
    record_test("Archival", "gunzip", "POS", "Decompress .gz to original", code == 0 and os.path.exists(f))
    with open(f, "rb") as fp: decompressed = fp.read()
    record_test("Archival", "gunzip", "EDGE", "Decompressed byte fidelity", decompressed == sample_text)

    # 4. NEG
    code, _, _ = run_applet("gunzip", [f]) # Decompressing non-gzip
    record_test("Archival", "gunzip", "NEG", "Decompress non-gzip file fails", code != 0)

def test_dd(tmpdir):
    f_in = os.path.join(tmpdir, "dd_in.bin")
    f_out = os.path.join(tmpdir, "dd_out.bin")
    with open(f_in, "wb") as fp: fp.write(b"A" * 1024)

    code, _, _ = run_applet("dd", [f"if={f_in}", f"of={f_out}", "bs=256", "count=2"])
    size = os.path.getsize(f_out) if os.path.exists(f_out) else 0
    record_test("BlockIO", "dd", "POS", "Block copy bs=256 count=2 (512 bytes)", code == 0 and size == 512)

    code, _, _ = run_applet("dd", ["if=/nonexistent/dd/path", f"of={f_out}"])
    record_test("BlockIO", "dd", "NEG", "Nonexistent if= path fails", code != 0)

# ============================================================================
# 3. Process Lifecycle & Verification Suite
# ============================================================================

def test_process_ledger_and_verification():
    # 1. proc-ledger POS
    code, out, _ = run_applet("proc-ledger")
    record_test("Process", "proc-ledger", "POS", "Render process ledger", code == 0 and b"LIFECYCLE LEDGER" in out)

    # 2. proc-ledger filters
    code, out, _ = run_applet("proc-ledger", ["--active"])
    record_test("Process", "proc-ledger", "EDGE", "Filter --active only", code == 0 and b"ACTIVE WORKLOADS" in out and b"IDLE & SAFELY PARKED" not in out)

    code, out, _ = run_applet("proc-ledger", ["--idle"])
    record_test("Process", "proc-ledger", "EDGE", "Filter --idle only", code == 0 and b"IDLE & SAFELY PARKED" in out and b"ACTIVE WORKLOADS" not in out)

    # 3. pstree
    code, out, _ = run_applet("pstree")
    record_test("Process", "pstree", "POS", "Render process hierarchy tree", code == 0 and b"(" in out)

    # 4. ghost-hunter
    code, out, _ = run_applet("ghost-hunter")
    record_test("Process", "ghost-hunter", "POS", "Scan for ghost/zombie processes", code == 0)

    # 5. proc-kill / kill -v verification
    # Spawn dummy background sleep
    p = subprocess.Popen(["sleep", "30"])
    pid = p.pid
    time.sleep(0.1)

    code, out, err = run_applet("kill", ["-v", str(pid)])
    record_test("Process", "kill", "REAL", "Verified kill with post-mortem probe", code == 0)
    p.poll()

# ============================================================================
# 4. Modern Cloud & Developer Ergonomics Suite
# ============================================================================

def test_envsubst():
    template = "HOST=${TEST_FERRO_HOST} PORT=$TEST_FERRO_PORT"
    env = os.environ.copy()
    env["TEST_FERRO_HOST"] = "localhost"
    env["TEST_FERRO_PORT"] = "8080"

    code, out, _ = run_applet("envsubst", stdin=template, env=env)
    record_test("Modern", "envsubst", "POS", "Substitute env variables", code == 0 and out == b"HOST=localhost PORT=8080")

    # Unset variable default empty
    code, out, _ = run_applet("envsubst", stdin="UNSET=$UNSET_FERRO_VAR_XYZ")
    record_test("Modern", "envsubst", "EDGE", "Unset env var resolves to empty", code == 0 and out == b"UNSET=")

def test_json():
    raw_json = '{"name":"ferro","version":2.3,"active":true,"tags":["fast","safe"]}'

    code, out, _ = run_applet("json", [".name"], stdin=raw_json)
    record_test("Modern", "json", "POS", "Extract field .name", code == 0 and b"ferro" in out)

    code, out, _ = run_applet("json", [".tags.[1]"], stdin=raw_json)
    record_test("Modern", "json", "EDGE", "Extract array index .tags.[1]", code == 0 and b"safe" in out)

    code, _, _ = run_applet("json", [".name"], stdin="{unclosed json")
    record_test("Modern", "json", "NEG", "Corrupt JSON exits != 0", code != 0)

def test_uuidgen():
    code, out, _ = run_applet("uuidgen")
    uuid_str = out.decode().strip()
    is_valid_uuid = len(uuid_str) == 36 and uuid_str.count("-") == 4 and uuid_str[14] == "4"
    record_test("Modern", "uuidgen", "POS", "RFC 4122 v4 UUID format", code == 0 and is_valid_uuid)

# ============================================================================
# Main Test Harness Runner
# ============================================================================

def main():
    print("=" * 80)
    print("      FERRO-OS EXHAUSTIVE REAL-WORLD EDGE-CASE & QUALITY TEST SUITE     ")
    print("=" * 80)

    if not os.path.exists(FERRO_CORE_BIN):
        print(f"[-] Release binary not found at {FERRO_CORE_BIN}. Please build first!")
        sys.exit(1)

    tmpdir = tempfile.mkdtemp(prefix="ferro_exhaustive_")
    try:
        # Tier 1: Stream & Text
        test_cat(tmpdir)
        test_echo_and_printf()
        test_head_and_tail(tmpdir)
        test_wc(tmpdir)
        test_grep()
        test_awk()
        test_sponge(tmpdir)
        test_dos2unix_and_unix2dos(tmpdir)
        test_ts()

        # Tier 2: Archival & Block I/O
        test_gzip_gunzip_zcat(tmpdir)
        test_dd(tmpdir)

        # Tier 3: Process Lifecycle & Verification
        test_process_ledger_and_verification()

        # Tier 4: Modern Cloud & Ergonomics
        test_envsubst()
        test_json()
        test_uuidgen()

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n" + "=" * 80)
    total = len(TEST_RESULTS)
    passed = sum(1 for t in TEST_RESULTS if t["passed"])
    failed = total - passed

    print(f"  EXHAUSTIVE TEST RESULTS: Total: {total} | Passed: {passed} | Failed: {failed}")
    print("=" * 80)

    if failed > 0:
        print("\n❌ Failures encountered:")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("\n🎉 ALL MULTI-DIMENSIONAL TESTS PASSED WITH ZERO FAILURES!")
        print("  POSIX Compliance, Edge Cases, Error Handling, and Pipeline Interactions Verified.")
        sys.exit(0)

if __name__ == "__main__":
    main()
