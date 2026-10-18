# FerroOS Architecture Specification

FerroOS is designed to combine the **minimalist speed and efficiency of Alpine Linux** with the **runtime compatibility of Debian** (supporting Python, pip, dynamic C libraries, and standard POSIX software), powered by **safe, concurrent Rust**.

---

## 1. High-Level Architecture Diagram

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

---

## 2. Core Components

### A. `ferro-init` (The Rust PID 1 Init System)
* **Role**: The first userspace process executed by the kernel (`/sbin/init` or `/init`).
* **Responsibilities**:
  1. **Virtual Filesystem Setup**: Mounts `/proc` (procfs), `/sys` (sysfs), `/dev` (devtmpfs), and `/dev/pts`.
  2. **Signal Handling**: Catches `SIGCHLD` to prevent and immediately reap zombie processes.
  3. **Process Supervision**: Spawns interactive shells (getty/sh) or daemons, monitoring their status and restarting if configured.
  4. **Clean Shutdown**: Catches `SIGINT`/`SIGTERM` or commands from `ferro-core poweroff` to unmount filesystems and invoke `sys_reboot(LINUX_REBOOT_CMD_POWER_OFF)`.

### B. `ferro-core` (Multi-Call Rust Utilities)
* Inspired by **BusyBox** and **uutils coreutils**.
* Compiled into a single binary. Symlinks determine the active command based on `argv[0]`:
  - `/bin/sh` -> `/bin/ferro-core` (builtin interactive command dispatcher)
  - `/bin/ls` -> `/bin/ferro-core`
  - `/bin/cat` -> `/bin/ferro-core`
  - `/bin/echo` -> `/bin/ferro-core`
  - `/bin/uname` -> `/bin/ferro-core`
  - `/sbin/poweroff` -> `/bin/ferro-core`
  - `/sbin/reboot` -> `/bin/ferro-core`
* **Advantage**: Extreme disk savings (one compact binary), zero memory leakage, and instant execution.

### C. Standard Python & POSIX Runtime
* Unlike Alpine which defaults to musl (causing incompatibility with many pre-compiled C-Python wheels), FerroOS maintains standard ABI compatibility.
* Python 3 and its dynamic dependencies (`libpython3.so`, `libc.so.6`, `libm.so.6`, `libdl.so.2`) are packaged into the rootfs.
* Any Python script runs out-of-the-box:
  ```sh
  ferro-os# python3 -c "import sys; print('Python', sys.version, 'on FerroOS!')"
  ```

---

## 3. Remote Cloud-Build Workflow (GitHub Actions)

Because building kernels, disk images, and root filesystems consumes heavy CPU and storage, the build process is offloaded entirely to GitHub:

```mermaid
flowchart LR
    Dev["Local Mac (Code only)"] -->|git push| GH["GitHub Repo"]
    GH --> Runner["GitHub Actions Runner (Ubuntu Linux)"]
    Runner --> BuildRust["1. Build Rust Binaries (cargo build)"]
    BuildRust --> AssembleRootfs["2. Assemble Minimal Rootfs + Python 3"]
    AssembleRootfs --> CreateImage["3. Pack Kernel & Initramfs (.img)"]
    CreateImage --> QEMU["4. Boot Test in Headless QEMU"]
    QEMU --> Artifact["5. Publish Release Artifacts"]
```

---

## 4. Boot Sequence Timing Target

| Stage | Expected Duration |
| :--- | :--- |
| **Kernel Decompress & Init** | ~200 ms |
| **ferro-init (PID 1) Mounts & Setup** | ~15 ms |
| **Login Shell / Python Ready** | ~30 ms |
| **Total Boot Time** | **< 300 ms** |
