# FerroOS Distribution & Bootable ISO Engine (Track 1)

This directory provides the distribution packaging system for **FerroOS 3.0**, turning the pure-Rust userland into a bootable ISO image running on bare-metal or virtual machines (QEMU, VirtualBox, VMware, Bare Metal).

---

## Architecture Overview

```
                      +-----------------------------+
                      |   BIOS / UEFI Firmware      |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |       GRUB 2 Bootloader     |
                      |   (/boot/grub/grub.cfg)     |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |  Linux LTS Kernel (vmlinuz) |
                      |    (Mounts Devtmpfs & init) |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |   FerroOS Initramfs (CPIO)  |
                      |   /init (ferro-init, PID 1) |
                      +--------------+--------------+
                                     |
                                     v
       +-----------------------------------------------------------+
       |                  FerroOS Userland                         |
       |  - /bin/ferro-core (220 Multi-Call Applets)              |
       |  - /bin/rpk (Package Manager)                             |
       |  - /etc/{passwd, group, shadow, os-release, hostname}     |
       |  - Interactive Shell, Process Ledger, Networking, etc.    |
       +-----------------------------------------------------------+
```

---

## Quick Start

### 1. Build the Initramfs
Packages `ferro-init`, `ferro-core` (with 220 applet symlinks), `ferro-pkg` (`rpk`), and standard `/etc` configuration files:
```bash
make initramfs
# Output: distro/build/initramfs.img (1.4MB)
```

### 2. Build the Bootable ISO
Packages the kernel, GRUB bootloader configuration, and initramfs into a standard ISO image:
```bash
make iso
# Output: distro/build/ferro-os-3.0.0.iso
```

### 3. Test in QEMU
```bash
make run
```
Or directly:
```bash
qemu-system-x86_64 -cdrom distro/build/ferro-os-3.0.0.iso -m 512M -serial mon:stdio
```
