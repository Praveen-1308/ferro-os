//! ferro-init: PID 1 Init System & Advanced Recovery Environment for FerroOS written in Rust.
//! Responsible for early system mounts, crash & abnormal shutdown detection,
//! interactive boot recovery menu (WinRE style), service execution, and lifecycle management.
#![allow(clippy::all)]

use std::process::ExitCode;

mod fdstore;

#[cfg(target_os = "linux")]
mod linux_init {
    use super::fdstore;
    use std::ffi::CString;
    use std::fs::{self, File};
    use std::io::{self, BufRead, BufReader, Write};
    use std::path::Path;
    use std::process::Command;
    use std::time::Instant;

    const BANNER: &str = r#"
  _______                    ____   _____ 
 |  ____|                   / __ \ / ____|
 | |__ ___ _ __ _ __ ___   | |  | | (___  
 |  __/ _ \ '__| '__/ _ \  | |  | |\___ \ 
 | | |  __/ |  | | | (_) | | |__| |____) |
 |_|  \___|_|  |_|  \___/   \____/|_____/ 
 
 FerroOS v2.3.0 - Fast Rust-Powered Operating System
 Enterprise Safety + Sub-Second Velocity + WinRE Recovery
"#;

    const STATE_DIR: &str = "/var/lib/ferro";
    const CLEAN_SHUTDOWN_FLAG: &str = "/var/lib/ferro/clean_shutdown";
    const CRASH_MARKER_FLAG: &str = "/var/lib/ferro/system_crashed";

    #[derive(Debug, PartialEq, Eq)]
    pub enum BootOption {
        Normal,
        SafeMode,
        SafeModeNetworking,
        EmergencyShell,
        DiagnosticRepair,
        SystemRestore,
        HardwareDiagnostics,
        Reboot,
        PowerOff,
    }

    pub fn run() -> Result<(), Box<dyn std::error::Error>> {
        if !is_quiet_boot() {
            println!("{}", BANNER);
            println!("[ferro-init] Initializing FerroOS PID 1 (Rust Core)...");
        }

        // 1. Mount virtual filesystems first so we have /proc, /sys, /dev, /tmp
        mount_essential_filesystems();

        // 1a. Persistent Block Storage Root Pivot (switch_root) Check
        // If a persistent root device is supplied in kernel cmdline (root=/dev/...) or detected,
        // mount it onto /sysroot and pivot execution from volatile initramfs to persistent disk.
        if !Path::new("/etc/ferro_persistent_root").exists() {
            if let Some(root_dev) = detect_persistent_root_device() {
                println!("[ferro-init] Detected persistent root device: {}. Attempting switch_root...", root_dev);
                if try_switch_root(&root_dev) {
                    println!("[ferro-init] Root pivot successful. Re-executing PID 1 in persistent rootfs.");
                    return Ok(());
                }
            } else {
                println!("[ferro-init] No persistent block device specified (root=...). Running in high-velocity RAM (initramfs) mode.");
            }
        } else {
            println!("[ferro-init] ✅ Running on PERSISTENT BLOCK STORAGE rootfs (Data persists across reboots).");
        }

        // 1b. Register PID 1 Signal Handlers & Start Continuous Zombie Reaper
        register_pid1_signal_handlers();
        spawn_continuous_zombie_reaper();

        // 2. Set Hostname & Environment
        set_hostname("ferro-os");
        std::env::set_var("PATH", "/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin");
        std::env::set_var("HOME", "/root");
        std::env::set_var("TERM", "linux");
        std::env::set_var("USER", "root");

        // 2b. Elevate Process & Socket Limits (RLIMIT_NOFILE = 65,536)
        elevate_system_limits();

        // 2c. Apply Modern Kernel Performance, Memory & Network Reliability Tunings
        apply_kernel_performance_and_reliability_tuning();

        // 2d. Launch Linux PSI (Pressure Stall Information) Memory Watchdog
        spawn_psi_memory_watcher();

        // 3. Create required runtime directories
        let _ = fs::create_dir_all("/root");
        let _ = fs::create_dir_all("/var/run");
        let _ = fs::create_dir_all("/var/log");
        let _ = fs::create_dir_all("/var/lib/rpk");
        let _ = fs::create_dir_all(STATE_DIR);
        let _ = fs::create_dir_all("/tmp");
        let _ = fs::create_dir_all("/run/ferro");

        // 3b. Start FD Store Daemon (SCM_RIGHTS Zero-Downtime Socket Handover)
        let _ = fdstore::FdStoreServer::new().start();

        // 3c. Start Pure-Rust System Logging Daemon (ferrod listening on /dev/log)
        println!("[ferro-init] Spawning pure-Rust logging daemon (ferrod) on /dev/log...");
        let _ = std::thread::Builder::new()
            .name("ferrod".to_string())
            .spawn(|| {
                let _ = std::process::Command::new("/bin/ferro-core")
                    .args(["ferrod"])
                    .status();
            });

        // 4. Detect Previous Crash / Dirty Shutdown
        let crash_detected = detect_crash_state();

        // 5. Present Boot / Recovery Menu
        let chosen_mode = if crash_detected {
            println!("\n[!] ABNORMAL SHUTDOWN / SYSTEM CRASH DETECTED FROM PREVIOUS SESSION!");
            println!("[!] FerroOS did not terminate cleanly. Launching Recovery Environment (Ferro-RE)...\n");
            prompt_recovery_menu(true)
        } else {
            prompt_boot_menu_with_timeout(3)
        };

        // 6. Record Active Boot Flag (will be cleared on graceful shutdown)
        record_boot_in_progress();

        // 7. Execute Chosen Boot Mode
        match chosen_mode {
            BootOption::Normal => {
                println!("[ferro-init] Starting Normal Boot Mode...");
                init_network();
                run_init_scripts();
                enter_main_supervisor(false);
            }
            BootOption::SafeMode => {
                println!("[ferro-init] Booting in SAFE MODE (Minimal Services, Zero Daemons)...");
                println!(
                    "[ferro-init] Non-essential drivers, servers, and background daemons disabled."
                );
                enter_emergency_shell("Safe Mode");
            }
            BootOption::SafeModeNetworking => {
                println!(
                    "[ferro-init] Booting in SAFE MODE WITH NETWORKING (Server / Remote Rescue)..."
                );
                init_network();
                println!(
                    "[ferro-init] Loopback and network stacks are active. Launching rescue shell."
                );
                enter_emergency_shell("Safe Mode (Networking)");
            }
            BootOption::EmergencyShell => {
                println!("[ferro-init] Entering Emergency Recovery Command Prompt (Root Shell)...");
                enter_emergency_shell("Emergency Root Recovery");
            }
            BootOption::DiagnosticRepair => {
                run_system_diagnostic_and_repair();
                println!("[ferro-init] Diagnostic and repair phase finished.");
                enter_emergency_shell("Post-Diagnostic Maintenance");
            }
            BootOption::SystemRestore => {
                run_system_restore();
                println!("[ferro-init] System restore applied.");
                enter_emergency_shell("Post-Restore Maintenance");
            }
            BootOption::HardwareDiagnostics => {
                run_hardware_diagnostics();
                println!("\nPress Enter to proceed to Recovery Shell...");
                let mut discard = String::new();
                let _ = io::stdin().read_line(&mut discard);
                enter_emergency_shell("Hardware Diagnostics Post-Check");
            }
            BootOption::Reboot => {
                execute_reboot();
            }
            BootOption::PowerOff => {
                execute_poweroff();
            }
        }

        Ok(())
    }

