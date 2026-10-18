#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "  Launching FerroOS Live Web Desktop in GitHub Codespaces "
echo "=========================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# 1. Ensure required dependencies are installed
if ! command -v qemu-system-x86_64 >/dev/null 2>&1 || ! command -v websockify >/dev/null 2>&1 || [ ! -d "/usr/share/novnc" ]; then
    echo "--> Installing QEMU, noVNC, and websockify in Codespaces..."
    sudo apt-get update
    sudo apt-get install -y qemu-system-x86 novnc websockify python3 cpio gzip net-tools
fi

# 2. Ensure /usr/share/novnc has an index.html so root / loads without 404/502
if [ -f "/usr/share/novnc/vnc.html" ] && [ ! -f "/usr/share/novnc/index.html" ]; then
    sudo ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html
fi

# 3. Build or update rootfs & kernel if missing
if [ ! -f "build_out/initramfs.cpio.gz" ] || [ ! -f "build_out/vmlinuz" ]; then
    echo "--> Building FerroOS rootfs & kernel..."
    ./build/build-rootfs.sh
    KERNEL=$(ls -1 /boot/vmlinuz* 2>/dev/null | head -n1 || true)
    if [ -n "$KERNEL" ]; then
        sudo cp "$KERNEL" build_out/vmlinuz
        sudo chmod +r build_out/vmlinuz
    fi
fi

# 4. Clean up any stale QEMU or websockify instances
sudo pkill -9 -f "qemu-system-x86_64" 2>/dev/null || true
sudo pkill -9 -f "websockify" 2>/dev/null || true
sleep 1

# 5. Start QEMU with VNC display on 127.0.0.1:5900
echo "--> Starting QEMU with VNC on localhost:5900..."
qemu-system-x86_64 \
    -kernel build_out/vmlinuz \
    -initrd build_out/initramfs.cpio.gz \
    -append "console=ttyS0 quiet vga=792" \
    -vga std \
    -vnc 127.0.0.1:0 \
    -m 512M \
    -no-reboot \
    &
QEMU_PID=$!

# 6. Wait for QEMU VNC port 5900 to become available
echo "--> Waiting for QEMU VNC to initialize..."
for i in {1..20}; do
    if ! kill -0 "$QEMU_PID" 2>/dev/null; then
        echo "ERROR: QEMU exited unexpectedly. Check console output."
        exit 1
    fi
    if nc -z 127.0.0.1 5900 2>/dev/null || ss -tlpn | grep -q ":5900 "; then
        echo "--> QEMU VNC is active on port 5900!"
        break
    fi
    sleep 0.5
done

# 7. Start websockify gateway on port 6080
echo "=========================================================="
echo "  FerroOS Live Web Desktop is READY!                      "
echo "  Click port 6080 in the Ports tab, or navigate to:       "
echo "  http://localhost:6080/vnc.html?autoconnect=true         "
echo "=========================================================="

exec websockify --web /usr/share/novnc 6080 127.0.0.1:5900
