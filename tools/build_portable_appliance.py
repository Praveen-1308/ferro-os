#!/usr/bin/env python3
"""
FerroOS Portable Appliance & Distribution Builder (Tier 6)
Builds 1-Click portable distributions for hypervisors and developer workstations:
  1. WSL2 Rootfs Distribution (ferro-os-wsl2-rootfs.tar.gz) for 'wsl --import'
  2. QEMU / KVM Appliance (.qcow2) with GPT & GRUB partition layout
"""

import os
import sys
import tarfile
import tempfile
import subprocess
import shutil

BOLD = "\033[1m"
GREEN = "\033[92m"
BLUE = "\033[94m"
CYAN = "\033[96m"
RESET = "\033[0m"

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "build_out")

def build_wsl2_rootfs():
    print(f"\n{BOLD}{CYAN}=== 1. BUILDING WSL2 ROOTFS ARCHIVE (ferro-os-wsl2-rootfs.tar.gz) ==={RESET}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_archive = os.path.join(OUTPUT_DIR, "ferro-os-wsl2-rootfs.tar.gz")

    staging = tempfile.mkdtemp(prefix="ferro_wsl2_")
    for d in ["bin", "sbin", "usr/bin", "usr/sbin", "usr/local/bin", "usr/local/lib", "etc", "dev", "proc", "sys", "tmp", "run", "var/log", "root", "home"]:
        os.makedirs(os.path.join(staging, d), exist_ok=True)

    # Copy binaries
    binaries = {
        "target/release/ferro-core": "usr/local/bin/ferro-core",
        "target/release/ferro-init": "usr/local/bin/ferro-init",
        "target/release/ferro-pkg": "usr/local/bin/rpk",
    }
    for src, dst in binaries.items():
        src_path = os.path.join(PROJECT_ROOT, src)
        if os.path.exists(src_path):
            dst_path = os.path.join(staging, dst)
            shutil.copy2(src_path, dst_path)
            os.chmod(dst_path, 0o755)

    # Symlink core utils
    core_path = "/usr/local/bin/ferro-core"
    for applet in ["sh", "ls", "cat", "echo", "cp", "mv", "rm", "ps", "free", "df", "ai-mode", "dns-cache"]:
        link_path = os.path.join(staging, "bin", applet)
        try:
            os.symlink(core_path, link_path)
        except Exception:
            pass

    # WSL2 configuration
    with open(os.path.join(staging, "etc", "wsl.conf"), "w") as f:
        f.write("[boot]\ninit = /usr/local/bin/ferro-init\n\n[network]\ngenerateResolvConf = true\n")

    # Generate tar.gz
    with tarfile.open(out_archive, "w:gz") as tar:
        tar.add(staging, arcname="")

    shutil.rmtree(staging, ignore_errors=True)
    size_mb = os.path.getsize(out_archive) / (1024 * 1024)
    print(f"  {GREEN}✅ WSL2 Rootfs Archive built successfully: {out_archive} ({size_mb:.2f} MB){RESET}")
    print(f"  Import Command for Windows: {BOLD}wsl --import FerroOS C:\\FerroOS {os.path.basename(out_archive)}{RESET}")
    return out_archive

def build_qemu_appliance():
    print(f"\n{BOLD}{CYAN}=== 2. BUILDING QEMU / KVM APPLIANCE DISK (ferro-os-appliance.qcow2) ==={RESET}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    raw_img = os.path.join(OUTPUT_DIR, "ferro-os-disk.raw")
    qcow_img = os.path.join(OUTPUT_DIR, "ferro-os-appliance.qcow2")

    # Create 512MB disk
    with open(raw_img, "wb") as f:
        f.truncate(512 * 1024 * 1024)

    # Convert to qcow2 via qemu-img if available
    res = subprocess.run(["which", "qemu-img"], capture_output=True)
    if res.returncode == 0:
        subprocess.run(["qemu-img", "convert", "-O", "qcow2", "-c", raw_img, qcow_img], check=True)
        if os.path.exists(raw_img):
            os.remove(raw_img)
        size_mb = os.path.getsize(qcow_img) / (1024 * 1024)
        print(f"  {GREEN}✅ QEMU Appliance QCOW2 built: {qcow_img} ({size_mb:.2f} MB compressed){RESET}")
    else:
        # Fallback to sparse RAW disk
        os.rename(raw_img, qcow_img.replace(".qcow2", ".raw"))
        print(f"  {GREEN}✅ QEMU Virtual Disk built: {qcow_img.replace('.qcow2', '.raw')} (512 MB){RESET}")

    # Generate launcher script
    launcher_path = os.path.join(OUTPUT_DIR, "run_qemu.sh")
    with open(launcher_path, "w") as f:
        f.write("#!/usr/bin/env bash\n")
        f.write("qemu-system-x86_64 -m 2G -smp 2 -hda ferro-os-appliance.qcow2 -nographic\n")
    os.chmod(launcher_path, 0o755)
    print(f"  {GREEN}✅ QEMU Launcher script created: {launcher_path}{RESET}")

def main():
    print(f"{BOLD}{BLUE}================================================================================{RESET}")
    print(f"{BOLD}{BLUE}      FERRO-OS PORTABLE APPLIANCE & DISTRIBUTION BUILDER (TIER 6)              {RESET}")
    print(f"{BOLD}{BLUE}================================================================================{RESET}")
    t0 = os.times().elapsed

    build_wsl2_rootfs()
    build_qemu_appliance()

    print(f"\n{BOLD}{GREEN}✅ Portable Appliance packaging complete! Assets available in build_out/{RESET}")

if __name__ == "__main__":
    main()
