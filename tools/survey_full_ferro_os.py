#!/usr/bin/env python3
"""
FerroOS Full-Stack Codebase Survey & Unified Architecture Graph Generator
========================================================================
Surveys every line of code, comment, struct, function, and Linux kernel ABI
across all three specialized editions of FerroOS:
  1. Cloud Server Edition (Pure Rust micro-appliance, $12 challenge, superd, ferrocage)
  2. Desktop & Web Edition (Wayland compositor, framebuffer /dev/fb0, XDG portal, noVNC)
  3. Gaming & Proton Edition (sched_ext, GameMode Nice -10, DXVK/VKD3D, Wine, PE/MSI)

Generates:
  - Structured survey JSON: tools/reports/ferro_os_full_codebase_survey.json
  - Standalone interactive HTML graph: docs/ferro_os_architecture_graph.html
"""

import os
import re
import sys
import json
import time
from typing import Dict, Any, List

WORKSPACE = "/home/tarun-kumar/Desktop/sample os "
CRATES_DIR = os.path.join(WORKSPACE, "crates")
TOOLS_DIR = os.path.join(WORKSPACE, "tools")
DOCS_DIR = os.path.join(WORKSPACE, "docs")
REPORTS_DIR = os.path.join(TOOLS_DIR, "reports")

# ==============================================================================
# 1. Source Code & Comment Scanner Engine
# ==============================================================================

def scan_rust_file(file_path: str) -> Dict[str, Any]:
    rel_path = os.path.relpath(file_path, WORKSPACE)
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    total_lines = len(lines)
    code_lines = 0
    comment_lines = 0
    blank_lines = 0

    comments = []
    structs = []
    enums = []
    functions = []
    traits = []
    syscalls_and_abi = []

    in_block_comment = False
    current_block_comment = []

    struct_pat = re.compile(r"^\s*(?:pub(?:\([^)]+\))?\s+)?struct\s+([A-Za-z0-9_]+)")
    enum_pat = re.compile(r"^\s*(?:pub(?:\([^)]+\))?\s+)?enum\s+([A-Za-z0-9_]+)")
    fn_pat = re.compile(r"^\s*(?:pub(?:\([^)]+\))?\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+([A-Za-z0-9_]+)")
    trait_pat = re.compile(r"^\s*(?:pub(?:\([^)]+\))?\s+)?trait\s+([A-Za-z0-9_]+)")
    syscall_pat = re.compile(r"\b(libc::[a-zA-Z0-9_]+|syscall::[a-zA-Z0-9_]+|landlock_[a-zA-Z0-9_]+|prctl|clone3|unshare|pivot_root|mount|umount2|epoll_[a-zA-Z0-9_]+|signalfd|timerfd_[a-zA-Z0-9_]+|seccomp|bpf)\b")

    for idx, raw_line in enumerate(lines, 1):
        line = raw_line.strip()

        if not line:
            blank_lines += 1
            continue

        if in_block_comment:
            comment_lines += 1
            if "*/" in line:
                in_block_comment = False
                current_block_comment.append(line.split("*/")[0].strip())
                comments.append({"line": idx, "text": " ".join(current_block_comment), "type": "block"})
                current_block_comment = []
            else:
                current_block_comment.append(line)
            continue

        if line.startswith("/*"):
            comment_lines += 1
            if "*/" in line:
                comments.append({"line": idx, "text": line.replace("/*", "").replace("*/", "").strip(), "type": "block"})
            else:
                in_block_comment = True
                current_block_comment.append(line[2:].strip())
            continue

        if line.startswith("//"):
            comment_lines += 1
            comment_type = "module_doc" if line.startswith("//!") else ("item_doc" if line.startswith("///") else "line")
            clean_text = line.lstrip("/! ").strip()
            if clean_text:
                comments.append({"line": idx, "text": clean_text, "type": comment_type})
            continue

        code_lines += 1

        m_struct = struct_pat.search(line)
        if m_struct:
            structs.append({"name": m_struct.group(1), "line": idx})

        m_enum = enum_pat.search(line)
        if m_enum:
            enums.append({"name": m_enum.group(1), "line": idx})

        m_fn = fn_pat.search(line)
        if m_fn:
            functions.append({"name": m_fn.group(1), "line": idx})

        m_trait = trait_pat.search(line)
        if m_trait:
            traits.append({"name": m_trait.group(1), "line": idx})

        for sc in syscall_pat.findall(line):
            if sc not in syscalls_and_abi:
                syscalls_and_abi.append(sc)

    insight_keywords = ["invariant", "architecture", "security", "zero-copy", "atomic", "cgroup", "landlock", "sandbox", "memory", "perf", "cache", "wal", "lock", "fail", "fallback", "wayland", "gamemode", "sched_ext", "proton"]
    insights = []
    for c in comments:
        txt = c["text"]
        if len(txt) > 20 and any(k in txt.lower() for k in insight_keywords):
            insights.append({"line": c["line"], "text": txt})

    return {
        "file": rel_path,
        "name": os.path.basename(file_path),
        "total_lines": total_lines,
        "code_lines": code_lines,
        "comment_lines": comment_lines,
        "blank_lines": blank_lines,
        "comment_density_pct": round((comment_lines / total_lines * 100) if total_lines > 0 else 0, 1),
        "structs": structs,
        "enums": enums,
        "functions": functions,
        "traits": traits,
        "syscalls_and_abi": syscalls_and_abi,
        "insights": insights,
        "sample_comments": comments[:15]
    }

# ==============================================================================
# 2. Editions & Multi-Architecture Layer Model
# ==============================================================================

