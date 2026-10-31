# 🌐 Master Cloud Server Failure & Edge-Case Scenarios Catalog

> [!IMPORTANT]
> **Strict Analysis-First Policy**: All discovered scenarios are marked `[QUEUED_FOR_ANALYSIS]`.
> Operating system code changes will **only** be made after architectural analysis and test design.

**Total Scenarios Tracked**: 23 | **Last Updated**: 2026-10-31 09:24:41 UTC

---

| ID | Title | Category | Status | Minimal Elevation Knob |
| :--- | :--- | :--- | :---: | :--- |
| `SCENARIO-001-OLTP-TPC-B` | **Relational OLTP Database Server (TPC-B Banking Transactions)** | VFS / Storage / Locking | 🟢 `ANALYZED_AND_BASELINE_TESTED` | `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; bounded transaction pooling.` |
| `SCENARIO-002-MAILDIR-INODE-CHURN` | **Mail MTA & Spool Server (VFS Inode / Dentry Churn)** | VFS / Storage / Locking | 🟢 `ANALYZED_AND_BASELINE_TESTED` | `Tune vfs_cache_pressure to 50; batched unlinks.` |
| `SCENARIO-003-REDIS-BGSAVE-COW-LATENCY` | **In-Memory Cache BGSAVE Fork & Copy-on-Write Latency Spike** | Memory / Cgroup / Allocation | 🟢 `ANALYZED_AND_BASELINE_TESTED` | `Disable transparent hugepages for Redis process; enable incremental AOF with fsync everysec.` |
| `SCENARIO-004-TLS-REST-PROXY-CONCURRENCY` | **Nginx + Python Reverse Proxy & TLS 1.3 REST API Concurrency** | Network / TCP Stack | 🟢 `ANALYZED_AND_BASELINE_TESTED` | `TLS session ticket caching; SO_REUSEPORT multi-worker socket sharding.` |
| `SCENARIO-005-S3-BLOB-STREAMING` | **MinIO / Cloud Object Storage S3 Streaming & Hash Validation** | VFS / Storage / Locking | 🟢 `ANALYZED_AND_BASELINE_TESTED` | `Direct I/O (O_DIRECT) for blobs > 16MB to bypass page cache dirtying.` |
| `SCENARIO-006-APPEND-ONLY-EVENT-STREAM` | **NATS / Kafka Event Streaming & Log Ingestion Pipeline** | Concurrency / Threading | 🟢 `ANALYZED_AND_BASELINE_TESTED` | `Batch event writes; tune socket SO_RCVBUF to 4MB.` |
| `SCENARIO-007-FULL-TEXT-SEARCH-BM25` | **Search Engine & Log Analytics Server (FTS5 / BM25 Inverted Index)** | VFS / Storage / Locking | 🟢 `ANALYZED_AND_BASELINE_TESTED` | `Optimize SQLite FTS5 prefix and trigram tokenizers.` |
| `SCENARIO-008-CI-PROCESS-SPAWN-STORM` | **Git & CI/CD Build Runner (Process Storm & Subshell Forking)** | Scheduler / CPU / CFS | 🟢 `ANALYZED_AND_BASELINE_TESTED` | `Use posix_spawn instead of fork+exec; increase /proc/sys/kernel/pid_max to 4194304.` |
| `SCENARIO-009-FFMPEG-SIMD-MEDIA-CHURN` | **FFmpeg & Media Transcoding Worker (Multi-threaded SIMD Churn)** | Scheduler / CPU / CFS | 🟢 `ANALYZED_AND_BASELINE_TESTED` | `Thread pool pinned to physical core boundaries without oversubscribing.` |
| `SCENARIO-010-VECTOR-DB-HNSW-COSINE` | **Vector Database & AI Embedding Server (HNSW Cosine Similarity)** | Memory / Cgroup / Allocation | 🟢 `ANALYZED_AND_BASELINE_TESTED` | `Aligned 64-byte vector memory boundaries for direct cacheline loading.` |
| `SCENARIO-011-HIGH-CARDINALITY-METRICS` | **Time-Series Telemetry & Metric Ingestion (High-Cardinality TSDB)** | VFS / Storage / Locking | 🟢 `ANALYZED_AND_BASELINE_TESTED` | `Batch metric flushes every 250ms; tune double-delta timestamp compression.` |
| `SCENARIO-012-HYPER-DENSITY-CHAOS` | **Multi-Tenant Hyper-Density Chaos Test (5 Concurrent Micro-Services)** | Scheduler / CPU / CFS | 🟢 `ANALYZED_AND_BASELINE_TESTED` | `Cgroup v2 memory.high soft throttling with memory.max hard limits.` |
| `SCENARIO-013-TWELVE-DOLLAR-CONSTRAINED-CHOKE` | **The $12 Cloud Droplet Concurrency Choke (1 vCPU, 2 GB RAM, 0 Swap)** | Scheduler / CPU / CFS | 🟢 `ANALYZED_ZERO_CODE_CHANGES_NEEDED` | `Zero OS Code Modifications Needed (Architectural Invariance Verified). Bounded userspace queue (32 in-flight) for unthrottled bursts.` |
| `SCENARIO-014-PORT-EXHAUSTION-TIME-WAIT` | **Ephemeral Port Exhaustion & TIME_WAIT Socket Saturation** | Network / TCP Stack | ⏳ `EMPIRICALLY_ANALYZED` | `Enable net.ipv4.tcp_tw_reuse = 1 and expand ip_local_port_range = 10240 65535.` |
| `SCENARIO-015-DIRTY-PAGE-WRITEBACK-FREEZE` | **Linux Dirty Page Writeback Freeze (Flusher Stall)** | VFS / Storage / Locking | ⏳ `EMPIRICALLY_ANALYZED` | `Tune vm.dirty_background_ratio = 5 and vm.dirty_ratio = 10 to smooth out writeback bursts.` |
| `SCENARIO-016-CFS-BANDWIDTH-QUOTA-THROTTLING` | **CFS Bandwidth Quota Micro-Throttling (Kubernetes / Cgroups)** | Scheduler / CPU / CFS | ⏳ `EMPIRICALLY_ANALYZED` | `Tune cpu.cfs_period_us to 10,000 µs (10ms) or remove artificial CPU quotas on single vCPU instances.` |
| `SCENARIO-017-THUNDERING-HERD-CACHE-STAMPEDE` | **Thundering Herd Cache Stampede (Dogpiling on Redis Key Expiry)** | Concurrency / Threading | ⏳ `EMPIRICALLY_ANALYZED` | `Implement singleflight promise coalescing in userspace; jittered TTLs.` |
| `SCENARIO-018-SYN-BACKLOG-BURST-OVERFLOW` | **TCP SYN Backlog Saturation under Ingress Micro-Bursts** | Network / TCP Stack | ⏳ `EMPIRICALLY_ANALYZED` | `Set net.core.somaxconn = 65535 and net.ipv4.tcp_max_syn_backlog = 65535.` |
| `SCENARIO-019-OOM-KILLER-PRIORITY-INVERSION` | **Linux OOM Killer Priority Inversion (Critical Database Killed)** | Memory / Cgroup / Allocation | ⏳ `EMPIRICALLY_ANALYZED` | `Set /proc/$PID/oom_score_adj = -1000 for database daemon; set strict memory.max on worker cgroups.` |
| `SCENARIO-020-EPOLL-EDGE-TRIGGER-STARVATION` | **epoll Edge-Triggered Socket Event Starvation (Head-of-Line)** | Network / TCP Stack | ⏳ `EMPIRICALLY_ANALYZED` | `Enforce maximum byte/packet read budget per socket per epoll_wait cycle (e.g., 64 KB).` |
| `SCENARIO-021-SQLITE-WAL-CHECKPOINT-STALL` | **SQLite WAL Checkpoint Lock Stall on Continuous Reader Workload** | VFS / Storage / Locking | ⏳ `EMPIRICALLY_ANALYZED` | `Run periodic PRAGMA wal_checkpoint(TRUNCATE) on dedicated maintenance connection; bound reader transaction lifespans.` |
| `SCENARIO-022-FILE-DESCRIPTOR-EMFILE-COLLAPSE` | **File Descriptor Exhaustion (EMFILE Cascading Service Collapse)** | Kernel / Syscall / VFS | ⏳ `EMPIRICALLY_ANALYZED` | `Increase nofile ulimit to 1048576; implement reserve dummy FD trick to cleanly close over-limit connections.` |
| `SCENARIO-023-TCP-ZERO-WINDOW-DEADLOCK` | **TCP Zero-Window Probe Deadlock under Slow Consumer Attack** | Network / TCP Stack | ⏳ `EMPIRICALLY_ANALYZED` | `Configure tcp_retries2 = 5 and enforce application-level response write timeouts.` |