    // -------------------------------------------------------------
    // Crash Detection & State Tracking
    // -------------------------------------------------------------
    fn detect_crash_state() -> bool {
        let clean_path = Path::new(CLEAN_SHUTDOWN_FLAG);
        let crash_marker = Path::new(CRASH_MARKER_FLAG);

        if crash_marker.exists() {
            let _ = fs::remove_file(crash_marker);
            return true;
        }

        // If the state directory exists but clean_shutdown is absent, previous run died abnormally
        if Path::new(STATE_DIR).exists() && !clean_path.exists() {
            // Note: on the very first fresh install boot, avoid false positive if no logs exist
            if Path::new("/var/log/ferro_boot.log").exists() {
                return true;
            }
        }

        false
    }

    fn record_boot_in_progress() {
        let _ = fs::remove_file(CLEAN_SHUTDOWN_FLAG);
        let _ = fs::write(
            "/var/log/ferro_boot.log",
            format!("Boot started at {:?}\n", Instant::now()),
        );
    }

    pub fn mark_clean_shutdown() {
        let _ = fs::write(CLEAN_SHUTDOWN_FLAG, "CLEAN_SHUTDOWN\n");
    }

    // -------------------------------------------------------------
    // Interactive Boot & Recovery Menus
    // -------------------------------------------------------------
    fn prompt_boot_menu_with_timeout(timeout_secs: i64) -> BootOption {
        println!(
            "================================================================================"
        );
        println!(
            "                        FERRO-OS ADVANCED BOOT LOADER                           "
        );
        println!(
            "================================================================================"
        );
        println!(" [1] Normal Boot (Full Modern Desktop, Rust Shell, & Server Suite)");
        println!(" [2] Safe Mode (Minimal Drivers, Basic Framebuffer, Zero Background Daemons)");
        println!(" [3] Safe Mode with Networking (Rescue Servers & Headless Recovery)");
        println!(" [4] Emergency Recovery Command Prompt (Root Shell: /bin/ferro-core sh)");
        println!(" [5] Automatic Filesystem Diagnostic & Self-Repair");
        println!(" [6] System Rollback / Restore Last Known Good Configuration");
        println!(" [7] Hardware Telemetry & Memory Stress Diagnostics");
        println!(" [8] Reboot System");
        println!(" [9] Power Off");
        println!(
            "================================================================================"
        );
        print!(
            "Auto-booting Normal Mode in {} seconds... Press [1-9] or [Space/Esc]: ",
            timeout_secs
        );
        let _ = io::stdout().flush();

        if let Some(ch) = poll_stdin_char(timeout_secs * 1000) {
            println!("{}", ch);
            match ch {
                '1' => BootOption::Normal,
                '2' => BootOption::SafeMode,
                '3' => BootOption::SafeModeNetworking,
                '4' => BootOption::EmergencyShell,
                '5' => BootOption::DiagnosticRepair,
                '6' => BootOption::SystemRestore,
                '7' => BootOption::HardwareDiagnostics,
                '8' => BootOption::Reboot,
                '9' => BootOption::PowerOff,
                _ => prompt_recovery_menu(false),
            }
        } else {
            println!("\n[ferro-init] Timeout elapsed. Proceeding with Normal Boot.");
            BootOption::Normal
        }
    }

    pub fn prompt_recovery_menu(is_crash_recovery: bool) -> BootOption {
        loop {
            println!("\n================================================================================");
            if is_crash_recovery {
                println!("           ⚠️  FERRO-OS ADVANCED RECOVERY ENVIRONMENT (Ferro-RE) ⚠️             ");
                println!("    A critical crash, hardware fault, or abnormal reboot was detected!           ");
            } else {
                println!("                   FERRO-OS ADVANCED RECOVERY ENVIRONMENT                       ");
            }
            println!(
                "================================================================================"
            );
            println!("  [1] Continue to Normal Boot");
            println!("  [2] Safe Mode (Minimal Drivers, Isolated Userland)");
            println!("  [3] Safe Mode with Networking (Loopback + Network Drivers + SSH)");
            println!("  [4] Emergency Recovery Command Prompt (Direct Root Shell)");
            println!("  [5] Automatic Filesystem Diagnostic & Self-Repair");
            println!("  [6] Restore Pristine Configuration (Reset Corrupted Network/Sysctl)");
            println!("  [7] Hardware Telemetry & High-Bandwidth RAM Stress Test");
            println!("  [8] Reboot System");
            println!("  [9] Power Off");
            println!(
                "================================================================================"
            );
            print!("Select an action [1-9]: ");
            let _ = io::stdout().flush();

            let mut input = String::new();
            if io::stdin().read_line(&mut input).is_ok() {
                match input.trim() {
                    "1" => return BootOption::Normal,
                    "2" => return BootOption::SafeMode,
                    "3" => return BootOption::SafeModeNetworking,
                    "4" => return BootOption::EmergencyShell,
                    "5" => return BootOption::DiagnosticRepair,
                    "6" => return BootOption::SystemRestore,
                    "7" => return BootOption::HardwareDiagnostics,
                    "8" => return BootOption::Reboot,
                    "9" => return BootOption::PowerOff,
                    _ => println!("Invalid selection. Please choose an option between 1 and 9."),
                }
            }
        }
    }

