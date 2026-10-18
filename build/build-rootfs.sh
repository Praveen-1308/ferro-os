#!/usr/bin/env bash
set -euo pipefail

echo "=========================================================="
echo "  FerroOS: Building Root Filesystem with Python 3 & Rust  "
echo "=========================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_ROOT/build_out"
ROOTFS="$BUILD_DIR/rootfs"

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR" "$ROOTFS"

echo "--> 1. Compiling FerroOS Rust Workspace (Release)..."
cd "$PROJECT_ROOT"
cargo build --release

echo "--> 2. Creating POSIX Filesystem Layout..."
mkdir -p "$ROOTFS"/{bin,sbin,etc,etc/init.d,proc,sys,dev,tmp,usr/bin,usr/lib,usr/lib64,lib,lib64,var,var/run}

echo "--> 3. Installing ferro-init (PID 1) and ferro-core..."
cp "$PROJECT_ROOT/target/release/ferro-init" "$ROOTFS/init"
cp "$PROJECT_ROOT/target/release/ferro-init" "$ROOTFS/sbin/init"
chmod +x "$ROOTFS/init" "$ROOTFS/sbin/init"

cp "$PROJECT_ROOT/target/release/ferro-core" "$ROOTFS/bin/ferro-core"
chmod +x "$ROOTFS/bin/ferro-core"

# Create symlinks for all applets
for applet in sh ls cat echo pwd uname clear mkdir rm; do
    ln -sf /bin/ferro-core "$ROOTFS/bin/$applet"
done
for applet in reboot poweroff; do
    ln -sf /bin/ferro-core "$ROOTFS/sbin/$applet"
done

echo "--> 4. Packaging Standard C Library (glibc) & Python 3 Runtime..."
# Locate host dynamic linker and core libraries
if [ -f /lib64/ld-linux-x86-64.so.2 ]; then
    cp /lib64/ld-linux-x86-64.so.2 "$ROOTFS/lib64/"
fi

# Copy Python 3 binary and resolve shared library dependencies
PYTHON_BIN="$(which python3)"
mkdir -p "$ROOTFS/$(dirname "$PYTHON_BIN")"
cp "$PYTHON_BIN" "$ROOTFS/$PYTHON_BIN"

copy_deps() {
    local bin="$1"
    ldd "$bin" | grep "=>" | awk '{print $3}' | while read -r lib; do
        if [ -f "$lib" ]; then
            local dir="$ROOTFS/$(dirname "$lib")"
            mkdir -p "$dir"
            cp -n "$lib" "$dir/" 2>/dev/null || true
        fi
    done
    # Also copy the interpreter
    local interp
    interp="$(ldd "$bin" | grep -o '/lib[^ ]*' | head -n1 || true)"
    if [ -n "$interp" ] && [ -f "$interp" ]; then
        mkdir -p "$ROOTFS/$(dirname "$interp")"
        cp -n "$interp" "$ROOTFS/$interp" 2>/dev/null || true
    fi
}

copy_deps "$PYTHON_BIN"
copy_deps "$PROJECT_ROOT/target/release/ferro-init"
copy_deps "$PROJECT_ROOT/target/release/ferro-core"

# Copy standard Python 3 standard library
PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_LIB_DIR="/usr/lib/python$PY_VERSION"
if [ -d "$PY_LIB_DIR" ]; then
    mkdir -p "$ROOTFS/usr/lib/python$PY_VERSION"
    cp -r "$PY_LIB_DIR"/* "$ROOTFS/usr/lib/python$PY_VERSION/" 2>/dev/null || true
fi

echo "--> 5. Creating Startup Scripts & Configuration..."
cat << 'EOF' > "$ROOTFS/etc/init.d/test.py"
import sys
print(f">>> SUCCESS: Python {sys.version.split()[0]} is running natively on FerroOS (Rust PID 1)! <<<")
EOF

cat << 'EOF' > "$ROOTFS/etc/init.d/rcS"
echo "---------------------------------------------------------"
echo "  FerroOS Early Startup: rcS                             "
echo "---------------------------------------------------------"
echo "[rcS] Verifying Python 3 execution on FerroOS..."
python3 /etc/init.d/test.py
echo "---------------------------------------------------------"
poweroff
EOF
chmod +x "$ROOTFS/etc/init.d/rcS"

cat << 'EOF' > "$ROOTFS/etc/hostname"
ferro-os
EOF

echo "--> 6. Packaging into Compressed initramfs..."
cd "$ROOTFS"
find . -print0 | cpio --null --create --format=newc | gzip -9 > "$BUILD_DIR/initramfs.cpio.gz"

echo "=========================================================="
echo "  Build Complete! Initramfs ready at:                    "
echo "  $BUILD_DIR/initramfs.cpio.gz                           "
echo "=========================================================="
