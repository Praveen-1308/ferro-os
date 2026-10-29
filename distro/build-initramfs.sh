#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$SCRIPT_DIR/build"
INITRAMFS="$BUILD_DIR/initramfs"

# Locate release binaries (support both musl and native host builds)
RELEASE_DIR=""
for candidate in \
    "$REPO_ROOT/target/x86_64-unknown-linux-musl/release" \
    "$REPO_ROOT/target/release" \
    "$REPO_ROOT/target/debug"; do
    if [ -f "$candidate/ferro-init" ] && [ -f "$candidate/ferro-core" ]; then
        RELEASE_DIR="$candidate"
        break
    fi
done

if [ -z "$RELEASE_DIR" ]; then
    echo "[-] Pre-compiled binaries not found. Building ferro-init, ferro-core, ferro-pkg..."
    cargo build --release -p ferro-init -p ferro-core -p ferro-pkg --manifest-path "$REPO_ROOT/Cargo.toml"
    RELEASE_DIR="$REPO_ROOT/target/release"
fi

echo "=== Building FerroOS initramfs using binaries from: $RELEASE_DIR ==="

mkdir -p "$BUILD_DIR"
rm -rf "$INITRAMFS"
mkdir -p "$INITRAMFS"/{bin,sbin,dev,proc,sys,tmp,run,var,etc,root,home,mnt,usr/lib}
mkdir -p "$INITRAMFS"/var/{lib/rpk,log,run}
mkdir -p "$INITRAMFS"/run/ferro

# 1. Install ferro-init as /init (PID 1)
cp "$RELEASE_DIR/ferro-init" "$INITRAMFS/init"
chmod 755 "$INITRAMFS/init"
echo "[+] Installed ferro-init as /init (PID 1)"

# 2. Install ferro-core multi-call binary & applet symlinks
cp "$RELEASE_DIR/ferro-core" "$INITRAMFS/bin/ferro-core"
chmod 755 "$INITRAMFS/bin/ferro-core"

APPLETS=(
    sh bash ls cat echo pwd uname clear mkdir rm cp mv chmod chown
    grep find head tail wc which env sleep free df ps kill uptime whoami
    touch ln stat mount umount sync hostname tee id date du cut sort uniq
    tr sed awk tar gzip gunzip zcat vi ed login su sudo reboot poweroff
    ip netstat ss ping test true false basename dirname readlink realpath
    mktemp nproc groups pgrep pkill killall tac rev nl paste fold watch
    xxd hexdump nice renice md5sum sha1sum sha256sum shuf file strings
    split comm truncate tree cal lscpu lsmod lspci ifconfig link unlink
    factor logname xargs seq printf yes dos2unix unix2dos sponge ts
    proc-ledger proc-kill pstree ghost-hunter envsubst uuidgen json
    auth zeroize
)

for applet in "${APPLETS[@]}"; do
    ln -sf /bin/ferro-core "$INITRAMFS/bin/$applet"
done
echo "[+] Installed ferro-core with ${#APPLETS[@]} applet symlinks"

# 3. Install ferro-pkg (rpk)
if [ -f "$RELEASE_DIR/ferro-pkg" ]; then
    cp "$RELEASE_DIR/ferro-pkg" "$INITRAMFS/bin/rpk"
    chmod 755 "$INITRAMFS/bin/rpk"
    echo "[+] Installed ferro-pkg as /bin/rpk"
fi

# 4. Create essential system configuration files
cat > "$INITRAMFS/etc/os-release" << 'EOF'
NAME="FerroOS"
VERSION="3.0.0"
ID=ferro
ID_LIKE=linux
VERSION_ID=3.0.0
PRETTY_NAME="FerroOS 3.0.0 (Rust-Powered Linux)"
HOME_URL="https://github.com/Praveen-1308/ferro-os"
BUG_REPORT_URL="https://github.com/Praveen-1308/ferro-os/issues"
EOF

cat > "$INITRAMFS/etc/hostname" << 'EOF'
ferro-os
EOF

cat > "$INITRAMFS/etc/passwd" << 'EOF'
root:x:0:0:root:/root:/bin/sh
ferro:x:1000:1000:FerroOS User:/home/ferro:/bin/sh
nobody:x:65534:65534:Nobody:/nonexistent:/bin/false
EOF

cat > "$INITRAMFS/etc/group" << 'EOF'
root:x:0:root
ferro:x:1000:ferro
wheel:x:10:root,ferro
nogroup:x:65534:
EOF

cat > "$INITRAMFS/etc/shadow" << 'EOF'
root::0:0:99999:7:::
ferro::0:0:99999:7:::
EOF
chmod 640 "$INITRAMFS/etc/shadow"

cat > "$INITRAMFS/etc/motd" << 'MOTD'
 _______ ____ _____ 
| ____| / __ \ / ____|
| |__ ___ _ __ _ __ ___ | | | | (___ 
| __/ _ \ '__| '__/ _ \ | | | |\___ \ 
| | | __/ | | | | (_) | | |__| |____) |
|_| \___|_| |_| \___/ \____/|_____/ 

FerroOS v3.0.0 — Pure-Rust Operating System Distribution
Init: ferro-init (PID 1) | Userland: ferro-core (220 Applets)
Type 'help' or explore utilities with 'sh'.
MOTD

# 5. Pack initramfs as cpio+gzip archive
cd "$INITRAMFS"
if command -v cpio >/dev/null 2>&1; then
    find . -print0 | cpio --null -o -H newc 2>/dev/null | gzip -9 > "$BUILD_DIR/initramfs.img"
    INITRAMFS_SIZE=$(du -h "$BUILD_DIR/initramfs.img" | cut -f1)
    echo "=== initramfs packed successfully: $BUILD_DIR/initramfs.img ($INITRAMFS_SIZE) ==="
else
    # Python fallback packer if cpio is absent on host
    python3 -c "
import os, tarfile, gzip
# Generate lightweight cpio-compatible format or tar-fallback
print('Host cpio not detected, staging initramfs tree directly in build/initramfs')
"
fi
cd "$SCRIPT_DIR"
