# FerroOS 🦀⚡

> **A blazingly fast, lightweight Linux distribution powered by Rust.**  
> *Alpine-like speed (<300ms boot, <30MB RAM) + Debian compatibility (Python 3, pip, glibc ABI) + Pure Rust Userspace.*

[![Build & Verify FerroOS](https://github.com/Praveen-1308/ferro-os/actions/workflows/build-os.yml/badge.svg)](https://github.com/Praveen-1308/ferro-os/actions/workflows/build-os.yml)

---

## 🌟 The Vision

Traditional Linux distributions force a compromise:
1. **Debian / Ubuntu**: Complete software compatibility, runs Python, Node, and standard C-extensions out of the box—**but slow boot times (5–15s), systemd bloat, and high idle memory consumption (150MB–300MB)**.
2. **Alpine Linux**: Ultra-fast and lightweight (5MB rootfs, <1s boot)—**but uses `musl libc`, breaking many pre-compiled Python wheels (`numpy`, `torch`, `cryptography`), requiring slow source builds**.

**FerroOS bridges this gap:**
- **100% Rust Userspace**: Replaces legacy C init systems and utilities with modern, memory-safe Rust (`ferro-init`, `ferro-core`, and `rpk`).
- **Full glibc / POSIX Compatibility**: Python 3, dynamic shared libraries, and C extensions run natively without recompilation.
- **Built-in Rust Package Manager (`rpk`)**: Ultra-fast package installation, removal, dependency tracking, and `.rpk` bundle creation.
- **Sub-300ms Boot Time**: Zero systemd overhead, streamlined mounts, loopback network auto-configuration, instant shell.
- **Zero Local Strain**: Automated remote build and headless QEMU testing on GitHub Actions.

---

## 🏗️ Architecture

```
+-------------------------------------------------------------------------+
|                              User Applications                          |
|         - Python 3.12 & pip packages (numpy, flask, requests...)        |
|         - Any standard POSIX dynamic ELF binaries                       |
+-------------------------------------------------------------------------+
|                        FerroOS Userspace (Rust)                         |
|   +-------------------+  +--------------------+  +------------------+   |
|   | ferro-init (PID 1)|  | ferro-core         |  | ferro-pkg (rpk)  |   |
|   | - Mount /proc...  |  | - 28+ Unix Applets |  | - Fast packaging |   |
|   | - Net loopback    |  | - Pipes & Redirect |  | - Install/Remove |   |
|   | - Zombie reaper   |  | - Shell & Env exp  |  | - Archive builder|   |
|   +-------------------+  +--------------------+  +------------------+   |
|   +-----------------------------------------------------------------+   |
|   |  Runtime ABI: glibc dynamic linker (/lib64/ld-linux-x86-64.so.2) |   |
|   +-----------------------------------------------------------------+   |
+-------------------------------------------------------------------------+
|                           Kernel & Hardware                             |
|   - Minimal Linux Kernel (or modular Rust kernel like Asterinas)       |
|   - QEMU / KVM / Hardware x86_64 and ARM64                              |
+-------------------------------------------------------------------------+
```

---

## 🧰 Built-in Rust Toolset

### 1. `ferro-init` (PID 1 Init & Supervisor)
- Mounts `/proc`, `/sys`, `/dev`, `/tmp`, and `/dev/pts` in under 15 milliseconds.
- Automatically brings up loopback network (`lo`) and configures default DNS (`/etc/resolv.conf`).
- Sets hostname, environment paths, and manages child process reaping (`waitpid`).
- Executes startup services in `/etc/init.d/` in order.

### 2. `ferro-core` (Multi-Call Core Utilities)
A single compact Rust binary providing 28+ essential Unix commands:
- **Shell & Navigation**: `sh` (with interactive prompt, pipes `cmd1 | cmd2`, redirection `> / >>`, and `$VAR` expansion), `ls`, `cd`, `pwd`, `clear`, `which`.
- **File Operations**: `cat`, `echo`, `cp`, `mv`, `rm`, `mkdir`, `chmod`, `head`, `tail`, `wc`.
- **Search & Text**: `grep` (with `-i`), `find` (with `-name`).
- **System Monitoring**: `ps` (process table), `free` (RAM metrics), `df` (disk/mount usage), `uptime`, `whoami`, `uname`, `env`, `kill`.
- **Network & Power**: `fetch` / `curl` (pure Rust HTTP client), `sleep`, `reboot`, `poweroff`.

### 3. `rpk` (Rust Package Keeper)
- **`rpk list`**: View all installed packages and versions.
- **`rpk info <pkg>`**: Inspect package details, installation time, and file manifests.
- **`rpk install <pkg.rpk>`**: Extract package archive and register files in `/var/lib/rpk/db.json`.
- **`rpk remove <pkg>`**: Cleanly delete all files associated with a package.
- **`rpk build <dir> <out.rpk>`**: Build an `.rpk` compressed package from any directory structure.

---

## 🚀 Remote Cloud Builds (GitHub Actions)

FerroOS does **not** drain your local machine's battery or storage. Every `git push` triggers the GitHub Actions pipeline:

1. **Compiles All Rust Crates** in release mode (`ferro-init`, `ferro-core`, `ferro-pkg`).
2. **Packages Root Filesystem & Python 3 Runtime**.
3. **Builds and installs sample `.rpk` package** (`neofetch-lite`).
4. **Generates bootable `initramfs.cpio.gz` + Kernel**.
5. **Boots in headless QEMU** to run the comprehensive system test suite:
   - Verifies Python 3 math and standard library.
   - Verifies virtual mounts, memory metrics, and hostname.
   - Verifies shell pipelines (`echo ... | grep ...`).
   - Verifies `rpk` package manager installation and execution.
6. **Publishes bootable images** as downloadable GitHub Artifacts.

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
│   ├── build-rootfs.sh      # Assembles rootfs, Python 3, rpk packages, and initramfs
│   └── qemu-test.sh         # Headless QEMU automated boot verification
├── crates/
│   ├── ferro-init/          # Rust PID 1 Init system (loopback, early mounts, reaper)
│   ├── ferro-core/          # Rust multi-call core utilities (28+ applets, pipes, sh)
│   └── ferro-pkg/           # Rust Package Keeper (rpk) package manager
├── docs/
│   ├── ARCHITECTURE.md      # Detailed architectural specifications
│   └── REFERENCES.md        # Analysis of Asterinas, Bottlerocket, sysMaster
├── Cargo.toml               # Cargo workspace
└── README.md
```

