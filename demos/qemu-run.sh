#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=================================================="
echo "          FerroOS QEMU Unified Boot Launcher      "
echo "=================================================="

# 1. Detect QEMU binary
QEMU_BIN=""
for bin in qemu-system-x86_64 /opt/homebrew/bin/qemu-system-x86_64 /usr/local/bin/qemu-system-x86_64; do
    if command -v "$bin" >/dev/null 2>&1; then
        QEMU_BIN="$bin"
        break
    fi
done

if [ -z "$QEMU_BIN" ]; then
    echo "[-] QEMU (qemu-system-x86_64) not detected on your system."
    echo "[*] Installation instructions:"
    echo "    macOS:  brew install qemu"
    echo "    Ubuntu: sudo apt-get install qemu-system-x86"
    echo "    Arch:   sudo pacman -S qemu-system-x86"
    exit 1
fi

echo "[+] Detected QEMU: $QEMU_BIN"

# 2. Detect Hardware Acceleration
ACCEL_FLAG=""
if [ "$(uname)" = "Darwin" ]; then
    # Test if hvf is supported
    if "$QEMU_BIN" -accel help 2>&1 | grep -q hvf; then
        ACCEL_FLAG="-accel hvf"
        echo "[+] Using macOS Hypervisor Framework (HVF) acceleration"
    fi
elif [ "$(uname)" = "Linux" ] && [ -w /dev/kvm ]; then
    ACCEL_FLAG="-enable-kvm"
    echo "[+] Using Linux KVM hardware acceleration"
else
    echo "[*] Running with standard software emulation (TCG)"
fi

# 3. Mode Selection
MODE="${1:-}"

if [ -z "$MODE" ]; then
    echo ""
    echo "Select boot target:"
    echo "  1) Track 1: Bootable Linux Distribution ISO (distro/build/ferro-os-3.0.0.iso)"
    echo "  2) Track 2: Bare-Metal #![no_std] Microkernel (kernel/target/x86_64-unknown-none/release/ferro-kernel)"
    echo "  3) Track 2: Bare-Metal Kernel Headless (Serial Console stdio)"
    echo ""
    read -rp "Enter choice [1-3] (default 2): " CHOICE
    case "$CHOICE" in
        1) MODE="iso" ;;
        3) MODE="headless" ;;
        *) MODE="kernel" ;;
    esac
fi

case "$MODE" in
    iso|1)
        ISO_PATH="$REPO_ROOT/distro/build/ferro-os-3.0.0.iso"
        if [ ! -f "$ISO_PATH" ]; then
            echo "[*] ISO not found at $ISO_PATH. Building now..."
            "$REPO_ROOT/distro/build-iso.sh"
        fi
        echo "[+] Booting FerroOS Distribution ISO..."
        exec "$QEMU_BIN" \
            $ACCEL_FLAG \
            -cdrom "$ISO_PATH" \
            -m 512M \
            -serial mon:stdio
        ;;

    kernel|2)
        KERNEL_BIN="$REPO_ROOT/kernel/target/x86_64-unknown-none/release/ferro-kernel"
        if [ ! -f "$KERNEL_BIN" ]; then
            echo "[*] Kernel binary not found. Building now..."
            (cd "$REPO_ROOT/kernel" && cargo +nightly build --release --target x86_64-unknown-none)
        fi
        echo "[+] Booting FerroOS Bare-Metal #![no_std] Microkernel..."
        exec "$QEMU_BIN" \
            -kernel "$KERNEL_BIN" \
            -m 512M \
            -serial mon:stdio
        ;;

    headless|3)
        KERNEL_BIN="$REPO_ROOT/kernel/target/x86_64-unknown-none/release/ferro-kernel"
        if [ ! -f "$KERNEL_BIN" ]; then
            echo "[*] Kernel binary not found. Building now..."
            (cd "$REPO_ROOT/kernel" && cargo +nightly build --release --target x86_64-unknown-none)
        fi
        echo "[+] Booting FerroOS Bare-Metal Microkernel in Headless Mode..."
        exec "$QEMU_BIN" \
            -kernel "$KERNEL_BIN" \
            -m 512M \
            -display none \
            -serial stdio
        ;;

    *)
        echo "Unknown mode: $MODE (Supported: iso, kernel, headless)"
        exit 1
        ;;
esac