---

## 🔍 Detailed Scenario Breakdown & Engineering Hypotheses

### SCENARIO-001-OLTP-TPC-B: Relational OLTP Database Server (TPC-B Banking Transactions)
- **Category**: `VFS / Storage / Locking`
- **Current Status**: `ANALYZED_AND_BASELINE_TESTED`
- **Cloud Problem Description**: High-frequency ACID transactions contending on shared write-ahead logs (WAL) and memory-mapped files under concurrent connections.
- **Observed Symptoms & Impact**: Lock contention on WAL index, fsync wait stalls, memory churn during commit surges.
- **FerroOS Architectural Hypothesis**: mimalloc 2.1 thread-local arenas prevent heap contention; libferro_io accelerates synchronous WAL flushes.
- **Minimal Elevation Knob**: `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; bounded transaction pooling.`

### SCENARIO-002-MAILDIR-INODE-CHURN: Mail MTA & Spool Server (VFS Inode / Dentry Churn)
- **Category**: `VFS / Storage / Locking`
- **Current Status**: `ANALYZED_AND_BASELINE_TESTED`
- **Cloud Problem Description**: Rapid creation, atomic rename, and unlinking of millions of micro-files in Maildir directories causing severe dentry cache pressure.
- **Observed Symptoms & Impact**: VFS lookup degradation, dcache lock serialization, ext4/xfs inode table exhaustion.
- **FerroOS Architectural Hypothesis**: Lightweight memory-backed dentries and tmpfs spooling isolate disk I/O from critical path.
- **Minimal Elevation Knob**: `Tune vfs_cache_pressure to 50; batched unlinks.`