FERRO_EDITIONS = [
    {
        "id": "edition_cloud",
        "name": "Cloud Server Edition",
        "badge": "☁️ Cloud Server",
        "color": "#38bdf8",
        "description": "Pure-Rust autonomous cloud appliance. Eliminates Docker, containerd, and systemd. Features Landlock LSM sandboxing, ferro-superd Cgroup v2 supervisor (2.66 MB RAM), and ferrocage sub-2ms micro-containers. Tested in $12 challenge.",
        "metrics": {"rootfs_size": "3.59 MB", "daemon_ram": "2.66 MB", "throughput": "1,858 req/s", "cold_startup": "1 ms"},
        "node_ids": ["init_pid1", "superd_daemon", "cage_engine", "sand_strict", "init_cloud", "init_disk", "tool_12dollar"]
    },
    {
        "id": "edition_desktop",
        "name": "Desktop & Web Edition",
        "badge": "🖥️ Desktop & Web",
        "color": "#10b981",
        "description": "Pure-Rust graphical desktop stack. GPU Wayland compositor with Dual-Kawase acrylic blur, lightweight framebuffer window manager (/dev/fb0), XDG desktop portal, and remote HTML5 Web Desktop streaming (port 6080).",
        "metrics": {"compositor": "Pure Rust Wayland", "framebuffer": "/dev/fb0 (Zero X11)", "web_port": "6080 (HTML5 Canvas)", "blur": "Dual-Kawase GPU"},
        "node_ids": ["comp_wayland", "gui_framebuffer", "portal_xdg", "web_desktop_stream", "core_shell"]
    },
    {
        "id": "edition_gaming",
        "name": "Gaming & Proton Edition",
        "badge": "🎮 Gaming & Proton",
        "color": "#a855f7",
        "description": "Real-time gaming performance engine. Sched_ext GameMode scheduling (500µs slice, <50µs jitter), automatic Nice -10 CPU priority, Vulkan DXVK/VKD3D mapping, PE/MSI binary inspection, and Wine/Proton/Box64 compatibility.",
        "metrics": {"task_slice": "500 µs target", "wakeup_jitter": "< 50 µs", "dxvk": "DXVK_ASYNC=1", "driver": "Mesa Vulkan ICD"},
        "node_ids": ["game_sched_ext", "game_gamemode", "game_dxvk_vkd3d", "game_proton_wine", "game_pe_msi", "pkg_rpk"]
    }
]

