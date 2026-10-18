# FerroOS 🦀⚡

> **A blazingly fast, lightweight Linux distribution powered by Rust.**  
> *Alpine-like speed (<300ms boot, <30MB RAM) + Debian compatibility (Python 3, pip, glibc ABI).*

[![Build & Verify FerroOS](https://github.com/Praveen-1308/ferro-os/actions/workflows/build-os.yml/badge.svg)](https://github.com/Praveen-1308/ferro-os/actions/workflows/build-os.yml)

---

## 🌟 The Vision

Traditional Linux distributions make you choose between two extremes:
1. **Debian / Ubuntu**: Full software compatibility, runs Python, Node, C-extensions, and pre-compiled wheels out of the box—**but slow boot times (5–15s), systemd bloat, and high idle memory consumption (150MB–300MB)**.
2. **Alpine Linux**: Ultra-fast and lightweight (5MB rootfs, <1s boot)—**but uses `musl libc`, breaking many pre-compiled Python wheels (`numpy`, `torch`, `cryptography`), requiring slow source builds**.

**FerroOS bridges this gap:**
- **100% Rust Userspace**: Replaces heavy C init systems and utilities with modern, memory-safe Rust (`ferro-init` and `ferro-core`).
- **Full glibc / POSIX Compatibility**: Python 3, dynamic shared libraries, and C extensions run without recompilation.
- **Sub-300ms Boot Time**: Zero systemd overhead, streamlined mounts, instant shell.
- **Zero Local Strain**: Automated remote build and headless QEMU testing on GitHub Actions.

---

## 🏗️ Architecture

```
+-------------------------------------------------------------------------+
|                              User Applications                          |
|    - Python 3 & pip packages (numpy, flask, etc.)                       |
|    - Custom Rust / C / Go / Node applications                           |
+-------------------------------------------------------------------------+
|                        FerroOS Userspace (Rust)                         |
|   +--------------------------+   +----------------------------------+   |
|   |  ferro-init (PID 1)      |   |  ferro-core (Multi-Call Binary)  |   |
|   |  - Early mount (/proc...) |   |  - sh, ls, cat, echo, uname...   |   |
|   |  - Zombie reaping        |   |  - poweroff, reboot, clear...    |   |
|   |  - Service supervision   |   |  - Rust memory safety & speed    |   |
|   +--------------------------+   +----------------------------------+   |
|   +-----------------------------------------------------------------+   |
|   |  Runtime ABI: glibc / standard dynamic linker (/lib64/ld-linux)  |   |
|   +-----------------------------------------------------------------+   |
+-------------------------------------------------------------------------+
|                           Kernel & Hardware                             |
|   - Streamlined Linux Kernel (or modular Rust kernel like Asterinas)   |
|   - QEMU / KVM / Bare-metal x86_64 and ARM64                            |
+-------------------------------------------------------------------------+
```

Read the full [Architecture Specification](docs/ARCHITECTURE.md).

---

## 🔬 GitHub Ecosystem Research & References

Before building FerroOS, we analyzed the state of the art in the Rust OS ecosystem:

* **[Asterinas](https://github.com/asterinas/asterinas)**: Proves that a Rust-based OS can achieve Linux syscall compatibility and run complex runtimes like Python 3 and Redis.
* **[Bottlerocket OS (AWS)](https://github.com/bottlerocket-os/bottlerocket)**: Proves that replacing Linux userspace with custom Rust daemons creates an ultra-fast, minimal, hardened OS.
* **[sysMaster](https://github.com/openeuler-mirror/sysmaster)**: Proves that systemd's bloat can be replaced with a modular Rust PID 1 and service manager.
* **[uutils coreutils](https://github.com/uutils/coreutils)**: Proves that GNU utilities can be rewritten in safe Rust with drop-in compatibility.

Read our complete [Ecosystem Research & References](docs/REFERENCES.md).

---

## 🚀 Remote Cloud Builds (GitHub Actions)

FerroOS does **not** drain your local machine's battery or storage. Every `git push` triggers the GitHub Actions pipeline:

1. **Compiles Rust Crates** in release mode (`ferro-init`, `ferro-core`).
2. **Packages Root Filesystem & Python 3 Runtime**.
3. **Generates bootable `initramfs.cpio.gz` + Kernel**.
4. **Boots in headless QEMU** to verify that Python 3 and Rust PID 1 run cleanly.
5. **Publishes bootable images** as downloadable GitHub Artifacts.

---

## 💻 Running FerroOS Locally

Once downloaded from GitHub Actions artifacts:

```bash
# Launch FerroOS in QEMU
qemu-system-x86_64 \
  -kernel vmlinuz \
  -initrd initramfs.cpio.gz \
  -append "console=ttyS0 quiet" \
  -nographic \
  -m 512M
```

---

## 📂 Repository Structure

```
ferro-os/
├── .github/workflows/
│   └── build-os.yml         # Automated GitHub Actions OS builder & QEMU tester
├── build/
│   ├── build-rootfs.sh      # Assembles rootfs, Python 3, and initramfs
│   └── qemu-test.sh         # Headless QEMU automated boot verification
├── crates/
│   ├── ferro-init/          # Rust PID 1 Init system (early mounts, reaper)
│   └── ferro-core/          # Rust multi-call core utilities & shell
├── docs/
│   ├── ARCHITECTURE.md      # Detailed architectural specifications
│   └── REFERENCES.md        # Analysis of Asterinas, Bottlerocket, sysMaster
├── Cargo.toml               # Cargo workspace
└── README.md
```

