#!/usr/bin/env bash
set -euo pipefail

echo "=========================================================="
echo "  FerroOS: Running Automated Headless QEMU Boot Test      "
echo "=========================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_ROOT/build_out"
INITRD="$BUILD_DIR/initramfs.cpio.gz"
LOG_FILE="$BUILD_DIR/qemu_boot.log"

if [ ! -f "$INITRD" ]; then
    echo "ERROR: Initramfs not found at $INITRD. Run build-rootfs.sh first."
    exit 1
fi

# Locate host Linux kernel
KERNEL=$(ls -1 /boot/vmlinuz* 2>/dev/null | head -n1 || true)
if [ -z "$KERNEL" ] || [ ! -f "$KERNEL" ]; then
    echo "ERROR: No Linux kernel found in /boot/vmlinuz*."
    exit 1
fi

echo "Using Kernel:  $KERNEL"
echo "Using Initramfs: $INITRD"
echo "Starting QEMU test (timeout 20s)..."

# Ensure /etc/init.d/rcS triggers poweroff in CI test mode so QEMU exits cleanly
# Run QEMU with timeout
set +e
timeout 20s qemu-system-x86_64 \
    -kernel "$KERNEL" \
    -initrd "$INITRD" \
    -append "console=ttyS0 quiet panic=1" \
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

if grep -q "SUCCESS: Python" "$LOG_FILE"; then
    echo " [PASSED] FerroOS booted successfully and executed Python 3 on Rust PID 1!"
    exit 0
else
    echo " [FAILED] Expected success message not found in QEMU boot log."
    exit 1
fi