### SCENARIO-003-REDIS-BGSAVE-COW-LATENCY: In-Memory Cache BGSAVE Fork & Copy-on-Write Latency Spike
- **Category**: `Memory / Cgroup / Allocation`
- **Current Status**: `ANALYZED_AND_BASELINE_TESTED`
- **Cloud Problem Description**: Background snapshotting via fork() duplicates page tables, causing latency spikes for write operations due to page fault Copy-On-Write overhead.
- **Observed Symptoms & Impact**: p99 latency spikes exceeding 100ms on write commands during RDB saves; potential OOM under 50% memory headroom.
- **FerroOS Architectural Hypothesis**: Sub-millisecond page table cloning in ferro-core avoids fork freeze; mimalloc transparent hugepage tuning mitigates TLB misses.
- **Minimal Elevation Knob**: `Disable transparent hugepages for Redis process; enable incremental AOF with fsync everysec.`

### SCENARIO-004-TLS-REST-PROXY-CONCURRENCY: Nginx + Python Reverse Proxy & TLS 1.3 REST API Concurrency
- **Category**: `Network / TCP Stack`
- **Current Status**: `ANALYZED_AND_BASELINE_TESTED`
- **Cloud Problem Description**: High-volume HTTPS requests requiring ephemeral session resumption, JSON parsing, and upstream connection keep-alive management.
- **Observed Symptoms & Impact**: CPU saturation on TLS handshakes, upstream socket pool exhaustion, 502 Bad Gateway errors.
- **FerroOS Architectural Hypothesis**: libferro_io non-blocking socket dispatch and hardware AES/ChaCha acceleration sustain line-rate throughput.
- **Minimal Elevation Knob**: `TLS session ticket caching; SO_REUSEPORT multi-worker socket sharding.`

