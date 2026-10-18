#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "  Launching FerroOS Live Web Desktop in GitHub Codespaces "
echo "=========================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# 1. Ensure required tools are installed
if ! command -v qemu-system-x86_64 >/dev/null 2>&1 || ! command -v websockify >/dev/null 2>&1 || [ ! -d "/usr/share/novnc" ]; then
    echo "--> Installing QEMU, noVNC, and websockify in Codespaces..."
    sudo apt-get update
    sudo apt-get install -y qemu-system-x86 novnc websockify python3 cpio gzip net-tools
fi

# 2. Ensure /usr/share/novnc has an index.html so root / loads cleanly
if [ -f "/usr/share/novnc/vnc.html" ] && [ ! -f "/usr/share/novnc/index.html" ]; then
    sudo ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html
fi

# 3. Ensure rootfs initramfs is built
if [ ! -f "build_out/initramfs.cpio.gz" ]; then
    echo "--> Ensuring FerroOS rootfs..."
    mkdir -p build_out
    if [ -f "build/build-rootfs.sh" ] && command -v cargo >/dev/null 2>&1; then
        echo "--> Building FerroOS rootfs from source..."
        ./build/build-rootfs.sh
    else
        echo "--> Downloading pre-verified FerroOS rootfs from GitHub Release..."
        curl -sSL -f -o build_out/initramfs.cpio.gz "https://github.com/Praveen-1308/ferro-os/releases/download/v0.1.0/initramfs.cpio.gz"
    fi
fi

# 4. Ensure Linux kernel (vmlinuz) exists in build_out/
if [ ! -f "build_out/vmlinuz" ]; then
    echo "--> Locating Linux kernel..."
    mkdir -p build_out
    KERNEL=$(ls -1 /boot/vmlinuz* 2>/dev/null | head -n1 || true)

    if [ -n "$KERNEL" ] && [ -f "$KERNEL" ]; then
        echo "--> Found local kernel at $KERNEL, copying to build_out/vmlinuz..."
        sudo cp "$KERNEL" build_out/vmlinuz
        sudo chmod +r build_out/vmlinuz
        sudo chown "$USER:$USER" build_out/vmlinuz 2>/dev/null || true
    else
        echo "--> Downloading verified FerroOS Linux kernel from GitHub Release..."
        if ! curl -sSL -f -o build_out/vmlinuz "https://github.com/Praveen-1308/ferro-os/releases/download/v0.1.0/vmlinuz"; then
            echo "--> Fallback: Installing Debian/Ubuntu kernel via apt..."
            sudo apt-get update || true
            sudo apt-get install -y --no-install-recommends linux-image-amd64 || \
            sudo apt-get install -y --no-install-recommends linux-image-cloud-amd64 || \
            sudo apt-get install -y --no-install-recommends linux-image-virtual || true
            KERNEL=$(ls -1 /boot/vmlinuz* 2>/dev/null | head -n1 || true)
            if [ -n "$KERNEL" ] && [ -f "$KERNEL" ]; then
                sudo cp "$KERNEL" build_out/vmlinuz
                sudo chmod +r build_out/vmlinuz
                sudo chown "$USER:$USER" build_out/vmlinuz 2>/dev/null || true
            fi
        fi
    fi

    if [ ! -f "build_out/vmlinuz" ]; then
        echo "ERROR: Unable to acquire Linux kernel (vmlinuz)."
        exit 1
    fi
    echo "--> Kernel successfully prepared at build_out/vmlinuz"
fi

# 5. Clean up any stale QEMU or websockify instances cleanly
set +e
sudo killall -q -9 qemu-system-x86_64 websockify 2>/dev/null
set -e
sleep 1

# 6. Start QEMU with VNC display on 127.0.0.1:5900
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

# 7. Wait for QEMU VNC port 5900 to become available
echo "--> Waiting for QEMU VNC to initialize..."
for i in {1..20}; do
    if ! kill -0 "$QEMU_PID" 2>/dev/null; then
        echo "ERROR: QEMU exited unexpectedly. Check console output."
        exit 1
    fi
    if nc -z 127.0.0.1 5900 2>/dev/null || ss -tlpn 2>/dev/null | grep -q ":5900 "; then
        echo "--> QEMU VNC is active on port 5900!"
        break
    fi
    sleep 0.5
done

# 8. Start websockify gateway on port 6080
echo "=========================================================="
echo "  FerroOS Live Web Desktop is READY!                      "
echo "  Click port 6080 in the Ports tab, or navigate to:       "
echo "  http://localhost:6080/vnc.html?autoconnect=true         "
echo "=========================================================="

exec websockify --web /usr/share/novnc 6080 127.0.0.1:5900
