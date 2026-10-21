#!/usr/bin/env python3
"""
tools/test_e2e_gaming_layer.py - 12-Scenario Empirical Test Suite for FerroOS
Steam & Proton Multi-Architecture Gaming Layer (Box64/FEX, DXVK, and Proton Integration).

Zero mocks: tests real ELF/PE binary header detection, real environment variables,
real Steam compatibility manifests, real .desktop shortcuts, and GameMode lifecycle.
"""

import sys
import os
import shutil
import struct
import subprocess
import time

GREEN = "\033[92m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"

PASS_COUNT = 0
FAIL_COUNT = 0

def resolve_bin(name):
    candidates = [
        shutil.which(name),
        os.path.join(os.getcwd(), f"target/release/{name}"),
        os.path.join(os.getcwd(), f"target/debug/{name}"),
        f"/usr/local/bin/{name}",
        f"/usr/bin/{name}",
    ]
    for c in candidates:
        if c and os.path.exists(c) and os.access(c, os.X_OK):
            return c
    return None

FERRO_CORE = resolve_bin("ferro-core")
RPK = resolve_bin("ferro-pkg")

def log_test(name, passed, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if passed:
        PASS_COUNT += 1
        print(f"  {GREEN}✅ PASS{RESET}: {name} {BLUE}{detail}{RESET}")
    else:
        FAIL_COUNT += 1
        print(f"  {RED}❌ FAIL{RESET}: {name} {RED}{detail}{RESET}")

def run_cmd(cmd_list):
    try:
        res = subprocess.run(cmd_list, capture_output=True, text=True, timeout=30)
        return res.returncode, res.stdout, res.stderr
    except Exception as e:
        return -1, "", str(e)

print("================================================================================")
print("  FERRO-OS STEAM & PROTON MULTI-ARCH GAMING LAYER VALIDATION SUITE            ")
print("================================================================================")

if not FERRO_CORE:
    print(f"{RED}Error: ferro-core binary not found!{RESET}")
    sys.exit(1)

print(f"Using ferro-core: {FERRO_CORE}")
if RPK:
    print(f"Using rpk:        {RPK}")

test_dir = "/tmp/ferro_game_test"
os.makedirs(test_dir, exist_ok=True)

# ------------------------------------------------------------------------------
# SCENARIO 01: Host Architecture & Gaming Layer Introspection
# ------------------------------------------------------------------------------
print("\n[Scenario 01] Host Architecture & Gaming Layer Introspection")
code, out, err = run_cmd([FERRO_CORE, "game", "status"])
status_ok = (
    code == 0
    and "Host System Architecture:" in out
    and "Box64 Dynamic Translation:" in out
    and "DXVK D3D9/10/11 -> Vulkan:" in out
    and "Dynamic GameMode Engine:" in out
)
log_test("Gaming Subsystem Introspection", status_ok, f"Exit: {code}")

# ------------------------------------------------------------------------------
# SCENARIO 02: Native Linux ELF ARM64 Binary Identification
# ------------------------------------------------------------------------------
print("\n[Scenario 02] Native Linux ELF ARM64 Binary Identification")
elf_arm64_path = os.path.join(test_dir, "game_arm64.bin")
# ELF Header: 0x7F 'E' 'L' 'F', class=2 (64-bit), data=1 (little endian), version=1
# e_machine at offset 18 (2 bytes little endian) = 0x00B7 (AArch64)
with open(elf_arm64_path, "wb") as f:
    hdr = bytearray(64)
    hdr[0:4] = b"\x7fELF"
    hdr[4] = 2 # 64-bit
    hdr[5] = 1 # little endian
    hdr[18:20] = struct.pack("<H", 0x00B7)
    f.write(hdr)

code, out, err = run_cmd([FERRO_CORE, "game", "probe", elf_arm64_path])
arm64_ok = (code == 0 and "Linux ELF 64-bit (ARM aarch64 native)" in out and "Direct Native Execution" in out)
log_test("Native Linux ELF ARM64 Binary Probe", arm64_ok, "AArch64 native direct routing")

# ------------------------------------------------------------------------------
# SCENARIO 03: Foreign Linux ELF x86_64 Binary Identification & Translation Routing
# ------------------------------------------------------------------------------
print("\n[Scenario 03] Foreign Linux ELF x86_64 Binary Identification & Translation Routing")
elf_x86_64_path = os.path.join(test_dir, "game_x86_64.bin")
with open(elf_x86_64_path, "wb") as f:
    hdr = bytearray(64)
    hdr[0:4] = b"\x7fELF"
    hdr[4] = 2 # 64-bit
    hdr[5] = 1 # little endian
    hdr[18:20] = struct.pack("<H", 0x003E) # EM_X86_64
    f.write(hdr)

code, out, err = run_cmd([FERRO_CORE, "game", "probe", elf_x86_64_path])
x86_64_ok = (code == 0 and "Linux ELF 64-bit (x86_64 / AMD64)" in out and "BOX64" in out)
log_test("Foreign Linux ELF x86_64 Binary Probe", x86_64_ok, "Routed to Box64 DBT bridge")

# ------------------------------------------------------------------------------
# SCENARIO 04: Legacy 32-bit Linux ELF i386 Binary Identification
# ------------------------------------------------------------------------------
print("\n[Scenario 04] Legacy 32-bit Linux ELF i386 Binary Identification")
elf_i386_path = os.path.join(test_dir, "game_i386.bin")
with open(elf_i386_path, "wb") as f:
    hdr = bytearray(64)
    hdr[0:4] = b"\x7fELF"
    hdr[4] = 1 # 32-bit
    hdr[5] = 1 # little endian
    hdr[18:20] = struct.pack("<H", 0x0003) # EM_386
    f.write(hdr)

code, out, err = run_cmd([FERRO_CORE, "game", "probe", elf_i386_path])
i386_ok = (code == 0 and "Linux ELF 32-bit (i386)" in out)
log_test("Legacy 32-bit Linux ELF i386 Binary Probe", i386_ok, "Identified i386 multi-lib binary")

# ------------------------------------------------------------------------------
# SCENARIO 05: Windows PE 64-bit Executable Identification (DirectX / Vulkan Target)
# ------------------------------------------------------------------------------
print("\n[Scenario 05] Windows PE 64-bit Executable Identification")
pe_64_path = os.path.join(test_dir, "game_win64.exe")
with open(pe_64_path, "wb") as f:
    data = bytearray(256)
    data[0:2] = b"MZ" # DOS Header magic
    # Offset 0x3C points to PE header
    pe_offset = 0x80
    data[0x3C:0x40] = struct.pack("<I", pe_offset)
    # PE signature at 0x80
    data[pe_offset:pe_offset+4] = b"PE\x00\x00"
    # Machine type at pe_offset + 4: 0x8664 = IMAGE_FILE_MACHINE_AMD64
    data[pe_offset+4:pe_offset+6] = struct.pack("<H", 0x8664)
    f.write(data)

code, out, err = run_cmd([FERRO_CORE, "game", "probe", pe_64_path])
pe64_ok = (code == 0 and "Windows PE 64-bit Executable (AMD64)" in out and "Proton" in out)
log_test("Windows PE 64-bit Executable Probe", pe64_ok, "Routed to Proton/Wine + DXVK pipeline")

# ------------------------------------------------------------------------------
# SCENARIO 06: Windows PE 32-bit Executable Identification
# ------------------------------------------------------------------------------
print("\n[Scenario 06] Windows PE 32-bit Executable Identification")
pe_32_path = os.path.join(test_dir, "game_win32.exe")
with open(pe_32_path, "wb") as f:
    data = bytearray(256)
    data[0:2] = b"MZ"
    pe_offset = 0x80
    data[0x3C:0x40] = struct.pack("<I", pe_offset)
    data[pe_offset:pe_offset+4] = b"PE\x00\x00"
    # Machine type: 0x014C = IMAGE_FILE_MACHINE_I386
    data[pe_offset+4:pe_offset+6] = struct.pack("<H", 0x014C)
    f.write(data)

code, out, err = run_cmd([FERRO_CORE, "game", "probe", pe_32_path])
pe32_ok = (code == 0 and "Windows PE 32-bit Executable (i386)" in out)
log_test("Windows PE 32-bit Executable Probe", pe32_ok, "Identified Win32 PE binary")

# ------------------------------------------------------------------------------
# SCENARIO 07: Executable Script / Wrapper Identification
# ------------------------------------------------------------------------------
print("\n[Scenario 07] Executable Script / Wrapper Identification")
script_path = os.path.join(test_dir, "run_game.sh")
with open(script_path, "w") as f:
    f.write("#!/bin/bash\necho 'Starting native Linux game engine...'\n")
os.chmod(script_path, 0o755)

code, out, err = run_cmd([FERRO_CORE, "game", "probe", script_path])
script_ok = (code == 0 and "Executable Script" in out and "/bin/bash" in out)
log_test("Executable Script Probe", script_ok, "Identified /bin/bash launcher script")

# ------------------------------------------------------------------------------
# SCENARIO 08: Steam Proton Compatibility Tool Registration
# ------------------------------------------------------------------------------
print("\n[Scenario 08] Steam Proton Compatibility Tool Registration")
code, out, err = run_cmd([FERRO_CORE, "game", "setup-steam"])
home = os.environ.get("HOME", "/root")
steam_vdf = os.path.join(home, ".local/share/Steam/compatibilitytools.d/ferro-proton/compatibilitytool.vdf")
steam_runner = os.path.join(home, ".local/share/Steam/compatibilitytools.d/ferro-proton/proton-ferro")

steam_ok = (
    code == 0
    and os.path.exists(steam_vdf)
    and os.path.exists(steam_runner)
    and os.access(steam_runner, os.X_OK)
)
if steam_ok:
    with open(steam_vdf, "r") as f:
        vdf_text = f.read()
    steam_ok = "ferro-proton" in vdf_text and "Proton - FerroOS Optimized" in vdf_text

log_test("Steam Proton Compatibility Tool Registration", steam_ok, f"VDF created at {steam_vdf}")

# ------------------------------------------------------------------------------
# SCENARIO 09: KDE Plasma Desktop Shortcut Generator
# ------------------------------------------------------------------------------
print("\n[Scenario 09] KDE Plasma Desktop Shortcut Generator")
code, out, err = run_cmd([
    FERRO_CORE, "game", "shortcut", script_path,
    "--name", "Cyberpunk Rust", "--icon", "steam_icon_1091500"
])
desktop_path = os.path.join(home, ".local/share/applications/ferro-cyberpunk-rust.desktop")
shortcut_ok = (code == 0 and os.path.exists(desktop_path))
if shortcut_ok:
    with open(desktop_path, "r") as f:
        dtext = f.read()
    shortcut_ok = (
        "Name=Cyberpunk Rust" in dtext
        and "Exec=ferro-core game run" in dtext
        and "Icon=steam_icon_1091500" in dtext
    )
log_test("KDE Plasma Desktop Shortcut Generator", shortcut_ok, f"Shortcut created at {desktop_path}")

# ------------------------------------------------------------------------------
# SCENARIO 10: Automatic GameMode & Scheduler Elevation on Launch
# ------------------------------------------------------------------------------
print("\n[Scenario 10] Automatic GameMode & Scheduler Elevation on Launch")
# Launch test binary through ferro-core game run
test_runner_script = os.path.join(test_dir, "test_game_runner.sh")
with open(test_runner_script, "w") as f:
    f.write("#!/bin/sh\necho 'GAME_EXEC_SUCCESS'\n")
os.chmod(test_runner_script, 0o755)

code, out, err = run_cmd([FERRO_CORE, "game", "run", test_runner_script])
runner_ok = (
    code == 0
    and "GAME_EXEC_SUCCESS" in out
    and "GameMode Profile: ACTIVE" in out or "High-Performance" in out
)
log_test("GameMode Automatic Elevation on Launch", runner_ok, "Engaged GameMode & gaming schedule")

# ------------------------------------------------------------------------------
# SCENARIO 11: Clean Teardown & Post-Game Profile Restoration
# ------------------------------------------------------------------------------
print("\n[Scenario 11] Clean Teardown & Post-Game Profile Restoration")
# When game process exits, GameRunner should restore balanced governor
post_restore_ok = "Restoring balanced system profile" in out and "BALANCED" in out
log_test("Post-Game Profile Restoration", post_restore_ok, "Restored balanced profile on exit")

# ------------------------------------------------------------------------------
# SCENARIO 12: High-Frequency Probe & Launcher Churn Stress Test
# ------------------------------------------------------------------------------
print("\n[Scenario 12] High-Frequency Probe & Launcher Churn Stress Test")
probe_targets = [elf_arm64_path, elf_x86_64_path, elf_i386_path, pe_64_path, pe_32_path, script_path]
t_churn_0 = time.time()
churn_count = 60
churn_success = True

for i in range(churn_count):
    target = probe_targets[i % len(probe_targets)]
    c, o, _ = run_cmd([FERRO_CORE, "game", "probe", target])
    if c != 0:
        churn_success = False
        break

churn_dur = time.time() - t_churn_0
churn_rate = churn_count / churn_dur if churn_dur > 0 else 0
log_test(
    "High-Frequency Binary Probe Churn Stress Test",
    churn_success,
    f"{churn_count} probes in {churn_dur:.2f} s ({churn_rate:.1f} ops/s)"
)

# Cleanup test directory
shutil.rmtree(test_dir, ignore_errors=True)

# ------------------------------------------------------------------------------
# FINAL REPORT
# ------------------------------------------------------------------------------
print("\n================================================================================")
print(f"  FERRO-OS GAMING LAYER RESULTS: {PASS_COUNT} / 12 SCENARIOS PASSED")
print("================================================================================")

if FAIL_COUNT > 0:
    print(f"{RED}❌ TEST RUN FAILED with {FAIL_COUNT} failures.{RESET}")
    sys.exit(1)
else:
    print(f"{GREEN}🏆 ALL 12 / 12 STEAM & PROTON GAMING LAYER SCENARIOS PASSED WITH 100% FIDELITY!{RESET}")
    sys.exit(0)
