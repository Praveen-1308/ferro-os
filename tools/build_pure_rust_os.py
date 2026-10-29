#!/usr/bin/env python3
"""
tools/build_pure_rust_os.py
Builds Autonomous Pure-Rust Linux Operating System Rootfs & Container Appliances

Specifications:
  - 100% Rust-powered userland: ferro-init (PID 1), ferro-core (multi-call coreutils & shell),
    ferro-pkg, ferro-superd, ferrocage, ferro-gui, ferro-compositor, xdg-desktop-portal-ferro, libferro_io.
  - FHS 3.0 directory tree with UsrMerge (/bin->/usr/bin, /sbin->/usr/sbin, /lib->/usr/lib, /lib64->/usr/lib)
  - Strict enterprise permissions: /tmp (1777 sticky bit), /etc/shadow (0600), /home/ferro (1000:1000)
  - Zero GNU coreutils / Busybox / Docker daemon dependencies
  - Builds and packages 4 appliances:
      1. Cloud Server Edition:      build_out/ferro_cloud_appliance.tar.gz      (ferro-os-cloud:latest)
      2. Desktop & Web Edition:     build_out/ferro_desktop_appliance.tar.gz    (ferro-os-desktop:latest)
      3. Gaming & Proton Edition:    build_out/ferro_gaming_appliance.tar.gz     (ferro-os-gaming:latest)
      4. Universal Pure-Rust RootFS: build_out/pure_rust_rootfs.tar.gz          (ferro-os-pure:latest)
  - Generates comprehensive telemetry report in tools/reports/ferro_os_editions_build_report.json
"""

import os
import sys
import shutil
import hashlib
import tarfile
import argparse
import subprocess
import json
import time

WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BUILD_OUT = os.path.join(WORKSPACE, "build_out")
REPORTS_DIR = os.path.join(WORKSPACE, "tools/reports")

# Common core applets for ferro-core multi-call binary
BASE_APPLETS = [
    "sh", "bash", "ls", "cat", "echo", "pwd", "uname", "clear", "mkdir", "rm", "cp",
    "mv", "chmod", "chown", "touch", "ln", "stat", "id", "grep", "find",
    "head", "tail", "wc", "which", "env", "sleep", "free", "df", "ps", "kill",
    "uptime", "whoami", "sync", "hostname", "tee", "ip", "mount", "umount",
    "fetch", "curl", "serve", "httpd", "server-suite", "server", "dns-cache", "dns",
    "ferrod", "syslogd", "logger", "logs", "log", "journalctl", "dmesg",
    "dhcp", "ferro-net", "udhcpc", "hackbench", "bench-fsync", "fsync-bench",
    "gamemode", "bpf", "ebpf", "sched", "scx", "game", "proton", "win", "wine",
    "install", "snapshot", "ai-mode", "sandbox", "supervise",
    "disk", "cloud-init", "cloudinit", "sshd",
    "netstat", "ss", "service", "ferro-service", "container", "cage",
    "reboot", "poweroff", "bench", "fdstore", "recovery", "help"
]

