# FerroOS Engineering Action Plan & Living Change Tracker

**Target Repository:** [Praveen-1308/ferro-os](https://github.com/Praveen-1308/ferro-os)  
**Document Purpose:** Living engineering backlog tracking verified audit fixes, architectural gap analyses, hybrid package management workflows, optional legacy C-library compatibility packs, compatibility risk guards, and user-directed enhancements.

## 1. Priority Code & Test-Harness Fixes (From Blind Audit)

These items address the discrepancies identified during the one-to-one command audit (where the raw out-of-the-box command pass rate was 40/62 [64.5%] due to unlinked applets, inactive daemons, and masked pipeline checks).

| ID | Component / File | Issue Identified | Required Implementation | Status |
| :--- | :--- | :--- | :--- | :--- |
| **FIX-001** | `tools/test_5os_comprehensive_commands_matrix.py` | Unshielded pipes (`cmd \| head -n 1`) without `pipefail`, flawed `grep -qv 'unknown applet'` matching line 1 of help output, and exit code `127` relabeled as `RESTRICTED` falsely inflated command scores to 100%. | Enforce `set -o pipefail`, check binary existence strictly via `command -v <cmd>` / `--has-applet`, and classify exit code `127` as `MISSING`. | `[x] Completed` |
| **FIX-002** | `crates/ferro-core/src/main.rs` | Built-in `ferro-core` multi-call applets are not linked into standard `$PATH` directories (`/bin`, `/usr/bin`), causing direct shell invocations to fail with exit code `127`. | Implement `/bin/ferro-core --install-symlinks /bin` during container/image build to populate symlinks for all 83 built-in applets. | `[x] Completed` |
| **FIX-003** | `crates/ferro-core/src/main.rs` (`ip` applet) | `ferro-core ip addr` scrapes `/proc/net/fib_trie` using basic string splitting instead of kernel Netlink sockets, outputting malformed `/32` subnet addresses. | Refactored `ip` to query POSIX Linux Netlink sockets via `libc::getifaddrs`, and parsed `/proc/net/route` hex bytes into CIDR notation. | `[x] Completed` |
| **FIX-004** | `entrypoint-server.sh` | Step E4 (`/bin/ferro-core dns-cache query localhost`) timed out after 2,109 ms with `os error 11` (`EAGAIN`) because the background resolver daemon was not running on UDP port 5353. | Added native background `&` execution to `ferro-core sh`, started `dns-cache` on UDP port 5353 in `entrypoint-server.sh`, resolving queries in ~229 µs. | `[x] Completed` |
| **FIX-005** | `Dockerfile.server` & `ferro-pkg` (`rpk`) | 16 SRE forensic and networking binaries (`strace`, `tcpdump`, `lsof`, `fuser`, `iostat`, `mpstat`, `ip`, `ss`, `ping`, `nc`, `dig`, `host`, `wget`, `gpg`, `capsh`, `nft`) were missing from the base image. | Bundled incident-response tools (`iproute2`, `iputils-ping`, `strace`, `lsof`, `tcpdump`, `sysstat`, `bind9-dnsutils`, `nftables`, `iptables`, `gnupg`, `wget`, `netcat`, `libcap2-bin`) into the server image. | `[x] Completed` |

## 2. Documentation & Honest Enterprise Gap Analysis

Replace defensive "strawman" gap comparisons (which only mentioned deprecated 1990s tools like `plipconfig`, `slattach`, and SysVinit `chkconfig`) with an accurate enterprise architectural scope analysis.

### 2.1 Documentation Action Items

| ID | Target Document | Required Documentation Change | Status |
| :--- | :--- | :--- | :--- |
| **DOC-001** | `README.md` & Whitepapers | Clarify that the `< 0.8 ms` cold-boot metric measures **userspace supervisor initialization (`ferro-init` PID 1) and container spawn time**, not bare-metal UEFI/BIOS and Linux kernel hardware initialization. | `[ ] Pending` |
| **DOC-002** | `README.md` (Gap Analysis Section) | Replace the 3-point legacy gap section with the 5-part Enterprise Scope & Gap Analysis below, clarifying how the 2.9 MB Rust core pairs with the Debian 12 `glibc` runtime substrate and optional compatibility packs. | `[ ] Pending` |

### 2.2 Reference Matrix: Standard Enterprise Linux vs. FerroOS Base Scope

| Subsystem Category | Standard RHEL 9 / Ubuntu 24.04 Full Install | FerroOS Default Base Image | Optional `rpk` Compatibility Pack |
| :--- | :--- | :--- | :--- |
| **1. Init & Device Suite** | Full `systemd` suite (`udevd` hardware hotplug, `logind` multi-seat sessions, `NetworkManager`, `journald`). | Lightweight `ferro-init` PID 1 supervisor with `SCM_RIGHTS` FD handover for cloud VMs and containers. | `@legacy-sysv-compat` (maps `service` & `chkconfig` calls to `ferro-init`). |
| **2. SAN & Volume Management** | LVM2, `dm-multipath` (Fibre Channel SANs), iSCSI initiators, `mdadm` RAID, LUKS (`cryptsetup`). | Cloud NVMe/EBS block storage + Btrfs Copy-on-Write (CoW) atomic subvolumes. | `@enterprise-storage` (`lvm2`, `cryptsetup`, `multipath-tools`, `nfs-common`). |
| **3. Corporate Identity & Auth** | PAM, SSSD, Kerberos (`krb5`), Active Directory / LDAP domain joining for multi-user SSH nodes. | Single-purpose microservice runtime identity (`uid=1000(ferro)`) with zero-trust capability dropping. | `@enterprise-auth` (`sssd`, `libpam-krb5`, `sudo`, LDAP client libraries). |
| **4. C/C++ Libraries & Toolchains** | Pre-bundles or provides 40+ legacy C shared libraries (`libnsl`, `libtirpc`, `libcrypt`), headers (`libc6-dev`), and `gcc`/`make`. | Minimal runtime `glibc` + preloaded `libmimalloc.so.2` and `libferro_io.so` (keeps CVE count at 0 and Lynis at 89/100). | `@c-compat-libs` & `@c-toolchain` (40+ legacy C libraries, headers, `gcc`, `g++`, `make`). |
| **5. Bare-Metal Peripherals** | ACPI thermal daemons, `fwupd` BIOS updates, `ipmitool` BMC tools, CUPS printing, Bluetooth/Wi-Fi. | Omitted from default cloud/container image to minimize attack surface. | `@baremetal-hw` (`ipmitool`, `fwupd`, `lm-sensors`, `pciutils`, `usbutils`). |

## 3. Software Installation & Update Architecture (`rpk` + `apt` Hybrid Flow)

In normal Linux distributions, users install and update software with a single command (`apt update && apt upgrade` or `dnf upgrade`). Because FerroOS pairs a custom Rust core with a Debian 12 (`bookworm`) `glibc` substrate, updates operate across a unified two-layer pipeline:

| ID | Feature / Subsystem | Current Behavior | Target Production Behavior | Status |
| :--- | :--- | :--- | :--- | :--- |
| **PKG-001** | Native Curated Packages (`rpk` / `/bin/ferro-pkg`) | Installs local `.rpk` bundles with SHA-256 verification and `--root` isolation, but lacks a populated default remote repository index (`[rpk] No packages currently installed`). | Host an official `rpk` repository index on GitHub Releases / Cloudflare R2 so `rpk update && rpk install <pkg>` fetches signed FerroOS packages in one command. | `[ ] Pending` |
| **PKG-002** | Seamless Debian `apt` Fallback Wrapper | Users must manually switch between `rpk` (for FerroOS native tools) and `apt-get` (for the 60,000+ Debian `glibc` packages on the Bookworm substrate). | Add automatic fallback in `rpk` (`rpk install <pkg>` checks the FerroOS `.rpk` index first, then delegates to `apt-get install -y <pkg>`) so users only ever need one command. | `[ ] Pending` |
| **PKG-003** | Transactional Btrfs Pre-Update Snapshots | Standard `apt-get upgrade` modifies files in-place without instant rollback if an update breaks a library. | Before `rpk upgrade` or `rpk install` modifies the rootfs, automatically create a Btrfs CoW snapshot (`@pre_update`). If a service health check fails, `rpk rollback` reverts the OS in ~15 ms. | `[ ] Pending` |
| **PKG-004** | Unattended Security Patching | Requires manual container rebuild or manual `apt-get upgrade`. | Add `rpk upgrade --security` to pull Debian security advisories (`bookworm-security`) plus updated FerroOS Rust binaries with atomic rollback protection. | `[ ] Pending` |

## 4. Optional Legacy C-Library & Feature Profiles (`rpk` Capability Packs)

By offering legacy C libraries, compilers (`gcc`), and administrative utilities as **optional, on-demand `rpk` profile packs**, FerroOS keeps its default image ultra-lean and hardened while giving 100% compatibility to users who need legacy C support:

| Profile Command | Included Components & Libraries | Use Case & Rollback Behavior | Status |
| :--- | :--- | :--- | :--- |
| `rpk install @c-compat-libs` | 40+ standard & legacy C runtime shared libraries (`libnsl2`, `libtirpc3`, `libcrypt1`, `libstdc++6`, `libgcc-s1`, `libffi8`, `libssl3`, `libz1`, `libbz2`, `liblzma5`, `libncurses6`, `libreadline8`, `libsqlite3-0`, `libxml2`, `libcurl4`, `libexpat1`, `libpcre2`, `libuuid1`, etc.). | Runs older pre-compiled commercial C/C++ binaries and proprietary enterprise agents without recompilation. | `[ ] Planned` |
| `rpk install @c-toolchain` | `gcc`, `g++`, `make`, `cmake`, `pkg-config`, `libc6-dev`, `linux-libc-dev`, `binutils`. | Allows developers to compile C/C++ extensions (e.g., native Python/Node wheels) on the box, then remove via `rpk rollback` before production lock-down. | `[ ] Planned` |
| `rpk install @sre-forensics` | All 22 missing/masked audit commands (`strace`, `tcpdump`, `lsof`, `fuser`, `iproute2`, `iputils-ping`, `sysstat`, `dnsutils`, `nftables`, `iptables`, `wget`, `gpg`, `libcap2-bin`). | Brings the 62-command SRE incident-response matrix to a genuine, unmasked **62 / 62 (100%)** on demand. | `[ ] Planned` |
| `rpk install @legacy-sysv-compat` | Wrapper shims for `service`, `chkconfig`, `update-rc.d`, and deprecated `net-tools` (`arp`, `route`, `ifconfig`) translating calls into `ferro-init` and `ferro-core`. | Lets legacy enterprise bash scripts and 10-year-old automation run unmodified on FerroOS. | `[ ] Planned` |
| `rpk install @enterprise-infra` | `lvm2`, `cryptsetup`, `multipath-tools`, `open-iscsi`, `nfs-common`, `sssd`, `libpam-krb5`. | Enables SAN storage, LUKS encryption, and Active Directory/Kerberos authentication for bare-metal or hybrid enterprise deployments. | `[ ] Planned` |

## 5. Compatibility Risks, Bug Vectors & Required Safeguards

Introducing optional legacy C libraries, hybrid `apt` packages, and global `LD_PRELOAD` shims creates five concrete failure modes that must be guarded against in code:

| Risk ID | Failure Vector / Potential Bug | Why It Happens on FerroOS | Required Engineering Safeguard | Status |
| :--- | :--- | :--- | :--- | :--- |
| **CMP-001** | **Allocator & Preload Crashes (`SIGSEGV` / Deadlocks)** | FerroOS injects `libmimalloc.so.2` and `libferro_io.so` globally via `/etc/ld.so.preload`. Legacy C binaries that call glibc-internal `mallinfo()`, apps with bundled allocators (`jemalloc` in Redis/Valkey), or debuggers (`strace`, `gdb`, `valgrind`) can crash or deadlock when their symbols are intercepted. | Add a process-name exclusion guard inside `libferro_io.so` constructor (`/proc/self/comm` bypass list for `strace`, `gdb`, `gcc`, `dpkg`, `apt-get`) and transition from blind `/etc/ld.so.preload` to service-scoped `LD_PRELOAD` in `ferro-init`. | `[ ] Open` |
| **CMP-002** | **Symlink Overwrite Collisions (`ferro-core` vs. `dpkg`)** | If `ferro-core --install-symlinks /bin` overwrites `/bin/ip` or `/bin/ps`, installing `iproute2` or `procps` via `rpk`/`apt` causes `dpkg` file-conflict errors or wipes out `ferro-core` links. Furthermore, Debian maintainer scripts (`postinst`) often pass GNU-specific flags that minimal Rust applets reject. | Install `ferro-core` applet symlinks into an isolated priority directory (`/usr/local/ferro/bin`) or register `dpkg-divert` rules, preserving standard GNU binaries in `/bin` and `/usr/bin` for package installation scripts. | `[ ] Open` |
| **CMP-003** | **`GLIBC_2.38+` Symbol Version Mismatch** | The Debian 12 Bookworm substrate uses `glibc 2.36`. Pre-compiled third-party binaries or `.rpk` packages built on Ubuntu 24.04 (`glibc 2.39`) or Fedora 40 will fail at launch with `version 'GLIBC_2.38' not found`. | Have `rpk` inspect ELF symbol requirements (`readelf -V`) prior to installation; either upgrade the base libc to Debian Trixie (`glibc 2.40+`) or provide an isolated newer-glibc compatibility runtime path. | `[ ] Open` |
| **CMP-004** | **Stale Shared-Library Cache (`ld.so.cache`)** | Unpacking optional C libraries (`@c-compat-libs`) without rebuilding the dynamic linker cache causes apps to fail with `cannot open shared object file: No such file or directory`. | Enforce an automatic `ldconfig` trigger and an `ldd` unresolved-symbol health check at the end of every `rpk install` or `rpk rollback` transaction. | `[ ] Open` |
| **CMP-005** | **Package Database Split-Brain After Rollback** | If a Btrfs rollback restores `/usr` without restoring `/var/lib/dpkg` and `/var/lib/rpk`, the package manager thinks libraries are installed when their `.so` files were rolled back. | Keep `/usr`, `/etc`, `/var/lib/dpkg`, and `/var/lib/rpk` inside the **same atomic root subvolume (`@rootfs`)**, isolating only logs (`/var/log`) and database data (`/var/lib/postgresql`) into separate subvolumes. | `[ ] Open` |

## 6. User-Recommended Changes & Future Backlog

This section logs all user-directed architectural decisions and upcoming requirements.

| ID | Date Added | Requested Change / Requirement | Target Component | Priority | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **USR-001** | 2026-10-25 | Provide single-command software installation and update parity with standard Linux (`rpk update` / `rpk upgrade` with Debian `apt` fallback and Btrfs snapshot rollback). | `crates/ferro-pkg` (`rpk`) | High | `[ ] Open` |
| **USR-002** | 2026-10-25 | Support the 40+ legacy/standard C libraries, toolchains, and legacy admin commands as **optional installable `rpk` profiles** (`@c-compat-libs`, `@c-toolchain`, `@sre-forensics`, `@legacy-sysv-compat`) so the base OS stays lean while users who need legacy C support can enable it with one command. | `crates/ferro-pkg` & `Dockerfile.server` | High | `[ ] Open` |
| **USR-003** | 2026-10-25 | Audit and prevent compatibility bugs, `LD_PRELOAD` allocator crashes, symlink overwrites, and `glibc` version mismatches when optional C libraries and hybrid packages are installed (`CMP-001` through `CMP-005`). | `libferro_io`, `ferro-core`, `ferro-pkg` | High | `[ ] Open` |
| **USR-004** | 2026-10-25 | Comprehensive Software Deployment & Full OS Stress Testing: Deploy real software stacks (Python, Node, Go, databases), stress system runtime libraries, audit OS interactions, runtime crashes, and API integrations. | Testing & Quality Engineering | High | `[ ] Open` |