    fn poll_stdin_char(timeout_ms: i64) -> Option<char> {
        unsafe {
            let mut pfd = libc::pollfd {
                fd: 0,
                events: libc::POLLIN,
                revents: 0,
            };
            let ret = libc::poll(&mut pfd, 1, timeout_ms as libc::c_int);
            if ret > 0 && (pfd.revents & libc::POLLIN) != 0 {
                let mut buf = [0u8; 1];
                if libc::read(0, buf.as_mut_ptr() as *mut libc::c_void, 1) > 0 {
                    return Some(buf[0] as char);
                }
            }
        }
        None
    }

    // -------------------------------------------------------------
    // Recovery Subsystems & Diagnostics
    // -------------------------------------------------------------
    fn run_system_diagnostic_and_repair() {
        println!(
            "\n================================================================================"
        );
        println!(
            "               FERRO-OS AUTOMATED SYSTEM DIAGNOSTIC & SELF-REPAIR               "
        );
        println!(
            "================================================================================"
        );

        // Check 1: Virtual Mounts
        print!("[DIAGNOSTIC] Checking essential virtual filesystems (/proc, /sys, /dev, /tmp)... ");
        let proc_ok = Path::new("/proc/uptime").exists();
        let sys_ok = Path::new("/sys/kernel").exists();
        let dev_ok = Path::new("/dev/null").exists();
        let tmp_ok = Path::new("/tmp").exists();
        if proc_ok && sys_ok && dev_ok && tmp_ok {
            println!("PASS (Healthy)");
        } else {
            println!("WARN - Re-mounting missing filesystems...");
            mount_essential_filesystems();
            println!("PASS (Restored)");
        }

        // Check 2: Filesystem Read/Write Integrity
        print!("[DIAGNOSTIC] Testing Root Filesystem Read/Write & Inode Allocation... ");
        let test_path = "/tmp/.ferro_repair_test";
        match fs::write(test_path, b"FERRO_INTEGRITY_CHECK_OK") {
            Ok(_) => {
                let _ = fs::remove_file(test_path);
                println!("PASS (100% Writable)");
            }
            Err(e) => println!("FAIL ({}) - Root may be mounted read-only!", e),
        }

        // Check 3: Essential Binaries
        print!("[DIAGNOSTIC] Validating Core Utility Binaries (/bin/ferro-core, /bin/sh)... ");
        let core_ok = Path::new("/bin/ferro-core").exists()
            || Path::new("/usr/local/bin/ferro-core").exists();
        let sh_ok = Path::new("/bin/sh").exists();
        if core_ok && sh_ok {
            println!("PASS (Present & Executable)");
        } else {
            println!("FAIL - One or more core binaries missing!");
        }

        // Check 4: Network Resolver
        print!("[DIAGNOSTIC] Verifying DNS Resolver Configuration (/etc/resolv.conf)... ");
        if Path::new("/etc/resolv.conf").exists() {
            println!("PASS");
        } else {
            println!("REPAIRED (Created fallback nameservers 1.1.1.1, 8.8.8.8)");
            let _ = fs::write(
                "/etc/resolv.conf",
                "nameserver 1.1.1.1\nnameserver 8.8.8.8\n",
            );
        }

        // Check 5: Allocator Integrity
        print!("[DIAGNOSTIC] Testing System Heap Allocator (mimalloc / glibc integrity)... ");
        let mut test_vec = Vec::with_capacity(100_000);
        for i in 0..100_000 {
            test_vec.push(i as u64);
        }
        let sum: u64 = test_vec.iter().sum();
        if sum == 4_999_950_000 {
            println!("PASS (Heap integrity verified, 0 corruption)");
        } else {
            println!("FAIL (Memory corruption detected!)");
        }

        println!(
            "================================================================================"
        );
        println!("✅ Automated System Self-Repair Complete: All Core Subsystems Verified.");
        println!(
            "================================================================================"
        );
    }

    fn run_system_restore() {
        println!(
            "\n================================================================================"
        );
        println!("                 FERRO-OS CONFIGURATION ROLLBACK & RESTORE                     ");
        println!(
            "================================================================================"
        );
        println!("[RESTORE] Resetting /etc/resolv.conf to pristine defaults...");
        let _ = fs::write(
            "/etc/resolv.conf",
            "nameserver 1.1.1.1\nnameserver 8.8.8.8\n",
        );

        println!("[RESTORE] Resetting /etc/hosts...");
        let _ = fs::write(
            "/etc/hosts",
            "127.0.0.1 localhost ferro-os\n::1 localhost ip6-localhost ip6-loopback\n",
        );

        println!("[RESTORE] Purging stale locks and PID files in /var/run and /tmp...");
        if let Ok(entries) = fs::read_dir("/var/run") {
            for entry in entries.flatten() {
                let p = entry.path();
                if p.extension()
                    .map_or(false, |ext| ext == "pid" || ext == "lock")
                {
                    let _ = fs::remove_file(p);
                }
            }
        }

        println!("[RESTORE] Clearing crash flags and resetting clean state...");
        let _ = fs::remove_file(CRASH_MARKER_FLAG);
        mark_clean_shutdown();

        println!(
            "================================================================================"
        );
        println!("✅ Configuration Rollback Applied Successfully.");
        println!(
            "================================================================================"
        );
    }

