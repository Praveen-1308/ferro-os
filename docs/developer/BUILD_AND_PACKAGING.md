# FerroOS Build & Appliance Packaging Guide

This guide covers building the complete FerroOS userland, compiling release binaries, packaging specialized rootfs appliances, and booting bare-metal distributions inside QEMU.

---

## 1. Prerequisites

FerroOS requires:
* **Rust Toolchain**: Stable Rust 1.80+ (`cargo`, `rustc`).
* **Python**: Python 3.10+ (for build automation scripts).
* **Optional Virtualization**: QEMU (`qemu-system-x86_64`) for bare-metal testing, and Docker (if building container images from scratch).

---

## 2. Compiling the Rust Workspace

To compile all 9 pure-Rust crates in release mode:

```bash
cargo build --release --workspace
```

The resulting binaries will be placed in `target/release/`:
* `ferro-init` (~535 KB)
* `ferro-core` (~1.2 MB)
* `ferro-pkg` (~907 KB)
* `ferro-superd` (~483 KB)
* `ferrocage` (~503 KB)
* `ferro-gui` (~335 KB)
* `ferro-compositor` (~363 KB)
* `xdg-desktop-portal-ferro` (~323 KB)
* `libferro_io.so` (~319 KB)

*Total combined size of all userspace binaries is under 5 MB!*

---

## 3. Building Multi-Edition Appliances

FerroOS includes an automated builder script [`tools/build_pure_rust_os.py`](file:///home/tarun-kumar/Desktop/sample%20os%20/tools/build_pure_rust_os.py) that generates FHS 3.0 directory trees with UsrMerge, symlinks, security permissions, and compressed tarball appliances.

### Build All Appliances at Once:
```bash
python3 tools/build_pure_rust_os.py --edition all
```

### Build a Specific Target Edition:
```bash
# Cloud Server Edition (3.61 MB)
python3 tools/build_pure_rust_os.py --edition cloud

# Desktop & Web Edition (4.10 MB)
python3 tools/build_pure_rust_os.py --edition desktop

# Gaming & Proton Edition (4.10 MB)
python3 tools/build_pure_rust_os.py --edition gaming

# AS/400 Enterprise Edition (3.61 MB)
python3 tools/build_pure_rust_os.py --edition enterprise

# Universal Pure-Rust Master (4.10 MB)
python3 tools/build_pure_rust_os.py --edition universal
```

All generated archives are placed into [`build_out/`](file:///home/tarun-kumar/Desktop/sample%20os%20/build_out/), and structured build telemetry is saved to [`tools/reports/ferro_os_editions_build_report.json`](file:///home/tarun-kumar/Desktop/sample%20os%20/tools/reports/ferro_os_editions_build_report.json).

---

## 4. Bare-Metal Bootable ISO Creation & QEMU Boot

FerroOS can be compiled into a real, standalone, bootable hybrid ISO (`ISO9660 + ISOLINUX`) containing a real Linux kernel (6.1 LTS) and the pure-Rust initramfs.

### Build the Bare-Metal ISO:
```bash
python3 tools/build_real_ferro_os.py
```
* Generates: `build_out/ferro-os-live.iso` (approx. 11 MB).

### Boot in Headless QEMU Serial Console:
```bash
python3 tools/test_qemu_real_os.py
```
* Or run interactively via bash script:
```bash
./tools/run_qemu_pure_os.sh
```
FerroOS boots to an interactive prompt in **< 1.5 seconds**!
