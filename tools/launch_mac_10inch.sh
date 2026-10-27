#!/usr/bin/env bash
# tools/launch_mac_10inch.sh - Launch FerroOS on macOS in a Calibrated 10-Inch Window
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(dirname "$SCRIPT_DIR")"

echo "================================================================================"
echo "          FERRO-OS macOS 10-INCH WINDOW LAUNCHER (13\" MAC SCREEN)              "
echo "================================================================================"
echo "Your Screen: ~13-inch Retina Display"
echo "Target Window: 10-inch Diagonal (~960x600 pt / 1024x640 px)"
echo "--------------------------------------------------------------------------------"

# 1. Resize current macOS Terminal window to exactly 10-inch diagonal
if command -v osascript >/dev/null 2>&1; then
    echo "[*] Resizing Terminal window to a 10-inch diagonal frame on your 13\" screen..."
    osascript -e '
    tell application "Terminal"
        if (count of windows) > 0 then
            set bounds of front window to {140, 80, 1100, 680}
        end if
    end tell' 2>/dev/null || true
fi

echo ""
echo "Select how you would like to run FerroOS right now on your Mac:"
echo " [1] Interactive Pure-Rust Shell (Runs inside Docker on Mac - Instant <3MB)"
echo " [2] Web Graphical Desktop (noVNC in Safari/Chrome - 10-inch browser window)"
echo " [3] QEMU Bare-Metal Cocoa Window (Requires Homebrew QEMU)"
echo "--------------------------------------------------------------------------------"
read -r -p "Enter choice [1-3] (Default: 1): " CHOICE
CHOICE="${CHOICE:-1}"

case "$CHOICE" in
    1)
        echo ""
        echo "[*] Launching FerroOS pure-Rust interactive shell in a 10-inch window..."
        echo "[*] Type 'uname -a', 'free', 'ls -la', 'ps', or 'help' inside FerroOS."
        echo "[*] Type 'exit' to quit."
        echo "--------------------------------------------------------------------------------"
        
        # Check if ferro-os-pure image exists, else run from rootfs mount
        if docker image inspect ferro-os-pure:latest >/dev/null 2>&1; then
            exec docker run -it --rm --name ferro-mac-session --memory=64m ferro-os-pure:latest /usr/bin/sh
        else
            exec docker run -it --rm --name ferro-mac-session \
                -v "$WORKSPACE/build_out/pure_rust_rootfs":/rootfs \
                -w /home/ferro \
                alpine:latest /rootfs/usr/bin/ferro-core sh
        fi
        ;;

    2)
        echo ""
        echo "[*] Launching FerroOS Web Desktop Container..."
        docker stop ferro-desktop-10in 2>/dev/null || true
        docker rm ferro-desktop-10in 2>/dev/null || true
        
        docker run -d --name ferro-desktop-10in \
            -p 6080:6080 \
            --memory=2g \
            ferro-os-web:latest 2>/dev/null || {
                echo "[*] ferro-os-web not built locally yet. Building now..."
                docker build -t ferro-os-web:latest "$WORKSPACE"
                docker run -d --name ferro-desktop-10in -p 6080:6080 --memory=2g ferro-os-web:latest
            }

        echo "[+] Web Desktop is running on http://localhost:6080"
        echo "[*] Opening Safari/Chrome in a 10-inch sized window..."
        
        # Open browser in a sized window
        osascript -e '
        tell application "Safari"
            make new document with properties {URL:"http://localhost:6080/vnc.html?autoconnect=true"}
            set bounds of front window to {140, 80, 1100, 680}
            activate
        end tell' 2>/dev/null || open "http://localhost:6080/vnc.html?autoconnect=true"
        ;;

    3)
        if ! command -v qemu-system-x86_64 >/dev/null 2>&1; then
            echo "[-] QEMU is not installed on your Mac host."
            echo "[*] Install via Homebrew: brew install qemu"
            echo "[*] Then re-run this script and select [3]."
            exit 1
        fi
        
        echo "[*] Launching QEMU with 10-inch Cocoa Display (800x600 VESA)..."
        exec qemu-system-x86_64 \
            -m 512M \
            -kernel "$WORKSPACE/build_out/vmlinuz" \
            -initrd "$WORKSPACE/build_out/initramfs-pure.cpio.gz" \
            -append "console=tty0 vga=788 quiet rdinit=/init" \
            -vga std \
            -display cocoa
        ;;

    *)
        echo "Invalid selection."
        exit 1
        ;;
esac