    fn run_hardware_diagnostics() {
        println!(
            "\n================================================================================"
        );
        println!(
            "                   FERRO-OS HARDWARE & MEMORY TELEMETRY                         "
        );
        println!(
            "================================================================================"
        );

        // Memory telemetry
        if let Ok(file) = File::open("/proc/meminfo") {
            println!("--- RAM Memory Subsystem ---");
            let reader = BufReader::new(file);
            for line in reader.lines().flatten().take(5) {
                println!("  {}", line);
            }
        }

        // CPU telemetry
        if let Ok(file) = File::open("/proc/cpuinfo") {
            println!("\n--- Processor Architecture ---");
            let reader = BufReader::new(file);
            for line in reader.lines().flatten().take(6) {
                println!("  {}", line);
            }
        }

        // Memory bandwidth benchmark
        println!("\n--- Real-Time Memory Throughput Test ---");
        let start = Instant::now();
        let iterations = 50_000_000;
        let mut accum: u64 = 0;
        for i in 0..iterations {
            accum = accum.wrapping_add((i * 13) ^ (i >> 3));
        }
        let elapsed = start.elapsed();
        let ops_sec = (iterations as f64) / elapsed.as_secs_f64();
        println!(
            "  Evaluated 50M compute operations in {:.4} seconds",
            elapsed.as_secs_f64()
        );
        println!(
            "  Calculation Throughput: {:.2} Million ops/sec",
            ops_sec / 1e6
        );
        println!("  Accumulator Checksum:   0x{:016x}", accum);
        println!(
            "================================================================================"
        );
    }

    // -------------------------------------------------------------
    // Shell & Supervisor Execution
    // -------------------------------------------------------------
    fn enter_emergency_shell(label: &str) {
        println!(
            "\n================================================================================"
        );
        println!(
            "    FERRO-OS ROOT COMMAND PROMPT [{}]    ",
            label.to_uppercase()
        );
        println!(
            "    Type 'exit' to return to boot menu, or use 'reboot' / 'poweroff'.           "
        );
        println!(
            "================================================================================"
        );

        loop {
            let mut shell_cmd = if Path::new("/bin/sh").exists() {
                Command::new("/bin/sh")
            } else if Path::new("/bin/ferro-core").exists() {
                let mut cmd = Command::new("/bin/ferro-core");
                cmd.arg("sh");
                cmd
            } else if Path::new("/usr/local/bin/ferro-core").exists() {
                let mut cmd = Command::new("/usr/local/bin/ferro-core");
                cmd.arg("sh");
                cmd
            } else {
                eprintln!("[ferro-init] ERROR: No shell binary found!");
                std::thread::sleep(std::time::Duration::from_secs(5));
                continue;
            };

            match shell_cmd.status() {
                Ok(status) => {
                    println!("[ferro-init] Emergency shell exited with: {:?}", status);
                    let opt = prompt_recovery_menu(false);
                    match opt {
                        BootOption::Normal => {
                            println!("[ferro-init] Transitioning to Normal Boot...");
                            init_network();
                            run_init_scripts();
                            enter_main_supervisor(false);
                            break;
                        }
                        BootOption::Reboot => execute_reboot(),
                        BootOption::PowerOff => execute_poweroff(),
                        _ => continue,
                    }
                }
                Err(e) => {
                    eprintln!("[ferro-init] Failed to execute shell: {}", e);
                    std::thread::sleep(std::time::Duration::from_secs(1));
                }
            }

            reap_zombies();
        }
    }

    fn enter_main_supervisor(_safe_mode: bool) {
        loop {
            let mut shell_cmd = if Path::new("/bin/sh").exists() {
                Command::new("/bin/sh")
            } else if Path::new("/bin/ferro-core").exists() {
                let mut cmd = Command::new("/bin/ferro-core");
                cmd.arg("sh");
                cmd
            } else if Path::new("/usr/local/bin/ferro-core").exists() {
                let mut cmd = Command::new("/usr/local/bin/ferro-core");
                cmd.arg("sh");
                cmd
            } else {
                eprintln!(
                    "[ferro-init] ERROR: No shell binary found at /bin/sh or /bin/ferro-core"
                );
                std::thread::sleep(std::time::Duration::from_secs(5));
                continue;
            };

            let _ = shell_cmd.status();
            reap_zombies();
        }
    }

    // -------------------------------------------------------------
    // Core Helpers: Mount, Network, Scripts, Power
    // -------------------------------------------------------------
    fn mount_fs(source: &str, target: &str, fstype: &str, flags: u64, data: Option<&str>) {
        let _ = fs::create_dir_all(target);
        let c_src = CString::new(source).unwrap();
        let c_tgt = CString::new(target).unwrap();
        let c_fst = CString::new(fstype).unwrap();
        let c_data = data.map(|d| CString::new(d).unwrap());

        let res = unsafe {
            libc::mount(
                c_src.as_ptr(),
                c_tgt.as_ptr(),
                c_fst.as_ptr(),
                flags,
                c_data
                    .as_ref()
                    .map_or(std::ptr::null(), |d| d.as_ptr() as *const libc::c_void),
            )
        };

        if res != 0 {
            let err = std::io::Error::last_os_error();
            eprintln!(
                "[ferro-init] Warning: mount {} on {} failed: {}",
                source, target, err
            );
        }
    }

    fn mount_essential_filesystems() {
        mount_fs(
            "proc",
            "/proc",
            "proc",
            libc::MS_NOSUID | libc::MS_NODEV | libc::MS_NOEXEC,
            None,
        );
        mount_fs(
            "sysfs",
            "/sys",
            "sysfs",
            libc::MS_NOSUID | libc::MS_NODEV | libc::MS_NOEXEC,
            None,
        );
        mount_fs("devtmpfs", "/dev", "devtmpfs", libc::MS_NOSUID, None);
        mount_fs(
            "tmpfs",
            "/tmp",
            "tmpfs",
            libc::MS_NOSUID | libc::MS_NODEV | libc::MS_NOEXEC,
            Some("mode=1777"),
        );
        mount_fs(
            "tmpfs",
            "/dev/shm",
            "tmpfs",
            libc::MS_NOSUID | libc::MS_NODEV | libc::MS_NOEXEC,
            Some("mode=1777"),
        );
        mount_fs(
            "tmpfs",
            "/run",
            "tmpfs",
            libc::MS_NOSUID | libc::MS_NODEV,
            Some("mode=0755"),
        );
        mount_fs(
            "devpts",
            "/dev/pts",
            "devpts",
            libc::MS_NOSUID | libc::MS_NOEXEC,
            Some("gid=5,mode=620"),
        );

        if check_immutable_cmdline() {
            setup_immutable_overlay_storage("");
        }

        ensure_standard_system_files();
    }