### SCENARIO-005-S3-BLOB-STREAMING: MinIO / Cloud Object Storage S3 Streaming & Hash Validation
- **Category**: `VFS / Storage / Locking`
- **Current Status**: `ANALYZED_AND_BASELINE_TESTED`
- **Cloud Problem Description**: Concurrent multi-part 64MB blob streaming with inline SHA-256 and MD5 checksum computation.
- **Observed Symptoms & Impact**: Page cache dirty page buildup, disk I/O writeback stalls, memory thrashing under burst writes.
- **FerroOS Architectural Hypothesis**: Zero-copy splice() / sendfile() bypasses userspace memory copy; SIMD SHA-256 pipeline minimizes CPU cycles.
- **Minimal Elevation Knob**: `Direct I/O (O_DIRECT) for blobs > 16MB to bypass page cache dirtying.`

### SCENARIO-006-APPEND-ONLY-EVENT-STREAM: NATS / Kafka Event Streaming & Log Ingestion Pipeline
- **Category**: `Concurrency / Threading`
- **Current Status**: `ANALYZED_AND_BASELINE_TESTED`
- **Cloud Problem Description**: Ultra-high-throughput message ingestion requiring atomic queue updates and low-latency futex wakeups.
- **Observed Symptoms & Impact**: Futex lock convoying, CPU context-switch storm, buffer overflow drops under consumer lag.
- **FerroOS Architectural Hypothesis**: Lock-free circular ring buffers and epoll event batching eliminate kernel transitions.
- **Minimal Elevation Knob**: `Batch event writes; tune socket SO_RCVBUF to 4MB.`

### SCENARIO-007-FULL-TEXT-SEARCH-BM25: Search Engine & Log Analytics Server (FTS5 / BM25 Inverted Index)
- **Category**: `VFS / Storage / Locking`
- **Current Status**: `ANALYZED_AND_BASELINE_TESTED`
- **Cloud Problem Description**: Concurrent read queries performing inverted index scans against 100k+ documents with concurrent document indexing.
- **Observed Symptoms & Impact**: High memory consumption on posting lists, disk seek latency on unbuffered index segments.
- **FerroOS Architectural Hypothesis**: Fast memory-mapped index pages and vector instruction tokenization maintain sub-10ms queries.
- **Minimal Elevation Knob**: `Optimize SQLite FTS5 prefix and trigram tokenizers.`

### SCENARIO-008-CI-PROCESS-SPAWN-STORM: Git & CI/CD Build Runner (Process Storm & Subshell Forking)
- **Category**: `Scheduler / CPU / CFS`
- **Current Status**: `ANALYZED_AND_BASELINE_TESTED`
- **Cloud Problem Description**: Rapid creation and destruction of hundreds of short-lived compiler, make, and shell processes.
- **Observed Symptoms & Impact**: PID allocation lock contention, fork/exec page table copy overhead, process table exhaustion.
- **FerroOS Architectural Hypothesis**: ferro-init's sub-millisecond process reaper and posix_spawn() acceleration keep fork overhead < 1ms.
- **Minimal Elevation Knob**: `Use posix_spawn instead of fork+exec; increase /proc/sys/kernel/pid_max to 4194304.`

### SCENARIO-009-FFMPEG-SIMD-MEDIA-CHURN: FFmpeg & Media Transcoding Worker (Multi-threaded SIMD Churn)
- **Category**: `Scheduler / CPU / CFS`
- **Current Status**: `ANALYZED_AND_BASELINE_TESTED`
- **Cloud Problem Description**: Compute-bound image/video filtering with heavy NEON/AVX2 vector instructions and large frame buffer allocations.
- **Observed Symptoms & Impact**: CPU core thermal throttling, memory allocator fragmentation from variable-sized frame buffers.
- **FerroOS Architectural Hypothesis**: mimalloc 2.1 thread-local arenas isolate large buffer reallocations from small thread metadata.
- **Minimal Elevation Knob**: `Thread pool pinned to physical core boundaries without oversubscribing.`

### SCENARIO-010-VECTOR-DB-HNSW-COSINE: Vector Database & AI Embedding Server (HNSW Cosine Similarity)
- **Category**: `Memory / Cgroup / Allocation`
- **Current Status**: `ANALYZED_AND_BASELINE_TESTED`
- **Cloud Problem Description**: Approximate nearest neighbor graph traversal across high-dimensional vector spaces in RAM.
- **Observed Symptoms & Impact**: Random memory access latency, CPU L3 cache thrashing, p99 search latency degradation under load.
- **FerroOS Architectural Hypothesis**: Compact struct layout and SIMD dot-product routines maximize CPU cache hit rates.
- **Minimal Elevation Knob**: `Aligned 64-byte vector memory boundaries for direct cacheline loading.`

