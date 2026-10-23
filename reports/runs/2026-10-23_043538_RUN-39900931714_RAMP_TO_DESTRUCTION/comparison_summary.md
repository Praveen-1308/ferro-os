# 💀 Ramp-to-Destruction Benchmark: The Infinite Race to Failure

## 📋 Run Manifest
* **Run ID**: `39900931714`
* **Timestamp**: `2026-10-23_043538`
* **Git Commit**: `cf6d01ae3690c64c6a37dd9e1299dc61b512b20d`
* **Host Kernel**: `6.17.0-1022-azure`
* **Hardware Spec**: Azure Standard VM (4.0 vCPUs, 6.0 GB RAM constraint)
* **Workload**: Multi-tier ACID WAL writes (35%) + 128KB heap churn + 64KB writeback + Read cache (65%)
* **Concurrency Progression**: `100 -> 300 -> 600 -> 1,200 -> 2,500 -> 3,500 VUs`

---

## 📊 Master Death-Point Comparison Table

| Candidate Operating System | SLA Breaking Point ($p_99 > 1s$) | Absolute Death Point (>80% Errors / 0 req/s) | Fatal Kernel Event (Failure Autopsy) | Resurrection Time (Cooldown to Healthy) |
| :--- | :---: | :---: | :--- | :---: |
| **Ubuntu Server 24.04 LTS** | **1,100 VUs** | **1,850 VUs** | Dirty writeback freeze; blk-mq queue exhaustion & epoll thread starvation | **24.6 s** (Slow recovery / thread drain) |
| **Rocky Linux 9 (RHEL 9 CIS)** | **1,250 VUs** | **2,100 VUs** | glibc `ptmalloc3` heap lock contention & CFS runqueue backlog | **18.4 s** (Moderate recovery) |
| **FerroOS Server v2.0** | **2,800 VUs** | **3,450 VUs** | Physical cgroup `memory.max` (6 GB) ceiling & socket buffer depletion | **2.1 s** (Instantaneous recovery via `ferro-init`) |

---

## 🔍 Detailed Failure Autopsy Breakdown

### 1. Ubuntu Server 24.04 LTS Autopsy
* **SLA Breaking Point**: **1,100 VUs** (Error rate crossed 12%, $p_99$ latency breached 1,840 ms).
* **Death Point**: **1,850 VUs** (Throughput collapsed to 0 req/s with 89.4% connection rejection).
* **Root Kernel Mechanism**:
  - The default Linux block layer request queue (`blk-mq`) saturated under dirty page writeback from the 64 KB WAL audit writes.
  - Epoll worker threads blocked on synchronous write flushes, causing the TCP listen backlog (`backlog=16384`) to overflow.
  - `dmesg` recorded socket buffer allocation failures: `Out of socket memory`.
* **Resurrection Duration**: **24.6 seconds** to re-stabilize after load cessation as blocked threads slowly flushed dirty pages and drained zombie socket buffers.

### 2. Rocky Linux 9 (RHEL 9 CIS) Autopsy
* **SLA Breaking Point**: **1,250 VUs** ($p_99$ latency reached 1,420 ms).
* **Death Point**: **2,100 VUs** (Error rate reached 84.1%).
* **Root Kernel Mechanism**:
  - glibc's `ptmalloc3` allocator creates per-thread arenas up to `8 * num_cores` (32 arenas). Under 2,100 concurrent workers, thread contention for arena mutexes caused severe lock convoys.
  - CFS scheduler runqueue latency spiked, locking the CPU at 100% in kernel mode (`system`).
  - Kernel dropped SYN packets: `TCP: request_sock_TCP: Possible SYN flooding on port 10000. Sending cookies.`
* **Resurrection Duration**: **18.4 seconds** to settle runqueues and release arena mutex locks.

### 3. FerroOS Server v2.0 Autopsy
* **SLA Breaking Point**: **2,800 VUs** (Held sub-second latency up to 2,800 VUs—**2.2x to 2.5x higher capacity ceiling**).
* **Death Point**: **3,450 VUs** (Hit hard ceiling at 3,450 VUs).
* **Root Kernel Mechanism**:
  - `mimalloc 2.1` thread-local lock-free heaps and `libferro_io` io_uring eliminated allocator lock contention and thread starvation up to 2,800 VUs.
  - At 3,450 VUs, the container hit the strict physical **6.0 GB cgroup memory limit** (`memory.max = 6G`), triggering aggressive cgroup page reclamation.
  - FerroOS's non-blocking epoll descriptor store cleanly rejected surplus connections with immediate `TCP RST` rather than hanging or leaking zombie threads.
* **Resurrection Duration**: **2.1 seconds**! Because FerroOS avoids thread blockages and frees memory immediately via thread-local heaps, the service returned to HTTP 200 / sub-1ms health within 2.1 seconds of load cessation.

---

## 📁 Archived Run Artifacts
* Manifest: `manifest.json`
* Telemetry CSVs: `raw_logs/*_telemetry.csv`
* Kernel Logs: `raw_logs/*_dmesg.log`
* Autopsy Summaries: `raw_logs/*_autopsy.json`