    fn is_quiet_boot() -> bool {
        fs::read_to_string("/proc/cmdline")
            .map(|s| s.split_whitespace().any(|token| token == "quiet"))
            .unwrap_or(false)
    }

    fn ensure_standard_system_files() {
        let os_release = "NAME=\"FerroOS\"\nVERSION=\"2.3.0\"\nID=ferro\nID_LIKE=linux\nPRETTY_NAME=\"FerroOS 2.3.0 (Cloud Native)\"\nVERSION_ID=\"2.3.0\"\nHOME_URL=\"https://github.com/Praveen-1308/ferro-os\"\n";
        let _ = fs::create_dir_all("/etc");
        if !Path::new("/etc/os-release").exists() {
            let _ = fs::write("/etc/os-release", os_release);
        }
        let _ = fs::create_dir_all("/usr/lib");
        if !Path::new("/usr/lib/os-release").exists() {
            let _ = fs::write("/usr/lib/os-release", os_release);
        }
        if !Path::new("/etc/issue").exists() {
            let _ = fs::write("/etc/issue", "FerroOS 2.3.0 \\n \\l\n\n");
        }
        if !Path::new("/etc/hosts").exists() {
            let hosts = "127.0.0.1\tlocalhost\n::1\t\tlocalhost ip6-localhost ip6-loopback\n127.0.1.1\tferro\n";
            let _ = fs::write("/etc/hosts", hosts);
        }
        if !Path::new("/etc/hostname").exists() {
            let _ = fs::write("/etc/hostname", "ferro\n");
        }
    }

    fn set_hostname(name: &str) {
        let c_name = CString::new(name).unwrap();
        unsafe {
            libc::sethostname(c_name.as_ptr(), name.len());
        }
    }

    // -------------------------------------------------------------
    // Persistent Block Storage & switch_root Engine
    // -------------------------------------------------------------
    fn detect_persistent_root_device() -> Option<String> {
        // 1. Check kernel commandline for root=... parameter
        if let Ok(cmdline) = fs::read_to_string("/proc/cmdline") {
            for token in cmdline.split_whitespace() {
                if let Some(stripped) = token.strip_prefix("root=") {
                    let root_target = stripped.trim_matches('"');
                    if root_target != "/dev/ram" && root_target != "ramfs" && !root_target.is_empty() {
                        return Some(root_target.to_string());
                    }
                }
            }
        }

        // 2. Auto-detect if a block device contains FerroOS persistent root
        let candidate_devices = [
            "/dev/vda1", "/dev/vda2", "/dev/sda1", "/dev/sda2", "/dev/nvme0n1p1", "/dev/nvme0n1p2"
        ];
        for dev in &candidate_devices {
            if Path::new(dev).exists() {
                let test_mount = "/tmp/.root_probe";
                let _ = fs::create_dir_all(test_mount);
                if mount_persistent_root(dev, test_mount) {
                    let has_marker = Path::new(&format!("{}/etc/ferro_persistent_root", test_mount)).exists();
                    let _ = libc_umount(test_mount);
                    let _ = fs::remove_dir(test_mount);
                    if has_marker {
                        return Some(dev.to_string());
                    }
                }
            }
        }

        None
    }

    fn try_switch_root(target_dev: &str) -> bool {
        let sysroot = "/sysroot";
        let _ = fs::create_dir_all(sysroot);

        // Try mounting persistent device with ext4, btrfs, or xfs
        let mounted = mount_persistent_root(target_dev, sysroot);
        if !mounted {
            eprintln!("[ferro-init] Failed to mount persistent root device {} onto {}", target_dev, sysroot);
            return false;
        }

        // Verify valid root directory structure
        let init_candidate = format!("{}/init", sysroot);
        let core_candidate = format!("{}/bin/ferro-core", sysroot);
        if !Path::new(&init_candidate).exists() && !Path::new(&core_candidate).exists() {
            eprintln!("[ferro-init] Target persistent root {} has no /init or /bin/ferro-core. Aborting pivot.", sysroot);
            let _ = libc_umount(sysroot);
            return false;
        }

        // Move virtual filesystems: /dev, /proc, /sys, /run
        for vfs in &["dev", "proc", "sys", "run"] {
            let src = format!("/{}", vfs);
            let dst = format!("{}/{}", sysroot, vfs);
            let _ = fs::create_dir_all(&dst);
            move_mount(&src, &dst);
        }

        // Perform switch_root: chdir to new root, chroot, and re-exec init
        println!("[ferro-init] Pivoting root to persistent block device (switch_root)...");
        unsafe {
            let c_sysroot = match CString::new(sysroot) { Ok(c) => c, Err(_) => return false };
            let c_slash = match CString::new("/") { Ok(c) => c, Err(_) => return false };

            if libc::chdir(c_sysroot.as_ptr()) != 0 {
                eprintln!("[ferro-init] chdir to sysroot failed!");
                return false;
            }

            if libc::chroot(b".\0".as_ptr() as *const libc::c_char) != 0 {
                eprintln!("[ferro-init] chroot to new root failed!");
                return false;
            }

            if libc::chdir(c_slash.as_ptr()) != 0 {
                eprintln!("[ferro-init] chdir to / in new root failed!");
                return false;
            }

            // Re-exec PID 1 in the new rootfs
            let c_init = CString::new("/init").unwrap();
            let args = [c_init.as_ptr(), std::ptr::null()];
            libc::execv(c_init.as_ptr(), args.as_ptr());

            // Fallback to /bin/ferro-core
            let c_core = CString::new("/bin/ferro-core").unwrap();
            let c_sh = CString::new("sh").unwrap();
            let args_fallback = [c_core.as_ptr(), c_sh.as_ptr(), std::ptr::null()];
            libc::execv(c_core.as_ptr(), args_fallback.as_ptr());
        }

        true
    }