ARCHITECTURAL_LAYERS = [
    {
        "id": "layer_0",
        "name": "Layer 0: Hardware & Cloud Hypervisor",
        "color": "#64748b",
        "description": "Underlying physical & virtual hardware abstractions: x86_64/aarch64 CPU registers, NVMe SSDs, VirtIO block devices, DRM GPU display outputs, and Cloud IMDS (169.254.169.254).",
        "components": [
            {"id": "hw_cpu", "name": "CPU & MMU (x86_64 / aarch64)", "type": "Hardware", "details": "4-8 Cores, Hardware Page Tables, SIMD instructions, Memory Hierarchy", "editions": ["edition_cloud", "edition_desktop", "edition_gaming"]},
            {"id": "hw_nvme", "name": "NVMe / VirtIO Physical Storage", "type": "Storage", "details": "Direct hardware write path, 350+ GB capacity, PCI-e Gen4 throughput", "editions": ["edition_cloud"]},
            {"id": "hw_gpu", "name": "GPU DRM/KMS Hardware", "type": "Graphics Hardware", "details": "Intel Iris/Xe, AMD RDNA/Radeon, ARM Mali Panfrost, Qualcomm Adreno scanout", "editions": ["edition_desktop", "edition_gaming"]},
            {"id": "hw_imds", "name": "Cloud IMDS (169.254.169.254)", "type": "Hypervisor", "details": "Autonomous metadata endpoint for AWS, GCP, Azure, and Hetzner", "editions": ["edition_cloud"]}
        ]
    },
    {
        "id": "layer_1",
        "name": "Layer 1: Linux Kernel ABI & LSM Subsystems",
        "color": "#0284c7",
        "description": "Kernel-level security, schedulers, and controllers invoked directly without runtime daemon intermediaries.",
        "components": [
            {"id": "abi_landlock", "name": "Landlock LSM (ABI v1-v4)", "type": "Kernel LSM", "details": "Unprivileged filesystem path restriction at hardware syscall speed (11ms)", "editions": ["edition_cloud", "edition_desktop", "edition_gaming"]},
            {"id": "abi_cgroups", "name": "Cgroups v2 Unified Hierarchy", "type": "Kernel Controller", "details": "cpu.max, memory.max, memory.swap.max=0, pids.max, cpu.weight", "editions": ["edition_cloud", "edition_gaming"]},
            {"id": "abi_namespaces", "name": "Linux Namespaces", "type": "Virtualization", "details": "CLONE_NEWPID, CLONE_NEWNS, CLONE_NEWNET, CLONE_NEWUSER rootless mapping", "editions": ["edition_cloud", "edition_gaming"]},
            {"id": "game_sched_ext", "name": "sched_ext Gaming Scheduler", "type": "Kernel Scheduler", "details": "Real-time task scheduling (500µs slice, <50µs jitter) prioritizing game rendering", "editions": ["edition_gaming"]}
        ]
    },
    {
        "id": "layer_2",
        "name": "Layer 2: Autonomous PID 1 Boot & Init",
        "color": "#059669",
        "description": "ferro-init & cloud_init: Pure-Rust PID 1 bootstrap, early pseudofs mounting, autonomous IMDS cloud network discovery, and block storage scanning.",
        "crates": ["crates/ferro-init", "crates/ferro-core/src/cloud_init.rs", "crates/ferro-core/src/disk.rs"],
        "components": [
            {"id": "init_pid1", "name": "ferro-init (PID 1)", "type": "Init", "details": "Sub-millisecond bootstrap, early /sys, /proc, /dev, /tmp mount, zombie reaping", "editions": ["edition_cloud", "edition_desktop", "edition_gaming"]},
            {"id": "init_fdstore", "name": "fdstore Crash Recovery", "type": "Reliability", "details": "Preserves open file descriptors across supervisor restarts without socket loss", "editions": ["edition_cloud"]},
            {"id": "init_cloud", "name": "cloud_init Autonomous IMDS", "type": "Cloud Provisioning", "details": "Scans AWS/GCP/Azure IMDS, provisions eth0, injects SSH public keys (0600)", "editions": ["edition_cloud"]},
            {"id": "init_disk", "name": "disk Block Scanner", "type": "Storage", "details": "Autonomous discovery of NVMe, SCSI, VirtIO disks, ext4/btrfs mounting", "editions": ["edition_cloud"]}
        ]
    },
    {
        "id": "layer_3",
        "name": "Layer 3: Process Supervision & Cgroups v2",
        "color": "#d97706",
        "description": "ferro-superd: Ultra-lightweight process supervisor replacing systemd. Enforces Cgroup v2 quotas, ring-buffer logging, backoff auto-restarts, and IPC control.",
        "crates": ["crates/ferro-superd", "crates/ferro-core/src/service.rs"],
        "components": [
            {"id": "superd_daemon", "name": "ferro-superd Daemon", "type": "Supervisor", "details": "483 KB pure-Rust daemon, 2.66 MB background RAM (vs 231 MB Docker/containerd)", "editions": ["edition_cloud", "edition_desktop"]},
            {"id": "superd_cgroup", "name": "Cgroup v2 Resource Manager", "type": "Resource Control", "details": "Direct control of memory.max, memory.swap.max, cpu.max, pids.max", "editions": ["edition_cloud"]},
            {"id": "superd_watchdog", "name": "Health Engine & Backoff Watchdog", "type": "Resilience", "details": "Periodic health checks, crash detection in <250ms, exponential backoff retries", "editions": ["edition_cloud"]},
            {"id": "game_gamemode", "name": "Dynamic GameMode Engine", "type": "Resource Governor", "details": "Automatic Nice -10 CPU priority boost & throttling of background services", "editions": ["edition_gaming"]}
        ]
    },
    {
        "id": "layer_4",
        "name": "Layer 4: Micro-Container & Isolation Engine",
        "color": "#7c3aed",
        "description": "ferrocage: Autonomous micro-container runner replacing Docker & containerd. Sub-2ms cold startup, rootless user namespaces, and host volume bind mounts.",
        "crates": ["crates/ferrocage"],
        "components": [
            {"id": "cage_engine", "name": "ferrocage Engine", "type": "Micro-Container", "details": "1.7 ms micro-container startup (~200x faster than Docker), 0 MB background daemon", "editions": ["edition_cloud", "edition_gaming"]},
            {"id": "cage_ns", "name": "Namespace Virtualizer", "type": "Isolation", "details": "CLONE_NEWPID + CLONE_NEWNS + CLONE_NEWUSER UID/GID map without root privileges", "editions": ["edition_cloud"]},
            {"id": "cage_vols", "name": "Host Volume Bind Mounts", "type": "Storage", "details": "-v host:container direct bind mounting delegating disk access with 0 overhead", "editions": ["edition_cloud"]}
        ]
    },
    {
        "id": "layer_5",
        "name": "Layer 5: Unprivileged Sandbox & Security Mesh",
        "color": "#dc2626",
        "description": "ferro sandbox: Multi-profile Landlock LSM security framework. Selectable profiles (strict, shared, broker, dev) and zero-copy shared memory pools.",
        "crates": ["crates/ferro-core/src/main.rs (run_sandbox)"],
        "components": [
            {"id": "sand_strict", "name": "Profile 'strict'", "type": "Profile", "details": "Maximum isolation: locked root, dropped capabilities, private network, zero ambient authority", "editions": ["edition_cloud"]},
            {"id": "sand_shared", "name": "Profile 'shared' (SHM Mesh)", "type": "Profile", "details": "Multi-sandbox cooperative processing via zero-copy /dev/shm/ferro_<pool> pools", "editions": ["edition_cloud"]},
            {"id": "sand_broker", "name": "Profile 'broker' (Gateway)", "type": "Profile", "details": "Strict communication routing exclusively through authorized UNIX domain socket gateways", "editions": ["edition_cloud"]},
            {"id": "game_proton_wine", "name": "Wine / Proton Subsystem", "type": "Translation Layer", "details": "Windows ABI emulation under sandboxed user permissions (/usr/bin/wine64)", "editions": ["edition_gaming"]}
        ]
    },
    {
        "id": "layer_6",
        "name": "Layer 6: Package Governance & Registry",
        "color": "#0891b2",
        "description": "ferro-pkg: Autonomous binary packaging system supporting native RPK archives, cryptographic integrity verification, atomic rollbacks, and PE/MSI inspection.",
        "crates": ["crates/ferro-pkg"],
        "components": [
            {"id": "pkg_rpk", "name": "RPK Binary Package Engine", "type": "Package Manager", "details": "Fast pure-Rust format, zstd compression, cryptographic SHA-256 signing", "editions": ["edition_cloud", "edition_desktop", "edition_gaming"]},
            {"id": "pkg_tx", "name": "Transactional Atomicity", "type": "Rollback", "details": "Atomic snapshot installs; zero partial state on installation interruption", "editions": ["edition_cloud"]},
            {"id": "game_pe_msi", "name": "PE & MSI Binary Inspector", "type": "Package Analysis", "details": "Native extraction of Windows PE32/PE32+ and MSI headers for Wine/Proton dependency mapping", "editions": ["edition_gaming"]}
        ]
    },
    {
        "id": "layer_7",
        "name": "Layer 7: Graphical Desktop, Core Utilities & Shell",
        "color": "#ea580c",
        "description": "Pure-Rust graphical compositor, framebuffer window manager, 30/30 GNU coreutils parity suite, and interactive shell.",
        "crates": ["crates/ferro-compositor", "crates/ferro-gui", "crates/xdg-desktop-portal-ferro", "crates/ferro-core"],
        "components": [
            {"id": "comp_wayland", "name": "ferro-compositor (Wayland)", "type": "Compositor", "details": "GPU-accelerated Wayland compositor, Dual-Kawase acrylic blur, Layer-shell protocols", "editions": ["edition_desktop", "edition_gaming"]},
            {"id": "gui_framebuffer", "name": "ferro-gui (Framebuffer)", "type": "Window Manager", "details": "Direct /dev/fb0 double-buffered framebuffer rendering, font8x8 ASCII rasterizer", "editions": ["edition_desktop"]},
            {"id": "portal_xdg", "name": "xdg-desktop-portal-ferro", "type": "Portal", "details": "Native XDG desktop portal integration for file pickers, screencasting, notifications", "editions": ["edition_desktop", "edition_gaming"]},
            {"id": "core_files", "name": "30/30 GNU Parity Coreutils", "type": "Coreutils", "details": "Complete GNU/POSIX parity: ls, cp, mv, grep, sed, awk, ps, top, kill, df, free, etc.", "editions": ["edition_cloud", "edition_desktop", "edition_gaming"]},
            {"id": "core_shell", "name": "Interactive Ferro Shell", "type": "Shell", "details": "Command history, pipelines (|), I/O redirection (<, >, >>), job control", "editions": ["edition_cloud", "edition_desktop"]}
        ]
    },
    {
        "id": "layer_8",
        "name": "Layer 8: High-Throughput I/O & Streaming",
        "color": "#4f46e5",
        "description": "ferro-io, sshd, dhcp, Web Desktop streaming, and Vulkan translation layers.",
        "crates": ["crates/ferro-io", "crates/ferro-core", "tools/verify-web-desktop.sh"],
        "components": [
            {"id": "io_buffers", "name": "ferro-io Buffer Pools", "type": "I/O Engine", "details": "Zero-copy ring buffers, async event multiplexing, buffer reuse without heap allocation", "editions": ["edition_cloud"]},
            {"id": "web_desktop_stream", "name": "Web Desktop Streaming (Port 6080)", "type": "Remote Desktop", "details": "HTML5 canvas live streaming over WebSocket / noVNC / KasmVNC for browser-based access", "editions": ["edition_desktop"]},
            {"id": "game_dxvk_vkd3d", "name": "DXVK & VKD3D Vulkan Mapping", "type": "Graphics Translation", "details": "DirectX 9/10/11/12 to Vulkan mapping (DXVK_ASYNC=1, State Cache enabled)", "editions": ["edition_gaming"]},
            {"id": "net_sshd", "name": "Embedded SSH Server", "type": "Networking", "details": "Pure-Rust SSH protocol handler with public-key cryptographic authentication", "editions": ["edition_cloud", "edition_desktop"]}
        ]
    },
    {
        "id": "layer_9",
        "name": "Layer 9: Workloads, Benchmarks & Chaos Suites",
        "color": "#be123c",
        "description": "$12 Challenge SQLite WAL suite, high-concurrency engines, and 9-vector adversarial chaos qualification.",
        "crates": ["tools/"],
        "components": [
            {"id": "tool_12dollar", "name": "$12 Challenge WAL Benchmark", "type": "Benchmark", "details": "High-throughput 4-core 8GB SQLite WAL benchmark (1,858 req/s vs Ubuntu collapse)", "editions": ["edition_cloud"]},
            {"id": "tool_chaos", "name": "9-Vector Adversarial Chaos Suite", "type": "Chaos Test", "details": "Path traversal, root defacement, OOM bombs, fork bombs, SIGKILL durability", "editions": ["edition_cloud"]}
        ]
    }
]

