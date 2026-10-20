# Contributing to FerroOS 🦀⚡

Thank you for your interest in contributing to FerroOS! Whether you are fixing bugs, optimizing system calls, adding applets, or writing documentation, your help is welcome.

---

## 1. Core Architectural Principles

When contributing to FerroOS, keep these three foundational rules in mind:

1. **Zero Mock Testing**: We do not use mock sockets, mock filesystems, or fake timers. All tests must be end-to-end, empirical tests asserting real POSIX syscalls, real network sockets, and real files.
2. **Thermal & Memory Discipline**: Never assume infinite memory or CPU. All test suites and build containers should run reliably under a **6 GB RAM ceiling** to avoid thermal throttling and memory thrashing.
3. **Memory Safety & Raw Speed**: Userspace logic is written in modern Rust with minimal dependencies. I/O acceleration shims (`libferro_io.so`) must remain strictly async-signal-safe and preserve standard libc semantics.

---

## 2. Development Setup

### Prerequisites
* **Rust**: `1.80+` (via `rustup`)
* **Python**: `3.10+` (for running empirical E2E suites)
* **Docker**: (optional, for testing containerized server & desktop images)
* **QEMU**: (optional, for testing full OS boot)

### Getting the Code
```bash
git clone https://github.com/Praveen-1308/ferro-os.git
cd ferro-os
```

### Building the Workspace
```bash
cargo build --workspace
```

### Running Tests
```bash
# Unit tests
cargo test --workspace

# Formatting check
cargo fmt --check

# Clippy linter
cargo clippy --workspace
```

---

## 3. Running Empirical Test Suites

FerroOS maintains specialized real-world test scripts in the [`tools/`](tools/) directory:

```bash
# 1. 12-Scenario Real-World File I/O Matrix
python3 tools/test_e2e_all_file_scenarios.py

# 2. 12-Scenario Multi-Architecture & Secure Package Keeper Suite
python3 tools/test_e2e_rpk_multiarch_secure.py

# 3. Crash-Only & Zero-Downtime Socket Handover Test
python3 tools/test_e2e_fdstore_crash_recovery.py

# 4. Local Shared-Memory DNS Caching Resolver Benchmark
python3 tools/test_e2e_dns_cache.py
```

---

## 4. Submitting a Pull Request

1. Create a descriptive branch from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```
2. Commit your changes with conventional commit messages (`feat: ...`, `fix: ...`, `perf: ...`, `docs: ...`).
3. Ensure formatting is clean (`cargo fmt`).
4. Push your branch and open a Pull Request using the standard PR template.
5. GitHub Actions will automatically run the test suite and report status.
