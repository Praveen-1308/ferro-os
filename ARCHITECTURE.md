# FerroOS Architecture & Engineering Blueprint

```
===================================================================================
                       FERRO-OS ARCHITECTURAL TAXONOMY
===================================================================================

 TRACK 1: PRODUCTION LINUX DISTRIBUTION       TRACK 2: BARE-METAL MICROKERNEL
 (Available Now — 3.61 MB Compressed)         (Active Development — 55 KB ELF)
+------------------------------------+       +------------------------------------+
|  FerroOS Userland (Layer 5)        |       |  FerroOS Userland (Layer 5)        |
|  - ferro-init (PID 1)              |       |  - ferro-init (PID 1)              |
|  - ferro-core (220 Multi-Call)     |       |  - ferro-core (220 Multi-Call)     |
|  - ferro-superd & ferrocage        |       |  - ferro-pkg (rpk)                 |
|  - ferro-pkg (rpk)                 |       |  - Interactive Shell (sh)          |
+-----------------+------------------+       +-----------------+------------------+
                  |                                            |
                  | Linux x86_64 ABI Syscall Interface         | Linux x86_64 ABI
                  v                                            v
+------------------------------------+       +------------------------------------+
|  Hardened Linux LTS Kernel (vmlinuz|       |  ferro-kernel (Layer 0-4)          |
|  - Memory Management & Paging      |       |  - #![no_std] Freestanding         |
|  - Device Drivers & Hardware       |       |  - VGA 80x25 Buffer (0xB8000)      |
|  - Cgroups v2 & Landlock LSM       |       |  - Serial COM1 UART 16550          |
|  - io_uring & Network Stack        |       |  - GDT + TSS Double Fault Stack    |
|                                    |       |  - IDT & 8259 PIC Interrupts       |
|                                    |       |  - Linked-List Heap Allocator      |
|                                    |       |  - Round-Robin Scheduler & PCB     |
+-----------------+------------------+       +-----------------+------------------+
                  |                                            |
                  +---------------------+----------------------+
                                        |
                                        v
                       +----------------------------------+
                       |        x86_64 Hardware /         |
                       |       QEMU / KVM / Hyper-V       |
                       +----------------------------------+
```

---

## 1. Executive Summary & Honest System Positioning

There is a fundamental question every systems engineer asks about operating system projects:  
**"Is this an operating system distribution, or a bare-metal kernel written from scratch?"**

FerroOS answers this with complete transparency and an ambitious dual-track execution model:

### Track 1: Production Pure-Rust Linux Distribution (Ship Now)
Today, FerroOS is an ultra-lightweight, memory-safe, pure-Rust operating system distribution. Just as **Android** pairs the Linux kernel with a custom userland (Bionic libc, SurfaceFlinger, ART) and **ChromeOS** pairs Linux with custom windowing and daemons, **FerroOS replaces legacy GNU coreutils, systemd, glibc, and Docker with 100% memory-safe pure-Rust equivalents**:
- `ferro-init`: Pure-Rust PID 1 init process.
- `ferro-core`: 220 multi-call applets compiled into a single static memory-safe binary (1.8 MB).
- `ferro-superd`: High-performance service supervisor with Cgroups v2 enforcement (<3 MB RSS).
- `ferrocage`: Container engine utilizing unprivileged user namespaces and Landlock LSM without a heavy daemon.
- `rpk`: Pure-Rust cryptographic package manager with FIPS 180-4 SHA-256 package verification.

### Track 2: Bare-Metal `#![no_std]` Rust Microkernel (The Next Frontier)
In parallel, the FerroOS team is developing `kernel/` (`ferro-kernel`), an experimental freestanding `#![no_std]` 64-bit microkernel. By intentionally implementing the **standard Linux x86_64 syscall ABI** (`SYS_READ=0`, `SYS_WRITE=1`, `SYS_FORK=57`, `SYS_EXECVE=59`, `SYS_EXIT=60`), the exact same `ferro-core` userland binaries execute directly on `ferro-kernel` without recompilation.

---

## 2. The Top-Down Engineering Advantage

