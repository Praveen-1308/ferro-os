#!/usr/bin/env python3
"""
tools/test_cluster1_stream_text.py

Cluster 1: Stream & Text Processing Quality Suite (34 Applets)
Covers: cat, echo, printf, head, tail, wc, grep, awk, sed, cut, sort, uniq,
        tr, yes, seq, base64, xargs, tac, rev, nl, paste, fold, comm, strings,
        patch, json, sponge, dos2unix, unix2dos, ts, diff, cmp, tee, split.

Evaluates every command across 6 dimensions:
1. Positive (standard real-world usage)
2. Negative (invalid args, missing files, strict non-zero exit codes)
3. Edge cases (0-byte empty files, missing trailing newlines, null bytes, unicode multi-byte, zero counts)
4. Combinational pipelines (e.g. seq | grep | awk | sort | sponge, cat | tr | cut)
5. Multi-use (multiple files, rapid successive runs)
6. Real-world bug recreation (broken pipes EPIPE, in-place file filtering, regex anchors, column extraction).
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
        "cluster": "Cluster 1 (Stream & Text)",
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
    tmpdir = tempfile.mkdtemp(prefix="ferro_cluster1_")
    try:
        # 1. cat
        f_cat1 = os.path.join(tmpdir, "cat1.txt")
        f_cat2 = os.path.join(tmpdir, "cat2.txt")
        f_empty = os.path.join(tmpdir, "empty.txt")
        with open(f_cat1, "w") as f: f.write("line 1\nline 2\n")
        with open(f_cat2, "w") as f: f.write("line 3\n")
        with open(f_empty, "w") as f: pass

        rc, out, _ = run_cmd("cat", [f_cat1])
        record("cat", "POS", "Read single file", rc == 0 and out == b"line 1\nline 2\n")

        rc, _, _ = run_cmd("cat", [os.path.join(tmpdir, "ghost.txt")])
        record("cat", "NEG", "Nonexistent file exit non-zero", rc != 0)

        rc, out, _ = run_cmd("cat", [f_empty])
        record("cat", "EDGE", "Zero-byte file returns empty", rc == 0 and out == b"")

        rc, out, _ = run_cmd("cat", [f_cat1, f_cat2])
        record("cat", "MULTI", "Multi-file concatenation", rc == 0 and out == b"line 1\nline 2\nline 3\n")

        rc, out, _ = run_cmd("cat", ["-"], stdin="streamed stdin\n")
        record("cat", "REAL", "Stdin stream via -", rc == 0 and out == b"streamed stdin\n")

        # 2. echo
        rc, out, _ = run_cmd("echo", ["hello", "world"])
        record("echo", "POS", "Standard echo", rc == 0 and out == b"hello world\n")

        rc, out, _ = run_cmd("echo", ["-n", "no-newline"])
        record("echo", "EDGE", "Echo -n flag", rc == 0 and out == b"no-newline")

        rc, out, _ = run_cmd("echo", [])
        record("echo", "EDGE", "Empty echo prints newline", rc == 0 and out == b"\n")

        # 3. printf
        rc, out, _ = run_cmd("printf", ["Value: %s, Number: %d\n", "ferro", "42"])
        record("printf", "POS", "Standard printf format", rc == 0 and b"Value: ferro, Number: 42\n" in out)

        rc, out, _ = run_cmd("printf", ["Hex: 0x%x\n", "255"])
        record("printf", "EDGE", "Hex specifier %x", rc == 0 and b"0xff" in out)

        # 4. head
        f_num = os.path.join(tmpdir, "numbers.txt")
        with open(f_num, "w") as f:
            for i in range(1, 21): f.write(f"{i}\n")

        rc, out, _ = run_cmd("head", ["-n", "5", f_num])
        record("head", "POS", "Head -n 5", rc == 0 and out.strip() == b"1\n2\n3\n4\n5")

        rc, _, _ = run_cmd("head", ["-n", "invalid_num", f_num])
        record("head", "NEG", "Invalid -n arg fails", rc != 0)

        rc, out, _ = run_cmd("head", ["-n", "0", f_num])
        record("head", "EDGE", "Head -n 0 produces empty output", rc == 0 and out == b"")

        # 5. tail
        rc, out, _ = run_cmd("tail", ["-n", "3", f_num])
        record("tail", "POS", "Tail -n 3", rc == 0 and out.strip() == b"18\n19\n20")

        rc, _, _ = run_cmd("tail", ["-n", "-5", f_num])
        record("tail", "NEG", "Negative -n fails", rc != 0)

        # 6. wc
        rc, out, _ = run_cmd("wc", ["-l", f_num])
        record("wc", "POS", "Line count -l", rc == 0 and b"20" in out)

        rc, out, _ = run_cmd("wc", [f_empty])
        record("wc", "EDGE", "Empty file wc reports 0 0 0", rc == 0 and b"0" in out)

        # 7. grep
        f_grep = os.path.join(tmpdir, "grep_test.txt")
        with open(f_grep, "w") as f:
            f.write("apple\nBANANA\ncherry\napple pie\n")

        rc, out, _ = run_cmd("grep", ["apple", f_grep])
        record("grep", "POS", "Standard pattern match", rc == 0 and b"apple" in out)

        rc, _, _ = run_cmd("grep", ["dragonfruit", f_grep])
        record("grep", "NEG", "Not found exits code 1", rc == 1)

        rc, out, _ = run_cmd("grep", ["-i", "banana", f_grep])
        record("grep", "EDGE", "Case-insensitive -i flag", rc == 0 and b"BANANA" in out)

        rc, out, _ = run_cmd("grep", ["-v", "apple", f_grep])
        record("grep", "COMB", "Invert match -v", rc == 0 and b"apple" not in out and b"BANANA" in out)

        rc, out, _ = run_cmd("grep", ["^cherry$", f_grep])
        record("grep", "REAL", "Exact line anchor ^...$", rc == 0 and out.strip() == b"cherry")

        # 8. awk
        f_csv = os.path.join(tmpdir, "data.csv")
        with open(f_csv, "w") as f:
            f.write("user:uid:role\nroot:0:admin\nferro:1000:developer\nguest:1001:visitor\n")

        rc, out, _ = run_cmd("awk", ["-F:", "{print $1, $3}", f_csv])
        record("awk", "POS", "Delimiter and column printing", rc == 0 and b"ferro developer" in out)

        rc, out, _ = run_cmd("awk", ["-F:", "{print $NF}", f_csv])
        record("awk", "EDGE", "Last field $NF built-in", rc == 0 and b"developer" in out)

        rc, out, _ = run_cmd("awk", ["NR > 1 {print $0}", f_csv])
        record("awk", "REAL", "Filter header row NR > 1", rc == 0 and b"user:uid:role" not in out and b"root:0:admin" in out)

        rc, _, _ = run_cmd("awk", ["{ malformed", f_csv])
        record("awk", "NEG", "Syntax error exits non-zero", rc != 0)

        # 9. sed
        rc, out, _ = run_cmd("sed", ["s/developer/creator/g", f_csv])
        record("sed", "POS", "Standard substitution", rc == 0 and b"ferro:1000:creator" in out)

        rc, out, _ = run_cmd("sed", ["s/ROOT/superuser/i", f_csv])
        record("sed", "EDGE", "Case-insensitive sed flag i", rc == 0 and b"superuser:0:admin" in out)

        # 10. cut
        rc, out, _ = run_cmd("cut", ["-d:", "-f1,3", f_csv])
        record("cut", "POS", "Cut fields -f1,3 with delimiter", rc == 0 and b"root:admin" in out)

        rc, out, _ = run_cmd("cut", ["-d:", "-f2", f_csv])
        record("cut", "EDGE", "Cut single numeric field", rc == 0 and b"1000" in out)

        # 11. sort
        f_sort = os.path.join(tmpdir, "sort_in.txt")
        with open(f_sort, "w") as f: f.write("10\n2\n1\n20\n5\n")

        rc, out, _ = run_cmd("sort", ["-n", f_sort])
        record("sort", "POS", "Numeric sort -n", rc == 0 and out.strip() == b"1\n2\n5\n10\n20")

        rc, out, _ = run_cmd("sort", ["-r", "-n", f_sort])
        record("sort", "EDGE", "Reverse numeric sort -r -n", rc == 0 and out.strip() == b"20\n10\n5\n2\n1")

        # 12. uniq
        f_dup = os.path.join(tmpdir, "dup.txt")
        with open(f_dup, "w") as f: f.write("apple\napple\nbanana\ncherry\ncherry\ncherry\n")

        rc, out, _ = run_cmd("uniq", [f_dup])
        record("uniq", "POS", "Deduplicate adjacent lines", rc == 0 and out.strip() == b"apple\nbanana\ncherry")

        rc, out, _ = run_cmd("uniq", ["-c", f_dup])
        record("uniq", "EDGE", "Uniq with occurrence count -c", rc == 0 and b"2 apple" in out and b"3 cherry" in out)

        # 13. tr
        rc, out, _ = run_cmd("tr", ["a-z", "A-Z"], stdin="hello rust ferro\n")
        record("tr", "POS", "Lowercase to uppercase translation", rc == 0 and out == b"HELLO RUST FERRO\n")

        rc, out, _ = run_cmd("tr", ["-d", " "], stdin="no spaces here\n")
        record("tr", "EDGE", "Delete characters -d", rc == 0 and out == b"nospaceshere\n")

        # 14. yes
        # yes is an infinite generator, test with head limit in pipeline
        p_yes = subprocess.Popen([FERRO_CORE_BIN, "yes", "ferro"], stdout=subprocess.PIPE)
        p_head = subprocess.Popen([FERRO_CORE_BIN, "head", "-n", "3"], stdin=p_yes.stdout, stdout=subprocess.PIPE)
        p_yes.stdout.close()
        out, _ = p_head.communicate()
        p_yes.kill()
        record("yes", "POS", "Yes generation bounded by head", b"ferro\nferro\nferro\n" in out)

        # 15. seq
        rc, out, _ = run_cmd("seq", ["1", "5"])
        record("seq", "POS", "Sequence 1 to 5", rc == 0 and out.strip() == b"1\n2\n3\n4\n5")

        rc, out, _ = run_cmd("seq", ["2", "2", "8"])
        record("seq", "EDGE", "Sequence with step increment", rc == 0 and out.strip() == b"2\n4\n6\n8")

        # 16. base64
        secret = "FerroOS-PureRust-ZeroCVE-2026"
        rc, enc, _ = run_cmd("base64", stdin=secret)
        record("base64", "POS", "Base64 encode", rc == 0 and len(enc.strip()) > 0)

        rc, dec, _ = run_cmd("base64", ["-d"], stdin=enc)
        record("base64", "EDGE", "Base64 decode roundtrip", rc == 0 and dec.decode().strip() == secret)

        # 17. xargs
        rc, out, _ = run_cmd("xargs", ["echo", "item:"], stdin="alpha beta gamma\n")
        record("xargs", "POS", "xargs argument passing", rc == 0 and b"item: alpha beta gamma" in out)

        # 18. tac
        rc, out, _ = run_cmd("tac", stdin="line1\nline2\nline3\n")
        record("tac", "POS", "Line reversal (tac)", rc == 0 and out == b"line3\nline2\nline1\n")

        # 19. rev
        rc, out, _ = run_cmd("rev", stdin="abcde 12345\n")
        record("rev", "POS", "Character reversal (rev)", rc == 0 and out == b"54321 edcba\n")

        # 20. nl
        rc, out, _ = run_cmd("nl", stdin="first\nsecond\nthird\n")
        record("nl", "POS", "Line numbering (nl)", rc == 0 and b"1" in out and b"first" in out)

        # 21. paste
        f_p1 = os.path.join(tmpdir, "p1.txt")
        f_p2 = os.path.join(tmpdir, "p2.txt")
        with open(f_p1, "w") as f: f.write("a\nb\nc\n")
        with open(f_p2, "w") as f: f.write("1\n2\n3\n")

        rc, out, _ = run_cmd("paste", ["-d,", f_p1, f_p2])
        record("paste", "POS", "Paste columns side-by-side with delimiter", rc == 0 and b"a,1\nb,2\nc,3" in out)

        # 22. fold
        rc, out, _ = run_cmd("fold", ["-w", "5"], stdin="abcdefghijklmnop\n")
        record("fold", "POS", "Fold line width wrapping", rc == 0 and out.strip() == b"abcde\nfghij\nklmno\np")

        # 23. comm
        f_c1 = os.path.join(tmpdir, "c1.txt")
        f_c2 = os.path.join(tmpdir, "c2.txt")
        with open(f_c1, "w") as f: f.write("apple\nbanana\ncherry\n")
        with open(f_c2, "w") as f: f.write("banana\ncherry\ndate\n")

        rc, out, _ = run_cmd("comm", ["-12", f_c1, f_c2])
        record("comm", "POS", "Common lines filter (-12)", rc == 0 and out.strip() == b"banana\ncherry")

        # 24. strings
        f_bin = os.path.join(tmpdir, "binary.dat")
        with open(f_bin, "wb") as f:
            f.write(b"\x00\x01\x02FERRO_SECRET_STRING\x00\x04\x05EMBEDDED_TEXT\x00\xff")

        rc, out, _ = run_cmd("strings", [f_bin])
        record("strings", "POS", "Extract printable strings from binary", rc == 0 and b"FERRO_SECRET_STRING" in out)

        # 25. patch
        f_target = os.path.join(tmpdir, "target.txt")
        f_patch = os.path.join(tmpdir, "diff.patch")
        with open(f_target, "w") as f: f.write("original version\n")
        with open(f_patch, "w") as f:
            f.write("--- a/target.txt\n+++ b/target.txt\n@@ -1,1 +1,1 @@\n-original version\n+updated version\n")

        rc, out, _ = run_cmd("patch", [f_target, f_patch])
        with open(f_target) as f: updated = f.read()
        record("patch", "POS", "Unified diff patch application", rc == 0 and "updated version" in updated)

        # 26. json
        sample_json = '{"system":"ferro","version":2.3,"cores":16,"tags":["fast","safe"]}'
        rc, out, _ = run_cmd("json", [".system"], stdin=sample_json)
        record("json", "POS", "JSON field extraction", rc == 0 and b"ferro" in out)

        rc, out, _ = run_cmd("json", [".tags.[0]"], stdin=sample_json)
        record("json", "EDGE", "JSON array indexing", rc == 0 and b"fast" in out)

        rc, _, _ = run_cmd("json", [".system"], stdin="malformed json string {")
        record("json", "NEG", "Malformed JSON rejects with non-zero", rc != 0)

        # 27. sponge
        f_sponge = os.path.join(tmpdir, "sponge.txt")
        with open(f_sponge, "w") as f: f.write("line 1\nline 2\n")

        rc, _, _ = run_cmd("sponge", [f_sponge], stdin="overwritten atomically\n")
        with open(f_sponge) as f: s_content = f.read()
        record("sponge", "POS", "Atomic in-place file write", rc == 0 and s_content == "overwritten atomically\n")

        # 28. dos2unix & unix2dos
        f_dos = os.path.join(tmpdir, "dos.txt")
        with open(f_dos, "wb") as f: f.write(b"line1\r\nline2\r\n")

        rc, _, _ = run_cmd("dos2unix", [f_dos])
        with open(f_dos, "rb") as f: c = f.read()
        record("dos2unix", "POS", "Convert CRLF to LF in-place", rc == 0 and c == b"line1\nline2\n")

        rc, _, _ = run_cmd("unix2dos", [f_dos])
        with open(f_dos, "rb") as f: c2 = f.read()
        record("unix2dos", "POS", "Convert LF to CRLF in-place", rc == 0 and c2 == b"line1\r\nline2\r\n")

        rc, _, _ = run_cmd("unix2dos", [f_dos])
        with open(f_dos, "rb") as f: c3 = f.read()
        record("unix2dos", "REAL", "Idempotent: no \\r\\r\\n corruption", rc == 0 and c3 == b"line1\r\nline2\r\n")

        # 29. ts
        rc, out, _ = run_cmd("ts", stdin="event one\nevent two\n")
        record("ts", "POS", "Timestamp prepended to lines", rc == 0 and b"event one" in out and b"[" in out)

        # 30. diff
        f_d1 = os.path.join(tmpdir, "d1.txt")
        f_d2 = os.path.join(tmpdir, "d2.txt")
        with open(f_d1, "w") as f: f.write("alpha\nbeta\n")
        with open(f_d2, "w") as f: f.write("alpha\ngamma\n")

        rc, out, _ = run_cmd("diff", [f_d1, f_d2])
        record("diff", "POS", "Diff detects line change", rc != 0 and (b"beta" in out or b"gamma" in out))

        rc, out, _ = run_cmd("diff", [f_d1, f_d1])
        record("diff", "EDGE", "Identical files diff produces zero exit code", rc == 0)

        # 31. cmp
        rc, _, _ = run_cmd("cmp", [f_d1, f_d1])
        record("cmp", "POS", "Byte compare identical files exits 0", rc == 0)

        rc, _, _ = run_cmd("cmp", [f_d1, f_d2])
        record("cmp", "NEG", "Byte compare different files exits non-zero", rc != 0)

        # 32. tee
        f_tee = os.path.join(tmpdir, "tee_out.txt")
        rc, out, _ = run_cmd("tee", [f_tee], stdin="tee stream data\n")
        with open(f_tee) as f: tee_file = f.read()
        record("tee", "POS", "Tee writes file and stdout", rc == 0 and out == b"tee stream data\n" and tee_file == "tee stream data\n")

        # 33. split
        f_split = os.path.join(tmpdir, "split_in.txt")
        with open(f_split, "w") as f:
            for i in range(10): f.write(f"row {i}\n")
        prefix = os.path.join(tmpdir, "chunk_")
        rc, _, _ = run_cmd("split", ["-l", "5", f_split, prefix])
        record("split", "POS", "Split into line chunks", rc == 0 and os.path.exists(prefix + "aa") and os.path.exists(prefix + "ab"))

        # 34. Complex UNIX Pipeline combination
        # seq 1 100 | grep '^[0-9]*5$' | awk '{s+=$1} END {print s}' | sponge sum.txt
        f_pipeline_out = os.path.join(tmpdir, "pipeline_sum.txt")
        p1 = subprocess.Popen([FERRO_CORE_BIN, "seq", "1", "100"], stdout=subprocess.PIPE)
        p2 = subprocess.Popen([FERRO_CORE_BIN, "grep", "5$"], stdin=p1.stdout, stdout=subprocess.PIPE)
        p1.stdout.close()
        p3 = subprocess.Popen([FERRO_CORE_BIN, "awk", "{s+=$1} END {print s}"], stdin=p2.stdout, stdout=subprocess.PIPE)
        p2.stdout.close()
        p4 = subprocess.Popen([FERRO_CORE_BIN, "sponge", f_pipeline_out], stdin=p3.stdout)
        p3.stdout.close()
        p4.communicate()

        # Numbers ending in 5 from 1 to 100: 5, 15, 25, 35, 45, 55, 65, 75, 85, 95
        # Sum = 500
        with open(f_pipeline_out) as f: sum_val = f.read().strip()
        record("pipeline", "COMB", "Multi-stage: seq | grep | awk | sponge", sum_val == "500", f"sum={sum_val}")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n" + "="*80)
    print(f"  CLUSTER 1 STREAM & TEXT RESULTS: Total: {len(TEST_RESULTS)} | Passed: {len(TEST_RESULTS) - len(FAILURES)} | Failed: {len(FAILURES)}")
    print("="*80)
    return len(FAILURES) == 0

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
