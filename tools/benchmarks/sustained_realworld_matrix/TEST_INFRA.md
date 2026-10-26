# Sustained Real-World Benchmark Matrix — Test Infrastructure Specification (TEST_INFRA.md)

## 1. Test Philosophy & Methodology

The Sustained Real-World Empirical Benchmark Matrix test suite implements an **opaque-box, requirement-driven testing methodology**.
The test suite derives strictly from the project requirements, architecture specifications, interface contracts, and mathematical invariants defined in:
- `PROJECT.md`
- `ORIGINAL_REQUEST.md`
- `prompt_draft.md`

### 1.1 Core Principles
1. **Opaque-Box Independence**: Tests evaluate system behavior, interface contracts, mathematical formulas, and data invariants through public boundaries and observable outputs. Tests do not depend on internal private state or ephemeral implementation details.
2. **0% Synthetic / 0% Mock Verification**: Real datasets (`enterprise_seed.db`), genuine binary image buffers, authentic cryptographic signatures (HMAC-SHA256, JWTs), and strict elimination of mock sleeps or synthetic math loops.
3. **Progressive Testability**: Every test tier is isolated, deterministic, and self-contained. Tests set up their own state, run in parallel or sequence, and clean up after themselves.
4. **Authoritative Expected Output Derivation**:
   - Placement bias variance calculation: $\Delta = \frac{|M_A - M_B|}{\frac{1}{2}(M_A + M_B)} \times 100\% < 2.5\%$.
   - Host headroom preservation: $\text{Free RAM} \ge 6.0\text{ GB}$ nominal, emergency abort triggered if $\text{Free RAM} < 4.5\text{ GB}$, and host CPU idle $\ge 20.0\%$.
   - 3-Container topology limits: Slot A (2 vCPUs, 4GB RAM), Slot B (2 vCPUs, 4GB RAM), Slot C (1 vCPU, 2GB RAM); total $\le 5.0\text{ vCPUs}$ and $\le 10.0\text{ GB RAM}$.
   - 6-Stage 300s stress ladder: Phase 1 (0–60s), Phase 2 (60–120s), Phase 3 (120–180s), Phase 4 (180–240s), Phase 5 (240–280s), Phase 6 (280–300s).

### 1.2 Formal Test Techniques
- **Category-Partition Testing**: Input spaces for OS targets, scenario catalogs, payload types, and telemetry metrics are systematically partitioned into disjoint equivalence classes.
- **Boundary Value Analysis (BVA)**: Edge cases, zero/negative values, resource ceilings (4GB memory limit, 10k FDs, 5 vCPUs total), and variance thresholds (2.49% vs 2.50% vs 2.51%) are comprehensively probed.
- **Combinatorial Pairwise Testing**: Multi-feature interactions (e.g., slot swapping + chaos injection, dirty-page flushing + rate limiting) are tested to catch cascading faults.
- **Workload Testing (Tier 4)**: End-to-end execution of complete multi-minute enterprise benchmark runs across real web, database, media, queueing, and fault scenarios.

---

## 2. Feature Inventory to Test Tier Mapping

Every feature from `PROJECT.md` (Features 1–27) is enumerated and explicitly mapped to the four test tiers:

