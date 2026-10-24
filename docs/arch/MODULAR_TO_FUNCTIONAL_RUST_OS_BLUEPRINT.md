# FerroOS: Modular-to-Functional Pure-Rust Linux OS Blueprint
**A Deterministic Systems Engineering Roadmap from Standard Linux Files to a 100% Rust-Native Operating System**

---

## 1. Vision & Architectural Imperative

The objective is to progressively transform FerroOS from a hybrid environment (using Debian/Linux base files with Rust daemons) into an **autonomous, pure-Rust Linux-based operating system**. 

Rather than risking an all-at-once monolithic rewrite, FerroOS employs a **modular-to-functional phased migration**. Each functional layer of the operating system is incrementally converted to pure, memory-safe Rust while maintaining bit-for-bit compliance with:
1. **POSIX.1-2017 & Linux ABI Specifications** (LTP verification)
2. **Filesystem Hierarchy Standard (FHS 3.0)**
3. **Cloud & Enterprise Hypervisor Rules** (AWS EC2, GCP Compute Engine, Azure, KVM/Proxmox, VMware ESXi)
4. **Least-Privilege Security & Permission Governance** (Guaranteeing zero permission blocks at any lifecycle phase).

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                   MODULAR-TO-FUNCTIONAL PURE-RUST OS EVOLUTION                         │
└────────────────────────────────────────────────────────────────────────────────────────┘
                                    │
    ┌───────────────────────────────┴───────────────────────────────┐
    │                                                               │
    ▼                                                               ▼
[Tier 1: Core POSIX Primitives]                         [Tier 2: FHS & Permissions]
• 100% Rust Multi-Call Binary (`ferro-core`)            • Linux Foundation FHS 3.0 Directory Tree
• `cat`, `ls`, `mkdir`, `cp`, `rm`, `chmod`, `chown`   • Sticky bit on `/tmp` (`1777`)
• `touch`, `ln`, `stat`, `id`, `sync`, `mount`, `umount` • Least-Privilege non-root UID 1000 (`ferro`)
• `hostname`, `tee`, `ip`, `ps`, `kill`, `df`, `free`   • `/etc/shadow` (0600), `/etc/passwd` (0644)
    │                                                               │
    └───────────────────────────────┬───────────────────────────────┘
                                    │
    ┌───────────────────────────────┴───────────────────────────────┐
    │                                                               │
    ▼                                                               ▼
[Tier 3: Pure-Rust Network Core]                        [Tier 4: Supervised Init & LSM]
• Direct Netlink (`rtnetlink`) link & route plumbing    • PID 1 Init System (`ferro-init`)
• In-memory DNS cache & resolver (`ferro-core dns`)     • eBPF sockops & sched-ext scheduling
• Native DHCP client for cloud/hypervisor IP leasing     • Landlock LSM filesystem sandboxing
• Zero external dependency on `iproute2` / `net-tools`  • SCM_RIGHTS FDStore socket preservation
    │                                                               │
    └───────────────────────────────┬───────────────────────────────┘
                                    │
                                    ▼
