#!/bin/bash
set -e

echo "================================================================================"
echo "          FERRO-OS PURE-RUST (<3MB) QEMU + noVNC WEB RUNNER                     "
echo "================================================================================"

# Boot QEMU with VNC on port 5900
# VGA display at 1024x768 (vga=792)
# console=tty0 so VGA display receives all terminal I/O and shell prompts
echo "--> Starting QEMU with pure-Rust OS on VNC:5900..."
run_qemu() {
    while true; do
        echo "--> Launching QEMU instance..."
        qemu-system-x86_64 \
            -m 512M \
            -kernel /os/vmlinuz \
            -initrd /os/initramfs.cpio.gz \
            -append "console=ttyS0 console=tty0 rdinit=/init vga=792" \
            -nic user,model=virtio-net-pci,hostfwd=tcp::8080-:8080 \
            -vga std \
            -serial file:/tmp/serial.log \
            -vnc 127.0.0.1:0 || true
        echo "--> QEMU exited. Restarting in 1s..."
        sleep 1
    done
}
run_qemu &

QEMU_PID=$!

echo "--> Waiting for QEMU VNC to be ready..."
sleep 2

echo "--> Starting noVNC Web Gateway on port 6080..."
exec websockify --web /usr/share/novnc 0.0.0.0:6080 127.0.0.1:5900
