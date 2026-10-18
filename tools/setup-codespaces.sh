#!/usr/bin/env bash
set -euo pipefail

echo "=========================================================="
echo "  FerroOS: Pre-configuring Codespaces Environment         "
echo "=========================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "--> 1. Installing QEMU, noVNC, websockify, and Linux Kernel..."
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    qemu-system-x86 \
    novnc \
    websockify \
    python3 \
    python3-minimal \
    cpio \
    gzip \
    linux-image-virtual \
    net-tools \
    curl

echo "--> 2. Configuring noVNC root index..."
if [ -f "/usr/share/novnc/vnc.html" ]; then
    sudo ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html
fi

echo "--> 3. Pre-building FerroOS Workspace & Rootfs..."
./build/build-rootfs.sh

echo "--> 4. Extracting Linux Kernel for QEMU..."
KERNEL=$(ls -1 /boot/vmlinuz* 2>/dev/null | head -n1 || true)
if [ -n "$KERNEL" ] && [ -f "$KERNEL" ]; then
    mkdir -p build_out
    sudo cp "$KERNEL" build_out/vmlinuz
    sudo chmod +r build_out/vmlinuz
    sudo chown "$USER:$USER" build_out/vmlinuz
    echo "--> Kernel successfully cached at build_out/vmlinuz"
else
    echo "ERROR: Failed to locate kernel image."
    exit 1
fi

echo "=========================================================="
echo "  Codespaces Pre-configuration Complete! Ready to launch. "
echo "=========================================================="
