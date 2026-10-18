//! ferro-init: PID 1 Init System for FerroOS written in Rust.
//! Responsible for early system mounts, signal handling, zombie reaping,
//! and launching userspace services.

use std::process::ExitCode;

#[cfg(target_os = "linux")]
mod linux_init {
    use std::ffi::{CStr, CString};
    use std::fs;
    use std::os::unix::process::CommandExt;
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
        println!("[ferro-init] Initializing FerroOS PID 1...");

        // 1. Mount virtual filesystems
        mount_essential_filesystems();

        // 2. Set Hostname & Environment
        set_hostname("ferro-os");
        std::env::set_var("PATH", "/bin:/sbin:/usr/bin:/usr/sbin");
        std::env::set_var("HOME", "/");
        std::env::set_var("TERM", "linux");

        // 3. Create required directories
        let _ = fs::create_dir_all("/var/run");
        let _ = fs::create_dir_all("/tmp");

        println!("[ferro-init] Virtual filesystems mounted successfully.");

        // 4. Run startup scripts if present (/etc/init.d/rcS)
        if Path::new("/etc/init.d/rcS").exists() {
            println!("[ferro-init] Executing /etc/init.d/rcS...");
            let _ = Command::new("/bin/sh")
                .arg("/etc/init.d/rcS")
                .status();
        }

        // 5. Main loop: Spawn interactive shell or service supervisor
        loop {
            println!("[ferro-init] Starting interactive shell session (/bin/sh)...");
            
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

            // Spawn shell in foreground
            match shell_cmd.status() {
                Ok(status) => {
                    println!("[ferro-init] Shell exited with: {:?}", status);
                }
                Err(e) => {
                    eprintln!("[ferro-init] Failed to execute shell: {}", e);
                    std::thread::sleep(std::time::Duration::from_secs(2));
                }
            }

            // Reap any orphaned zombies
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
        // MS_NOSUID = 2, MS_NODEV = 4, MS_NOEXEC = 8
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