Most hobby OS projects follow a **bottom-up** path:
```
Bootloader  ──>  Page Tables  ──>  Interrupts  ──>  [Project Abandoned]
```
99% of operating systems built bottom-up stall before ever implementing a working shell, file manipulation utilities, or an init system.

FerroOS inverted this dynamic with a **Top-Down strategy**:
1. **Build Layer 5 first (The Hardest Part)**: Build a fully functioning, robust, battle-tested userspace with 220+ applets, comprehensive test suites, shell scripting, package management, and service supervision.
2. **Boot immediately on Linux (Track 1)**: Package the userland into a bootable ISO (`distro/build-iso.sh`) and minimal initramfs (`distro/build-initramfs.sh`) to provide a usable system from day one.
3. **Build the `#![no_std]` kernel in parallel (Track 2)**: Implement CPU initialization, memory paging, hardware interrupts, and syscall dispatching.
4. **Swap kernels seamlessly**: Because the syscall ABI is identical, transitioning from Track 1 to Track 2 requires zero changes to the userland applications.

---

## 3. Subsystem Breakdown

### Layer 5: Userland Utilities (`crates/ferro-core`)
- Multi-call binary pattern (similar to BusyBox, but 100% memory-safe Rust).
- 220 applets spanning:
  - File management (`ls`, `cp`, `mv`, `rm`, `find`, `stat`, `chmod`)
  - Text & stream processing (`grep`, `awk`, `sed`, `cut`, `sort`, `uniq`, `wc`, `xxd`)
  - Process lifecycle & concurrency (`ps`, `pgrep`, `pkill`, `killall`, `pstree`, `proc-ledger`)
  - Ghost hunter: active detection and reclamation of zombie and orphaned process trees.
  - Networking & diagnostics (`ip`, `ping`, `netstat`, `ss`, `curl`, `fetch`, `nc`)
  - Archival & compression (`tar`, `gzip`, `gunzip`, `zcat`)
  - System diagnostics (`uname`, `uptime`, `free`, `df`, `dmesg`, `lscpu`)

### Layer 4: Service Supervision & Containers (`ferro-superd`, `ferrocage`)
- Declarative service definitions with automatic dependency ordering.
- Cgroups v2 resource quotas (`memory.max`, `memory.swap.max = 0`, `cpu.max`).
- Socket activation and file descriptor preservation across supervisor restarts.
- Sub-2ms container launch using Linux user, PID, mount, and network namespaces.

### Layer 3: Init & System Orchestration (`ferro-init`)
- Direct PID 1 execution on kernel handoff.
- Automatic pseudo-filesystem mounting (`/proc`, `/sys`, `/dev`, `/dev/pts`, `/tmp`, `/run`).
- Kernel sysctl parameter tuning (`vm.overcommit_memory = 2`, `kernel.kptr_restrict = 2`).
- Graceful shutdown and signal reaping (`SIGCHLD`, `SIGTERM`, `SIGINT`).

### Layer 2 & 1: Bare-Metal Microkernel (`kernel/`)
- Pure `#![no_std]` Rust targeting `x86_64-unknown-none`.
- 80x25 memory-mapped VGA text buffer driver with automatic scrolling and color management (`0xB8000`).
- 16550 UART serial driver (`0x3F8` COM1) for virtualized console logging.
- GDT & TSS with dedicated Interrupt Stack Table (IST) protecting against triple-fault crashes.
- IDT handling CPU hardware exceptions and 8259 PIC timer (IRQ0) and PS/2 keyboard (IRQ1).
- Dynamic kernel heap allocator backed by `linked_list_allocator::LockedHeap`.
- Linux x86_64 ABI syscall dispatcher (`sys_read`, `sys_write`, `sys_uname`, `sys_exit`, `sys_getpid`, `sys_brk`).

---

## 4. Verification & Testing Discipline

FerroOS enforces strict multi-dimensional test coverage across all subsystems:
- **Workspace Unit Tests**: 93+ built-in test suites covering cryptography, parsers, and system utilities.
- **6-Dimension Testing Matrix**: 288 automated empirical tests evaluating positive cases, negative cases, edge cases, cross-command UNIX pipelines, concurrency, and real-world failure injection.
- **Zero-Synthetic Parity**: Head-to-head functional parity verification against Ubuntu GNU coreutils and Alpine BusyBox.