| # | Feature Name | Description | Tier 1 (Isolated) | Tier 2 (Boundaries) | Tier 3 (Pairwise) | Tier 4 (Workloads) |
|---|--------------|-------------|-------------------|---------------------|-------------------|--------------------|
| 1 | Target OS Matrix Verification | Verify and standardize base images for all 7 targets (FerroOS, Ubuntu 24.04, Debian 12, Rocky Linux 9, AlmaLinux 9, Alpine 3.20, Amazon Linux 2023) | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-07) |
| 2 | Alpine 3.20 Image Alignment | Ensure `bench-alpine` is strictly built from `alpine:3.20` (`musl 1.2.5`) rather than `alpine:latest` | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-07) |
| 3 | FerroOS Bash Invocation Safety | Ensure benchmark runner inside FerroOS invokes `/usr/bin/bash` or `python3` directly, avoiding applet shell loops | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-01) |
| 4 | 3-Container Topology Orchestration | Slot A (2 vCPU/4 GB), Slot B (2 vCPU/4 GB), Slot C (1 vCPU/2 GB) bounded by Docker limits; total 5 vCPU / 10 GB RAM | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-10) |
| 5 | Docker Bridge Network Isolation | Create `realworld_matrix_net` (`172.30.0.0/16`) for container-to-container traffic | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-10) |
| 6 | Host Headroom Watchdog Daemon | macOS background monitor polling `vm_stat` and `top`, enforcing $\ge$ 5 cores and $\ge$ 6 GB RAM with 3-tier escalation | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-08) |
| 7 | Shell & Process Pipefail Enforcement | `set -eo pipefail` and unmasked exit code preservation (0, 1, 127, 137, 139) | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-05) |
| 8 | Web & Microservices Scenarios (15) | SCEN-WEB-01 through SCEN-WEB-15 (FastAPI, Express, Gin, Axum, Nginx TLS, GraphQL, Django, HTTP/2, gRPC, SSE, WebSockets, Circuit Breakers) | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-01) |
| 9 | Databases & State Engines Scenarios (12) | SCEN-DB-01 through SCEN-DB-12 (Postgres TPC-B, SQLite WAL, Redis pipelining, Redis BGSAVE COW, Valkey, PgBouncer, FTS5 BM25, Deadlocks, MVCC) | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-02) |
| 10 | High-Churn I/O & Media Scenarios (10) | SCEN-IO-01 through SCEN-IO-10 (Multipart uploads, sendfile zero-copy, MinIO S3, Maildir inode churn, fdatasync bursts, FIO direct I/O, libvips SIMD, mmap) | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-03) |
| 11 | Queueing, Telemetry & Streaming Scenarios (10) | SCEN-Q-01 through SCEN-Q-10 (RabbitMQ AMQP, NATS core pub/sub, ZeroMQ PUSH/PULL, Prometheus 10k scrapes, Vector log ingestion, OTel spans, StatsD UDP) | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-04) |
| 12 | Incident Radar & Fault Injection Scenarios (10) | SCEN-FLT-01 through SCEN-FLT-10 (TIME_WAIT exhaustion, memory leaks, unclosed FDs, SIGKILL recovery, zombie reap, slowloris, zero-window, packet corruption) | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-05) |
| 13 | Deadzone & Hardware Extremes Scenarios (8) | SCEN-DZN-01 through SCEN-DZN-08 (Cgroup OOM 4GB limit, 10k concurrent FDs, hackbench context storm, epoll queue saturation, io.max throttle, fork bomb pids.max) | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-06) |
| 14 | 0% Synthetic Payload Engine | Strict elimination of mock sleeps and synthetic math loops; real datasets (`enterprise_seed.db`, binary images, HMAC signatures, JWTs) | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-03) |
| 15 | Container Slot C Generator Orchestration | wrk2, k6, redis-benchmark, pgbench, and custom chaos injection drivers running in Slot C | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-10) |
| 16 | 5-Minute Sustained Stress Ladder Engine | 300-second 6-stage operational progression (Baseline, Healthy, High Concurrency, Choking, Fault Injection, Deadzone) | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-01) |
| 17 | Symmetric Crossover Slot-Swapping Engine | Automated forward run, cache flush, swapped run, and relative variance calculation | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-09) |
| 18 | Placement Bias Variance Gate (< 2.5%) | Verification that $\max(\Delta_X, \Delta_Y) < 2.5\%$ for throughput, p95 latency, and memory RSS across slots | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-09) |
| 19 | Second-by-Second JSON Telemetry Pipeline | 300 records per run persisted to `tools/reports/sustained_realworld_multi_os_matrix.json` with cgroup v2 & socket telemetry | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-10) |
| 20 | Latency Distribution CDF Visualization | Dual-subplot logarithmic CDF and HDR percentile curves (p50 to p99.99) across 7 OS targets | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-10) |
| 21 | Throughput Timeline Boxplots Visualization | Side-by-side boxplots per phase tracking throughput stability and degradation | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-10) |
| 22 | Memory RSS Stability Area Visualization | Stacked area plot tracking RSS and dirty-page flush pressure | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-10) |
| 23 | 6-Spoke Radar Resilience Visualization | Spider radar chart comparing OS resilience across all 6 stress ladder phases | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-10) |
| 24 | Crossover Variance Bar Visualization | Visual proof of slot independence (< 2.5% variance) | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-10) |
| 25 | Individual OS Dossiers & Scorecard | In-depth technical dossiers for all 7 targets and 4-tier color-coded business qualification ratings | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-07) |
| 26 | Final Milestone: 100% E2E Test Suite Pass | Phase 1: Pass 100% of requirement-driven E2E tests (Tiers 1–4) generated by E2E Testing Track | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-10) |
| 27 | Final Milestone: Adversarial Hardening (Tier 5) | Phase 2: White-box adversarial probing, slot bias audit, and integrity verification | Yes (>=5) | Yes (>=5) | Yes | Yes (WK-09) |

---

## 3. Test Architecture & Runner Invocation

