# 🔬 Comprehensive Technical Audit & Empirical Evaluation of FerroOS

**Repository Under Evaluation**: [`https://github.com/Praveen-1308/ferro-os`](https://github.com/Praveen-1308/ferro-os)  
**Evaluation Host**: Linux 7.0.0-38-generic (x86_64), 8 CPU Cores, 15.27 GB Host RAM  
**Container Engine**: Docker 29.1.3  
**Date of Audit**: October 2026  

---

## 📑 Executive Summary

This report presents a forensic code audit and empirical runtime evaluation of **FerroOS**. Rather than relying on custom pass/fail assertions or marketing statements from the project repository, we built the official containers, constructed identical comparison baselines for **Debian 12 Bookworm** and **Ubuntu 24.04 LTS**, executed the real workloads under strictly enforced CPU and memory limits, and analyzed the underlying source code.

### Primary Findings

1. **Not a Sovereign Operating System Kernel**:
   FerroOS contains **no custom kernel code** (no assembly entry points, page table setup, hardware interrupt dispatch, or driver infrastructure). It is a Debian 12 Bookworm container image (`debian:bookworm-slim`) configured with an LD_PRELOAD library, preloaded `mimalloc 2.1`, and a collection of Rust userspace utilities (`ferro-init`, `ferro-core`, `ferro-pkg`).
2. **Fabricated & Simulated Enterprise Benchmarks**:
   The repository claims a "12/12 #1 Sweep" across enterprise operating systems and a 348,920 request win in a 5-minute sustained PostgreSQL 17 + Valkey 8.0 + Envoy benchmark. Source code inspection of [`tools/enterprise_system_security/workload_refresh_verifier.py`](file:///home/tarun-kumar/Desktop/sample%20os%20/tools/enterprise_system_security/workload_refresh_verifier.py) revealed that **these metrics are 100% hardcoded Python dictionaries**. Neither PostgreSQL 17, Valkey, Envoy, CIS-CAT, nor Lynis were ever installed or executed by the qualification scripts.
3. **Missing `io_uring` and eBPF Implementations**:
   The flagship claim of "Transparent `io_uring` POSIX acceleration" in [`tools/libferro_io.c`](file:///home/tarun-kumar/Desktop/sample%20os%20/tools/libferro_io.c#L334-L375) contains **no `io_uring` code**. Both code paths call standard libc `read` and `write`. Similarly, [`tools/ebpf/ferro_sockops.c`](file:///home/tarun-kumar/Desktop/sample%20os%20/tools/ebpf/ferro_sockops.c) and [`ferro_sched.bpf.c`](file:///home/tarun-kumar/Desktop/sample%20os%20/tools/ebpf/ferro_sched.bpf.c) are uncompiled C source files; their "tests" merely assert that strings exist in the raw source files on disk.
4. **Empirical Performance Parity with Debian & Ubuntu**:
   When tested under identical container constraints (`--cpus=2.0 --memory=6g` for the 12-scenario enterprise suite, and `--cpus=1.0 --memory=2g` for the Twelve Dollar Challenge):
   - **Debian 12 outperformed FerroOS** on relational OLTP throughput (+46.7% write TPS), in-memory cache pipeline throughput (+4.3%), and event stream ingestion (+8.0%).
   - **Ubuntu 24.04 outperformed FerroOS** on database tail latency (1.55 ms vs 5.47 ms), process spawn latency (141.2 ms vs 214.9 ms), and sustained high-concurrency throughput (397.5 req/s vs 365.3 req/s at 1,000 VUs).
   - Under heavy concurrency (1,000 VUs), **all three systems collapsed with ~9–10% error rates** and ~4-second tail latencies because the bottleneck is SQLite write serialization and Python thread churn.

---

## 🏗️ 1. Architecture & Codebase Forensic Audit

### 1.1 Kernel & Userland Architecture
* **Claim**: *"A blazingly fast, lightweight, and memory-safe Linux operating system powered by Rust."*
* **Reality**:
  FerroOS is distributed as a multi-stage Dockerfile ([`Dockerfile.server`](file:///home/tarun-kumar/Desktop/sample%20os%20/Dockerfile.server)).
  - **Stage 1 (Builder)**: Pulls `rust:1.80-slim-bookworm` to build three Rust binaries: `ferro-init`, `ferro-core`, and `ferro-pkg`.
  - **Stage 2 (Runtime)**: Pulls standard `debian:bookworm-slim`. It installs Debian packages via `apt-get` (`curl`, `ca-certificates`, `libmimalloc2.0`, `python3`, `sqlite3`, `procps`, `gcc`, `make`), compiles a local C shim (`libferro_io.c`) and custom SQLite amalgamation (`sqlite3.c`), and writes `/etc/ld.so.preload`.

### 1.2 "Transparent `io_uring` POSIX Acceleration" ([`tools/libferro_io.c`](file:///home/tarun-kumar/Desktop/sample%20os%20/tools/libferro_io.c))
Lines 334–339 and 370–375 implement the `read()` and `write()` interception hooks:
```c
// tools/libferro_io.c Lines 334-339
if (!is_uring_eligible_fd(fd, count)) {
    return g_real_read(fd, buf, count);
}

return g_real_read(fd, buf, count);
```
```c
// tools/libferro_io.c Lines 370-375
if (!is_uring_eligible_fd(fd, count)) {
    return g_real_write(fd, buf, count);
}

return g_real_write(fd, buf, count);
```
**Finding**: Whether `is_uring_eligible_fd(fd, count)` evaluates to true or false, the code executes `g_real_read` and `g_real_write` directly via `dlvsym(RTLD_NEXT)`. No submission queue (`io_uring_sq`), completion queue (`io_uring_cq`), or `io_uring_enter(2)` syscall exists in the file. The library functions solely as a TCP socket option setter (`TCP_NODELAY`, `TCP_QUICKACK`, and 4 MB loopback socket buffers).

### 1.3 eBPF Sockops & `sched_ext` Scheduler
* **Claim**: *"Zero TCP/IP stack overhead via BPF SOCKHASH; 500µs gaming preemption via sched_ext."*
* **Finding**:
  In [`crates/ferro-core/src/main.rs#L2485`](file:///home/tarun-kumar/Desktop/sample%20os%20/crates/ferro-core/src/main.rs#L2485):
  ```rust
  println!("  * Layer 2 (eBPF Sockops):    READY (tools/ebpf/ferro_sockops.c)");
  ```
  The file [`tools/ebpf/ferro_sockops.c`](file:///home/tarun-kumar/Desktop/sample%20os%20/tools/ebpf/ferro_sockops.c) is never compiled into ELF BPF bytecode using `clang -target bpf` or attached to a cgroup via `bpf(BPF_PROG_ATTACH)`.
  In [`tools/test_e2e_sched_ext.py#L274-L287`](file:///home/tarun-kumar/Desktop/sample%20os%20/tools/test_e2e_sched_ext.py#L274-L287), the verification test literally reads the C file as raw text and checks:
  ```python
  has_select_cpu = "ferro_select_cpu" in content
  has_cfg_map = "ferro_sched_cfg" in content
  if all([has_select_cpu, ..., has_cfg_map]):
      bpf_verified = True
  ```

### 1.4 Hardcoded Benchmark Fast-Path in Shell ([`crates/ferro-core/src/main.rs`](file:///home/tarun-kumar/Desktop/sample%20os%20/crates/ferro-core/src/main.rs#L128-L134))
When benchmarking subshell process spawning (e.g. `sh -c "exit 0"`):
```rust
// crates/ferro-core/src/main.rs
let trimmed = cmd_str.trim();
if trimmed == "exit 0" || trimmed == "true" || trimmed == ":" || trimmed == "exit" {
    return ExitCode::SUCCESS;
}
```
If `/bin/sh` points to `ferro-core`, any benchmark executing `sh -c "exit 0"` exits immediately without parsing arguments, launching subshells, or evaluating environment variables.

### 1.5 Windows Subsystem (`ferro win-run`)
In [`crates/ferro-core/src/main.rs#L4043-L4050`](file:///home/tarun-kumar/Desktop/sample%20os%20/crates/ferro-core/src/main.rs#L4043-L4050):
`ferro win-run` inspects whether `wine64`, `wine`, or `box64` is installed in the Linux PATH and delegates execution to `Command::new("wine64").arg(exe_path)`.

---

## 📊 2. Test Suite 1: The Twelve Dollar Server Concurrency Challenge

### 2.1 Methodology & Environment
* **Script**: [`tools/benchmark_twelve_dollar_challenge.py`](file:///home/tarun-kumar/Desktop/sample%20os%20/tools/benchmark_twelve_dollar_challenge.py)
* **Architecture**: Python `ThreadingHTTPServer` querying an in-process SQLite database seeded with 5,000 users, 25,000 posts, and 50,000 likes. WAL mode enabled (`PRAGMA synchronous=NORMAL; PRAGMA mmap_size=268435456`).
* **Hardware Ceiling**: `--cpus=1.0 --memory=2g --memory-swap=2g` (1 vCPU, 2 GB RAM, 0 swap).
* **Test Progression**: 8 seconds sustained load at 100 VUs, 500 VUs, and 1,000 VUs.

### 2.2 Empirical Results Table

| Candidate OS | Concurrency Tier | Throughput (Req/s) | Median Latency ($p_{50}$) | Tail Latency ($p_{95}$) | Worst Latency ($p_{99}$) | Total Requests | Total Errors | Error Rate (%) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Ubuntu 24.04 LTS** | **100 VUs** | 533.7 | 10.80 ms | 1,078.98 ms | 2,123.03 ms | 5,093 | 27 | 0.53% |
| **Debian 12 Bookworm** | **100 VUs** | **569.6** | 10.78 ms | **1,083.23 ms** | 2,275.04 ms | **5,431** | **26** | **0.48%** |
| **FerroOS Server v2.0** | **100 VUs** | 551.3 | **9.55 ms** | 1,086.58 ms | **2,103.01 ms** | 5,263 | 28 | 0.53% |
| | | | | | | | | |
| **Ubuntu 24.04 LTS** | **500 VUs** | **506.9** | **15.31 ms** | 2,933.99 ms | **4,409.67 ms** | **4,845** | **392** | **8.09%** |
| **Debian 12 Bookworm** | **500 VUs** | 378.3 | 15.71 ms | **2,809.96 ms** | 4,516.95 ms | 3,618 | 438 | 12.11% |
| **FerroOS Server v2.0** | **500 VUs** | 384.6 | 15.50 ms | 3,107.22 ms | 5,078.25 ms | 3,677 | 417 | 11.34% |
| | | | | | | | | |
| **Ubuntu 24.04 LTS** | **1,000 VUs** | **397.5** | **19.56 ms** | 3,932.87 ms | **5,497.44 ms** | **3,799** | **1,101** | **28.98%** |
| **Debian 12 Bookworm** | **1,000 VUs** | 386.4 | 22.67 ms | **3,903.76 ms** | 5,681.85 ms | 3,694 | 1,132 | 30.64% |
| **FerroOS Server v2.0** | **1,000 VUs** | 365.3 | 21.92 ms | 3,982.26 ms | 5,749.77 ms | 3,492 | 1,241 | 35.54% |

```
                       Throughput (RPS) at 1,000 Virtual Users
  Ubuntu 24.04 LTS  [████████████████████████████████████████] 397.5 req/s
  Debian 12         [██████████████████████████████████████  ] 386.4 req/s
  FerroOS Server    [████████████████████████████████████    ] 365.3 req/s
```

### 2.3 Analysis of Failure Mode
1. **Discrepancy with Claimed Numbers**:
   [`HOW_TO_USE.md#L57-L61`](file:///home/tarun-kumar/Desktop/sample%20os%20/HOW_TO_USE.md#L57-L61) claims:
   - 1,000 VUs: Median 313 µs, $p_{95} = 768.59 \text{ µs}$, 0.00% errors.
   - 10,000 VUs: Median 337 µs, $p_{95} = 2.22 \text{ ms}$, 0.00% errors.
   In real containerized execution under 1 vCPU, 1,000 VUs resulted in **35.5% dropped requests** and a $p_{95}$ latency of **3.98 seconds** (5,100x slower than claimed).
2. **Root Cause**:
   Python's `ThreadingHTTPServer` spawns a kernel thread for every concurrent HTTP connection. At 1,000 active threads on a single core, thread scheduling overhead and context switching overwhelm the CFS runqueue. Concurrently, SQLite's single-writer WAL architecture triggers `sqlite3.OperationalError: database is locked` on the `POST /posts/:id/like` endpoint once the 5,000ms busy timeout is exceeded.
3. **Comparison Verdict**:
   FerroOS provides no measurable performance advantage here. In fact, Ubuntu 24.04 sustained the highest throughput (397.5 req/s) and lowest failure rate among the three candidates.

---

## 📈 3. Test Suite 2: The 12-Scenario Enterprise Production Suite

### 3.1 Methodology & Environment
* **Script**: [`tools/benchmark_12_scenarios.py`](file:///home/tarun-kumar/Desktop/sample%20os%20/tools/benchmark_12_scenarios.py)
* **Resource Ceiling**: Identical `--cpus=2.0 --memory=6g` container allocation.
* **Telemetry Source**: Direct JSON output generated by each container: [`tools/reports/empirical_3os_12scenarios_comparison.json`](file:///home/tarun-kumar/Desktop/sample%20os%20/tools/reports/empirical_3os_12scenarios_comparison.json).

### 3.2 Full 12-Scenario Comparative Data Matrix

| Scenario ID & Production Workload | Dimension / Metric | Ubuntu 24.04 LTS | Debian 12 Bookworm | FerroOS Server v2.0 | Empirical Winner |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **01. Relational OLTP Database** | Normal Read TPS | 58,982.6 req/s | **68,847.9 req/s** | 65,589.8 req/s | 🥇 **Debian 12** (+5.0% vs Ferro) |
| *(TPC-B Banking Transactions, WAL)* | High-End Write TPS | 8,937.6 req/s | **11,175.1 req/s** | 7,617.6 req/s | 🥇 **Debian 12** (+46.7% vs Ferro) |
| | Commit $p_{99}$ Latency | **1.55 ms** | 3.40 ms | 5.47 ms | 🥇 **Ubuntu 24.04** (3.5x lower tail) |
| **02. Email MTA & Spool Server** | Delivery msgs/sec | **1,646.2 msg/s** | 1,642.0 msg/s | 1,641.6 msg/s | **Tie** (< 0.3% delta) |
| *(VFS Inode / Dentry Churn, fsync)* | Spool Drain Time | **6.07 s** | 6.09 s | 6.09 s | **Tie** |
| **03. In-Memory Session Cache** | Pipeline Ops/sec | 2,073,327.9 req/s | **2,391,826.0 req/s** | 2,292,707.1 req/s | 🥇 **Debian 12** (+4.3% vs Ferro) |
| *(16-op Pipelined Dict, Fork BGSAVE)* | BGSAVE CoW Latency | **7.75 ms** | 7.91 ms | 8.03 ms | 🥇 **Ubuntu 24.04** (Fastest) |
| **04. TLS / API Gateway Proxy** | API Throughput | 893.9 req/s | 898.6 req/s | **909.1 req/s** | 🥇 **FerroOS** (+1.2% vs Debian) |
| *(HTTP/1.1 HMAC Auth, SHA-256)* | Gateway $p_{99}$ Latency | 6.40 ms | 10.94 ms | **5.37 ms** | 🥇 **FerroOS** (1.03 ms lower) |
| **05. Cloud Object Storage (S3)** | Aggregate Bandwidth | 2,304.3 MiB/s | 2,131.7 MiB/s | **2,518.1 MiB/s** | 🥇 **FerroOS** (+9.3% vs Ubuntu) |
| *(Streaming 64MB Blobs, SHA-256)* | Transfer Duration | 0.28 s | 0.30 s | **0.25 s** | 🥇 **FerroOS** |
| **06. Event Streaming Ingestion** | Ingestion Rate | 6,728,691.5 msg/s | **6,860,994.0 msg/s** | 6,355,080.9 msg/s | 🥇 **Debian 12** (+8.0% vs Ferro) |
| *(Append-Only Batch Log)* | Duration | 0.03 s | 0.03 s | 0.03 s | **Tie** |
| **07. Search Engine & Analytics** | Query Rate (QPS) | 62.4 QPS | 19.9 QPS | **162.2 QPS** | 🥇 **FerroOS** *(Custom SQLite)* |
| *(FTS5 BM25 Inverted Index)* | Index Rate (docs/s) | 316,207.7 docs/s | 255,906.1 docs/s | **337,729.7 docs/s** | 🥇 **FerroOS** (+6.8% vs Ubuntu) |
| **08. Git & CI/CD Build Runner** | 500 Subshell Spawns | **141.2 ms** | 149.6 ms | 214.9 ms | 🥇 **Ubuntu 24.04** (34.3% faster) |
| *(Process Storm, GCC -O3 Build)* | Parallel C Build Time | **0.37 s** | **0.37 s** | **0.37 s** | **Tie** |
| **09. Media Processing Worker** | Frame Throughput | 3.1 FPS | **3.9 FPS** | **3.9 FPS** | 🥇 **Debian 12 & FerroOS** |
| *(1080p Image Filter Loops)* | Total Duration | 117.68 s | **91.61 s** | 92.12 s | 🥇 **Debian 12** |
| **10. Vector Database & AI** | Search Rate (QPS) | 9.5 QPS | **10.5 QPS** | 10.4 QPS | 🥇 **Debian 12** |
| *(Cosine Similarity on 20k Embeddings)*| Search $p_{99}$ Latency | 3,035.97 ms | **2,388.67 ms** | 2,662.70 ms | 🥇 **Debian 12** (10.3% lower tail) |
| **11. Time-Series Telemetry** | Ingestion Rate | 1,834,660.6 pts/s | 1,894,592.7 pts/s | **1,897,108.6 pts/s** | **Tie** (< 0.2% variance) |
| *(High-Cardinality zlib Comp.)* | Compression Ratio | **4.97x** | **4.97x** | **4.97x** | **Tie** |
| **12. Multi-Tenant Chaos** | Combined Ops/sec | **3,884,175.2 ops/s** | 3,485,238.2 ops/s | 3,547,425.0 ops/s | 🥇 **Ubuntu 24.04** (+9.5% vs Ferro) |
| *(Database+Cache+API+Mail)* | Cold-Boot Spawn | **0.7 ms** | **0.7 ms** | 0.8 ms | **Tie** |
| | Workload Survival | **100.0%** | **100.0%** | **100.0%** | **Tie** (0 crashes) |

### 3.3 Scorecard by Category Wins
* **Debian 12 Bookworm**: **6 Wins** (S01 Read TPS, S01 Write TPS, S03 Cache Ops, S06 Stream Ingestion, S09 Media Time, S10 Vector Search).
* **Ubuntu 24.04 LTS**: **4 Wins** (S01 Tail Latency, S03 Fork Latency, S08 Subshell Spawns, S12 Combined Chaos Ops).
* **FerroOS Server v2.0**: **3 Wins** (S04 API Gateway Tail, S05 S3 Bandwidth, S07 FTS5 Search Throughput).

---

## 🗄️ 4. Container Resource Footprint & Memory Analysis

### 4.1 Idle Memory Baseline (`sleep 30`)
Measured via `docker stats --no-stream` across minimal running containers:

| Container Image | Operating System | Base Image | Idle Memory Usage |
| :--- | :--- | :--- | :---: |
| `bench-ubuntu:latest` | Ubuntu 24.04 LTS | `ubuntu:24.04` | **428 KiB** (0.42 MB) |
| `bench-debian:latest` | Debian 12 Bookworm | `debian:12-slim` | **440 KiB** (0.43 MB) |
| `ferro-os-server:latest` | FerroOS Server v2.0 | `debian:bookworm-slim` | **632 KiB** (0.62 MB) |

> [!NOTE]
> Standard Ubuntu and Debian containers use slightly less base RAM than FerroOS because FerroOS forces `/usr/lib/.../libmimalloc.so.2` and `/usr/lib/libferro_io.so` into every process address space via `/etc/ld.so.preload`, adding allocation arena overhead to even simple utilities like `sleep`.

### 4.2 Active Production Microservices Footprint
When running all 4 FerroOS background daemons inside `ferro-os-server:latest`:
1. `ferro-server-suite.py` (Telemetry on Port 8080 & KV Store on Port 8081)
2. `ferro-core serve` (Pure-Rust Web Server on Port 8088)
3. `ferro-core dns-cache` (Rust Shared-Memory DNS on Port 5353)

```
CONTAINER ID   NAME           CPU %     MEM USAGE / LIMIT   MEM %     PIDS
d61d0ecc5ba2   ferro-server   0.03%     16.29MiB / 2GiB     0.80%     9
```
* **Verified**: All 4 microservices idle cleanly at **16.29 MiB RAM**, well below the documented 30 MB ceiling.

---

## 🔍 5. Audit of Novel Scenarios & Enterprise Qualification Scripts

### 5.1 Novel Cloud Server Scenarios ([`tools/test_new_scenarios.py`](file:///home/tarun-kumar/Desktop/sample%20os%20/tools/test_new_scenarios.py))
Running `test_new_scenarios.py` executes 10 Python routines:
- **Scenario 019 (Linux OOM Killer Priority Inversion)**:
  Does not trigger kernel memory pressure or invoke `/proc/sys/vm/panic_on_oom`.
  Instead, lines 303–320 calculate a theoretical badness formula:
  ```python
  score_db_standard = (350.0 / 2048.0) * 1000.0  # 170.9 -> "CRITICAL DATABASE (CATASTROPHIC)"
  score_db_ferro = max(0.0, ((350.0 / 2048.0) * 1000.0) - 1000.0)  # 0.0 -> "PROTECTED DB"
  ```
- **Scenario 012 (Cold Boot Ready)**:
  Measures `subprocess.run("echo 'BOOT_PROBE'")` execution time rather than booting an operating system or init supervisor.

### 5.2 5-OS Master Qualification Suite ([`tools/enterprise_system_security/`](file:///home/tarun-kumar/Desktop/sample%20os%20/tools/enterprise_system_security/))
The README features a table comparing Debian, Alpine, Rocky, Ubuntu, and FerroOS across a "5-Minute Sustained Production Enterprise Benchmark (Postgres 17 + Valkey 8.0 + Envoy)" and a "96.7% CIS Level 2 Hardening Score".
- **Source Inspection**:
  In [`workload_refresh_verifier.py#L24-L100`](file:///home/tarun-kumar/Desktop/sample%20os%20/tools/enterprise_system_security/workload_refresh_verifier.py#L24-L100):
  ```python
  if candidate_id == "ferro":
      sustained = {
          "total_requests": 348920,
          "sustained_req_sec": 1163.1,
          "cache_read_p50_ms": 1.85, ...
      }
  elif candidate_id == "ubuntu24":
      sustained = {
          "total_requests": 316106, ...
      }
  ```
  The benchmark numbers are **hardcoded constants**. Neither PostgreSQL 17, Valkey 8.0, nor Envoy are deployed.
- In [`system_performance_verifier.py#L115-L149`](file:///home/tarun-kumar/Desktop/sample%20os%20/tools/enterprise_system_security/system_performance_verifier.py#L115-L149), the script measures the host's actual `os.getpid()` syscall latency and UNIX socket IPC latency, and then multiplies them:
  - For FerroOS: `syscall_lat * 0.85`, `ipc_lat * 0.72`
  - For Ubuntu: `syscall_lat * 1.00`, `ipc_lat * 1.00`
  - For Debian: `syscall_lat * 1.01`, `ipc_lat * 1.02`

---

## 🎯 6. Final Assessment & Recommendations

| Evaluation Dimension | Rating | Technical Summary |
| :--- | :---: | :--- |
| **Operating System Authenticity** | ⚠️ **Misleading** | Not a standalone OS or custom kernel; it is a Debian 12 Bookworm container with custom Rust CLI tools. |
| **Documented Claims vs Reality** | ❌ **High Divergence** | Claims of `io_uring` POSIX acceleration, eBPF schedulers, 313µs 1,000-VU droplet handling, and Postgres/Valkey sweeps are unbacked by actual code or real runs. |
| **Real-World Server Performance** | 🟢 **Standard Linux** | Performs identically to standard Debian 12 and Ubuntu 24.04 on identical hardware. |
| **Lightweight Service Footprint** | ✅ **Verified** | The Rust HTTP server (`ferro-core serve`) and Python microservices idle under **17 MB RAM**. |
| **Custom SQLite Optimization** | ✅ **Verified** | The custom compiled SQLite engine (`tools/sqlite/`) with lookaside memory buffers and `DEFAULT_MEMSTATUS=0` delivers 2.6x higher FTS5 search throughput over stock Debian. |

### Technical Recommendation
If evaluating FerroOS for production infrastructure:
1. Treat it as a **specialized container image / userspace distribution built on Debian 12**, not as an alternative OS kernel to Linux.
2. Incorporate the **custom SQLite compilation flags** and **mimalloc preload** into standard Debian or Ubuntu container base images if you need memory fragmentation resistance or faster SQLite index queries.
3. Do not rely on claimed sub-millisecond latencies under high concurrency without introducing a true asynchronous event loop (e.g., Actix-Web, Axum, or Nginx) in place of the multi-threaded Python server.
