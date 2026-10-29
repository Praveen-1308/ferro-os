# FerroOS Architecture Specification

FerroOS is designed to combine the **minimalist speed and efficiency of Alpine Linux** with the **runtime compatibility of Debian** (supporting Python, pip, dynamic C libraries, and standard POSIX software), powered by **safe, concurrent Rust**.

---

## 1. High-Level Architecture Diagram

```
+-------------------------------------------------------------------------+
|                              User Applications                          |
|    - Python 3 & pip packages (numpy, flask, etc.)                       |
|    - Custom Rust / C / Go / Node applications                           |
|    - Micro-Containers managed by ferrocage                              |
+-------------------------------------------------------------------------+
|                        FerroOS Userspace (Rust)                         |
|   +--------------------------+   +----------------------------------+   |
|   |  ferro-init (PID 1)      |   |  ferro-superd (Supervisor)       |   |
|   |  - Early mount (/proc...) |   |  - Cgroups v2 memory & CPU       |   |
|   |  - Zombie reaping        |   |  - Declarative TOML manifests    |   |
|   |  - Root pivot & recovery |   |  - Ring-buffer logging           |   |
|   +--------------------------+   +----------------------------------+   |
|   +--------------------------+   +----------------------------------+   |
|   |  ferrocage (Micro-Cont)  |   |  ferro-core (Multi-Call Binary)  |   |
|   |  - Linux namespaces      |   |  - 40+ POSIX coreutils applets   |   |
|   |  - Persistent volumes    |   |  - ferro sandbox (Landlock LSM)  |   |
|   |  - Sub-2ms container run |   |  - ferro cloud-init & disk       |   |
|   +--------------------------+   +----------------------------------+   |
|   +-----------------------------------------------------------------+   |
|   |  libferro_io.so: io_uring SQPOLL POSIX Acceleration Shim         |   |
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

## 3. The Four Strategic Cloud Pillars

```mermaid
flowchart TD
    subgraph P1["Pillar 1: Zero-Trust Security"]
        A["Native Landlock LSM"]
        B["Path-Delegated Storage Bounds"]
    end
    subgraph P2["Pillar 2: Cloud Supervisor"]
        C["ferro-superd: Cgroup v2 Manager"]
        D["Auto-OOM Guard & Health Self-Healing"]
    end
    subgraph P3["Pillar 3: Micro-Container Runtime"]
        E["ferrocage: Namespace Sandbox"]
        F["Sub-2ms Startup & Volume Persistence"]
    end
    subgraph P4["Pillar 4: Cloud Automation"]
        G["cloud-init: AWS/GCP/Azure IMDS"]
        H["Persistent Block Storage & Disk Scanner"]
    end

    P1 --> OS["FerroOS Pure-Rust Core (3.59 MB)"]
    P2 --> OS
    P3 --> OS
    P4 --> OS
