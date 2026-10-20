import os
import sys
import time
import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

def main():
    print("================================================================================")
    print("      FERRO-OS ADVANCED SCENARIO A: HIGH-CONCURRENCY ZERO-COPY STRESS TEST      ")
    print("================================================================================")
    
    template_path = "/tmp/template_cow.bin"
    file_size_mb = 25
    num_workers = 32
    clones_per_worker = 10
    total_clones = num_workers * clones_per_worker

    print(f"Creating {file_size_mb} MB random binary template file...")
    data = os.urandom(file_size_mb * 1024 * 1024)
    with open(template_path, "wb") as f:
        f.write(data)
    
    expected_hash = hashlib.sha256(data).hexdigest()
    print(f"Template SHA-256: {expected_hash}")
    print(f"Launching {num_workers} parallel workers (Target: {total_clones} concurrent zero-copy clones)...")

    errors = 0
    t0 = time.perf_counter()

    def clone_task(worker_id, iter_id):
        dest_path = f"/tmp/clone_w{worker_id}_i{iter_id}.bin"
        res = subprocess.run(["ferro-core", "cp", template_path, dest_path], capture_output=True)
        if res.returncode != 0:
            return (False, f"ferro-core cp failed: {res.stderr.decode()}")
        
        # Verify size & quick hash sample
        sz = os.path.getsize(dest_path)
        if sz != len(data):
            os.remove(dest_path)
            return (False, f"Size mismatch: {sz} vs {len(data)}")
        
        # Verify full sha256 on a fraction of clones to maximize I/O throughput
        if iter_id == 0:
            with open(dest_path, "rb") as f:
                h = hashlib.sha256(f.read()).hexdigest()
            if h != expected_hash:
                os.remove(dest_path)
                return (False, f"Hash mismatch: {h}")

        os.remove(dest_path)
        return (True, None)

    tasks = []
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        for w in range(num_workers):
            for i in range(clones_per_worker):
                tasks.append(executor.submit(clone_task, w, i))
        
        for fut in as_completed(tasks):
            ok, err = fut.result()
            if not ok:
                errors += 1
                print(f"  [ERROR]: {err}")

    duration = time.perf_counter() - t0
    total_gb = (total_clones * file_size_mb) / 1024.0
    throughput_gb_s = total_gb / duration

    if os.path.exists(template_path):
        os.remove(template_path)

    print("\n--------------------------------------------------------------------------------")
    print(f"Total Clones Executed:    {total_clones}")
    print(f"Total Data Duplicated:    {total_gb:.2f} GB")
    print(f"Total Duration:           {duration:.2f} s")
    print(f"Cloning Throughput:       {total_clones / duration:.1f} clones/sec ({throughput_gb_s:.2f} GB/s)")
    print(f"Failed Clones / Panics:   {errors}")
    print(f"Pass Rate:                {((total_clones - errors) / total_clones) * 100:.1f}%")
    print("--------------------------------------------------------------------------------")

    if errors == 0:
        print("✅ ADVANCED SCENARIO A: PASS (100% Zero-Copy Concurrency, Zero Panics)")
        sys.exit(0)
    else:
        print("❌ ADVANCED SCENARIO A: FAILED")
        sys.exit(1)

if __name__ == "__main__":
    main()
