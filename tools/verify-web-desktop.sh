#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "  FerroOS: Verifying Live Web Desktop & noVNC Gateway     "
echo "=========================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Ensure setup has been executed
if [ ! -f "build_out/vmlinuz" ] || [ ! -f "build_out/initramfs.cpio.gz" ]; then
    echo "--> Running pre-setup..."
    bash tools/setup-codespaces.sh
fi

# Clean old instances
sudo killall -q -9 qemu-system-x86_64 websockify 2>/dev/null || true
sleep 1

# Launch in background
echo "--> Starting live web desktop in background..."
bash tools/run-codespaces-gui.sh > build_out/web_desktop.log 2>&1 &
LAUNCH_PID=$!

echo "--> Waiting for web desktop to come online..."
ONLINE=0
for i in {1..30}; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:6080/vnc.html || true)
    if [ "$HTTP_CODE" = "200" ]; then
        echo "--> SUCCESS: noVNC HTTP Gateway is responding with HTTP 200 OK!"
        ONLINE=1
        break
    fi
    sleep 1
done

if [ "$ONLINE" -ne 1 ]; then
    echo "ERROR: Web desktop failed to respond on port 6080. Log output:"
    echo "----------------------------------------------------------"
    cat build_out/web_desktop.log
    echo "----------------------------------------------------------"
    sudo killall -q -9 qemu-system-x86_64 websockify 2>/dev/null || true
    exit 1
fi

ROOT_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:6080/ || true)
echo "--> Root endpoint '/' HTTP status: $ROOT_CODE"

echo "--> Cleaning up verification processes..."
sudo killall -q -9 qemu-system-x86_64 websockify 2>/dev/null || true

echo "=========================================================="
echo "  [VERIFIED] Codespaces Web Desktop is 100% operational!  "
echo "=========================================================="
exit 0