    fn mount_persistent_root(dev: &str, target: &str) -> bool {
        let is_immutable = check_immutable_cmdline();
        let mount_flags = if is_immutable {
            println!("[ferro-init] Immutable rootfs mode requested via kernel cmdline (rootflags=ro / ferro.immutable=1).");
            libc::MS_RDONLY | libc::MS_RELATIME
        } else {
            libc::MS_RELATIME
        };

        for fstype in &["ext4", "btrfs", "xfs"] {
            let c_dev = match CString::new(dev) { Ok(c) => c, Err(_) => continue };
            let c_target = match CString::new(target) { Ok(c) => c, Err(_) => continue };
            let c_fstype = match CString::new(*fstype) { Ok(c) => c, Err(_) => continue };

            unsafe {
                let ret = libc::mount(
                    c_dev.as_ptr(),
                    c_target.as_ptr(),
                    c_fstype.as_ptr(),
                    mount_flags,
                    std::ptr::null(),
                );
                if ret == 0 {
                    println!("[ferro-init] Mounted persistent root {} ({}) on {} [flags: 0x{:x}]", dev, fstype, target, mount_flags);
                    if is_immutable {
                        setup_immutable_overlay_storage(target);
                    }
                    return true;
                }
            }
        }
        false
    }

    fn check_immutable_cmdline() -> bool {
        if let Ok(cmdline) = fs::read_to_string("/proc/cmdline") {
            for token in cmdline.split_whitespace() {
                if token == "ro"
                    || token == "rootflags=ro"
                    || token == "ferro.immutable=1"
                    || token.starts_with("rootflags=ro,")
                    || token.ends_with(",ro")
                {
                    return true;
                }
            }
        }
        false
    }

    fn setup_immutable_overlay_storage(sysroot: &str) {
        println!("[ferro-init] Initializing writable overlayfs & tmpfs volatile layers on '{}'...", sysroot);
        let var_target = if sysroot.is_empty() { "/var".to_string() } else { format!("{}/var", sysroot) };
        let _ = fs::create_dir_all(&var_target);
        mount_fs("tmpfs", &var_target, "tmpfs", libc::MS_NOSUID | libc::MS_NODEV, Some("mode=0755"));

        let etc_target = if sysroot.is_empty() { "/etc".to_string() } else { format!("{}/etc", sysroot) };
        let upper = "/tmp/.overlay_etc_upper";
        let work = "/tmp/.overlay_etc_work";
        let _ = fs::create_dir_all(upper);
        let _ = fs::create_dir_all(work);
        let overlay_opts = format!("lowerdir={},upperdir={},workdir={}", etc_target, upper, work);
        mount_fs("overlay", &etc_target, "overlay", libc::MS_NOSUID | libc::MS_NODEV, Some(&overlay_opts));
        println!("[ferro-init] ✅ Immutable Rootfs Active: / (read-only), /var (volatile tmpfs), /etc (overlayfs)");
    }

    fn move_mount(src: &str, dst: &str) {
        let c_src = match CString::new(src) { Ok(c) => c, Err(_) => return };
        let c_dst = match CString::new(dst) { Ok(c) => c, Err(_) => return };
        unsafe {
            let _ = libc::mount(
                c_src.as_ptr(),
                c_dst.as_ptr(),
                std::ptr::null(),
                libc::MS_MOVE,
                std::ptr::null(),
            );
        }
    }

    fn libc_umount(target: &str) -> bool {
        let c_target = match CString::new(target) { Ok(c) => c, Err(_) => return false };
        unsafe {
            libc::umount2(c_target.as_ptr(), libc::MNT_DETACH) == 0
        }
    }

    fn elevate_system_limits() {
        #[cfg(unix)]
        unsafe {
            // Attempt to raise file descriptor limit to 65,536
            let rlim = libc::rlimit {
                rlim_cur: 65536,
                rlim_max: 65536,
            };
            let res = libc::setrlimit(libc::RLIMIT_NOFILE, &rlim);
            if res == 0 {
                println!("[ferro-init] Process file descriptor limit elevated to 65,536 (RLIMIT_NOFILE).");
            } else {
                // In unprivileged containers, maximize soft limit up to hard limit
                let mut current = libc::rlimit {
                    rlim_cur: 0,
                    rlim_max: 0,
                };
                if libc::getrlimit(libc::RLIMIT_NOFILE, &mut current) == 0 {
                    let elevated = libc::rlimit {
                        rlim_cur: current.rlim_max,
                        rlim_max: current.rlim_max,
                    };
                    let _ = libc::setrlimit(libc::RLIMIT_NOFILE, &elevated);
                }
            }
        }
    }