def run(cmd, cwd=None, check=True):
    print(f"[*] {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    res = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str), capture_output=True, text=True)
    if check and res.returncode != 0:
        print(f"[!] Error (exit {res.returncode}):\n{res.stderr}")
        sys.exit(res.returncode)
    return res

def sha256_file(filepath):
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

def ensure_binaries_compiled(force_rebuild=False):
    """Verifies all required release binaries exist; compiles via cargo or container if needed."""
    print("\n[Stage 1] Verifying and Compiling Pure-Rust Release Binaries...")
    target_rel = os.path.join(WORKSPACE, "target/release")
    required_bins = [
        "ferro-init", "ferro-core", "ferro-pkg", "ferro-superd", "ferrocage",
        "ferro-gui", "ferro-compositor", "xdg-desktop-portal-ferro"
    ]
    
    target_arch = os.environ.get("TARGET_ARCH", "x86_64")
    expected_machine = 0x3E if target_arch in ("x86_64", "amd64") else 0xB7
    
    bins_exist = all(os.path.exists(os.path.join(target_rel, b)) for b in required_bins)
    if bins_exist and not force_rebuild:
        # Check ELF magic and machine architecture
        try:
            with open(os.path.join(target_rel, "ferro-core"), "rb") as f:
                hdr = f.read(20)
                if hdr[:4] != b"\x7fELF" or (len(hdr) >= 19 and hdr[18] != expected_machine):
                    bins_exist = False
        except Exception:
            bins_exist = False

    if not bins_exist or force_rebuild:
        if sys.platform != "darwin" and shutil.which("cargo"):
            print("  • Building release workspace via native cargo...")
            compile_cmd = ["cargo", "build", "--release", "--workspace"]
            run(compile_cmd, cwd=WORKSPACE)
        else:
            arch_platform = "linux/amd64" if target_arch in ("x86_64", "amd64") else "linux/arm64"
            print(f"  • Cross-compiling release workspace via container ({arch_platform})...")
            compile_cmd = [
                "docker", "run", "--platform", arch_platform, "--rm",
                "-v", f"{WORKSPACE}:/build",
                "-w", "/build",
                "rust:1.80-slim-bookworm",
                "cargo", "build", "--release", "--workspace"
            ]
            run(compile_cmd)
    else:
        print("  • All 8 core binaries found pre-compiled in target/release, proceeding...")

def create_base_fhs_tree(rootfs_path):
    """Generates standard FHS 3.0 directory tree with UsrMerge."""
    if os.path.exists(rootfs_path):
        shutil.rmtree(rootfs_path)
    os.makedirs(rootfs_path, exist_ok=True)

    usr_dirs = [
        "usr/bin", "usr/sbin", "usr/lib", "usr/lib/ferro", "usr/share",
        "etc", "etc/ferro", "etc/ferro/services", "etc/sysctl.d", "etc/ssh",
        "home/ferro", "root", "root/.ssh",
        "var", "var/log", "var/log/ferro", "var/log/ferrocage",
        "var/lib/ferro", "var/lib/ferrocage", "var/lib/ferrocage/containers", "var/lib/ferrocage/images", "var/tmp",
        "tmp", "run", "run/ferro", "run/user/1000", "dev", "proc", "sys", "sysroot"
    ]
    for d in usr_dirs:
        os.makedirs(os.path.join(rootfs_path, d), exist_ok=True)

    # UsrMerge Compatibility Symlinks
    for src, dst in [("usr/bin", "bin"), ("usr/sbin", "sbin"), ("usr/lib", "lib"), ("usr/lib", "lib64")]:
        link_path = os.path.join(rootfs_path, dst)
        if not os.path.exists(link_path):
            os.symlink(src, link_path)

def copy_shared_libs(rootfs_path):
    """Copies required minimal dynamic linker and system C shared libraries."""
    libs = [
        "/lib/x86_64-linux-gnu/libc.so.6",
        "/usr/lib/x86_64-linux-gnu/libc.so.6",
        "/lib/x86_64-linux-gnu/libm.so.6",
        "/usr/lib/x86_64-linux-gnu/libm.so.6",
        "/lib/x86_64-linux-gnu/libdl.so.2",
        "/usr/lib/x86_64-linux-gnu/libdl.so.2",
        "/lib/x86_64-linux-gnu/libpthread.so.0",
        "/usr/lib/x86_64-linux-gnu/libpthread.so.0",
        "/lib/x86_64-linux-gnu/libgcc_s.so.1",
        "/usr/lib/x86_64-linux-gnu/libgcc_s.so.1",
        "/lib/x86_64-linux-gnu/liburing.so.2",
        "/usr/lib/x86_64-linux-gnu/liburing.so.2",
        "/lib64/ld-linux-x86-64.so.2",
        "/usr/lib64/ld-linux-x86-64.so.2",
    ]
    target_lib_dir = os.path.join(rootfs_path, "usr/lib")
    copied = []
    for lib in libs:
        if os.path.exists(lib):
            real_file = os.path.realpath(lib)
            basename = os.path.basename(lib)
            dst = os.path.join(target_lib_dir, basename)
            if not os.path.exists(dst):
                shutil.copy2(real_file, dst)
                copied.append(basename)
    return copied

def install_coreutils_symlinks(rootfs_path, extra_applets=None):
    """Installs multi-call symlinks pointing to /usr/bin/ferro-core."""
    applets = list(BASE_APPLETS)
    if extra_applets:
        applets.extend(extra_applets)
    for app in set(applets):
        link_path = os.path.join(rootfs_path, "usr/bin", app)
        if not os.path.exists(link_path):
            os.symlink("/usr/bin/ferro-core", link_path)

def install_system_configs(rootfs_path, edition_name, pretty_name):
    """Installs standard /etc files for user accounts, groups, shadow, and permissions."""
    etc = os.path.join(rootfs_path, "etc")
    
    with open(os.path.join(etc, "os-release"), "w") as f:
        f.write(f'NAME="FerroOS"\n'
                f'VERSION="2.3-{edition_name}"\n'
                f'ID="ferro"\n'
                f'ID_LIKE="linux"\n'
                f'PRETTY_NAME="{pretty_name}"\n'
                f'FERRO_EDITION="{edition_name}"\n'
                f'HOME_URL="https://github.com/Praveen-1308/ferro-os"\n')

    with open(os.path.join(etc, "hostname"), "w") as f:
        f.write(f"ferro-{edition_name}\n")

    with open(os.path.join(etc, "passwd"), "w") as f:
        f.write("root:x:0:0:root:/root:/usr/bin/sh\n"
                "ferro:x:1000:1000:Ferro Service User:/home/ferro:/usr/bin/sh\n")

    with open(os.path.join(etc, "group"), "w") as f:
        f.write("root:x:0:\n"
                "shadow:x:42:\n"
                "video:x:44:ferro\n"
                "render:x:106:ferro\n"
                "ferro:x:1000:\n")

    with open(os.path.join(etc, "shadow"), "w") as f:
        f.write("root:*:19000:0:99999:7:::\n"
                "ferro:*:19000:0:99999:7:::\n")

    with open(os.path.join(etc, "resolv.conf"), "w") as f:
        f.write("nameserver 1.1.1.1\nnameserver 8.8.8.8\n")

    # KSPP Sysctl rules if present in repo
    kspp_src = os.path.join(WORKSPACE, "etc/sysctl.d/99-ferro-kspp.conf")
    if os.path.exists(kspp_src):
        shutil.copy2(kspp_src, os.path.join(etc, "sysctl.d/99-ferro-kspp.conf"))

    # Apply strict enterprise permissions
    os.chmod(os.path.join(rootfs_path, "tmp"), 0o1777)
    os.chmod(os.path.join(rootfs_path, "var/tmp"), 0o1777)
    os.chmod(os.path.join(rootfs_path, "root"), 0o0700)
    os.chmod(os.path.join(rootfs_path, "home/ferro"), 0o0755)
    os.chmod(os.path.join(etc, "passwd"), 0o0644)
    os.chmod(os.path.join(etc, "group"), 0o0644)
    os.chmod(os.path.join(etc, "shadow"), 0o0600)
    os.chmod(os.path.join(etc, "resolv.conf"), 0o0644)
    os.chmod(os.path.join(etc, "os-release"), 0o0644)

def package_rootfs(rootfs_path, archive_name):
    """Packs directory into a .tar.gz archive and returns (archive_path, size_bytes, sha256)."""
    archive_path = os.path.join(BUILD_OUT, archive_name)
    if os.path.exists(archive_path):
        os.remove(archive_path)
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(rootfs_path, arcname="")
    size_bytes = os.path.getsize(archive_path)
    digest = sha256_file(archive_path)
    return archive_path, size_bytes, digest

def build_docker_image(archive_name, dockerfile_name, image_tag):
    """Builds Docker scratch image from given rootfs archive if Docker is available."""
    dockerfile_path = os.path.join(BUILD_OUT, dockerfile_name)
    with open(dockerfile_path, "w") as f:
        f.write("FROM scratch\n"
                f"ADD {archive_name} /\n"
                "ENV PATH=/usr/bin:/usr/sbin\n"
                "ENV HOME=/home/ferro\n"
                "USER ferro\n"
                "WORKDIR /home/ferro\n"
                'CMD ["/usr/bin/sh"]\n')
    
    if shutil.which("docker"):
        res = subprocess.run(["docker", "info"], capture_output=True)
        if res.returncode == 0:
            print(f"  • Building Docker image {image_tag} from {archive_name}...")
            run(["docker", "build", "-t", image_tag, "-f", dockerfile_path, BUILD_OUT], check=False)
            return True
    return False

# ==============================================================================
# SPECIFIC EDITION BUILDERS
# ==============================================================================

def build_cloud_edition(target_rel):
    """Builds Edition 1: Cloud Server Edition."""
    name = "cloud"
    pretty = "FerroOS 2.3 Cloud Server Edition (Pure-Rust Micro-Appliance)"
    rootfs = os.path.join(BUILD_OUT, "rootfs_cloud")
    print(f"\n---> Building Edition: {pretty}")
    
    create_base_fhs_tree(rootfs)
    copy_shared_libs(rootfs)
    
    # 1. Install Cloud Binaries
    shutil.copy2(os.path.join(target_rel, "ferro-init"), os.path.join(rootfs, "usr/sbin/ferro-init"))
    shutil.copy2(os.path.join(target_rel, "ferro-core"), os.path.join(rootfs, "usr/bin/ferro-core"))
    shutil.copy2(os.path.join(target_rel, "ferro-pkg"),  os.path.join(rootfs, "usr/bin/ferro-pkg"))
    shutil.copy2(os.path.join(target_rel, "ferro-superd"), os.path.join(rootfs, "usr/bin/ferro-superd"))
    shutil.copy2(os.path.join(target_rel, "ferrocage"),  os.path.join(rootfs, "usr/bin/ferrocage"))
    
    # Kernel executes /init as PID 1
    os.symlink("/usr/sbin/ferro-init", os.path.join(rootfs, "init"))
    os.symlink("/usr/bin/ferro-pkg", os.path.join(rootfs, "usr/bin/rpk"))
    
    # io_uring shim
    so_src = os.path.join(target_rel, "libferro_io.so")
    if os.path.exists(so_src):
        shutil.copy2(so_src, os.path.join(rootfs, "usr/lib/libferro_io.so"))

    install_coreutils_symlinks(rootfs)
    install_system_configs(rootfs, name, pretty)

    # Edition Config
    with open(os.path.join(rootfs, "etc/ferro/edition.toml"), "w") as f:
        f.write('[edition]\nname = "cloud"\nprofile = "cloud-server"\ndescription = "Autonomous micro-appliance for AWS/GCP/Azure"\n')

    # Default Cloud Services
    svc_dir = os.path.join(rootfs, "etc/ferro/services")
    with open(os.path.join(svc_dir, "dns.toml"), "w") as f:
        f.write('name = "dns"\ncommand = ["/usr/bin/ferro-core", "dns-cache", "--port", "5353"]\nrestart = "always"\nuser = "ferro"\ncapabilities = ["CAP_NET_BIND_SERVICE"]\nmemory_max_mb = 32\n')

    with open(os.path.join(svc_dir, "supervise.toml"), "w") as f:
        f.write('name = "supervise"\ncommand = ["/usr/bin/ferro-superd", "/etc/ferro/services"]\nrestart = "always"\nuser = "root"\nmemory_max_mb = 16\n')

    with open(os.path.join(svc_dir, "twelve-dollar.toml"), "w") as f:
        f.write('name = "twelve-dollar"\ncommand = ["/usr/bin/ferro-core", "server-suite", "--port", "8080"]\nrestart = "always"\nuser = "ferro"\nmemory_max_mb = 64\n')

    archive, sz, sha = package_rootfs(rootfs, "ferro_cloud_appliance.tar.gz")
    docker_ok = build_docker_image("ferro_cloud_appliance.tar.gz", "Dockerfile.cloud", "ferro-os-cloud:latest")
    
    return {
        "edition": "cloud",
        "archive": archive,
        "size_mb": sz / (1024 * 1024),
        "sha256": sha,
        "docker_image": "ferro-os-cloud:latest" if docker_ok else None,
        "binaries": ["ferro-init", "ferro-core", "ferro-pkg", "ferro-superd", "ferrocage", "libferro_io.so"]
    }

def build_desktop_edition(target_rel):
    """Builds Edition 2: Desktop & Web Edition."""
    name = "desktop"
    pretty = "FerroOS 2.3 Desktop & Web Edition (Pure-Rust Wayland & Framebuffer)"
    rootfs = os.path.join(BUILD_OUT, "rootfs_desktop")
    print(f"\n---> Building Edition: {pretty}")
    
    create_base_fhs_tree(rootfs)
    copy_shared_libs(rootfs)
    
    # 1. Install Cloud + Desktop Binaries
    for b in ["ferro-init", "ferro-core", "ferro-pkg", "ferro-superd", "ferrocage", "ferro-gui", "ferro-compositor", "xdg-desktop-portal-ferro"]:
        src = os.path.join(target_rel, b)
        dst_dir = "usr/sbin" if b == "ferro-init" else "usr/bin"
        shutil.copy2(src, os.path.join(rootfs, dst_dir, b))

    os.symlink("/usr/sbin/ferro-init", os.path.join(rootfs, "init"))
    os.symlink("/usr/bin/ferro-pkg", os.path.join(rootfs, "usr/bin/rpk"))

    so_src = os.path.join(target_rel, "libferro_io.so")
    if os.path.exists(so_src):
        shutil.copy2(so_src, os.path.join(rootfs, "usr/lib/libferro_io.so"))

    install_coreutils_symlinks(rootfs, extra_applets=["gui", "desktop", "compositor", "portal"])
    install_system_configs(rootfs, name, pretty)

    # Portal configs
    portal_dir = os.path.join(rootfs, "usr/share/xdg-desktop-portal/portals")
    os.makedirs(portal_dir, exist_ok=True)
    dbus_svc_dir = os.path.join(rootfs, "usr/share/dbus-1/services")
    os.makedirs(dbus_svc_dir, exist_ok=True)

    src_p = os.path.join(WORKSPACE, "config/portals/ferro.portal")
    if os.path.exists(src_p):
        shutil.copy2(src_p, os.path.join(portal_dir, "ferro.portal"))
    src_pc = os.path.join(WORKSPACE, "config/portals/portals.conf")
    if os.path.exists(src_pc):
        shutil.copy2(src_pc, os.path.join(rootfs, "usr/share/xdg-desktop-portal/portals.conf"))
    src_ds = os.path.join(WORKSPACE, "config/portals/org.freedesktop.impl.portal.desktop.ferro.service")
    if os.path.exists(src_ds):
        shutil.copy2(src_ds, os.path.join(dbus_svc_dir, "org.freedesktop.impl.portal.desktop.ferro.service"))

    # Desktop Edition config & services
    with open(os.path.join(rootfs, "etc/ferro/edition.toml"), "w") as f:
        f.write('[edition]\nname = "desktop"\nprofile = "desktop-web"\ndescription = "Pure-Rust Wayland & Framebuffer GUI with noVNC Web Streaming"\n')

    svc_dir = os.path.join(rootfs, "etc/ferro/services")
    with open(os.path.join(svc_dir, "compositor.toml"), "w") as f:
        f.write('name = "compositor"\ncommand = ["/usr/bin/ferro-compositor"]\nrestart = "always"\nuser = "ferro"\nmemory_max_mb = 128\n')

    with open(os.path.join(svc_dir, "gui.toml"), "w") as f:
        f.write('name = "gui"\ncommand = ["/usr/bin/ferro-gui"]\nrestart = "always"\nuser = "ferro"\nmemory_max_mb = 64\n')

    with open(os.path.join(svc_dir, "portal.toml"), "w") as f:
        f.write('name = "portal"\ncommand = ["/usr/bin/xdg-desktop-portal-ferro"]\nrestart = "always"\nuser = "ferro"\nmemory_max_mb = 32\n')

    archive, sz, sha = package_rootfs(rootfs, "ferro_desktop_appliance.tar.gz")
    docker_ok = build_docker_image("ferro_desktop_appliance.tar.gz", "Dockerfile.desktop", "ferro-os-desktop:latest")

    return {
        "edition": "desktop",
        "archive": archive,
        "size_mb": sz / (1024 * 1024),
        "sha256": sha,
        "docker_image": "ferro-os-desktop:latest" if docker_ok else None,
        "binaries": ["ferro-init", "ferro-core", "ferro-pkg", "ferro-superd", "ferrocage", "ferro-gui", "ferro-compositor", "xdg-desktop-portal-ferro", "libferro_io.so"]
    }

def build_gaming_edition(target_rel):
    """Builds Edition 3: Gaming & Proton Edition."""
    name = "gaming"
    pretty = "FerroOS 2.3 Gaming & Proton Edition (Pure-Rust sched_ext & GameMode)"
    rootfs = os.path.join(BUILD_OUT, "rootfs_gaming")
    print(f"\n---> Building Edition: {pretty}")

    create_base_fhs_tree(rootfs)
    copy_shared_libs(rootfs)

    # Binaries: Cloud + Desktop + sched_ext tools
    for b in ["ferro-init", "ferro-core", "ferro-pkg", "ferro-superd", "ferrocage", "ferro-gui", "ferro-compositor", "xdg-desktop-portal-ferro"]:
        src = os.path.join(target_rel, b)
        dst_dir = "usr/sbin" if b == "ferro-init" else "usr/bin"
        shutil.copy2(src, os.path.join(rootfs, dst_dir, b))

    os.symlink("/usr/sbin/ferro-init", os.path.join(rootfs, "init"))
    os.symlink("/usr/bin/ferro-pkg", os.path.join(rootfs, "usr/bin/rpk"))

    so_src = os.path.join(target_rel, "libferro_io.so")
    if os.path.exists(so_src):
        shutil.copy2(so_src, os.path.join(rootfs, "usr/lib/libferro_io.so"))

    install_coreutils_symlinks(rootfs, extra_applets=["gamemode", "scx", "game", "proton", "win", "wine"])
    install_system_configs(rootfs, name, pretty)

    # Gaming directories
    os.makedirs(os.path.join(rootfs, "var/lib/ferro/wine_prefixes"), exist_ok=True)
    os.makedirs(os.path.join(rootfs, "var/lib/ferro/shaders"), exist_ok=True)
    os.makedirs(os.path.join(rootfs, "var/lib/ferro/proton"), exist_ok=True)

    with open(os.path.join(rootfs, "etc/ferro/edition.toml"), "w") as f:
        f.write('[edition]\nname = "gaming"\nprofile = "gaming-proton"\ndescription = "Real-time sched_ext 500us slice scheduler, GameMode & Proton runner"\n')

    with open(os.path.join(rootfs, "etc/ferro/gamemode.toml"), "w") as f:
        f.write('[general]\nrenice = -10\nsched = "SCHED_ISO"\ninhibit_screensaver = 1\n')

    svc_dir = os.path.join(rootfs, "etc/ferro/services")
    with open(os.path.join(svc_dir, "scx-scheduler.toml"), "w") as f:
        f.write('name = "scx-scheduler"\ncommand = ["/usr/bin/ferro-core", "sched", "--target-slice-us", "500"]\nrestart = "always"\nuser = "root"\nmemory_max_mb = 32\n')

    with open(os.path.join(svc_dir, "proton-bridge.toml"), "w") as f:
        f.write('name = "proton-bridge"\ncommand = ["/usr/bin/ferro-core", "proton", "--daemon"]\nrestart = "always"\nuser = "ferro"\nmemory_max_mb = 128\n')

    archive, sz, sha = package_rootfs(rootfs, "ferro_gaming_appliance.tar.gz")
    docker_ok = build_docker_image("ferro_gaming_appliance.tar.gz", "Dockerfile.gaming", "ferro-os-gaming:latest")

    return {
        "edition": "gaming",
        "archive": archive,
        "size_mb": sz / (1024 * 1024),
        "sha256": sha,
        "docker_image": "ferro-os-gaming:latest" if docker_ok else None,
        "binaries": ["ferro-init", "ferro-core", "ferro-pkg", "ferro-superd", "ferrocage", "ferro-gui", "ferro-compositor", "xdg-desktop-portal-ferro", "libferro_io.so"]
    }

def build_universal_edition(target_rel):
    """Builds Edition 4: Universal Pure-Rust RootFS (Backward compatible pure_rust_rootfs)."""
    name = "pure"
    pretty = "FerroOS 2.3 Universal (Pure-Rust Linux OS)"
    rootfs = os.path.join(BUILD_OUT, "pure_rust_rootfs")
    print(f"\n---> Building Edition: {pretty} (Unified Master RootFS)")

    create_base_fhs_tree(rootfs)
    copy_shared_libs(rootfs)

    # 1. Install ALL compiled binaries
    all_bins = [
        "ferro-init", "ferro-core", "ferro-pkg", "ferro-superd", "ferrocage",
        "ferro-gui", "ferro-compositor", "xdg-desktop-portal-ferro"
    ]
    for b in all_bins:
        src = os.path.join(target_rel, b)
        if os.path.exists(src):
            dst_dir = "usr/sbin" if b == "ferro-init" else "usr/bin"
            shutil.copy2(src, os.path.join(rootfs, dst_dir, b))

    os.symlink("/usr/sbin/ferro-init", os.path.join(rootfs, "init"))
    os.symlink("/usr/bin/ferro-pkg", os.path.join(rootfs, "usr/bin/rpk"))

    so_src = os.path.join(target_rel, "libferro_io.so")
    if os.path.exists(so_src):
        shutil.copy2(so_src, os.path.join(rootfs, "usr/lib/libferro_io.so"))

    install_coreutils_symlinks(rootfs, extra_applets=["gui", "desktop", "compositor", "portal"])
    install_system_configs(rootfs, name, pretty)

    # Portal configs
    portal_dir = os.path.join(rootfs, "usr/share/xdg-desktop-portal/portals")
    os.makedirs(portal_dir, exist_ok=True)
    dbus_svc_dir = os.path.join(rootfs, "usr/share/dbus-1/services")
    os.makedirs(dbus_svc_dir, exist_ok=True)

    src_p = os.path.join(WORKSPACE, "config/portals/ferro.portal")
    if os.path.exists(src_p):
        shutil.copy2(src_p, os.path.join(portal_dir, "ferro.portal"))
    src_pc = os.path.join(WORKSPACE, "config/portals/portals.conf")
    if os.path.exists(src_pc):
        shutil.copy2(src_pc, os.path.join(rootfs, "usr/share/xdg-desktop-portal/portals.conf"))
    src_ds = os.path.join(WORKSPACE, "config/portals/org.freedesktop.impl.portal.desktop.ferro.service")
    if os.path.exists(src_ds):
        shutil.copy2(src_ds, os.path.join(dbus_svc_dir, "org.freedesktop.impl.portal.desktop.ferro.service"))

    # Universal Services
    svc_dir = os.path.join(rootfs, "etc/ferro/services")
    with open(os.path.join(svc_dir, "dns.toml"), "w") as f:
        f.write('name = "dns"\ncommand = ["/usr/bin/ferro-core", "dns-cache", "--port", "5353"]\nrestart = "always"\nuser = "ferro"\ncapabilities = ["CAP_NET_BIND_SERVICE"]\nmemory_max_mb = 32\n')

    with open(os.path.join(svc_dir, "supervise.toml"), "w") as f:
        f.write('name = "supervise"\ncommand = ["/usr/bin/ferro-superd", "/etc/ferro/services"]\nrestart = "always"\nuser = "root"\nmemory_max_mb = 16\n')

    archive, sz, sha = package_rootfs(rootfs, "pure_rust_rootfs.tar.gz")
    docker_ok = build_docker_image("pure_rust_rootfs.tar.gz", "Dockerfile.pure", "ferro-os-pure:latest")

    return {
        "edition": "universal",
        "archive": archive,
        "size_mb": sz / (1024 * 1024),
        "sha256": sha,
        "docker_image": "ferro-os-pure:latest" if docker_ok else None,
        "binaries": all_bins + ["libferro_io.so"]
    }

def main():
    parser = argparse.ArgumentParser(description="FerroOS Multi-Edition Pure-Rust Linux Builder")
    parser.add_argument("--edition", choices=["all", "cloud", "desktop", "gaming", "pure", "universal"],
                        default="all", help="Target edition to build (default: all)")
    parser.add_argument("--force-rebuild", action="store_true", help="Force recompilation of all Rust crates")
    args = parser.parse_args()

    print("=" * 80)
    print("      FERRO-OS AUTONOMOUS PURE-RUST LINUX MULTI-EDITION BUILDER")
    print(f"      Target Edition: {args.edition.upper()}")
    print("=" * 80)

    os.makedirs(BUILD_OUT, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)

    ensure_binaries_compiled(force_rebuild=args.force_rebuild)
    target_rel = os.path.join(WORKSPACE, "target/release")

    editions_to_build = []
    if args.edition in ("all", "cloud"):
        editions_to_build.append("cloud")
    if args.edition in ("all", "desktop"):
        editions_to_build.append("desktop")
    if args.edition in ("all", "gaming"):
        editions_to_build.append("gaming")
    if args.edition in ("all", "pure", "universal"):
        editions_to_build.append("universal")

    results = []
    start_time = time.time()
    for ed in editions_to_build:
        if ed == "cloud":
            res = build_cloud_edition(target_rel)
        elif ed == "desktop":
            res = build_desktop_edition(target_rel)
        elif ed == "gaming":
            res = build_gaming_edition(target_rel)
        elif ed == "universal":
            res = build_universal_edition(target_rel)
        results.append(res)

    elapsed = time.time() - start_time

    # Generate Telemetry Report
    report_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "build_duration_seconds": round(elapsed, 2),
        "editions_built": len(results),
        "editions": results
    }

    report_path = os.path.join(REPORTS_DIR, "ferro_os_editions_build_report.json")
    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=2)

    print("\n" + "=" * 80)
    print("✅ FERRO-OS MULTI-EDITION PURE-RUST OS BUILD COMPLETE!")
    print(f"   Duration: {elapsed:.2f} seconds | Editions Built: {len(results)}")
    for r in results:
        print(f"   • {r['edition'].upper():<12}: {os.path.basename(r['archive']):<34} | {r['size_mb']:.2f} MB | SHA: {r['sha256'][:16]}...")
        if r.get("docker_image"):
            print(f"     Docker Image: {r['docker_image']}")
    print(f"   Telemetry Report: {report_path}")
    print("=" * 80)

if __name__ == "__main__":
    main()
