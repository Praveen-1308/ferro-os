#!/usr/bin/env bash
set -euo pipefail

echo "=========================================================="
echo "  FerroOS: Running Automated Headless QEMU Boot Test      "
echo "=========================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_ROOT/build_out"
INITRD="$BUILD_DIR/initramfs.cpio.gz"
KERNEL="$BUILD_DIR/vmlinuz"
LOG_FILE="$BUILD_DIR/qemu_boot.log"

if [ ! -f "$INITRD" ]; then
    echo "ERROR: Initramfs not found at $INITRD. Run build-rootfs.sh first."
    exit 1
fi

if [ ! -f "$KERNEL" ]; then
    echo "ERROR: Kernel not found at $KERNEL."
    exit 1
fi

echo "Using Kernel:    $KERNEL"
echo "Using Initramfs: $INITRD"
echo "Starting QEMU test (timeout 25s)..."

set +e
timeout 25s qemu-system-x86_64 \
    -kernel "$KERNEL" \
    -initrd "$INITRD" \
    -append "console=ttyS0 quiet panic=1 ferro.test=1" \
    -nographic \
    -m 256M \
    -no-reboot \
    > "$LOG_FILE" 2>&1
QEMU_EXIT=$?
set -e

echo "QEMU Output:"
echo "----------------------------------------------------------"
cat "$LOG_FILE"
echo "----------------------------------------------------------"

if grep -q "SUCCESS: All core system capabilities verified!" "$LOG_FILE"; then
    echo " [PASSED] FerroOS booted, tested rpk package manager, executed Python 3, and verified all core capabilities on Rust PID 1!"
    exit 0
else
    echo " [FAILED] Expected success message not found in QEMU boot log."
    exit 1
fi