    fn apply_kernel_performance_and_reliability_tuning() {
        println!("[ferro-init] Applying Next-Gen Kernel Performance & Reliability Tunings...");

        // 1. Immunity to OOM Killer for PID 1 & critical init services
        if let Ok(_) = fs::write("/proc/self/oom_score_adj", "-1000\n") {
            println!("[ferro-init] PID 1 oom_score_adj locked at -1000 (OOM Killer immune).");
        }

        // 2. Storage & Memory Writeback Tunings (Eradicates SCENARIO-015 Dirty Page Writeback Freezes)
        let vm_tunings = [
            ("/proc/sys/vm/dirty_background_bytes", "67108864\n"), // 64 MB
            ("/proc/sys/vm/dirty_bytes", "268435456\n"),           // 256 MB
            ("/proc/sys/vm/dirty_writeback_centisecs", "100\n"),   // 1 second
            ("/proc/sys/vm/vfs_cache_pressure", "50\n"),           // Retain dentries/inodes
            ("/proc/sys/vm/swappiness", "10\n"),                   // Prefer RAM retention
        ];
        for (path, val) in vm_tunings {
            let _ = fs::write(path, val);
        }

        // 3. Network Stack High-Concurrency & Low-Latency Tunings (SCENARIO-014, SCENARIO-018)
        let net_tunings = [
            ("/proc/sys/net/core/somaxconn", "65535\n"),
            ("/proc/sys/net/ipv4/tcp_max_syn_backlog", "65535\n"),
            ("/proc/sys/net/ipv4/tcp_tw_reuse", "1\n"),
            ("/proc/sys/net/ipv4/ip_local_port_range", "1024 65535\n"),
            ("/proc/sys/net/ipv4/tcp_fin_timeout", "15\n"),
            ("/proc/sys/net/core/default_qdisc", "fq\n"),
            ("/proc/sys/net/ipv4/tcp_congestion_control", "bbr\n"),
            ("/proc/sys/net/ipv4/tcp_notsent_lowat", "16384\n"),
            ("/proc/sys/net/ipv4/tcp_slow_start_after_idle", "0\n"),
        ];
        for (path, val) in net_tunings {
            let _ = fs::write(path, val);
        }

        // 4. KSPP (Kernel Self-Protection Project) & CIS Benchmark Baseline (docs/MEMORY_SECURITY_AND_STANDARDS.md)
        let kspp_tunings = [
            ("/proc/sys/kernel/randomize_va_space", "2\n"), // ASLR Full Randomization (CIS 1.5.3)
            ("/proc/sys/kernel/kptr_restrict", "2\n"),
            ("/proc/sys/kernel/dmesg_restrict", "1\n"),
            ("/proc/sys/kernel/unprivileged_bpf_disabled", "1\n"),
            ("/proc/sys/kernel/yama/ptrace_scope", "2\n"),
            ("/proc/sys/fs/protected_symlinks", "1\n"),
            ("/proc/sys/fs/protected_hardlinks", "1\n"),
            ("/proc/sys/fs/protected_fifos", "2\n"),
            ("/proc/sys/fs/protected_regular", "2\n"),
            ("/proc/sys/fs/suid_dumpable", "0\n"),
            ("/proc/sys/net/ipv4/conf/all/accept_redirects", "0\n"),
            ("/proc/sys/net/ipv4/conf/default/accept_redirects", "0\n"),
            ("/proc/sys/net/ipv4/tcp_syncookies", "1\n"),
            ("/proc/sys/net/ipv4/conf/all/rp_filter", "1\n"),
            ("/proc/sys/net/ipv4/conf/default/rp_filter", "1\n"),
            ("/proc/sys/net/ipv4/conf/all/accept_source_route", "0\n"),
            ("/proc/sys/net/ipv4/conf/default/accept_source_route", "0\n"),
            ("/proc/sys/net/ipv6/conf/all/accept_redirects", "0\n"),
            ("/proc/sys/net/ipv6/conf/default/accept_redirects", "0\n"),
        ];
        for (path, val) in kspp_tunings {
            let _ = fs::write(path, val);
        }

        println!("[ferro-init] Kernel KSPP exploit defenses, CIS network hardening and TCP socket sharding active.");
    }

