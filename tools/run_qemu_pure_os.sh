#!/usr/bin/env bash
# tools/run_qemu_pure_os.sh - 1-Click Interactive QEMU Launcher for FerroOS Pure-Rust (<3MB)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(dirname "$SCRIPT_DIR")"
BUILD_OUT="$WORKSPACE/build_out"
ROOTFS="$BUILD_OUT/pure_rust_rootfs"
INITRD="$BUILD_OUT/initramfs-pure.cpio.gz"
KERNEL="$BUILD_OUT/vmlinuz"

echo "================================================================================"
echo "          FERRO-OS PURE-RUST (<3MB) INTERACTIVE QEMU LAUNCHER                   "
echo "================================================================================"

# 1. Check for QEMU installation
if ! command -v qemu-system-x86_64 >/dev/null 2>&1; then
    echo "[-] qemu-system-x86_64 not found."
    echo "[*] On Ubuntu/Debian: sudo apt-get update && sudo apt-get install -y qemu-system-x86"
    echo "[*] On Fedora/RHEL:   sudo dnf install -y qemu-system-x86"
    echo "[*] On Arch Linux:    sudo pacman -S qemu-system-x86"
    exit 1
fi

# 2. Ensure rootfs and initramfs exist
if [ ! -d "$ROOTFS" ]; then
    echo "[*] Building pure-Rust rootfs first via tools/build_pure_rust_os.py..."
    python3 "$WORKSPACE/tools/build_pure_rust_os.py"
fi

if [ ! -f "$INITRD" ]; then
    echo "[*] Compressing pure-Rust rootfs into $INITRD (<3MB)..."
    mkdir -p "$BUILD_OUT"
    (cd "$ROOTFS" && find . | cpio -H newc -o 2>/dev/null | gzip -9 > "$INITRD")
    INITRD_SIZE=$(du -h "$INITRD" | cut -f1)
    echo "[+] Generated compact initramfs: $INITRD ($INITRD_SIZE)"
fi

# 3. Ensure Kernel (vmlinuz) exists
if [ ! -f "$KERNEL" ]; then
    echo "[*] Locating Linux kernel..."
    LOCAL_KERNEL=$(ls -1 /boot/vmlinuz* 2>/dev/null | head -n1 || true)
    if [ -n "$LOCAL_KERNEL" ] && [ -f "$LOCAL_KERNEL" ]; then
        echo "[+] Found local kernel at $LOCAL_KERNEL. Copying to $KERNEL..."
        cp "$LOCAL_KERNEL" "$KERNEL"
        chmod +r "$KERNEL"
    else
        echo "[-] Could not find a kernel in /boot/vmlinuz*. Please specify or copy a Linux kernel to $KERNEL."
        exit 1
    fi
fi

# 4. Check for hardware virtualization (KVM)
KVM_FLAGS=""
if [ -e "/dev/kvm" ] && [ -r "/dev/kvm" ] && [ -w "/dev/kvm" ]; then
    echo "[+] Hardware KVM acceleration detected (/dev/kvm). Enabling -enable-kvm -cpu host."
    KVM_FLAGS="-enable-kvm -cpu host"
else
    echo "[*] Running with standard QEMU software emulation (TCG)."
fi

INITRD_SIZE=$(du -h "$INITRD" | cut -f1)
ROOTFS_SIZE=$(du -sh "$ROOTFS" | cut -f1)
echo "--------------------------------------------------------------------------------"
echo "  Initramfs Size: $INITRD_SIZE (Compressed)"
echo "  RootFS Size:    $ROOTFS_SIZE (Uncompressed)"
echo "  Kernel Image:   $KERNEL"
echo "  Memory Target:  512 MB"
echo "  Serial Console: ttyS0 (Attached directly to your current terminal)"
echo "--------------------------------------------------------------------------------"
echo "  * HOW TO INTERACT: Type commands directly when the FerroOS shell prompt appears."
echo "  * HOW TO EXIT:     Type 'poweroff' inside the shell, or press [Ctrl+A] then [X]."
echo "--------------------------------------------------------------------------------"
echo "Booting FerroOS in 2 seconds..."
sleep 2

# 5. Boot QEMU with direct serial interaction
exec qemu-system-x86_64 \
    -m 512M \
    ${KVM_FLAGS} \
    -kernel "$KERNEL" \
    -initrd "$INITRD" \
    -append "console=ttyS0 panic=1 quiet rdinit=/init" \
    -nographic \
    -no-reboot
