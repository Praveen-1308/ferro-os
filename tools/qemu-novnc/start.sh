#!/bin/bash
set -e

echo "================================================================================"
echo "          FERRO-OS PURE-RUST (<3MB) QEMU + noVNC WEB RUNNER                     "
echo "================================================================================"

# Boot QEMU with VNC on port 5900
# VGA display at 1024x768 (vga=792)
echo "--> Starting QEMU with pure-Rust OS on VNC:5900..."
qemu-system-x86_64 \
    -m 512M \
    -kernel /os/vmlinuz \
    -initrd /os/initramfs.cpio.gz \
    -append "console=tty0 console=ttyS0 quiet rdinit=/init vga=792" \
    -vga std \
    -vnc 127.0.0.1:0 \
    -no-reboot &

QEMU_PID=$!

echo "--> Waiting for QEMU VNC to be ready..."
sleep 2

echo "--> Starting noVNC Web Gateway on port 6080..."
exec websockify --web /usr/share/novnc 0.0.0.0:6080 127.0.0.1:5900
