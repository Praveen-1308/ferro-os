#!/usr/bin/env bash
set -euo pipefail

echo "=========================================================="
echo "  FerroOS: Pre-configuring Codespaces Environment         "
echo "=========================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "--> 1. Installing QEMU, noVNC, and websockify..."
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    qemu-system-x86 \
    novnc \
    websockify \
    python3 \
    python3-minimal \
    cpio \
    gzip \
    net-tools \
    curl

echo "--> 2. Configuring noVNC root index..."
if [ -f "/usr/share/novnc/vnc.html" ]; then
    sudo ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html
fi

echo "--> 3. Pre-building FerroOS Workspace & Rootfs..."
mkdir -p build_out
if [ -f "build/build-rootfs.sh" ] && command -v cargo >/dev/null 2>&1; then
    ./build/build-rootfs.sh
else
    echo "--> Downloading pre-built initramfs..."
    curl -sSL -f -o build_out/initramfs.cpio.gz "https://github.com/Praveen-1308/ferro-os/releases/download/v0.1.0/initramfs.cpio.gz"
fi

echo "--> 4. Acquiring Linux Kernel for QEMU..."
KERNEL=$(ls -1 /boot/vmlinuz* 2>/dev/null | head -n1 || true)
if [ -n "$KERNEL" ] && [ -f "$KERNEL" ]; then
    sudo cp "$KERNEL" build_out/vmlinuz
    sudo chmod +r build_out/vmlinuz
    sudo chown "$USER:$USER" build_out/vmlinuz 2>/dev/null || true
    echo "--> Kernel successfully cached at build_out/vmlinuz"
else
    echo "--> Downloading verified kernel from GitHub Release..."
    curl -sSL -f -o build_out/vmlinuz "https://github.com/Praveen-1308/ferro-os/releases/download/v0.1.0/vmlinuz"
    chmod +r build_out/vmlinuz
    echo "--> Kernel successfully downloaded to build_out/vmlinuz"
fi

echo "=========================================================="
echo "  Codespaces Pre-configuration Complete! Ready to launch. "
echo "=========================================================="