[Tier 5: Autonomous Cloud & Bare-Metal Boot (Autonomous RootFS)]
• Statically linked musl / minimal-glibc rootfs with zero GNU/Debian packages
• Cloud-init IMDS metadata discovery (`169.254.169.254`) for AWS/GCP/OpenStack
• Serial console (`ttyS0`, `tty1`) and virtio-net / virtio-blk driver auto-binding
• Bootable in QEMU/KVM, container runtimes (OCI scratch), and bare-metal UEFI/BIOS
```

---

## 2. The 5 Functional Evolution Tiers

### Tier 1: Core POSIX & System Primitives (`ferro-core`)
Instead of shipping GNU coreutils (30MB+ of legacy C binaries with decades of CVE history), FerroOS integrates all core utilities into a multi-call binary (`/bin/ferro-core`), dynamically symlinked:
* **Filesystem Operations**: `cat`, `echo`, `cp`, `mv`, `rm`, `mkdir`, `chmod`, `chown`, `touch`, `ln`, `stat`, `tee`.
* **Process & System Diagnostics**: `ps`, `kill`, `free`, `df`, `uptime`, `whoami`, `id`, `uname`, `env`, `sleep`, `sync`, `hostname`.
* **Storage Mount Primitives**: `mount`, `umount` using direct `libc::mount` and `libc::umount2`.
* **Network & Connectivity**: `ip` (link, addr, route inspection), `fetch` (HTTP/HTTPS client), `serve` (high-throughput non-blocking HTTP server).

### Tier 2: FHS 3.0 & Enterprise Permission Governance
To ensure workloads are never blocked by permission errors while adhering to CIS Level 1 & 2 server benchmarks:
* **The UsrMerge Standard**:
  ```
  /bin  -> /usr/bin
  /sbin -> /usr/sbin
  /lib  -> /usr/lib
  /lib64-> /usr/lib64
  ```
* **Deterministic File & Directory Permissions**:
  | Path | Standard Permissions | Ownership | Functional Purpose |
  | :--- | :---: | :---: | :--- |
  | `/tmp` | `1777` (`rwxrwxrwt`) | `root:root` | Multi-tenant temporary storage with sticky bit |
  | `/var/tmp` | `1777` (`rwxrwxrwt`) | `root:root` | Persistent temporary storage |
  | `/etc` | `0755` (`rwxr-xr-x`) | `root:root` | System configuration directory |
  | `/etc/passwd` | `0644` (`rw-r--r--`) | `root:root` | User database readable by all processes |
  | `/etc/shadow` | `0600` (`rw-------`) | `root:root` | Cryptographic password hashes (protected) |
  | `/etc/resolv.conf` | `0644` (`rw-r--r--`) | `root:root` | DNS nameserver configuration |
  | `/home/ferro` | `0755` (`rwxr-xr-x`) | `ferro:ferro` (1000:1000) | Default unprivileged service user workspace |
  | `/root` | `0700` (`rwx------`) | `root:root` | Administrator home directory |
  | `/usr/bin/*` | `0755` (`rwxr-xr-x`) | `root:root` | Executable system utilities |

### Tier 3: Pure-Rust Network & Interface Plumbing
* **Kernel Netlink Protocol**: Communicates with the kernel's network subsystem using Netlink sockets (`AF_NETLINK`, `NETLINK_ROUTE`), enabling interface up/down, IP address assignment, and routing table configuration without external CLI tools.
* **DNS Resolution**: `ferro-core dns` provides an asynchronous UDP/TCP stub resolver with local LRU caching and EDNS(0) support.
* **DHCPv4/v6 Client**: Minimal pure-Rust client requesting network configuration from hypervisor DHCP servers on boot.

### Tier 4: Supervised Init & Security LSM Core
* **PID 1 (`ferro-init`)**: Directly mounts virtual filesystems (`/proc`, `/sys`, `/dev`, `/tmp` with `1777`), sets hostname, elevates system limits, enforces KSPP kernel parameters, and reaps orphaned child processes (preventing zombie leak).
* **Landlock LSM**: Self-restricting sandboxing restricting unprivileged processes to explicit whitelist directories (`/var/ferro`, `/tmp`).
* **Zero-on-Free (`crates/ferro-core/src/zeroize.rs`)**: Automatic volatile memory scrubbing on memory drop, eliminating CWE-226 in-memory credential harvesting.

### Tier 5: Cloud & Bare-Metal Compatibility Standards
* **Cloud Instance Metadata Service (IMDS)**: Early boot hook querying `http://169.254.169.254/latest/meta-data/` on cloud providers to automatically import SSH public keys and hostname.
* **Hypervisor Drivers**: Direct support for standard Linux `virtio-net`, `virtio-blk`, and `virtio-pci` drivers, guaranteeing instant boots on AWS, GCP, Azure, and Proxmox.
* **Serial Console Redirection**: Direct output to `/dev/ttyS0` and `/dev/console` for headless enterprise cloud environments.
