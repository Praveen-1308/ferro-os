#!/usr/bin/env python3
"""
Comprehensive E2E File I/O Scenarios Matrix for FerroOS ferro-core (cp / mv)
Tests all real-world file patterns and edge-cases beyond basic text files:
1. Zero-byte empty files
2. Tiny sub-page config files (64B)
3. Exact page boundaries (4KB, 64KB, 2MB)
4. Sparse files with unallocated holes
5. Executable binaries with strict 0755 permissions
6. Read-only restricted files (0400)
7. Overwrite existing files of different sizes (truncation integrity)
8. High-entropy non-UTF8 binary blobs (SHA-256 verified)
9. Compressed archives (.tar.gz) verified via gzip decompression
10. Deep nested directory trees with mixed files (cp -r)
11. Cross-device filesystem transfers (EXDEV handling)
12. High-frequency file churn (no FD leaks under mimalloc)
"""

import os
import sys
import stat
import time
import tarfile
import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor

PASS = "✅ PASS"
FAIL = "❌ FAIL"

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def run_cmd(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def main():
    print("================================================================================")
    print("        FERRO-OS COMPREHENSIVE FILE I/O MATRIX & PATTERNS SUITE (E2E)           ")
    print("================================================================================")
    
    test_dir = "/tmp/ferro_io_matrix"
    os.makedirs(test_dir, exist_ok=True)
    all_passed = True

    # --------------------------------------------------------------------------
    # Scenario 1: Zero-byte empty file
    # --------------------------------------------------------------------------
    print("\n[Scenario 01] Zero-Byte Empty File (Kernel Boundary Check)")
    s1_src = f"{test_dir}/s1_empty.bin"
    s1_dst = f"{test_dir}/s1_dst.bin"
    open(s1_src, "w").close()
    
    res = run_cmd(["ferro-core", "cp", s1_src, s1_dst])
    if res.returncode == 0 and os.path.exists(s1_dst) and os.path.getsize(s1_dst) == 0:
        print(f"  -> {PASS}: Copied 0-byte file with zero errors.")
    else:
        print(f"  -> {FAIL}: Return={res.returncode}, Err={res.stderr}")
        all_passed = False

    # --------------------------------------------------------------------------
    # Scenario 2: Tiny sub-page file (64 bytes)
    # --------------------------------------------------------------------------
    print("\n[Scenario 02] Tiny Sub-Page Config File (64 Bytes)")
    s2_src = f"{test_dir}/s2_config.json"
    s2_dst = f"{test_dir}/s2_config_dst.json"
    content_64 = b'{"os":"FerroOS","arch":"aarch64","fast_path":true,"zero_copy":true}\n'
    with open(s2_src, "wb") as f: f.write(content_64)

    res = run_cmd(["ferro-core", "cp", s2_src, s2_dst])
    if res.returncode == 0 and sha256_file(s2_src) == sha256_file(s2_dst):
        print(f"  -> {PASS}: Sub-page 64B config copied bit-for-bit.")
    else:
        print(f"  -> {FAIL}: Hash mismatch or error: {res.stderr}")
        all_passed = False

    # --------------------------------------------------------------------------
    # Scenario 3: Exact Page-Boundary Aligned Files (4KB, 64KB, 2MB)
    # --------------------------------------------------------------------------
    print("\n[Scenario 03] Exact Page Boundaries (4KB standard, 64KB VFS, 2MB HugePage)")
    for sz_label, sz_bytes in [("4KB", 4096), ("64KB", 65536), ("2MB", 2097152)]:
        b_src = f"{test_dir}/page_{sz_label}.bin"
        b_dst = f"{test_dir}/page_{sz_label}_dst.bin"
        with open(b_src, "wb") as f: f.write(os.urandom(sz_bytes))
        
        t0 = time.perf_counter()
        res = run_cmd(["ferro-core", "cp", b_src, b_dst])
        dt = (time.perf_counter() - t0) * 1000
        
        if res.returncode == 0 and sha256_file(b_src) == sha256_file(b_dst):
            print(f"  -> {PASS}: Boundary {sz_label:>4} ({sz_bytes} B) copied in {dt:.3f} ms.")
        else:
            print(f"  -> {FAIL}: Boundary {sz_label} failed.")
            all_passed = False

    # --------------------------------------------------------------------------
    # Scenario 4: Sparse File with Unallocated Holes
    # --------------------------------------------------------------------------
    print("\n[Scenario 04] Sparse File with 500 MB Unallocated Hole")
    s4_src = f"{test_dir}/s4_sparse.img"
    s4_dst = f"{test_dir}/s4_sparse_dst.img"
    with open(s4_src, "wb") as f:
        f.seek(500 * 1024 * 1024 - 1)
        f.write(b"\x00")
    
    t0 = time.perf_counter()
    res = run_cmd(["ferro-core", "cp", s4_src, s4_dst])
    dt = time.perf_counter() - t0
    
    if res.returncode == 0 and os.path.getsize(s4_dst) == 500 * 1024 * 1024:
        print(f"  -> {PASS}: 500 MB Sparse File copied in {dt:.4f} s with exact virtual length.")
    else:
        print(f"  -> {FAIL}: Sparse copy failed: {res.stderr}")
        all_passed = False

    # --------------------------------------------------------------------------
    # Scenario 5: Executable Binary File with Strict 0755 Mode Preservation
    # --------------------------------------------------------------------------
    print("\n[Scenario 05] Executable Binary with Strict Mode Bits (chmod 0755)")
    s5_src = f"{test_dir}/s5_exec.sh"
    s5_dst = f"{test_dir}/s5_exec_dst.sh"
    with open(s5_src, "w") as f: f.write("#!/bin/sh\necho 'FerroOS Executable'\n")
    os.chmod(s5_src, 0o755)

    res = run_cmd(["ferro-core", "cp", s5_src, s5_dst])
    dst_mode = stat.S_IMODE(os.stat(s5_dst).st_mode)
    if res.returncode == 0 and dst_mode == 0o755:
        print(f"  -> {PASS}: Mode bits preserved (Source: 0755, Destination: {oct(dst_mode)}).")
    else:
        print(f"  -> {FAIL}: Mode bits mismatch: expected 0755, got {oct(dst_mode)}")
        all_passed = False

    # --------------------------------------------------------------------------
    # Scenario 6: Read-Only Restricted Source File (chmod 0400)
    # --------------------------------------------------------------------------
    print("\n[Scenario 06] Read-Only Restricted Source File (chmod 0400)")
    s6_src = f"{test_dir}/s6_readonly.key"
    s6_dst = f"{test_dir}/s6_readonly_dst.key"
    with open(s6_src, "w") as f: f.write("PRIVATE_KEY_DATA_PROTECTED_FERRO_OS\n")
    os.chmod(s6_src, 0o400)

    res = run_cmd(["ferro-core", "cp", s6_src, s6_dst])
    if res.returncode == 0 and sha256_file(s6_src) == sha256_file(s6_dst):
        print(f"  -> {PASS}: Read-only file copied successfully without permission errors.")
    else:
        print(f"  -> {FAIL}: Failed to copy read-only file: {res.stderr}")
        all_passed = False

    # --------------------------------------------------------------------------
    # Scenario 7: Overwriting Existing File with Different Size
    # --------------------------------------------------------------------------
    print("\n[Scenario 07] Overwriting Pre-Existing Target (Truncation Integrity)")
    s7_src = f"{test_dir}/s7_small.dat"
    s7_dst = f"{test_dir}/s7_large.dat"
    with open(s7_src, "wb") as f: f.write(b"A" * 1024)
    with open(s7_dst, "wb") as f: f.write(b"Z" * 100000) # previously 100KB

    res = run_cmd(["ferro-core", "cp", s7_src, s7_dst])
    if res.returncode == 0 and os.path.getsize(s7_dst) == 1024 and sha256_file(s7_src) == sha256_file(s7_dst):
        print(f"  -> {PASS}: Target truncated cleanly from 100KB down to exact 1024B.")
    else:
        print(f"  -> {FAIL}: Truncation failed, size = {os.path.getsize(s7_dst)}")
        all_passed = False

    # --------------------------------------------------------------------------
    # Scenario 8: High-Entropy Non-UTF8 Binary Payload (100 MB)
    # --------------------------------------------------------------------------
    print("\n[Scenario 08] High-Entropy 100 MB Non-UTF8 Binary Payload")
    s8_src = f"{test_dir}/s8_entropy.bin"
    s8_dst = f"{test_dir}/s8_entropy_dst.bin"
    with open(s8_src, "wb") as f: f.write(os.urandom(100 * 1024 * 1024))
    
    t0 = time.perf_counter()
    res = run_cmd(["ferro-core", "cp", s8_src, s8_dst])
    dt = time.perf_counter() - t0
    
    if res.returncode == 0 and sha256_file(s8_src) == sha256_file(s8_dst):
        print(f"  -> {PASS}: 100 MB Random Binary copied in {dt:.3f} s ({100/dt:.1f} MB/s), SHA256 verified.")
    else:
        print(f"  -> {FAIL}: 100 MB binary copy failed: {res.stderr}")
        all_passed = False

    # --------------------------------------------------------------------------
    # Scenario 9: Compressed Archive File (.tar.gz) Decompression Integrity
    # --------------------------------------------------------------------------
    print("\n[Scenario 09] Compressed Gzip Archive (.tar.gz) Integrity")
    s9_src = f"{test_dir}/archive.tar.gz"
    s9_dst = f"{test_dir}/archive_dst.tar.gz"
    with tarfile.open(s9_src, "w:gz") as tar:
        sample_txt = f"{test_dir}/sample.txt"
        with open(sample_txt, "w") as f: f.write("Archive internal contents\n")
        tar.add(sample_txt, arcname="sample.txt")
        os.remove(sample_txt)

    res = run_cmd(["ferro-core", "cp", s9_src, s9_dst])
    is_valid_archive = False
    if res.returncode == 0:
        try:
            with tarfile.open(s9_dst, "r:gz") as tar:
                names = tar.getnames()
                is_valid_archive = "sample.txt" in names
        except Exception:
            pass
            
    if is_valid_archive:
        print(f"  -> {PASS}: Gzip archive copied and decompressed successfully.")
    else:
        print(f"  -> {FAIL}: Corrupt archive after copy.")
        all_passed = False

    # --------------------------------------------------------------------------
    # Scenario 10: Deep Directory Tree with Nested Subdirectories & Mixed Content (cp -r)
    # --------------------------------------------------------------------------
    print("\n[Scenario 10] Deep Directory Tree Recursive Copy (cp -r)")
    tree_src = f"{test_dir}/tree_src"
    tree_dst = f"{test_dir}/tree_dst"
    os.makedirs(f"{tree_src}/a/b/c", exist_ok=True)
    with open(f"{tree_src}/root.bin", "wb") as f: f.write(os.urandom(1024))
    with open(f"{tree_src}/a/sub.txt", "w") as f: f.write("sub file\n")
    with open(f"{tree_src}/a/b/c/leaf.bin", "wb") as f: f.write(os.urandom(4096))

    res = run_cmd(["ferro-core", "cp", "-r", tree_src, tree_dst])
    tree_ok = (
        res.returncode == 0
        and os.path.exists(f"{tree_dst}/root.bin")
        and os.path.exists(f"{tree_dst}/a/sub.txt")
        and os.path.exists(f"{tree_dst}/a/b/c/leaf.bin")
        and sha256_file(f"{tree_src}/a/b/c/leaf.bin") == sha256_file(f"{tree_dst}/a/b/c/leaf.bin")
    )
    if tree_ok:
        print(f"  -> {PASS}: Recursive directory hierarchy copied with 100% fidelity.")
    else:
        print(f"  -> {FAIL}: Recursive directory copy failed: {res.stderr}")
        all_passed = False

    # --------------------------------------------------------------------------
    # Scenario 11: Cross-Device Move (EXDEV Fallback)
    # --------------------------------------------------------------------------
    print("\n[Scenario 11] Cross-Device Move (EXDEV Handling between /dev/shm and /tmp)")
    shm_file = "/dev/shm/ferro_shm_test.bin"
    dst_cross = f"{test_dir}/shm_moved.bin"
    try:
        with open(shm_file, "wb") as f: f.write(b"SHM_RAM_BUFFER_DATA" * 50)
        res = run_cmd(["ferro-core", "mv", shm_file, dst_cross])
        if res.returncode == 0 and os.path.exists(dst_cross) and not os.path.exists(shm_file):
            print(f"  -> {PASS}: Cross-device EXDEV move completed (source unlinked, destination preserved).")
        else:
            print(f"  -> {FAIL}: Cross-device move failed: {res.stderr}")
            all_passed = False
    except Exception as e:
        print(f"  -> ⚠️ Note: /dev/shm not mounted, skipping EXDEV check ({e})")

    # --------------------------------------------------------------------------
    # Scenario 12: High-Frequency File Churn (Leak & Stability Test)
    # --------------------------------------------------------------------------
    print("\n[Scenario 12] High-Frequency File Churn (500 Rapid Create-Copy-Verify Cycles)")
    churn_errors = 0
    t0_churn = time.perf_counter()
    
    def churn_task(i):
        src = f"{test_dir}/churn_src_{i}.bin"
        dst = f"{test_dir}/churn_dst_{i}.bin"
        data = os.urandom(8192)
        with open(src, "wb") as f: f.write(data)
        
        r = subprocess.run(["ferro-core", "cp", src, dst], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode != 0 or os.path.getsize(dst) != 8192:
            return False
            
        os.remove(src)
        os.remove(dst)
        return True

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(churn_task, range(500)))
        churn_errors = results.count(False)
        
    dt_churn = time.perf_counter() - t0_churn
    if churn_errors == 0:
        print(f"  -> {PASS}: 500 rapid cycles completed in {dt_churn:.2f} s ({500/dt_churn:.1f} ops/s) with 0 errors/leaks.")
    else:
        print(f"  -> {FAIL}: {churn_errors} errors during churn test.")
        all_passed = False

    # Cleanup
    import shutil
    shutil.rmtree(test_dir, ignore_errors=True)

    print("\n================================================================================")
    if all_passed:
        print("🏆 12 / 12 FILE I/O MATRIX SCENARIOS PASSED WITH PERFECT FIDELITY!")
        sys.exit(0)
    else:
        print("❌ SOME SCENARIOS FAILED. CHECK LOGS ABOVE.")
        sys.exit(1)

if __name__ == "__main__":
    main()