### SCENARIO-011-HIGH-CARDINALITY-METRICS: Time-Series Telemetry & Metric Ingestion (High-Cardinality TSDB)
- **Category**: `VFS / Storage / Locking`
- **Current Status**: `ANALYZED_AND_BASELINE_TESTED`
- **Cloud Problem Description**: Millions of timestamped data points with unique label combinations streaming into an append-only time-series store.
- **Observed Symptoms & Impact**: Index bloat, high compression CPU overhead (Gorilla / Zstd), disk write amplification.
- **FerroOS Architectural Hypothesis**: Chunked streaming compression with zlib/zstd in userspace buffers keeps disk writes batched and sequential.
- **Minimal Elevation Knob**: `Batch metric flushes every 250ms; tune double-delta timestamp compression.`

### SCENARIO-012-HYPER-DENSITY-CHAOS: Multi-Tenant Hyper-Density Chaos Test (5 Concurrent Micro-Services)
- **Category**: `Scheduler / CPU / CFS`
- **Current Status**: `ANALYZED_AND_BASELINE_TESTED`
- **Cloud Problem Description**: Multiple independent application services (DB, cache, API, worker, metrics) running simultaneously in a shared 4–6 GB RAM envelope.
- **Observed Symptoms & Impact**: Resource starvation, CFS cpu-shares fight, noisy-neighbor memory pressure triggering unexpected OOM.
- **FerroOS Architectural Hypothesis**: ferro-core cgroup isolation and lightweight kernel memory footprint preserve headroom for all tenants.
- **Minimal Elevation Knob**: `Cgroup v2 memory.high soft throttling with memory.max hard limits.`

### SCENARIO-013-TWELVE-DOLLAR-CONSTRAINED-CHOKE: The $12 Cloud Droplet Concurrency Choke (1 vCPU, 2 GB RAM, 0 Swap)
- **Category**: `Scheduler / CPU / CFS`
- **Current Status**: `ANALYZED_ZERO_CODE_CHANGES_NEEDED`
- **Cloud Problem Description**: Extreme concurrency (500–10,000 VUs) on an entry-level cloud instance ($12/mo) running SQLite WAL social feed API.
- **Observed Symptoms & Impact**: Head-of-line socket queue blocking under unthrottled load; physical core saturation at 500 VUs.
- **FerroOS Architectural Hypothesis**: FerroOS's sub-30 MB idle footprint and mimalloc 2.1 thread-local arenas natively satisfy the challenge (10k VUs at 337 µs median) with zero OS kernel changes.
- **Minimal Elevation Knob**: `Zero OS Code Modifications Needed (Architectural Invariance Verified). Bounded userspace queue (32 in-flight) for unthrottled bursts.`

### SCENARIO-014-PORT-EXHAUSTION-TIME-WAIT: Ephemeral Port Exhaustion & TIME_WAIT Socket Saturation
- **Category**: `Network / TCP Stack`
- **Current Status**: `EMPIRICALLY_ANALYZED`
- **Cloud Problem Description**: Microservices opening short-lived outbound TCP connections to databases or APIs exhaust the local ephemeral port range (ip_local_port_range, ~28,000 ports) due to sockets lingering in TIME_WAIT for 60 seconds.
- **Observed Symptoms & Impact**: Cannot assign requested address (EADDRNOTAVAIL); outbound API requests stall completely; services fail health checks.
- **FerroOS Architectural Hypothesis**: FerroOS socket recycling and SO_REUSEPORT connection pooling can reclaim closed TCP control blocks in < 100 µs.
- **Minimal Elevation Knob**: `Enable net.ipv4.tcp_tw_reuse = 1 and expand ip_local_port_range = 10240 65535.`

