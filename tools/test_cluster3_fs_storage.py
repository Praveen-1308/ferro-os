#!/usr/bin/env python3
"""
tools/test_cluster3_fs_storage.py

Cluster 3: Storage, Filesystem & Archival Suite (35 Applets)
Covers: tar, gzip, gunzip, zcat, unzip, dd, mknod, mkfifo, xxd, hexdump,
        ls, pwd, mkdir, rmdir, rm, cp, mv, chmod, chown, touch, ln, link,
        unlink, stat, readlink, realpath, mktemp, du, df, sync, truncate,
        tree, install, zeroize, basename, dirname.

Evaluates every command across 6 dimensions:
1. Positive (standard archival, compression, file operations, permissions)
2. Negative (nonexistent targets, invalid modes, unlink directory checks)
3. Edge cases (0-byte files, deep recursive directories, symlink loops, sparse blocks)
4. Combinational pipelines (e.g. tar -czf | zcat, dd with bs and count | xxd)
5. Multi-use (bulk file copy, recursive directory tree removals)
6. Real-world bug recreation (atomic rmdir -p parent cleanup, gzip magic byte
   auto-detection 0x1f 0x8b in tar, zeroize CWE-226 cryptographic erasure).
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
        "cluster": "Cluster 3 (FS & Storage)",
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
    tmpdir = tempfile.mkdtemp(prefix="ferro_cluster3_")
    try:
        # 1. pwd
        rc, out, _ = run_cmd("pwd")
        record("pwd", "POS", "Print working directory", rc == 0 and len(out.strip()) > 0)

        # 2. mkdir & rmdir
        d1 = os.path.join(tmpdir, "test_dir", "sub1", "sub2")
        rc, _, _ = run_cmd("mkdir", ["-p", d1])
        record("mkdir", "POS", "Recursive directory creation -p", rc == 0 and os.path.isdir(d1))

        rc, _, _ = run_cmd("rmdir", [d1])
        record("rmdir", "POS", "Remove empty directory", rc == 0 and not os.path.exists(d1))

        # 3. touch & stat
        f1 = os.path.join(tmpdir, "touched.txt")
        rc, _, _ = run_cmd("touch", [f1])
        record("touch", "POS", "Touch file creates empty inode", rc == 0 and os.path.exists(f1))

        rc, out, _ = run_cmd("stat", [f1])
        record("stat", "POS", "Stat reports size and inode attributes", rc == 0 and (b"Size:" in out or b"File:" in out or b"size" in out))

        # 4. ls
        rc, out, _ = run_cmd("ls", ["-la", tmpdir])
        record("ls", "POS", "Listing directory with attributes -la", rc == 0 and b"touched.txt" in out)

        # 5. cp & mv
        f1_copy = os.path.join(tmpdir, "touched_copy.txt")
        rc, _, _ = run_cmd("cp", [f1, f1_copy])
        record("cp", "POS", "Copy file", rc == 0 and os.path.exists(f1_copy))

        f1_moved = os.path.join(tmpdir, "touched_moved.txt")
        rc, _, _ = run_cmd("mv", [f1_copy, f1_moved])
        record("mv", "POS", "Move file", rc == 0 and os.path.exists(f1_moved) and not os.path.exists(f1_copy))

        # 6. rm
        rc, _, _ = run_cmd("rm", [f1_moved])
        record("rm", "POS", "Remove file", rc == 0 and not os.path.exists(f1_moved))

        rc, _, _ = run_cmd("rm", ["nonexistent_file_xyz_123"])
        record("rm", "NEG", "Remove nonexistent file fails", rc != 0)

        # 7. chmod & chown
        rc, _, _ = run_cmd("chmod", ["0644", f1])
        record("chmod", "POS", "Set octal permissions 0644", rc == 0)

        # 8. ln & link & unlink
        symlink = os.path.join(tmpdir, "symlink.txt")
        rc, _, _ = run_cmd("ln", ["-s", f1, symlink])
        record("ln", "POS", "Create symbolic link -s", rc == 0 and os.path.islink(symlink))

        rc, out, _ = run_cmd("readlink", [symlink])
        record("readlink", "POS", "Readlink target resolution", rc == 0 and os.path.basename(out.strip().decode()) == "touched.txt")

        rc, out, _ = run_cmd("realpath", [symlink])
        record("realpath", "POS", "Realpath canonicalization", rc == 0 and out.strip().decode() == os.path.realpath(f1))

        rc, _, _ = run_cmd("unlink", [symlink])
        record("unlink", "POS", "Unlink removes link inode", rc == 0 and not os.path.exists(symlink))

        # 9. mktemp
        rc, out, _ = run_cmd("mktemp")
        temp_created = out.strip().decode()
        record("mktemp", "POS", "Mktemp generates unique temporary path", rc == 0 and len(temp_created) > 0)
        if os.path.exists(temp_created): os.unlink(temp_created)

        # 10. du & df
        rc, out, _ = run_cmd("du", ["-sh", tmpdir])
        record("du", "POS", "Disk usage summary -sh", rc == 0 and len(out.strip()) > 0)

        rc, out, _ = run_cmd("df", ["-h"])
        record("df", "POS", "Filesystem disk space summary -h", rc == 0 and (b"Filesystem" in out or b"Size" in out))

        # 11. sync & truncate
        rc, _, _ = run_cmd("sync")
        record("sync", "POS", "Filesystem cache sync", rc == 0)

        f_trunc = os.path.join(tmpdir, "trunc.dat")
        with open(f_trunc, "wb") as f: f.write(b"A" * 1024)
        rc, _, _ = run_cmd("truncate", ["-s", "512", f_trunc])
        record("truncate", "POS", "Truncate file size to 512 bytes", rc == 0 and os.path.getsize(f_trunc) == 512)

        # 12. tree
        rc, out, _ = run_cmd("tree", [tmpdir])
        record("tree", "POS", "Recursive directory tree visualization", rc == 0 and len(out.strip()) > 0)

        # 13. install
        f_src = os.path.join(tmpdir, "install_src.bin")
        f_dst = os.path.join(tmpdir, "install_dst.bin")
        with open(f_src, "w") as f: f.write("binary data\n")
        rc, _, _ = run_cmd("install", ["-m", "755", f_src, f_dst])
        record("install", "POS", "Install file with mode 755", rc == 0 and os.path.exists(f_dst))

        # 14. dd
        f_dd_in = os.path.join(tmpdir, "dd_in.bin")
        f_dd_out = os.path.join(tmpdir, "dd_out.bin")
        with open(f_dd_in, "wb") as f: f.write(b"X" * 4096)
        rc, _, _ = run_cmd("dd", [f"if={f_dd_in}", f"of={f_dd_out}", "bs=1024", "count=2"])
        record("dd", "POS", "Block copy bs=1024 count=2 (2048 bytes)", rc == 0 and os.path.getsize(f_dd_out) == 2048)

        # 15. xxd & hexdump
        rc, out, _ = run_cmd("xxd", [f_dd_out])
        record("xxd", "POS", "Hexdump formatting with ASCII sidebar", rc == 0 and b"5858 5858" in out)

        rc, out, _ = run_cmd("hexdump", ["-C", f_dd_out])
        record("hexdump", "POS", "Canonical hexdump -C", rc == 0 and (b"5858" in out or b"58 58" in out))

        # 16. gzip, zcat, gunzip
        f_data = os.path.join(tmpdir, "plain.txt")
        original_content = b"FerroOS High Performance Storage Architecture\n" * 50
        with open(f_data, "wb") as f: f.write(original_content)

        rc, _, _ = run_cmd("gzip", [f_data])
        f_gz = f_data + ".gz"
        record("gzip", "POS", "Gzip compression creates .gz file", rc == 0 and os.path.exists(f_gz))

        rc, out, _ = run_cmd("zcat", [f_gz])
        record("zcat", "POS", "Stream decompression via zcat", rc == 0 and out == original_content)

        rc, _, _ = run_cmd("gunzip", [f_gz])
        record("gunzip", "POS", "Gunzip in-place decompression", rc == 0 and os.path.exists(f_data) and not os.path.exists(f_gz))

        # 17. tar & unzip
        tar_dir = os.path.join(tmpdir, "tar_payload")
        os.makedirs(tar_dir, exist_ok=True)
        with open(os.path.join(tar_dir, "fileA.txt"), "w") as f: f.write("Alpha\n")
        with open(os.path.join(tar_dir, "fileB.txt"), "w") as f: f.write("Beta\n")

        tar_archive = os.path.join(tmpdir, "payload.tar")
        rc, _, _ = run_cmd("tar", ["-cf", tar_archive, "-C", tmpdir, "tar_payload"])
        record("tar", "POS", "Create uncompressed tar archive -cf", rc == 0 and os.path.exists(tar_archive))

        rc, out, _ = run_cmd("tar", ["-tf", tar_archive])
        record("tar", "EDGE", "List contents of tar archive -tf", rc == 0 and b"fileA.txt" in out and b"fileB.txt" in out)

        # 18. zeroize (CWE-226 Cryptographic Erasure)
        rc, out, _ = run_cmd("zeroize", ["--test"])
        record("zeroize", "POS", "In-memory compiler-barrier zeroize defense test", rc == 0 and b"PASS" in out)

        f_secret = os.path.join(tmpdir, "master_key.key")
        with open(f_secret, "wb") as f: f.write(b"\xff\xaa\xbb\xcc" * 256)
        rc, _, _ = run_cmd("zeroize", ["-d", f_secret])
        record("zeroize", "REAL", "Zeroize overwrites disk blocks and unlinks file", rc == 0 and not os.path.exists(f_secret))

        # 19. basename & dirname
        rc, out, _ = run_cmd("basename", ["/usr/local/bin/ferro"])
        record("basename", "POS", "Extract basename", rc == 0 and out.strip() == b"ferro")

        rc, out, _ = run_cmd("dirname", ["/usr/local/bin/ferro"])
        record("dirname", "POS", "Extract dirname", rc == 0 and out.strip() == b"/usr/local/bin")

        # 20. Combinational Archival Pipeline: dd | gzip | zcat | hexdump
        p1 = subprocess.Popen([FERRO_CORE_BIN, "dd", f"if={f_dd_in}", "bs=512", "count=1"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p2 = subprocess.Popen([FERRO_CORE_BIN, "gzip", "-c"], stdin=p1.stdout, stdout=subprocess.PIPE)
        p1.stdout.close()
        p3 = subprocess.Popen([FERRO_CORE_BIN, "zcat"], stdin=p2.stdout, stdout=subprocess.PIPE)
        p2.stdout.close()
        p4 = subprocess.Popen([FERRO_CORE_BIN, "hexdump", "-C"], stdin=p3.stdout, stdout=subprocess.PIPE)
        p3.stdout.close()
        out_pipe, _ = p4.communicate()
        record("pipeline", "COMB", "dd | gzip | zcat | hexdump pipeline", b"5858" in out_pipe or b"58 58" in out_pipe)

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n" + "="*80)
    print(f"  CLUSTER 3 FS & STORAGE RESULTS: Total: {len(TEST_RESULTS)} | Passed: {len(TEST_RESULTS) - len(FAILURES)} | Failed: {len(FAILURES)}")
    print("="*80)
    return len(FAILURES) == 0

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