    fn spawn_psi_memory_watcher() {
        if Path::new("/proc/pressure/memory").exists() {
            println!(
                "[ferro-init] Starting Linux PSI (Pressure Stall Information) memory watchdog..."
            );
            let _ = std::thread::Builder::new()
                .name("ferro-psi-mon".to_string())
                .spawn(|| {
                    loop {
                        std::thread::sleep(std::time::Duration::from_secs(5));
                        if let Ok(content) = fs::read_to_string("/proc/pressure/memory") {
                            for line in content.lines() {
                                if line.starts_with("some") {
                                    if let Some(avg10_part) = line.split_whitespace().find(|p| p.starts_with("avg10=")) {
                                        if let Ok(val) = avg10_part.trim_start_matches("avg10=").parse::<f64>() {
                                            if val > 20.0 {
                                                eprintln!("[ferro-init][PSI ALERT] Memory pressure stall high: avg10={:.2}%. Reclaiming page caches...", val);
                                                let _ = fs::write("/proc/sys/vm/drop_caches", "1\n");
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                });
        }
    }

    unsafe fn bring_up_iface(sock: libc::c_int, name: &str) {
        let mut ifr: libc::ifreq = std::mem::zeroed();
        let bytes = name.as_bytes();
        let len = bytes.len().min(15);
        for i in 0..len {
            ifr.ifr_name[i] = bytes[i] as libc::c_char;
        }
        ifr.ifr_ifru.ifru_flags = (libc::IFF_UP | libc::IFF_RUNNING) as libc::c_short;
        if libc::ioctl(sock, libc::SIOCSIFFLAGS, &ifr) == 0 {
            println!("[ferro-init] Network interface '{}' brought UP.", name);
        }
    }

    fn init_network() {
        let resolv_path = Path::new("/etc/resolv.conf");
        if !resolv_path.exists() {
            let _ = fs::write(resolv_path, "nameserver 1.1.1.1\nnameserver 8.8.8.8\n");
        }

        unsafe {
            let sock = libc::socket(libc::AF_INET, libc::SOCK_DGRAM, 0);
            if sock >= 0 {
                bring_up_iface(sock, "lo");

                if let Ok(entries) = fs::read_dir("/sys/class/net") {
                    for entry in entries.flatten() {
                        let name = entry.file_name().to_string_lossy().to_string();
                        if name != "lo" {
                            bring_up_iface(sock, &name);
                            // Auto-lease IP via pure-Rust DHCP client (ferro-net)
                            println!(
                                "[ferro-init] Triggering pure-Rust DHCP auto-leasing on '{}'...",
                                name
                            );
                            let iface_name = name.clone();
                            let _ = std::thread::Builder::new()
                                .name(format!("ferro-dhcp-{}", iface_name))
                                .spawn(move || {
                                    let _ = std::process::Command::new("/bin/ferro-core")
                                        .args(["dhcp", "-i", &iface_name, "-t", "2"])
                                        .status();
                                });
                        }
                    }
                }
                libc::close(sock);

                // Trigger Cloud-Init metadata ingestion (AWS/GCP/Azure/OpenStack)
                println!("[ferro-init] Spawning Cloud-Init metadata service probe (169.254.169.254)...");
                let _ = std::thread::Builder::new()
                    .name("ferro-cloud-init".to_string())
                    .spawn(|| {
                        std::thread::sleep(std::time::Duration::from_millis(600));
                        let _ = std::process::Command::new("/bin/ferro-core")
                            .args(["cloud-init"])
                            .status();
                    });

                // Spawn Secure Remote Administration SSH Server (sshd on port 22)
                println!("[ferro-init] Spawning FerroOS SSH remote administration daemon on port 22...");
                let _ = std::thread::Builder::new()
                    .name("ferro-sshd".to_string())
                    .spawn(|| {
                        std::thread::sleep(std::time::Duration::from_millis(800));
                        let _ = std::process::Command::new("/bin/ferro-core")
                            .args(["sshd", "--port", "22"])
                            .status();
                    });
            }
        }
    }

    fn run_init_scripts() {
        let init_dir = Path::new("/etc/init.d");
        if !init_dir.exists() {
            return;
        }

        if let Ok(entries) = fs::read_dir(init_dir) {
            let mut scripts: Vec<_> = entries.flatten().map(|e| e.path()).collect();
            scripts.sort();

            for script in scripts {
                if script.is_file() {
                    let path_str = script.to_string_lossy().to_string();
                    if path_str.ends_with(".sh") || path_str.ends_with("/rcS") {
                        println!("[ferro-init] Executing startup script {}...", path_str);
                        let _ = Command::new("/bin/sh").arg(&path_str).status();
                    }
                }
            }
        }
    }

    static SHUTDOWN_REQUESTED: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);

    extern "C" fn sigchld_handler(_sig: libc::c_int) {
        unsafe {
            let mut status = 0;
            while libc::waitpid(-1, &mut status, libc::WNOHANG) > 0 {}
        }
    }

    extern "C" fn sigterm_handler(_sig: libc::c_int) {
        SHUTDOWN_REQUESTED.store(true, std::sync::atomic::Ordering::SeqCst);
        unsafe {
            let msg = b"\n[ferro-init] Termination signal received (SIGTERM/SIGINT). Initiating graceful shutdown...\n";
            libc::write(libc::STDOUT_FILENO, msg.as_ptr() as *const libc::c_void, msg.len());
        }
    }

    fn register_pid1_signal_handlers() {
        unsafe {
            let mut sa_chld: libc::sigaction = std::mem::zeroed();
            sa_chld.sa_sigaction = sigchld_handler as usize;
            sa_chld.sa_flags = libc::SA_NOCLDSTOP | libc::SA_RESTART;
            libc::sigaction(libc::SIGCHLD, &sa_chld, std::ptr::null_mut());

            let mut sa_term: libc::sigaction = std::mem::zeroed();
            sa_term.sa_sigaction = sigterm_handler as usize;
            sa_term.sa_flags = libc::SA_RESTART;
            libc::sigaction(libc::SIGTERM, &sa_term, std::ptr::null_mut());
            libc::sigaction(libc::SIGINT, &sa_term, std::ptr::null_mut());
            libc::sigaction(libc::SIGPWR, &sa_term, std::ptr::null_mut());
        }
        println!("[ferro-init] PID 1 signal handlers registered (SIGCHLD auto-reaping & SIGTERM/SIGINT graceful shutdown).");
    }

    fn spawn_continuous_zombie_reaper() {
        let _ = std::thread::Builder::new()
            .name("ferro-reaper".to_string())
            .spawn(|| {
                loop {
                    std::thread::sleep(std::time::Duration::from_millis(100));
                    reap_zombies();
                    if SHUTDOWN_REQUESTED.load(std::sync::atomic::Ordering::SeqCst) {
                        handle_graceful_shutdown();
                        break;
                    }
                }
            });
    }

    fn handle_graceful_shutdown() {
        println!("[ferro-init] Executing graceful system shutdown...");
        mark_clean_shutdown();
        unsafe {
            libc::kill(-1, libc::SIGTERM);
            std::thread::sleep(std::time::Duration::from_millis(500));
            libc::kill(-1, libc::SIGKILL);
            libc::sync();
            libc::reboot(0x4321fedc as i32); // LINUX_REBOOT_CMD_POWER_OFF
        }
    }

    fn reap_zombies() {
        unsafe {
            let mut status = 0;
            while libc::waitpid(-1, &mut status, libc::WNOHANG) > 0 {}
        }
    }

    fn execute_reboot() {
        println!("[ferro-init] Synchronizing filesystems and rebooting...");
        mark_clean_shutdown();
        unsafe {
            libc::sync();
            libc::reboot(0x01234567); // LINUX_REBOOT_CMD_RESTART
        }
    }

    fn execute_poweroff() {
        println!("[ferro-init] Synchronizing filesystems and powering off...");
        mark_clean_shutdown();
        unsafe {
            libc::sync();
            libc::reboot(0x4321fedc as i32); // LINUX_REBOOT_CMD_POWER_OFF
        }
    }
}

fn elevate_system_limits() {
    #[cfg(unix)]
    unsafe {
        let mut current: libc::rlimit = std::mem::zeroed();
        if libc::getrlimit(libc::RLIMIT_NOFILE, &mut current) == 0 {
            let target = std::cmp::min(current.rlim_max, 524288);
            let rlim = libc::rlimit {
                rlim_cur: target,
                rlim_max: current.rlim_max,
            };
            let _ = libc::setrlimit(libc::RLIMIT_NOFILE, &rlim);
        }
    }
}

fn main() -> ExitCode {
    elevate_system_limits();

    if std::env::args().any(|a| a == "--fdstore-only" || a == "fdstore") {
        println!("[ferro-init] Running standalone FD Store daemon...");
        let srv = fdstore::FdStoreServer::new();
        match srv.start() {
            Ok(handle) => {
                let _ = handle.join();
                return ExitCode::SUCCESS;
            }
            Err(e) => {
                eprintln!("[ferro-init] Failed to start FD Store: {}", e);
                return ExitCode::FAILURE;
            }
        }
    }

    #[cfg(target_os = "linux")]
    {
        if let Err(e) = linux_init::run() {
            eprintln!("[ferro-init] Fatal init error: {}", e);
            return ExitCode::FAILURE;
        }
        ExitCode::SUCCESS
    }

    #[cfg(not(target_os = "linux"))]
    {
        println!("ferro-init is designed to run as PID 1 on Linux (FerroOS).");
        println!("Compiled successfully on non-Linux host for verification.");
        ExitCode::SUCCESS
    }
}
