# Enterprise Cloud Benchmark Scorecard: RHEL 9 vs Ubuntu 24.04 vs Debian 12 vs FerroOS

## 📋 Run Manifest
* **Run ID**: `39853128630`
* **Timestamp**: `2026-10-22_210022`
* **Git Commit**: `e90dd7bff349ca4307ceb7bdde9b4e148a88350e`
* **Host Kernel**: `6.17.0-1022-azure`
* **Hardware Profile**: 4.0 vCPUs, 6.0 GB RAM, `ulimit -n 65536`
* **Connection Tracking**: `nf_conntrack_max = 1048576`

---

## 📊 Master Side-by-Side Comparison Scorecard

| Test Suite & Metric Category | Rocky Linux 9 (RHEL 9) | Ubuntu Server 24.04 | Debian 12 Bookworm | FerroOS Server v2.0 |
| :--- | :---: | :---: | :---: | :---: |
| **Test 1: Upstream Qualification** | | | | |
| • `fio` 4KB Direct Random Write IOPS | 57,400.0 | 60,700.0 | 60,600.0 | **60,200.0** |
| • `fio` Storage Bandwidth (MiB/s) | 224.0 | 237.0 | 237.0 | **235.0** |
| • `fio` Tail Latency $p_{99}$ (ms) | 4.832 ms | 6.048 ms | 5.024 ms | **4.896 ms** |
| • `hackbench` 400 Workers Runtime | 1.2 s | 1.264 s | 1.208 s | **1.574 s** |
| • `sysbench` Memory Ops/sec | 3,857,931.7 | 3,974,899.3 | 4,051,037.8 | **3,987,492.8** |
| • `sysbench` Memory Bandwidth | 15070.05 MiB/s | 15526.95 MiB/s | 15824.37 MiB/s | **15576.14 MiB/s** |
| **Test 2: CIS Golden Workload** | | | | |
| • Postgres 17 + Valkey 8.0 Status | ✅ PASSED | ✅ PASSED | ✅ PASSED | ✅ **PASSED** |
| **Test 3: Linux Test Project (LTP)** | | | | |
| • POSIX Syscall Conformance | 100.0% PASS | 100.0% PASS | 100.0% PASS | **100.0% PASS** |

---

## 📁 Archived Raw Telemetry & Logs
All raw logs, standard outputs, and 250ms interval telemetry CSVs are archived in `raw_logs/`:
* Rocky Linux 9 (RHEL 9): `raw_logs/rhel9_fio_stdout.log`, `raw_logs/rhel9_telemetry.csv`
* Ubuntu 24.04 LTS: `raw_logs/ubuntu24_fio_stdout.log`, `raw_logs/ubuntu24_telemetry.csv`
* Debian 12 Bookworm: `raw_logs/debian12_fio_stdout.log`, `raw_logs/debian12_telemetry.csv`
* FerroOS Server v2.0: `raw_logs/ferro_fio_stdout.log`, `raw_logs/ferro_telemetry.csv`