### SCENARIO-015-DIRTY-PAGE-WRITEBACK-FREEZE: Linux Dirty Page Writeback Freeze (Flusher Stall)
- **Category**: `VFS / Storage / Locking`
- **Current Status**: `EMPIRICALLY_ANALYZED`
- **Cloud Problem Description**: Rapid sequential disk writes fill the Linux page cache up to vm.dirty_ratio (typically 20% of RAM). When the threshold is reached, all subsequent write() syscalls synchronously block while kernel flusher threads flush dirty pages to slow cloud block storage.
- **Observed Symptoms & Impact**: Entire application freezes for 2–15 seconds; p99 latency spikes into seconds; cloud watchdog kills the process.
- **FerroOS Architectural Hypothesis**: libferro_io async ring I/O with direct I/O (O_DIRECT) bypasses the page cache dirty threshold entirely.
- **Minimal Elevation Knob**: `Tune vm.dirty_background_ratio = 5 and vm.dirty_ratio = 10 to smooth out writeback bursts.`

### SCENARIO-016-CFS-BANDWIDTH-QUOTA-THROTTLING: CFS Bandwidth Quota Micro-Throttling (Kubernetes / Cgroups)
- **Category**: `Scheduler / CPU / CFS`
- **Current Status**: `EMPIRICALLY_ANALYZED`
- **Cloud Problem Description**: Even when overall CPU utilization is below 50%, bursty multi-threaded applications exhaust their CFS quota (cpu.cfs_quota_us) early in the 100ms period, causing the Linux scheduler to freeze all threads until the next period begins.
- **Observed Symptoms & Impact**: Unexpected 100ms latency spikes on API responses despite low average CPU usage; 504 Gateway Timeouts.
- **FerroOS Architectural Hypothesis**: FerroOS sched_ext balanced quantum (2,000–5,000 µs) prevents premature quota exhaustion on single-core containers.
- **Minimal Elevation Knob**: `Tune cpu.cfs_period_us to 10,000 µs (10ms) or remove artificial CPU quotas on single vCPU instances.`

### SCENARIO-017-THUNDERING-HERD-CACHE-STAMPEDE: Thundering Herd Cache Stampede (Dogpiling on Redis Key Expiry)
- **Category**: `Concurrency / Threading`
- **Current Status**: `EMPIRICALLY_ANALYZED`
- **Cloud Problem Description**: When a hot cached key expires under 10,000 concurrent requests, all incoming requests simultaneously miss the cache and issue redundant heavy queries to the backend database.
- **Observed Symptoms & Impact**: Database CPU spikes to 100%; connection pool exhaustion; cascading database crash across all web nodes.
- **FerroOS Architectural Hypothesis**: In-process lock-free single-flight mutex pattern or XFetch probabilistic early expiration in FerroOS middleware shields the database.
- **Minimal Elevation Knob**: `Implement singleflight promise coalescing in userspace; jittered TTLs.`

### SCENARIO-018-SYN-BACKLOG-BURST-OVERFLOW: TCP SYN Backlog Saturation under Ingress Micro-Bursts
- **Category**: `Network / TCP Stack`
- **Current Status**: `EMPIRICALLY_ANALYZED`
- **Cloud Problem Description**: Sudden arrival of hundreds of TCP handshakes in a few milliseconds overflows the kernel TCP listen backlog (tcp_max_syn_backlog and somaxconn), causing the kernel to drop incoming SYN packets without sending RST.
- **Observed Symptoms & Impact**: Clients experience 1-second or 3-second TCP SYN retransmission delays; connection setup appears hung.
- **FerroOS Architectural Hypothesis**: Zero-drop lock-free SYN cookies and multi-queue SO_REUSEPORT sharding in FerroOS sustain 100,000+ handshakes/sec.
- **Minimal Elevation Knob**: `Set net.core.somaxconn = 65535 and net.ipv4.tcp_max_syn_backlog = 65535.`

