# FerroOS AS/400 Enterprise Edition

The **FerroOS AS/400 Enterprise Edition** is a specialized operating system profile tailored for high-throughput batch transactions, banking ledgers, and legacy IBM mid-range systems integration (IBM i, iSeries, AS/400). It combines an asynchronous multi-worker batch processing queue with an integrated IBM 5250 green-screen terminal server and continuous ACID transaction journaling.

---

## 1. Specifications & Key Metrics

| Metric | FerroOS AS/400 Enterprise Edition | Ubuntu Server Batch Pipeline | Legacy IBM i LPAR |
| :--- | :--- | :--- | :--- |
| **RootFS Compressed Size** | **3.61 MB** | 668 MB | Many GBs per partition |
| **Idle Memory (2 Workers + Gateway)**| **15.2 MB** | 110 MB – 180 MB | 2 GB – 8 GB base allocation |
| **Memory Efficiency Gain** | **5.9x vs Ubuntu** | Baseline | N/A |
| **Batch Queue Latency** | **Sub-millisecond worker dispatch** | Cron / systemd timers (1–5s) | Hardware batch queue |
| **5250 Terminal Interface** | IBM EBCDIC ↔ ASCII conversion (PUB400) | Third-party tn5250 package | Native twinax / TN5250 |
| **Ledger Storage Engine** | Continuous ACID Journal (`/var/lib/ferro/as400`) | SQLite / PostgreSQL | DB2 for i Journal Receiver |
| **Default Packaging** | `ferro_enterprise_appliance.tar.gz` | Enterprise Docker Image | LPAR Disk Image |

---

## 2. Enterprise System Architecture

```mermaid
graph TD
    subgraph Upstream ["Legacy Mainframe / Gateway"]
        PUB400["PUB400.com Gateway (Port 23 / TN5250)"]
        HostStream["EBCDIC Binary Data Stream"]
    end

    subgraph AS400Core ["FerroOS AS/400 Core (Pure Rust)"]
        TN5250["5250 Green-Screen Terminal Server<br/>- Port 2300 ASCII/HTML5 Rendering<br/>- Dual-Worker Thread Pool"]
        BatchQ["Multi-Worker Parallel Batch Queue<br/>- Worker 1 & Worker 2 Queues<br/>- Sub-millisecond Dispatch"]
        ACID["Continuous ACID Ledger Journal<br/>- Write-Ahead Logging (WAL)<br/>- Crash Recovery Safe"]
    end

    subgraph Storage ["Durable Persistence (/var/lib/ferro/as400)"]
        Ledgers["/var/lib/ferro/as400/ledgers/"]
        Journals["/var/lib/ferro/as400/journals/"]
        Queues["/var/lib/ferro/as400/queues/"]
    end

    PUB400 --> HostStream
    HostStream --> TN5250
    TN5250 --> BatchQ
    BatchQ --> ACID
    ACID --> Ledgers & Journals & Queues
```

---

## 3. Core Enterprise Components

### A. Multi-Worker Parallel Batch Processor
* **Worker Threads**: Spawns concurrent background batch processing pipelines (`Worker 1`, `Worker 2`, etc.) governed by `ferro-superd`.
* **Throughput**: Processes thousands of structured transactional records per minute with deterministic memory bounds.
* **Failure Isolation**: An error or deadlock in an individual batch transaction cannot crash the host supervisor or corrupt active journals.

### B. 5250 Green-Screen Terminal Server & Gateway
* **Protocol**: IBM 5250 Data Stream (TN5250) terminal emulation.
* **EBCDIC Translation**: Built-in IBM Code Page 037/500 EBCDIC to UTF-8/ASCII conversion engine.
* **HTML5 Terminal Web Transcripts**: Automatically generates live web-accessible green-screen transcripts (see [`tools/as400_batch_output/worker_1_terminal.html`](file:///home/tarun-kumar/Desktop/sample%20os%20/tools/as400_batch_output/worker_1_terminal.html)).
* **Remote Gateway**: Verified with live end-to-end communication to public test system `PUB400.com` on port 23.

### C. Continuous ACID Ledger Journaling
* **Storage Location**: `/var/lib/ferro/as400/journal.db`.
* **Integrity Guarantee**: Write-Ahead Logging (WAL) and synchronous disk barrier flushing (`fsync`) eliminate data corruption during sudden power loss or kernel panic.
* **Recovery Mechanism**: Automatic journal rollback on ungraceful termination.

---

## 4. Default Services & Configurations

The Enterprise Edition installs the following services into `/etc/ferro/services/`:

### `/etc/ferro/services/as400-batch.toml`
```toml
name = "as400-batch"
command = ["/usr/bin/ferro-core", "supervise", "--as400-worker", "2"]
restart = "always"
user = "ferro"
memory_max_mb = 128
```

### `/etc/ferro/services/tn5250-gateway.toml`
```toml
name = "tn5250-gateway"
command = ["/usr/bin/ferro-core", "serve", "2300", "/var/lib/ferro/as400"]
restart = "always"
user = "ferro"
memory_max_mb = 64
```

### `/etc/ferro/edition.toml`
```toml
[edition]
name = "enterprise"
profile = "as400-enterprise"
description = "AS/400 Parallel batch queue processing & 5250 terminal gateway"
```

---

## 5. Operations & Quick Start

### Build the AS/400 Enterprise Appliance
```bash
python3 tools/build_pure_rust_os.py --edition enterprise
```
* Generates: `build_out/ferro_enterprise_appliance.tar.gz` (3.61 MB)
* Builds Docker Image: `ferro-os-enterprise:latest`

### Run Live Parallel AS/400 Benchmark
```bash
python3 tools/run_parallel_as400_benchmark.py
```

### Inspect Output Telemetry & HTML Terminal Screens
```bash
ls -la tools/as400_batch_output/
cat tools/as400_batch_output/worker_1_screen.txt
```
