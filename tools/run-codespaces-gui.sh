#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "  Launching FerroOS Live Interactive Web Desktop          "
echo "=========================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# 1. Build rootfs & kernel if missing
if [ ! -f "build_out/initramfs.cpio.gz" ] || [ ! -f "build_out/vmlinuz" ]; then
    echo "--> 1. Building FerroOS workspace and rootfs..."
    ./build/build-rootfs.sh
    KERNEL=$(ls -1 /boot/vmlinuz* 2>/dev/null | head -n1 || true)
    if [ -n "$KERNEL" ]; then
        sudo cp "$KERNEL" build_out/vmlinuz
        sudo chmod +r build_out/vmlinuz
    fi
fi

# 2. Kill any stale processes
pkill -f "qemu-system-x86_64" 2>/dev/null || true
pkill -f "websockify" 2>/dev/null || true

# 3. Launch QEMU with VNC on :0 (port 5900)
echo "--> 2. Starting QEMU with VNC display on localhost:5900..."
qemu-system-x86_64 \
    -kernel build_out/vmlinuz \
    -initrd build_out/initramfs.cpio.gz \
    -append "console=ttyS0 quiet vga=792" \
    -vga std \
    -vnc :0 \
    -m 512M \
    &
QEMU_PID=$!

echo "--> 3. Starting noVNC WebSocket Gateway on port 6080..."
NOVNC_DIR="/usr/share/novnc"
if [ ! -d "$NOVNC_DIR" ]; then
    NOVNC_DIR="/usr/share/novnc-core"
fi

echo "=========================================================="
echo "  FerroOS is now LIVE!                                    "
echo "  Click the 'Ports' tab in VS Code / Codespaces, then     "
echo "  click the globe icon on port 6080 to open the desktop.  "
echo "=========================================================="

# Run websockify attached to port 6080
websockify --web "$NOVNC_DIR" 6080 localhost:5900
