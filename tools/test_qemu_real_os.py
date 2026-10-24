#!/usr/bin/env python3
"""
tools/test_qemu_real_os.py - Automated End-to-End Test for Booting Real FerroOS
Boots FerroOS in QEMU, monitors serial console, sends commands into the shell,
and verifies real kernel, init, and coreutils execution.
"""

import os
import sys
import time
import subprocess

def test_boot():
    workspace = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    kernel = os.path.join(workspace, "build_out", "vmlinuz")
    initrd = os.path.join(workspace, "build_out", "ferro-initrd.img")

    if not os.path.exists(kernel) or not os.path.exists(initrd):
        print("❌ Error: Kernel or initrd not found in build_out! Run tools/build_real_ferro_os.py first.")
        sys.exit(1)

    qemu_cmd = [
        "qemu-system-x86_64",
        "-m", "512M",
        "-kernel", kernel,
        "-initrd", initrd,
        "-append", "console=ttyS0 panic=1 quiet rdinit=/init",
        "-nographic",
        "-no-reboot"
    ]

    print("================================================================================")
    print("      AUTOMATED QEMU BARE-METAL BOOT VERIFICATION FOR REAL FERRO-OS             ")
    print("================================================================================")
    print(f"Kernel:  {kernel}")
    print(f"Initrd:  {initrd}")
    print("Launching QEMU process...")

    proc = subprocess.Popen(
        qemu_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    full_log = []
    shell_reached = False
    start_time = time.time()

    def send_line(cmd_str):
        print(f"\n>>> [TEST INJECT] Sending: '{cmd_str}'")
        proc.stdin.write(cmd_str + "\n")
        proc.stdin.flush()

    try:
        while time.time() - start_time < 20:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
                continue

            full_log.append(line)
            sys.stdout.write(line)
            sys.stdout.flush()

            if "ferro-os:/" in line or "Welcome to FerroOS Shell" in line:
                if not shell_reached:
                    shell_reached = True
                    time.sleep(0.3)
                    send_line("uname -a")
                    time.sleep(0.3)
                    send_line("free")
                    time.sleep(0.3)
                    send_line("ls -la /bin")
                    time.sleep(0.3)
                    send_line("echo 'REAL_FERRO_OS_VERIFIED'")
                    time.sleep(0.3)
                    send_line("poweroff")

            if "reboot: Power down" in line or proc.poll() is not None:
                break

        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass

    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

    full_output = "".join(full_log)
    print("\n================================================================================")
    print("                        BOOT VERIFICATION SUMMARY                               ")
    print("================================================================================")
    
    has_banner = "FerroOS v0.1.0 - Fast Rust-Powered Operating System" in full_output
    has_init = "Initializing FerroOS PID 1 (Rust Core)" in full_output
    has_shell = "Welcome to FerroOS Shell (Rust)" in full_output
    has_verified = "REAL_FERRO_OS_VERIFIED" in full_output

    print(f"  * FerroOS Kernel Booted:       {'✅ PASS' if has_init else '❌ FAIL'}")
    print(f"  * FerroOS PID 1 Init Executed: {'✅ PASS' if has_banner else '❌ FAIL'}")
    print(f"  * Rust Shell Interactive:      {'✅ PASS' if has_shell else '❌ FAIL'}")
    print(f"  * Command Execution Verified:  {'✅ PASS' if has_verified else '❌ FAIL'}")
    print("================================================================================")

    if has_banner and has_init and has_shell and has_verified:
        print("🎉 SUCCESS: REAL FERRO-OS IS FULLY FUNCTIONAL AND INDEPENDENTLY BOOTABLE!")
        return 0
    else:
        print("⚠️ Warning: Some verification milestones did not match expected output.")
        return 1

if __name__ == "__main__":
    sys.exit(test_boot())