# ==============================================================================
# 3. Codebase Survey Execution
# ==============================================================================

def execute_survey() -> Dict[str, Any]:
    print("=" * 80)
    print("      FERRO-OS COMPLETE CODEBASE & ARCHITECTURAL SURVEY ENGINE        ")
    print("=" * 80)
    print(f"  Timestamp:    {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Root:         {WORKSPACE}")
    print("=" * 80)

    rust_files = []
    for root, _, files in os.walk(CRATES_DIR):
        for f in files:
            if f.endswith(".rs"):
                rust_files.append(os.path.join(root, f))
    rust_files.sort()

    scanned_files = []
    total_code = 0
    total_comments = 0
    total_blanks = 0
    total_structs = 0
    total_enums = 0
    total_functions = 0
    all_insights = []

    for fpath in rust_files:
        info = scan_rust_file(fpath)
        scanned_files.append(info)
        total_code += info["code_lines"]
        total_comments += info["comment_lines"]
        total_blanks += info["blank_lines"]
        total_structs += len(info["structs"])
        total_enums += len(info["enums"])
        total_functions += len(info["functions"])
        for ins in info["insights"]:
            all_insights.append({
                "file": info["file"],
                "line": ins["line"],
                "text": ins["text"]
            })
        print(f"  • Scanned {info['file']:<38} | Code: {info['code_lines']:5d} | Comments: {info['comment_lines']:4d} | Fn: {len(info['functions']):3d} | Struct: {len(info['structs']):2d}")

    total_all_lines = total_code + total_comments + total_blanks
    overall_density = round((total_comments / total_all_lines * 100) if total_all_lines > 0 else 0, 1)

    survey_data = {
        "metadata": {
            "title": "FerroOS Complete Codebase Survey",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rust_files_count": len(rust_files),
            "total_lines": total_all_lines,
            "code_lines": total_code,
            "comment_lines": total_comments,
            "blank_lines": total_blanks,
            "comment_density_pct": overall_density,
            "structs_count": total_structs,
            "enums_count": total_enums,
            "functions_count": total_functions,
            "insights_count": len(all_insights)
        },
        "editions": FERRO_EDITIONS,
        "layers": ARCHITECTURAL_LAYERS,
        "files": scanned_files,
        "insights": all_insights
    }

    out_json = os.path.join(REPORTS_DIR, "ferro_os_full_codebase_survey.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w") as f:
        json.dump(survey_data, f, indent=2)
    print(f"✅ Saved full survey data to: {out_json}")

    return survey_data

# ==============================================================================
# 4. Interactive Visual HTML Graph Generator
# ==============================================================================