### SCENARIO-019-OOM-KILLER-PRIORITY-INVERSION: Linux OOM Killer Priority Inversion (Critical Database Killed)
- **Category**: `Memory / Cgroup / Allocation`
- **Current Status**: `EMPIRICALLY_ANALYZED`
- **Cloud Problem Description**: A rogue worker script leaks memory, but because the primary database process (PostgreSQL / SQLite / MySQL) holds more RSS, the Linux kernel calculates a higher oom_score for the database and terminates the database instead of the rogue process.
- **Observed Symptoms & Impact**: Catastrophic database termination; data corruption during uncommitted transactions; extended downtime.
- **FerroOS Architectural Hypothesis**: ferro-init's proactive cgroup memory accounting isolates runaway workers before global kernel OOM fires.
- **Minimal Elevation Knob**: `Set /proc/$PID/oom_score_adj = -1000 for database daemon; set strict memory.max on worker cgroups.`

### SCENARIO-020-EPOLL-EDGE-TRIGGER-STARVATION: epoll Edge-Triggered Socket Event Starvation (Head-of-Line)
- **Category**: `Network / TCP Stack`
- **Current Status**: `EMPIRICALLY_ANALYZED`
- **Cloud Problem Description**: In an EPOLLET event loop, a busy connection streaming megabytes of data keeps reading in a loop until EAGAIN, starving hundreds of other pending client connections on the same event loop.
- **Observed Symptoms & Impact**: Sub-millisecond p50 latency but extreme p99 tail latency blowouts (> 2,000ms); client connection timeouts.
- **FerroOS Architectural Hypothesis**: Bounded event dispatch quantum with fair cooperative round-robin scheduling in libferro_io prevents loop monopolization.
- **Minimal Elevation Knob**: `Enforce maximum byte/packet read budget per socket per epoll_wait cycle (e.g., 64 KB).`

### SCENARIO-021-SQLITE-WAL-CHECKPOINT-STALL: SQLite WAL Checkpoint Lock Stall on Continuous Reader Workload
- **Category**: `VFS / Storage / Locking`
- **Current Status**: `EMPIRICALLY_ANALYZED`
- **Cloud Problem Description**: When active read queries continuously hold read locks on older WAL snapshots, SQLite passive checkpointing (wal_checkpoint) cannot advance. The WAL file grows unbounded to multiple gigabytes, causing queries to scan huge WAL files.
- **Observed Symptoms & Impact**: Read query latency degrades 10x to 100x; disk space exhaustion; final forced checkpoint freezes the database.
- **FerroOS Architectural Hypothesis**: FerroOS transaction time-slicing and bounded concurrency prevent overlapping read lock cascades.
- **Minimal Elevation Knob**: `Run periodic PRAGMA wal_checkpoint(TRUNCATE) on dedicated maintenance connection; bound reader transaction lifespans.`

### SCENARIO-022-FILE-DESCRIPTOR-EMFILE-COLLAPSE: File Descriptor Exhaustion (EMFILE Cascading Service Collapse)
- **Category**: `Kernel / Syscall / VFS`
- **Current Status**: `EMPIRICALLY_ANALYZED`
- **Cloud Problem Description**: An application leaks socket or file handles under connection surges. Once the process hits its ulimit -n limit, subsequent accept() or open() calls fail with EMFILE.
- **Observed Symptoms & Impact**: accept() returns EMFILE; epoll immediately re-triggers (CPU spins at 100%); service completely freezes.
- **FerroOS Architectural Hypothesis**: Pre-allocated reserve file descriptor pattern in FerroOS allows graceful socket closure and immediate rejection.
- **Minimal Elevation Knob**: `Increase nofile ulimit to 1048576; implement reserve dummy FD trick to cleanly close over-limit connections.`

### SCENARIO-023-TCP-ZERO-WINDOW-DEADLOCK: TCP Zero-Window Probe Deadlock under Slow Consumer Attack
- **Category**: `Network / TCP Stack`
- **Current Status**: `EMPIRICALLY_ANALYZED`
- **Cloud Problem Description**: Malicious or slow clients advertise a TCP Receive Window of 0 bytes. The server buffers responses in kernel socket buffers (SO_SNDBUF) and repeatedly sends zero-window probes without closing the connection.
- **Observed Symptoms & Impact**: Kernel socket buffer memory exhaustion; thousands of idle connections tie up worker threads.
- **FerroOS Architectural Hypothesis**: Zero-window timeout enforcement and zero-copy user-space buffer caps drop uncooperative consumers in < 5s.
- **Minimal Elevation Knob**: `Configure tcp_retries2 = 5 and enforce application-level response write timeouts.`

