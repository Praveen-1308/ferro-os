# ferro-pkg (`rpk`) 🦀📦
### High-Performance Hybrid Package Engine for FerroOS

`ferro-pkg` (aliased as `rpk`) is the native package manager for FerroOS. It bridges ultra-lean pure-Rust package management with the massive Debian 12 package repository.

---

## Key Features

1. **Native Pure-Rust Recipes (`.rpk`)**: Ultra-fast, zero-overhead tar.gz package archives with checksum verification and atomic extraction.
2. **Seamless APT Fallback Wrapper (PKG-002)**: When requesting packages not available natively, `rpk` automatically queries and installs standard Debian packages via `apt-get` with non-interactive flags (`DEBIAN_FRONTEND=noninteractive`).
3. **Enterprise Capability Profiles**:
   - `@sre-forensics`: Installs `strace`, `tcpdump`, `lsof`, `fuser`, `iproute2`, `iputils-ping`, `sysstat`, `bind9-dnsutils`, `nftables`, `iptables`, `wget`, `gnupg`, `libcap2-bin`.
   - `@c-compat-libs`: Installs 40+ C runtime shared libraries (`libnsl2`, `libtirpc3`, `libcrypt1`, `libstdc++6`, `libffi8`, `libssl3`, etc.).
   - `@c-toolchain`: Installs `gcc`, `g++`, `make`, `cmake`, `pkg-config`, `binutils`, `libc6-dev`.
   - `@legacy-sysv-compat`: Shims legacy `service` and `chkconfig` commands to `ferro-init`.
4. **Transactional Snapshots & Instant Rollback (PKG-003, CMP-005)**:
   - Captures Btrfs CoW snapshots (`@pre_update_<timestamp>`) when running on Btrfs subvolumes.
   - Falls back to transactional JSON manifests in `/var/lib/ferro-pkg/transactions/` on ext4/overlayfs.
   - Supports `rpk rollback` to instantaneously undo package installations or profile activations.
5. **Security & ABI Safeguards (CMP-003, CMP-004)**:
   - Verifies target ELF binary requirements (such as minimum `glibc` versions) prior to execution.
   - Automatically runs `ldconfig` post-installation to rebind dynamic shared library links.
   - Provides `rpk upgrade --security` for security-only patching.

---

## Command Usage

```bash
# Install a package (native recipe or apt fallback)
rpk install htop

# Install an enterprise capability profile
rpk install @sre-forensics
rpk install @c-compat-libs
rpk install @c-toolchain
rpk install @legacy-sysv-compat

# Revert the latest transaction or profile installation
rpk rollback

# Search available packages
rpk search curl

# Upgrade packages (or security-only)
rpk upgrade
rpk upgrade --security

# List installed packages and capability profiles
rpk list
```