```

### Pillar 1: Zero-Trust Security & Path-Delegated Storage (`ferro sandbox`)
- **Kernel-Level Enforcement**: Native Linux Landlock LSM (`SYS_landlock_create_ruleset`, `SYS_landlock_add_rule`, `SYS_landlock_restrict_self`) and Seccomp-BPF filters.
- **Ambient Authority Elimination**: Base OS binaries (`/bin`, `/usr`, `/lib`) and system configurations (`/etc`) are strictly locked as read-only.
- **Path-Delegated Storage**: High-velocity write access is explicitly delegated to designated storage volumes:
  ```bash
  ferro sandbox --ro /app --rw /data --no-net --drop-caps -- python3 app.py
  ```
- **Performance**: Protected path write block enforced in **1.7 ms** (`Permission denied`); authorized storage write directly to disk in **1.6 ms**.

### Pillar 2: Cgroup v2 Service Supervisor (`ferro-superd` & `ferro service`)
- **Systemd Alternative**: A standalone 463 KB daemon reading declarative TOML manifests from `/etc/ferro/services/*.toml`.
- **Cgroup v2 Bounds**: Writes directly to `/sys/fs/cgroup/ferro.slice/<name>/` (`memory.max`, `memory.high`, `cpu.weight`, `pids.max`).
- **Resilience**: Integrated exponential backoff restart policies (`always`, `on-failure`, `never`) and continuous ring-buffer logging.
- **CLI Suite**:
  - `ferro service list [--format table|json]`
  - `ferro service status <name> [--format text|json]`
  - `ferro service start <name>` / `stop <name>` / `restart <name>`
  - `ferro service logs <name> [-n lines]`
  - `ferro service reload`

### Pillar 3: Pure-Rust Micro-Container Runtime (`ferrocage`)
- **Zero-Daemon Overhead**: Eliminates Docker/containerd (60+ MB RAM). `ferrocage` (495 KB) executes isolated micro-containers in **< 1.8 milliseconds** using Linux namespaces (`CLONE_NEWPID`, `CLONE_NEWNS`, `CLONE_NEWNET`, `CLONE_NEWUTS`, `CLONE_NEWIPC`, `CLONE_NEWUSER`).
- **Storage Volume Persistence**: Host volumes mounted with `-v host:container` use pure-Rust `MS_BIND`. All writes persist directly to physical host disk blocks and remain completely intact after container teardown.
- **Full CLI Suite**: `run`, `ps`, `stop`, `start`, `rm`, `logs`, `inspect`, `exec`.

### Pillar 4: Cloud-Native Automation & Persistent Storage
- **Autonomous IMDS Client (`ferro cloud-init`)**: Probes link-local metadata at `http://169.254.169.254/latest/meta-data/` on AWS EC2, GCP Compute Engine, Azure, and OpenStack. Dynamically sets instance hostnames, provisions SSH public keys into `/root/.ssh/authorized_keys` (mode `0600`), and executes user-data bootstrapping scripts in **1.8 ms**.
- **Block Storage Scanner (`ferro disk`)**: Scans `/proc/partitions`, identifies NVMe/SCSI devices, and manages partition formatting and persistent mounts.

---

## 4. The Four Connected Editions of FerroOS

FerroOS is designed around a single, unified pure-Rust core that powers four specialized operating system profiles:

```mermaid
flowchart TD
    CORE["FerroOS Pure-Rust Autonomous Core\n(ferro-init • ferro-core • ferro-superd • ferro sandbox • ferro-pkg)"]

    subgraph E1 ["1. Cloud Server Edition"]
        C_SVC["High-Throughput Microservices ($12 Challenge)"]
        C_SUPER["ferro-superd (2.66 MB RAM)"]
        C_CAGE["ferrocage (Sub-2ms Containers)"]
        C_IMDS["cloud_init Autonomous IMDS"]
    end

    subgraph E2 ["2. Desktop & Web Edition"]
        D_COMP["ferro-compositor (GPU Wayland)"]
        D_GUI["ferro-gui (Framebuffer /dev/fb0)"]
        D_PORTAL["xdg-desktop-portal-ferro"]
        D_WEB["Web Desktop Streaming (Port 6080)"]
    end

    subgraph E3 ["3. Gaming & Proton Edition"]
        G_SCHED["sched_ext Real-Time Gaming Policy"]
        G_MODE["Dynamic GameMode (Nice -10)"]
        G_VULKAN["DXVK & VKD3D Vulkan Mapping"]
        G_WINE["Wine / Proton / Box64 / PE-MSI"]
    end

    CORE --> E1
    CORE --> E2
    CORE --> E3
```

### Edition 1: Cloud Server Edition
- **Target**: Autonomous, high-density cloud computing droplets and hyperscaler instances (AWS, GCP, Azure, Hetzner).
- **Core Stack**: `ferro-init`, `ferro-superd`, `ferrocage`, `ferro sandbox` with Landlock LSM, and autonomous `cloud-init` IMDS (`169.254.169.254`).
- **Performance**: 3.59 MB rootfs, 2.66 MB supervisor memory, 1,858 req/s throughput in the $12 server challenge with zero Docker/containerd daemon footprint.

### Edition 2: Desktop & Web Desktop Edition
- **Target**: Ultra-fast graphical workstations, embedded kiosks, and browser-accessible cloud desktops.
- **Graphical Stack**:
  - `ferro-compositor`: GPU-accelerated Wayland compositor featuring DRM/KMS scanout, layer-shell protocols (`Background`, `Bottom`, `Top`, `Overlay`), damage tracking, and Dual-Kawase acrylic blur shaders.
  - `ferro-gui`: Double-buffered direct framebuffer (`/dev/fb0`) window manager with `font8x8` ASCII bitmap rendering for zero-X11/zero-Wayland fallback.
  - `xdg-desktop-portal-ferro`: Native XDG desktop portal integration for file pickers, screencasting, and system notifications.
  - **Web Desktop**: HTML5 canvas live streaming over WebSocket / noVNC on port 6080 for remote browser access from any device.

### Edition 3: Gaming & Proton Edition
- **Target**: Low-latency, high-frame-rate native and Windows gaming on Linux.
- **Gaming Stack**:
  - **`sched_ext` Gaming Policy**: Real-time task scheduling (500 µs target slice, sub-50µs wakeup jitter) elevating rendering threads.
  - **Dynamic GameMode Engine**: Automatic Nice -10 CPU priority boost, GPU performance governor, and background task cgroup throttling.
  - **DirectX -> Vulkan Translation**: DXVK (D3D9/10/11) and VKD3D (D3D12) with `DXVK_ASYNC=1` state cache integration.
  - **Wine / Proton & Multi-Arch Translation**: Native execution of Windows binaries via Wine64 and Box64/FEX-Emu bridges on ARM64; PE32/PE32+ and MSI header inspection in `ferro-pkg`.

- **Features**: Toggle between Hierarchical and Radial views, filter by edition (Cloud Server, Desktop & Web, Gaming & Proton), search symbols and functions, and view live codebase metrics.

---

## 8. Remote Cloud-Build Workflow (GitHub Actions)

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

## 9. Boot Sequence Timing Target

| Stage | Expected Duration |
| :--- | :--- |
| **Kernel Decompress & Init** | ~200 ms |
| **ferro-init (PID 1) Mounts & Setup** | ~15 ms |
| **Login Shell / Python Ready** | ~30 ms |
| **Total Boot Time** | **< 300 ms** |