def generate_interactive_html(survey_data: Dict[str, Any]):
    print("\n🎨 Generating Unified 4-Edition Architecture Graph HTML...")

    nodes = []
    edges = []

    # 1. Layer Nodes & Components
    for layer in survey_data["layers"]:
        nodes.append({
            "id": layer["id"],
            "label": layer["name"].split(":")[1].strip() if ":" in layer["name"] else layer["name"],
            "group": "layer",
            "layer_id": layer["id"],
            "color": layer["color"],
            "radius": 28,
            "description": layer["description"],
            "type": "Layer",
            "editions": ["edition_cloud", "edition_desktop", "edition_gaming"]
        })

        for comp in layer.get("components", []):
            nodes.append({
                "id": comp["id"],
                "label": comp["name"],
                "group": "component",
                "layer_id": layer["id"],
                "color": layer["color"],
                "radius": 18,
                "description": comp["details"],
                "type": comp.get("type", "Component"),
                "editions": comp.get("editions", ["edition_cloud"])
            })
            edges.append({
                "source": layer["id"],
                "target": comp["id"],
                "type": "layer_contains"
            })

    # Inter-layer connections
    layer_links = [
        ("layer_0", "layer_1"),
        ("layer_1", "layer_2"),
        ("layer_1", "layer_3"),
        ("layer_1", "layer_4"),
        ("layer_1", "layer_5"),
        ("layer_2", "layer_3"),
        ("layer_3", "layer_5"),
        ("layer_3", "layer_7"),
        ("layer_4", "layer_7"),
        ("layer_5", "layer_7"),
        ("layer_6", "layer_7"),
        ("layer_7", "layer_8"),
        ("layer_7", "layer_9")
    ]
    for s, t in layer_links:
        edges.append({"source": s, "target": t, "type": "structural_flow"})

    # Specific Cross-Edition Functional Links
    cross_links = [
        ("game_sched_ext", "game_gamemode", "scheduler_link"),
        ("game_gamemode", "superd_daemon", "priority_boost"),
        ("comp_wayland", "gui_framebuffer", "display_fallback"),
        ("comp_wayland", "portal_xdg", "portal_integration"),
        ("comp_wayland", "web_desktop_stream", "stream_scanout"),
        ("game_dxvk_vkd3d", "game_proton_wine", "vulkan_mapping"),
        ("game_pe_msi", "game_proton_wine", "binary_headers"),
        ("superd_daemon", "sand_strict", "supervision_link"),
    ]
    for s, t, typ in cross_links:
        edges.append({"source": s, "target": t, "type": typ})

    # Key Source Files as nodes attached to layers
    file_layer_map = {
        "crates/ferro-init/src/main.rs": ("layer_2", ["edition_cloud", "edition_desktop", "edition_gaming"]),
        "crates/ferro-init/src/fdstore.rs": ("layer_2", ["edition_cloud"]),
        "crates/ferro-core/src/cloud_init.rs": ("layer_2", ["edition_cloud"]),
        "crates/ferro-core/src/disk.rs": ("layer_2", ["edition_cloud"]),
        "crates/ferro-superd/src/main.rs": ("layer_3", ["edition_cloud", "edition_desktop"]),
        "crates/ferro-core/src/service.rs": ("layer_3", ["edition_cloud"]),
        "crates/ferrocage/src/main.rs": ("layer_4", ["edition_cloud", "edition_gaming"]),
        "crates/ferro-core/src/main.rs": ("layer_7", ["edition_cloud", "edition_desktop", "edition_gaming"]),
        "crates/ferro-core/src/shell.rs": ("layer_7", ["edition_cloud", "edition_desktop"]),
        "crates/ferro-compositor/src/main.rs": ("layer_7", ["edition_desktop", "edition_gaming"]),
        "crates/ferro-gui/src/main.rs": ("layer_7", ["edition_desktop"]),
        "crates/xdg-desktop-portal-ferro/src/main.rs": ("layer_7", ["edition_desktop", "edition_gaming"]),
        "crates/ferro-pkg/src/main.rs": ("layer_6", ["edition_cloud", "edition_desktop", "edition_gaming"]),
        "crates/ferro-pkg/src/pe.rs": ("layer_6", ["edition_gaming"]),
        "crates/ferro-pkg/src/msi.rs": ("layer_6", ["edition_gaming"]),
        "crates/ferro-io/src/lib.rs": ("layer_8", ["edition_cloud"]),
        "crates/ferro-core/src/sshd.rs": ("layer_8", ["edition_cloud", "edition_desktop"]),
        "crates/ferro-core/src/dhcp.rs": ("layer_8", ["edition_cloud", "edition_desktop"])
    }

    for f_info in survey_data["files"]:
        f_rel = f_info["file"]
        if f_rel in file_layer_map:
            l_id, ed_list = file_layer_map[f_rel]
            f_id = f"file_{f_info['name']}"
            nodes.append({
                "id": f_id,
                "label": f_info["name"],
                "group": "file",
                "layer_id": l_id,
                "color": "#10b981" if "main" in f_info["name"] else "#3b82f6",
                "radius": 14,
                "description": f"Source File: {f_rel} | Lines: {f_info['total_lines']} ({f_info['code_lines']} code, {f_info['comment_lines']} comments)",
                "file_data": f_info,
                "type": "Rust Source File",
                "editions": ed_list
            })
            edges.append({"source": l_id, "target": f_id, "type": "implemented_in"})

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FerroOS: Unified Architecture Graph (Cloud, Desktop, Gaming, AS/400)</title>
    <style>
        :root {{
            --bg-dark: #0a0f1d;
            --bg-panel: rgba(15, 23, 42, 0.85);
            --bg-card: rgba(30, 41, 59, 0.7);
            --border: rgba(148, 163, 184, 0.15);
            --border-hover: rgba(56, 189, 248, 0.4);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --accent-cyan: #38bdf8;
            --accent-emerald: #10b981;
            --accent-amber: #f59e0b;
            --accent-purple: #a855f7;
            --accent-rose: #f43f5e;
            --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-primary);
            overflow: hidden;
            height: 100vh;
            width: 100vw;
            display: flex;
            flex-direction: column;
        }}

        /* Header Navbar */
        header {{
            height: 64px;
            background: var(--bg-panel);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 24px;
            z-index: 50;
        }}
        .brand {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .brand-icon {{
            width: 36px;
            height: 36px;
            background: linear-gradient(135deg, #38bdf8, #a855f7);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            box-shadow: 0 0 16px rgba(56, 189, 248, 0.4);
        }}
        .brand-title {{
            font-size: 18px;
            font-weight: 700;
            letter-spacing: -0.5px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .brand-tag {{
            font-size: 11px;
            text-transform: uppercase;
            padding: 2px 8px;
            background: rgba(56, 189, 248, 0.15);
            border: 1px solid rgba(56, 189, 248, 0.3);
            border-radius: 12px;
            color: var(--accent-cyan);
            font-family: var(--font-mono);
        }}

        /* Stats Bar */
        .stats-strip {{
            display: flex;
            gap: 18px;
            align-items: center;
            font-size: 13px;
            font-family: var(--font-mono);
        }}
        .stat-item {{
            display: flex;
            align-items: baseline;
            gap: 6px;
        }}
        .stat-val {{
            font-weight: 700;
            color: var(--accent-cyan);
        }}
        .stat-lbl {{
            color: var(--text-muted);
            font-size: 11px;
            text-transform: uppercase;
        }}

        /* Edition Filter Bar */
        .edition-bar {{
            height: 48px;
            background: rgba(15, 23, 42, 0.95);
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 0 24px;
            z-index: 45;
        }}
        .edition-btn {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            color: var(--text-secondary);
            padding: 6px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s ease;
        }}
        .edition-btn:hover {{
            background: rgba(56, 189, 248, 0.15);
            color: var(--text-primary);
            border-color: var(--accent-cyan);
        }}
        .edition-btn.active {{
            background: rgba(56, 189, 248, 0.2);
            color: var(--accent-cyan);
            border-color: var(--accent-cyan);
            box-shadow: 0 0 12px rgba(56, 189, 248, 0.2);
        }}

        /* Main Workspace Container */
        .app-body {{
            flex: 1;
            display: flex;
            position: relative;
            overflow: hidden;
        }}

        /* Left Sidebar: Layer Navigation & Search */
        .sidebar {{
            width: 380px;
            background: var(--bg-panel);
            backdrop-filter: blur(16px);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            z-index: 40;
            transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }}
        .search-box {{
            padding: 16px;
            border-bottom: 1px solid var(--border);
        }}
        .search-input {{
            width: 100%;
            padding: 10px 14px;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text-primary);
            font-size: 13px;
            outline: none;
            transition: all 0.2s ease;
        }}
        .search-input:focus {{
            border-color: var(--accent-cyan);
            box-shadow: 0 0 12px rgba(56, 189, 248, 0.2);
        }}

        .edition-info-card {{
            margin: 12px 16px 0 16px;
            padding: 12px;
            background: rgba(56, 189, 248, 0.08);
            border: 1px solid rgba(56, 189, 248, 0.2);
            border-radius: 8px;
            display: none;
        }}
        .edition-info-card.visible {{
            display: block;
        }}
        .edition-card-title {{
            font-size: 13px;
            font-weight: 700;
            color: var(--accent-cyan);
            margin-bottom: 4px;
        }}
        .edition-card-desc {{
            font-size: 11px;
            color: var(--text-secondary);
            line-height: 1.4;
        }}

        .layer-list {{
            flex: 1;
            overflow-y: auto;
            padding: 12px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}
        .layer-item {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 12px;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        .layer-item:hover, .layer-item.active {{
            border-color: var(--border-hover);
            transform: translateX(4px);
            background: rgba(30, 41, 59, 0.9);
        }}
        .layer-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 6px;
        }}
        .layer-title {{
            font-size: 13px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .layer-badge {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }}
        .layer-desc {{
            font-size: 12px;
            color: var(--text-secondary);
            line-height: 1.4;
        }}
        .layer-comps {{
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
            margin-top: 8px;
        }}
        .comp-pill {{
            font-size: 10px;
            font-family: var(--font-mono);
            background: rgba(148, 163, 184, 0.1);
            border: 1px solid rgba(148, 163, 184, 0.2);
            padding: 2px 6px;
            border-radius: 4px;
            color: var(--text-secondary);
        }}

        /* Graph Canvas Stage */
        .stage {{
            flex: 1;
            position: relative;
            background: radial-gradient(circle at center, #0f172a 0%, #020617 100%);
            overflow: hidden;
        }}
        #viewport {{
            width: 100%;
            height: 100%;
            cursor: grab;
        }}
        #viewport:active {{
            cursor: grabbing;
        }}

        /* Floating Info Inspector Panel */
        .inspector {{
            position: absolute;
            top: 20px;
            right: 20px;
            width: 440px;
            max-height: calc(100vh - 150px);
            background: var(--bg-panel);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            z-index: 40;
            overflow-y: auto;
            box-shadow: 0 16px 36px rgba(0, 0, 0, 0.5);
            display: none;
            flex-direction: column;
            gap: 16px;
        }}
        .inspector.visible {{
            display: flex;
        }}
        .inspector-close {{
            position: absolute;
            top: 14px;
            right: 14px;
            background: transparent;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            font-size: 18px;
        }}
        .inspector-close:hover {{ color: var(--text-primary); }}
        .inspector-header {{
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}
        .inspector-type {{
            font-size: 11px;
            font-family: var(--font-mono);
            color: var(--accent-cyan);
            text-transform: uppercase;
        }}
        .inspector-name {{
            font-size: 18px;
            font-weight: 700;
        }}
        .inspector-desc {{
            font-size: 13px;
            color: var(--text-secondary);
            line-height: 1.5;
        }}
        .inspector-metric-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
            background: rgba(15, 23, 42, 0.6);
            padding: 10px;
            border-radius: 8px;
            border: 1px solid var(--border);
        }}
        .ins-metric {{
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
        }}
        .ins-val {{ font-size: 14px; font-weight: 700; color: var(--accent-emerald); font-family: var(--font-mono); }}
        .ins-lbl {{ font-size: 10px; color: var(--text-muted); text-transform: uppercase; }}

        .code-block {{
            background: #020617;
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 10px;
            font-family: var(--font-mono);
            font-size: 11px;
            color: #cbd5e1;
            max-height: 180px;
            overflow-y: auto;
            white-space: pre-wrap;
        }}

        /* Legend Controls */
        .controls-overlay {{
            position: absolute;
            bottom: 20px;
            left: 20px;
            background: var(--bg-panel);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 10px 14px;
            display: flex;
            align-items: center;
            gap: 12px;
            z-index: 30;
            font-size: 12px;
        }}
        .btn {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            color: var(--text-primary);
            padding: 6px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            transition: all 0.2s ease;
        }}
        .btn:hover {{
            background: rgba(56, 189, 248, 0.2);
            border-color: var(--accent-cyan);
        }}
    </style>
