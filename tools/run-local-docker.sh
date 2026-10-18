#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "=========================================================="
echo "  Launching FerroOS Live Web Desktop in Local Docker      "
echo "=========================================================="

# Ensure release binaries exist
if [ ! -f "build_out/vmlinuz" ] || [ ! -f "build_out/initramfs.cpio.gz" ]; then
    mkdir -p build_out
    echo "--> Downloading verified kernel and initramfs..."
    curl -sSL -f -o build_out/vmlinuz "https://github.com/Praveen-1308/ferro-os/releases/download/v0.1.0/vmlinuz"
    curl -sSL -f -o build_out/initramfs.cpio.gz "https://github.com/Praveen-1308/ferro-os/releases/download/v0.1.0/initramfs.cpio.gz"
fi

echo "--> Building local Docker container..."
docker build -t ferro-os-desktop .

echo "--> Starting FerroOS Web Desktop container on port 6080..."
docker rm -f ferro-os-web 2>/dev/null || true
docker run -d --name ferro-os-web -p 6080:6080 ferro-os-desktop

echo "=========================================================="
echo "  FerroOS is live! Open your browser to:                  "
echo "  http://localhost:6080/vnc.html?autoconnect=true         "
echo "=========================================================="
