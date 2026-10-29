#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$SCRIPT_DIR/build"
ISODIR="$BUILD_DIR/isodir"
OUTPUT_ISO="$BUILD_DIR/ferro-os-3.0.0.iso"

echo "=== FerroOS Bootable ISO Generator (Track 1) ==="

# 1. Build initramfs if not already present
if [ ! -f "$BUILD_DIR/initramfs.img" ]; then
    echo "[*] initramfs.img not found. Generating now..."
    "$SCRIPT_DIR/build-initramfs.sh"
fi

# 2. Stage ISO Directory Tree
rm -rf "$ISODIR"
mkdir -p "$ISODIR/boot/grub"

# Copy GRUB config
cp "$SCRIPT_DIR/grub.cfg" "$ISODIR/boot/grub/grub.cfg"
# Copy initramfs
cp "$BUILD_DIR/initramfs.img" "$ISODIR/boot/initramfs.img"

# Optional: Copy bare-metal kernel if built (Track 2)
if [ -f "$REPO_ROOT/kernel/target/x86_64-ferro/release/ferro-kernel.bin" ]; then
    cp "$REPO_ROOT/kernel/target/x86_64-ferro/release/ferro-kernel.bin" "$ISODIR/boot/ferro-kernel.bin"
    echo "[+] Included Track 2 bare-metal kernel: /boot/ferro-kernel.bin"
fi

# Kernel check
if [ -f "$BUILD_DIR/vmlinuz" ]; then
    cp "$BUILD_DIR/vmlinuz" "$ISODIR/boot/vmlinuz"
elif [ -f "/boot/vmlinuz-$(uname -r 2>/dev/null || echo '')" ]; then
    cp "/boot/vmlinuz-$(uname -r)" "$ISODIR/boot/vmlinuz"
else
    # Create kernel placeholder note
    cat > "$ISODIR/boot/README-KERNEL.txt" << 'EOF'
Place your target x86_64 Linux kernel here as 'vmlinuz'.
Examples:
  - Any minimal Linux LTS kernel (e.g., from Alpine or Debian kernel packages)
  - Custom kernel compiled with minimal drivers: CONFIG_DEVTMPFS=y, CONFIG_BLK_DEV_INITRD=y
EOF
    echo "[!] Notice: Host Linux kernel not automatically detected in macOS environment."
    echo "[!] Staged ISO structure ready at: $ISODIR"
fi

# 3. Create ISO if tools are available
if command -v grub-mkrescue >/dev/null 2>&1; then
    echo "[*] Creating bootable ISO with grub-mkrescue..."
    grub-mkrescue -o "$OUTPUT_ISO" "$ISODIR"
    echo "[+] Bootable ISO created: $OUTPUT_ISO ($(du -h "$OUTPUT_ISO" | cut -f1))"
elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    echo "[*] grub-mkrescue not installed locally, running in Docker container..."
    docker run --rm \
        -v "$REPO_ROOT:/workspace" \
        -w /workspace/distro \
        debian:bookworm-slim \
        bash -c "apt-get update -qq && apt-get install -y -qq grub-pc-bin grub-efi-amd64-bin mtools xorriso >/dev/null && grub-mkrescue -o build/ferro-os-3.0.0.iso build/isodir"
    echo "[+] Bootable ISO created via Docker: $OUTPUT_ISO"
else
    echo "[-] grub-mkrescue / xorriso not installed on host."
    echo "[*] ISO staging tree is ready at: $ISODIR"
    echo "[*] To generate the ISO on Linux or with Homebrew/Docker:"
    echo "    grub-mkrescue -o distro/build/ferro-os-3.0.0.iso distro/build/isodir"
fi