### 3.1 Test Directory Structure
```
tools/benchmarks/sustained_realworld_matrix/
├── TEST_INFRA.md
├── TEST_READY.md
└── tests/
    ├── __init__.py
    ├── test_harness.py                          # Common contracts, schemas, mathematical validators
    ├── tier1_feature_tests/                     # Isolated feature verification (>= 135 tests)
    │   ├── __init__.py
    │   ├── test_f01_to_f05_topology_and_os.py
    │   ├── test_f06_to_f07_host_safeguards.py
    │   ├── test_f08_to_f13_scenarios_catalog.py
    │   ├── test_f14_to_f15_payloads_and_slot_c.py
    │   ├── test_f16_to_f18_ladder_and_crossover.py
    │   ├── test_f19_to_f25_telemetry_charts_scorecard.py
    │   └── test_f26_to_f27_e2e_and_hardening.py
    ├── tier2_boundary_tests/                    # Boundary & limit verification (>= 135 tests)
    │   ├── __init__.py
    │   ├── test_b01_to_b05_topology_boundaries.py
    │   ├── test_b06_to_b07_safeguard_boundaries.py
    │   ├── test_b08_to_b13_scenario_boundaries.py
    │   ├── test_b14_to_b15_payload_boundaries.py
    │   ├── test_b16_to_b18_ladder_variance_boundaries.py
    │   ├── test_b19_to_b25_telemetry_reporting_boundaries.py
    │   └── test_b26_to_b27_hardening_boundaries.py
    ├── tier3_pairwise_tests/                    # Combinatorial pairwise interaction tests (>= 15 tests)
    │   ├── __init__.py
    │   └── test_pairwise_interactions.py
    ├── tier4_application_tests/                 # Full workload end-to-end tests (>= 10 tests)
    │   ├── __init__.py
    │   └── test_workload_e2e_scenarios.py
    ├── run_e2e_tests.py                         # Master Python test runner
    └── run_e2e_tests.sh                         # Shell wrapper with strict pipefail
```

### 3.2 Test Runner Invocation Commands
The test suite can be run via:
```bash
# Python direct invocation
python3 tools/benchmarks/sustained_realworld_matrix/tests/run_e2e_tests.py

# Or shell invocation with strict pipefail
bash tools/benchmarks/sustained_realworld_matrix/tests/run_e2e_tests.sh
```

Individual tiers can be invoked selectively:
```bash
python3 tools/benchmarks/sustained_realworld_matrix/tests/run_e2e_tests.py --tier 1
python3 tools/benchmarks/sustained_realworld_matrix/tests/run_e2e_tests.py --tier 2
python3 tools/benchmarks/sustained_realworld_matrix/tests/run_e2e_tests.py --tier 3
python3 tools/benchmarks/sustained_realworld_matrix/tests/run_e2e_tests.py --tier 4
```

### 3.3 Pass/Fail Semantics & Exit Codes
- Exit code `0`: 100% of discovered tests passed without error or failure.
- Exit code `1`: One or more tests failed or threw an unexpected exception.
- Standard POSIX error preservation: Unmasked signals (127 for missing binary, 137 for SIGKILL/OOM, 139 for SIGSEGV) are preserved and never suppressed.

---

## 4. Real-World Application Scenarios (Tier 4)

Tier 4 tests model end-to-end operational workflows:
1. **WK-01**: Web & Microservices Multi-Stage Ladder (FastAPI + Axum + Nginx across 300s ladder).
2. **WK-02**: Enterprise Databases & State Engine Ladder (TPC-B + SQLite WAL + Redis pipeline under memory pressure).
3. **WK-03**: High-Churn I/O & Real Media Ingestion (Multipart uploads, 1–25 MB binary chunks, sendfile zero-copy).
4. **WK-04**: Queueing, Telemetry & Streaming Engine (RabbitMQ AMQP + Vector log ingestion + Prometheus 10k scrapes/s).
5. **WK-05**: Incident Radar & Engineering Fault Recovery (SIGKILL worker crash, TIME_WAIT saturation, socket unlinking).
6. **WK-06**: Deadzone & Hardware Ceiling Limits (4GB cgroup ceiling, 10,000 FDs, epoll saturation).
7. **WK-07**: 7-Target Multi-OS Head-to-Head Comparative Run with Business Scorecard Generation.
8. **WK-08**: Host Headroom Preservation Under Sustained Hostile Contention.
9. **WK-09**: Symmetric Crossover Placement Bias Elimination ($\Delta < 2.5\%$).
10. **WK-10**: Complete End-to-End Benchmark Lifecycle (Topology -> Watchdog -> 6-Stage Ladder -> Telemetry -> Figures -> Report).

---

## 5. Coverage Thresholds & Success Criteria

- **Tier 1 (Isolated Features)**: $\ge 135$ test cases ($\ge 5$ tests per feature for all 27 features).
- **Tier 2 (Boundary Conditions)**: $\ge 135$ test cases ($\ge 5$ tests per feature for all 27 features).
- **Tier 3 (Pairwise Combinations)**: $\ge 15$ test cases.
- **Tier 4 (Application Workloads)**: $\ge 10$ test cases.
- **Total Test Suite Target**: $\ge 295$ automated test cases.
- **Execution Pass Rate**: 100% pass across all tiers.