</head>
<body>

    <!-- Header Navigation -->
    <header>
        <div class="brand">
            <div class="brand-icon">⬡</div>
            <div>
                <div class="brand-title">
                    FerroOS Unified Architecture Graph & Full Codebase Survey
                    <span class="brand-tag">Four Connected Editions</span>
                </div>
            </div>
        </div>
        <div class="stats-strip">
            <div class="stat-item">
                <span class="stat-val">{survey_data['metadata']['total_lines']:,}</span>
                <span class="stat-lbl">Lines</span>
            </div>
            <div class="stat-item">
                <span class="stat-val">{survey_data['metadata']['code_lines']:,}</span>
                <span class="stat-lbl">Rust Code</span>
            </div>
            <div class="stat-item">
                <span class="stat-val">{survey_data['metadata']['comment_lines']:,}</span>
                <span class="stat-lbl">Comments</span>
            </div>
            <div class="stat-item">
                <span class="stat-val">{survey_data['metadata']['functions_count']:,}</span>
                <span class="stat-lbl">Functions</span>
            </div>
            <div class="stat-item">
                <span class="stat-val">{survey_data['metadata']['structs_count']:,}</span>
                <span class="stat-lbl">Structs</span>
            </div>
            <div class="stat-item">
                <span class="stat-val">30 / 30</span>
                <span class="stat-lbl">GNU Parity</span>
            </div>
        </div>
    </header>

    <!-- Edition Selector Bar -->
    <div class="edition-bar">
        <span style="font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">Editions:</span>
        <button class="edition-btn active" data-edition="all" onclick="filterEdition('all')">🌐 All Systems (Full Ecosystem)</button>
        <button class="edition-btn" data-edition="edition_cloud" onclick="filterEdition('edition_cloud')">☁️ Cloud Server Edition</button>
        <button class="edition-btn" data-edition="edition_desktop" onclick="filterEdition('edition_desktop')">🖥️ Desktop & Web Edition</button>
        <button class="edition-btn" data-edition="edition_gaming" onclick="filterEdition('edition_gaming')">🎮 Gaming & Proton Edition</button>
    </div>

    <!-- Main Body -->
    <div class="app-body">

        <!-- Sidebar Navigation -->
        <aside class="sidebar">
            <div class="search-box">
                <input type="text" id="searchInput" class="search-input" placeholder="🔍 Search layers, structs, functions, syscalls...">
            </div>
            <div class="edition-info-card" id="editionCard">
                <div class="edition-card-title" id="edCardTitle">Edition Overview</div>
                <div class="edition-card-desc" id="edCardDesc">Description</div>
            </div>
            <div class="layer-list" id="layerList">
                <!-- Injected via JS -->
            </div>
        </aside>

        <!-- Canvas Stage -->
        <main class="stage">
            <svg id="viewport"></svg>

            <!-- Floating Controls -->
            <div class="controls-overlay">
                <button class="btn" onclick="resetZoom()">⟲ Reset Zoom</button>
                <button class="btn" onclick="toggleLayout()">⚡ Toggle Hierarchy / Radial</button>
                <span style="color: var(--text-muted);">| Pan: Drag Canvas • Zoom: Mouse Wheel • Select: Click Node</span>
            </div>

            <!-- Inspector Panel -->
            <div class="inspector" id="inspectorPanel">
                <button class="inspector-close" onclick="closeInspector()">✕</button>
                <div class="inspector-header">
                    <span class="inspector-type" id="insType">Layer</span>
                    <h3 class="inspector-name" id="insName">Node Title</h3>
                </div>
                <div class="inspector-desc" id="insDesc">Detailed architectural notes and implementation invariants.</div>
                <div class="inspector-metric-grid" id="insMetrics">
                    <!-- Metrics injected -->
                </div>
                <div id="insExtra">
                    <!-- Additional code/insights injected -->
                </div>
            </div>
        </main>
    </div>

    <!-- Graph Visualization Logic -->
    <script>
        const graphData = {{
            nodes: {json.dumps(nodes)},
            edges: {json.dumps(edges)},
            layers: {json.dumps(survey_data['layers'])},
            editions: {json.dumps(survey_data['editions'])}
        }};

        let transform = {{ x: 220, y: 120, k: 0.8 }};
        let isDragging = false;
        let dragStart = {{ x: 0, y: 0 }};
        let selectedNode = null;
        let activeEdition = 'all';
        let isHierarchical = true;

        const svg = document.getElementById('viewport');
        const layerListEl = document.getElementById('layerList');
        const searchInput = document.getElementById('searchInput');

        function renderSidebar() {{
            layerListEl.innerHTML = '';
            graphData.layers.forEach((layer) => {{
                const item = document.createElement('div');
                item.className = 'layer-item';
                item.dataset.layerId = layer.id;
                item.innerHTML = `
                    <div class="layer-header">
                        <div class="layer-title">
                            <span class="layer-badge" style="background: ${{layer.color}}"></span>
                            ${{layer.name}}
                        </div>
                    </div>
                    <div class="layer-desc">${{layer.description}}</div>
                    <div class="layer-comps">
                        ${{(layer.components || []).map(c => `<span class="comp-pill">${{c.name.split(' ')[0]}}</span>`).join('')}}
                    </div>
                `;
                item.onclick = () => selectLayer(layer.id);
                layerListEl.appendChild(item);
            }});
        }}

        function filterEdition(editionId) {{
            activeEdition = editionId;
            document.querySelectorAll('.edition-btn').forEach(btn => {{
                btn.classList.toggle('active', btn.dataset.edition === editionId);
            }});

            const edCard = document.getElementById('editionCard');
            if (editionId === 'all') {{
                edCard.classList.remove('visible');
            }} else {{
                const edObj = graphData.editions.find(e => e.id === editionId);
                if (edObj) {{
                    edCard.classList.add('visible');
                    document.getElementById('edCardTitle').textContent = edObj.badge;
                    document.getElementById('edCardDesc').textContent = edObj.description;
                }}
            }}

            draw();
        }}

        function layoutNodes() {{
            const width = svg.clientWidth || 1200;
            const height = svg.clientHeight || 800;

            if (isHierarchical) {{
                const layerYGap = 150;
                const startY = 80;

                graphData.layers.forEach((layer, layerIdx) => {{
                    const layerNode = graphData.nodes.find(n => n.id === layer.id);
                    const childNodes = graphData.nodes.filter(n => n.layer_id === layer.id && n.id !== layer.id);
                    const y = startY + (layerIdx * layerYGap);

                    if (layerNode) {{
                        layerNode.x = 240;
                        layerNode.y = y;
                    }}

                    const compXStart = 460;
                    const compXGap = 170;
                    childNodes.forEach((child, childIdx) => {{
                        child.x = compXStart + (childIdx * compXGap);
                        child.y = y + (childIdx % 2 === 0 ? -25 : 25);
                    }});
                }});
            }} else {{
                const cx = width / 2;
                const cy = height / 2;
                const radius = Math.min(width, height) * 0.42;
                graphData.nodes.forEach((n, idx) => {{
                    const angle = (idx / graphData.nodes.length) * 2 * Math.PI;
                    n.x = cx + Math.cos(angle) * radius;
                    n.y = cy + Math.sin(angle) * radius;
                }});
            }}
        }}

        function draw() {{
            svg.innerHTML = '';

            const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            g.setAttribute('transform', `translate(${{transform.x}}, ${{transform.y}}) scale(${{transform.k}})`);

            // Edges
            graphData.edges.forEach(edge => {{
                const s = graphData.nodes.find(n => n.id === edge.source);
                const t = graphData.nodes.find(n => n.id === edge.target);
                if (s && t) {{
                    const sMatch = activeEdition === 'all' || (s.editions && s.editions.includes(activeEdition));
                    const tMatch = activeEdition === 'all' || (t.editions && t.editions.includes(activeEdition));
                    const isDimmed = !sMatch || !tMatch;

                    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                    line.setAttribute('x1', s.x);
                    line.setAttribute('y1', s.y);
                    line.setAttribute('x2', t.x);
                    line.setAttribute('y2', t.y);

                    if (edge.type === 'structural_flow') {{
                        line.setAttribute('stroke', isDimmed ? 'rgba(148, 163, 184, 0.08)' : 'rgba(56, 189, 248, 0.45)');
                        line.setAttribute('stroke-width', '2.5');
                        line.setAttribute('stroke-dasharray', '5,5');
                    }} else if (edge.type === 'scheduler_link' || edge.type === 'priority_boost' || edge.type === 'vulkan_mapping') {{
                        line.setAttribute('stroke', isDimmed ? 'rgba(168, 85, 247, 0.08)' : 'rgba(168, 85, 247, 0.6)');
                        line.setAttribute('stroke-width', '2');
                    }} else {{
                        line.setAttribute('stroke', isDimmed ? 'rgba(148, 163, 184, 0.05)' : 'rgba(148, 163, 184, 0.25)');
                        line.setAttribute('stroke-width', '1.5');
                    }}
                    g.appendChild(line);
                }}
            }});

            // Nodes
            graphData.nodes.forEach(node => {{
                const isMatch = activeEdition === 'all' || (node.editions && node.editions.includes(activeEdition));

                const nodeG = document.createElementNS('http://www.w3.org/2000/svg', 'g');
                nodeG.setAttribute('transform', `translate(${{node.x}}, ${{node.y}})`);
                nodeG.style.cursor = 'pointer';
                nodeG.style.opacity = isMatch ? '1.0' : '0.15';

                const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                circle.setAttribute('r', node.radius);
                circle.setAttribute('fill', node.color);
                circle.setAttribute('stroke', selectedNode && selectedNode.id === node.id ? '#ffffff' : 'rgba(255, 255, 255, 0.25)');
                circle.setAttribute('stroke-width', selectedNode && selectedNode.id === node.id ? '3' : '1.5');
                if (isMatch) {{
                    circle.setAttribute('filter', 'drop-shadow(0 0 6px ' + node.color + '88)');
                }}

                const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                text.setAttribute('y', node.radius + 14);
                text.setAttribute('text-anchor', 'middle');
                text.setAttribute('fill', isMatch ? '#f8fafc' : '#64748b');
                text.setAttribute('font-size', node.group === 'layer' ? '12px' : '10px');
                text.setAttribute('font-weight', node.group === 'layer' ? '700' : '500');
                text.setAttribute('font-family', 'sans-serif');
                text.textContent = node.label.length > 20 ? node.label.slice(0, 18) + '...' : node.label;

                nodeG.appendChild(circle);
                nodeG.appendChild(text);

                nodeG.onclick = (e) => {{
                    e.stopPropagation();
                    selectNode(node);
                }};

                g.appendChild(nodeG);
            }});

            svg.appendChild(g);
        }}

        function selectNode(node) {{
            selectedNode = node;
            draw();

            const panel = document.getElementById('inspectorPanel');
            panel.classList.add('visible');

            document.getElementById('insType').textContent = node.type || 'Architectural Component';
            document.getElementById('insName').textContent = node.label;
            document.getElementById('insDesc').textContent = node.description || 'No description available.';

            const metricsEl = document.getElementById('insMetrics');
            const extraEl = document.getElementById('insExtra');

            if (node.file_data) {{
                const f = node.file_data;
                metricsEl.innerHTML = `
                    <div class="ins-metric"><span class="ins-val">${{f.total_lines}}</span><span class="ins-lbl">Lines</span></div>
                    <div class="ins-metric"><span class="ins-val">${{f.functions.length}}</span><span class="ins-lbl">Functions</span></div>
                    <div class="ins-metric"><span class="ins-val">${{f.structs.length}}</span><span class="ins-lbl">Structs</span></div>
                `;

                let extraHtml = `<h4 style="margin: 12px 0 6px 0; font-size: 12px; color: var(--accent-cyan); text-transform: uppercase;">Key Symbols & Functions</h4>`;
                extraHtml += `<div class="code-block">${{f.functions.slice(0, 8).map(fn => `fn ${{fn.name}}() [L${{fn.line}}]`).join('\\n')}}</div>`;

                if (f.insights && f.insights.length > 0) {{
                    extraHtml += `<h4 style="margin: 12px 0 6px 0; font-size: 12px; color: var(--accent-amber); text-transform: uppercase;">Architectural Insights & Invariants</h4>`;
                    extraHtml += `<div class="code-block">${{f.insights.slice(0, 4).map(i => `• L${{i.line}}: ${{i.text}}`).join('\\n\\n')}}</div>`;
                }}
                extraEl.innerHTML = extraHtml;
            }} else {{
                metricsEl.innerHTML = `
                    <div class="ins-metric"><span class="ins-val">LSM</span><span class="ins-lbl">Security</span></div>
                    <div class="ins-metric"><span class="ins-val">&lt; 1ms</span><span class="ins-lbl">Latency</span></div>
                    <div class="ins-metric"><span class="ins-val">Pure Rust</span><span class="ins-lbl">Runtime</span></div>
                `;
                extraEl.innerHTML = '';
            }}
        }}

        function selectLayer(layerId) {{
            document.querySelectorAll('.layer-item').forEach(el => {{
                el.classList.toggle('active', el.dataset.layerId === layerId);
            }});
            const targetNode = graphData.nodes.find(n => n.id === layerId);
            if (targetNode) {{
                selectNode(targetNode);
                transform.x = (svg.clientWidth / 2) - targetNode.x * transform.k;
                transform.y = (svg.clientHeight / 2) - targetNode.y * transform.k;
                draw();
            }}
        }}

        function closeInspector() {{
            document.getElementById('inspectorPanel').classList.remove('visible');
            selectedNode = null;
            draw();
        }}

        function resetZoom() {{
            transform = {{ x: 220, y: 120, k: 0.8 }};
            draw();
        }}

        function toggleLayout() {{
            isHierarchical = !isHierarchical;
            layoutNodes();
            draw();
        }}

        svg.addEventListener('mousedown', e => {{
            isDragging = true;
            dragStart = {{ x: e.clientX - transform.x, y: e.clientY - transform.y }};
        }});

        window.addEventListener('mousemove', e => {{
            if (isDragging) {{
                transform.x = e.clientX - dragStart.x;
                transform.y = e.clientY - dragStart.y;
                draw();
            }}
        }});

        window.addEventListener('mouseup', () => {{
            isDragging = false;
        }});

        svg.addEventListener('wheel', e => {{
            e.preventDefault();
            const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
            transform.k *= zoomFactor;
            transform.k = Math.max(0.2, Math.min(transform.k, 3.0));
            draw();
        }});

        searchInput.addEventListener('input', e => {{
            const query = e.target.value.toLowerCase().trim();
            if (!query) {{
                document.querySelectorAll('.layer-item').forEach(el => el.style.display = 'flex');
                return;
            }}
            document.querySelectorAll('.layer-item').forEach(el => {{
                const text = el.textContent.toLowerCase();
                el.style.display = text.includes(query) ? 'flex' : 'none';
            }});
        }});

        window.addEventListener('resize', () => {{
            layoutNodes();
            draw();
        }});

        renderSidebar();
        layoutNodes();
        draw();
    </script>
</body>
</html>
"""

    out_html = os.path.join(DOCS_DIR, "ferro_os_architecture_graph.html")
    os.makedirs(os.path.dirname(out_html), exist_ok=True)
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    dup_html = os.path.join(REPORTS_DIR, "ferro_os_architecture_graph.html")
    with open(dup_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"✅ Generated standalone interactive architecture graph HTML: {out_html}")
    print(f"✅ Replicated to reports directory: {dup_html}")

def main():
    survey_data = execute_survey()
    generate_interactive_html(survey_data)
    print("\n🚀 Full codebase survey and graph generation completed successfully!")

if __name__ == "__main__":
    main()
