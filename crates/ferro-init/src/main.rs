//! ferro-init: PID 1 Init System for FerroOS written in Rust.
//! Responsible for early system mounts, network loopback bringup,
//! service execution, zombie reaping, and shell lifecycle.

use std::process::ExitCode;

#[cfg(target_os = "linux")]
mod linux_init {
    use std::ffi::CString;
    use std::fs;
    use std::path::Path;
    use std::process::Command;

    const BANNER: &str = r#"
  _______                    ____   _____ 
 |  ____|                   / __ \ / ____|
 | |__ ___ _ __ _ __ ___   | |  | | (___  
 |  __/ _ \ '__| '__/ _ \  | |  | |\___ \ 
 | | |  __/ |  | | | (_) | | |__| |____) |
 |_|  \___|_|  |_|  \___/   \____/|_____/ 
 
 FerroOS v0.1.0 - Fast Rust-Powered Operating System
 Alpine-Speed + Debian Compatibility (Python, glibc)
"#;

    pub fn run() -> Result<(), Box<dyn std::error::Error>> {
        println!("{}", BANNER);
        println!("[ferro-init] Initializing FerroOS PID 1 (Rust)...");

        // 1. Mount virtual filesystems
        mount_essential_filesystems();

        // 2. Set Hostname & Environment
        set_hostname("ferro-os");
        std::env::set_var("PATH", "/bin:/sbin:/usr/bin:/usr/sbin");
        std::env::set_var("HOME", "/root");
        std::env::set_var("TERM", "linux");
        std::env::set_var("USER", "root");

        // 3. Create required directories
        let _ = fs::create_dir_all("/root");
        let _ = fs::create_dir_all("/var/run");
        let _ = fs::create_dir_all("/var/log");
        let _ = fs::create_dir_all("/var/lib/rpk");
        let _ = fs::create_dir_all("/tmp");

        // 4. Initialize Network (Loopback & DNS)
        init_network();

        println!("[ferro-init] Virtual filesystems and network initialized.");

        // 5. Execute init scripts in /etc/init.d/ in order
        run_init_scripts();

        // 6. Main loop: Spawn interactive shell or service supervisor
        loop {
            println!("[ferro-init] Spawning login shell (/bin/sh)...");

            let mut shell_cmd = if Path::new("/bin/sh").exists() {
                Command::new("/bin/sh")
            } else if Path::new("/bin/ferro-core").exists() {
                let mut cmd = Command::new("/bin/ferro-core");
                cmd.arg("sh");
                cmd
            } else {
                eprintln!("[ferro-init] ERROR: No shell binary found at /bin/sh or /bin/ferro-core");
                std::thread::sleep(std::time::Duration::from_secs(5));
                continue;
            };

            match shell_cmd.status() {
                Ok(status) => {
                    println!("[ferro-init] Shell exited with: {:?}", status);
                }
                Err(e) => {
                    eprintln!("[ferro-init] Failed to execute shell: {}", e);
                    std::thread::sleep(std::time::Duration::from_secs(1));
                }
            }

            // Clean up any zombies
            reap_zombies();
        }
    }

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
                c_data.as_ref().map_or(std::ptr::null(), |d| d.as_ptr() as *const libc::c_void),
            )
        };

        if res != 0 {
            let err = std::io::Error::last_os_error();
            eprintln!("[ferro-init] Warning: mount {} on {} failed: {}", source, target, err);
        }
    }

    fn mount_essential_filesystems() {
        mount_fs("proc", "/proc", "proc", libc::MS_NOSUID | libc::MS_NODEV | libc::MS_NOEXEC, None);
        mount_fs("sysfs", "/sys", "sysfs", libc::MS_NOSUID | libc::MS_NODEV | libc::MS_NOEXEC, None);
        mount_fs("devtmpfs", "/dev", "devtmpfs", libc::MS_NOSUID, None);
        mount_fs("tmpfs", "/tmp", "tmpfs", libc::MS_NOSUID | libc::MS_NODEV, Some("mode=1777"));
        mount_fs("devpts", "/dev/pts", "devpts", libc::MS_NOSUID | libc::MS_NOEXEC, Some("gid=5,mode=620"));
    }

    fn set_hostname(name: &str) {
        let c_name = CString::new(name).unwrap();
        unsafe {
            libc::sethostname(c_name.as_ptr(), name.len());
        }
    }

    fn init_network() {
        // Setup DNS default fallback
        let resolv_path = Path::new("/etc/resolv.conf");
        if !resolv_path.exists() {
            let _ = fs::write(resolv_path, "nameserver 1.1.1.1\nnameserver 8.8.8.8\n");
        }

        // Setup loopback via ioctl
        unsafe {
            let sock = libc::socket(libc::AF_INET, libc::SOCK_DGRAM, 0);
            if sock >= 0 {
                let mut ifr: libc::ifreq = std::mem::zeroed();
                let ifname = b"lo\0";
                std::ptr::copy_nonoverlapping(
                    ifname.as_ptr() as *const libc::c_char,
                    ifr.ifr_name.as_mut_ptr(),
                    ifname.len(),
                );
                // IFF_UP = 0x1, IFF_RUNNING = 0x40
                ifr.ifr_ifru.ifru_flags = (libc::IFF_UP | libc::IFF_RUNNING) as libc::c_short;
                libc::ioctl(sock, libc::SIOCSIFFLAGS, &ifr);
                libc::close(sock);
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

    fn reap_zombies() {
        unsafe {
            let mut status = 0;
            while libc::waitpid(-1, &mut status, libc::WNOHANG) > 0 {}
        }
    }
}

fn main() -> ExitCode {
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
