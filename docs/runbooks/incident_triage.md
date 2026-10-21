# Runbook: Production Triage & Incident Playbook
### *Operational Diagnostic Procedures for Memory Pressure, CPU Soft-Locks, and Socket Exhaustion*

---

## 1. Quick Reference: Incident Escalation Matrix

| Symptom / Alert | Root Subsystem | Immediate Diagnostic Command | Primary Remediation Action |
| :--- | :--- | :--- | :--- |
| **Tail Latency Spikes ($p_{95} > 500\text{ ms}$)** | CPU Scheduler / Runqueue | `ferro-core sched status` | Enable `ferro-core gamemode on` (500µs slice) |
| **`ECONNREFUSED` / Client Drops** | TCP Listen Backlog | `ss -lnt '( sport = :8088 )'` | Enable `SO_REUSEPORT` multi-sharding |
| **`EMFILE (Too many open files)`** | VFS File Descriptor Pool | `cat /proc/sys/fs/file-nr` | `ulimit -n 1048576` + FD Store recovery |
| **Container OOM Killed (Exit 137)** | Heap Fragmentation | `MIMALLOC_SHOW_STATS=1` | Verify `mimalloc 2.1` eager commit release |
| **`database is locked` (SQLite)** | WAL Journal Contention | `ls -lh /tmp/*.db-wal` | `PRAGMA wal_checkpoint(TRUNCATE);` |

---

## 2. Playbook 1: CPU Starvation & Scheduler Soft-Locks

### Symptoms:
* Microservices experience sporadic 50 ms to 200 ms latency spikes despite moderate CPU load.
* Task thread wakeup jitter climbs above 500 µs.

### Step-by-Step Triage:
1. **Inspect Thread Scheduling State**:
   ```bash
   ferro-core ps --sort cpu
   ```
2. **Profile Kernel Preemption Delays**:
   ```bash
   # Trace scheduler off-cpu time
   perf sched record -- sleep 2
   perf sched latency
   ```
3. **Remediation**:
   * Switch the CPU governor to maximum performance and enforce the 500 µs preemption slice:
     ```bash
     ferro-core gamemode on
     ferro-core sched set latency-critical
     ```
   * Pin worker processes to dedicated physical cores:
     ```bash
     taskset -cp 0-1 $(pgrep -f ferro-server)
     ```

---

## 3. Playbook 2: Memory Pressure & OOM Containment

### Symptoms:
* Resident Set Size (RSS) breaches 90% of cgroup limit (`--memory=4g`).
* Kernel kernel page reclaim activity rises in `/proc/vmstat`.

### Step-by-Step Triage:
1. **Inspect Cgroup Memory Limits**:
   ```bash
   cat /sys/fs/cgroup/memory.current
   cat /sys/fs/cgroup/memory.peak
   ```
2. **Inspect Mimalloc Thread-Local Arena Stats**:
   ```bash
   # Run process with mimalloc verbose statistics
   MIMALLOC_SHOW_STATS=1 ferro-core serve 8088 /var/www
   ```
   * *Check for high committed vs reserved ratios or delayed thread-local purge queues.*
3. **Remediation**:
   * Force instantaneous release of cached clean pages:
     ```bash
     echo 3 > /proc/sys/vm/drop_caches
     ```
   * Verify SQLite lookaside memory pools do not exceed 1.2 MB per handle:
     ```sql
     PRAGMA page_count;
     PRAGMA page_size;
     ```

---

## 4. Playbook 3: Socket Exhaustion & TCP Listen Backlog Drops

### Symptoms:
* Clients fail to complete TCP handshakes during burst traffic.
* Sockets report `Connection reset by peer` or `Too many open files`.

### Step-by-Step Triage:
1. **Check Kernel Socket Allocations & Sockets in TIME_WAIT**:
   ```bash
   cat /proc/net/sockstat
   ss -s
   ```
2. **Check Current Process File Descriptor Limits**:
   ```bash
   cat /proc/$(pgrep -f ferro-server)/limits | grep "open files"
   ```
3. **Remediation**:
   * Elevate file limits dynamically in the current shell:
     ```bash
     ulimit -n 1048576
     ```
   * Enable TCP socket recycling and widen kernel backlog:
     ```bash
     sysctl -w net.core.somaxconn=65535
     sysctl -w net.ipv4.tcp_max_syn_backlog=65535
     sysctl -w net.ipv4.tcp_tw_reuse=1
     ```
   * Restart microservice with `SO_REUSEPORT` kernel socket sharding across available CPU cores:
     ```bash
     /usr/local/bin/ferro-core serve 8088 /var/www --shards 4
     ```

---

## 5. Playbook 4: SQLite WAL Journal Stalls & Storage Backpressure

### Symptoms:
* Write operations (`POST /posts/:id/like` or `POST /posts`) fail with:
  `sqlite3.OperationalError: database is locked`
* Database write operations take $> 500\text{ ms}$.

### Step-by-Step Triage:
1. **Inspect SQLite WAL and SHM Sizes**:
   ```bash
   ls -lh /tmp/feed.db*
   ```
   * *If `feed.db-wal` exceeds 100 MB, checkpoints are failing to keep pace with incoming writes.*
2. **Inspect Process Locks on the SQLite File**:
   ```bash
   lsof /tmp/feed.db
   fuser /tmp/feed.db
   ```
3. **Remediation**:
   * Execute an immediate synchronous WAL truncate checkpoint:
     ```bash
     sqlite3 /tmp/feed.db "PRAGMA wal_checkpoint(TRUNCATE);"
     ```
   * Ensure the application initializes database handles with a busy timeout:
     ```sql
     PRAGMA busy_timeout = 5000;
     PRAGMA synchronous = NORMAL;
     ```
   * Enable `libferro_io.so` to route WAL disk flushes through `io_uring` kernel polling ring buffers.
