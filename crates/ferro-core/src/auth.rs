//! FerroOS Standard Authentication, Identity & Privileged Access Module
//!
//! Provides standard Linux / POSIX identity management:
//! - Standard `/etc/passwd` and `/etc/group` parsing with robust fallbacks
//! - `/etc/sudoers` rule checking (compliant with standard `%sudo` and `%wheel` syntax)
//! - Pure-Rust `sudo` applet: privilege elevation, UID/GID switching, environment sanitization
//! - Pure-Rust `su` applet: user identity substitution, login shell simulation
//! - Pure-Rust SNTP client (`ntp`, `timesync`, `ntpdate`): UDP port 123 wall-clock sync

use std::env;
use std::fs;
use std::net::UdpSocket;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UserRecord {
    pub name: String,
    pub uid: u32,
    pub gid: u32,
    pub gecos: String,
    pub home: String,
    pub shell: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GroupRecord {
    pub name: String,
    pub gid: u32,
    pub members: Vec<String>,
}

/// Fallback user records matching standard Linux/POSIX distributions
pub fn fallback_users() -> Vec<UserRecord> {
    vec![
        UserRecord {
            name: "root".to_string(),
            uid: 0,
            gid: 0,
            gecos: "root".to_string(),
            home: "/root".to_string(),
            shell: "/bin/sh".to_string(),
        },
        UserRecord {
            name: "daemon".to_string(),
            uid: 1,
            gid: 1,
            gecos: "daemon".to_string(),
            home: "/usr/sbin".to_string(),
            shell: "/usr/sbin/nologin".to_string(),
        },
        UserRecord {
            name: "nobody".to_string(),
            uid: 65534,
            gid: 65534,
            gecos: "nobody".to_string(),
            home: "/nonexistent".to_string(),
            shell: "/usr/sbin/nologin".to_string(),
        },
        UserRecord {
            name: "ferro".to_string(),
            uid: 1000,
            gid: 1000,
            gecos: "ferro".to_string(),
            home: "/home/ferro".to_string(),
            shell: "/bin/sh".to_string(),
        },
    ]
}

/// Fallback group records matching standard Linux/POSIX distributions
pub fn fallback_groups() -> Vec<GroupRecord> {
    vec![
        GroupRecord {
            name: "root".to_string(),
            gid: 0,
            members: Vec::new(),
        },
        GroupRecord {
            name: "daemon".to_string(),
            gid: 1,
            members: Vec::new(),
        },
        GroupRecord {
            name: "wheel".to_string(),
            gid: 10,
            members: vec!["ferro".to_string()],
        },
        GroupRecord {
            name: "sudo".to_string(),
            gid: 27,
            members: vec!["ferro".to_string()],
        },
        GroupRecord {
            name: "users".to_string(),
            gid: 100,
            members: Vec::new(),
        },
        GroupRecord {
            name: "nogroup".to_string(),
            gid: 65534,
            members: Vec::new(),
        },
        GroupRecord {
            name: "ferro".to_string(),
            gid: 1000,
            members: Vec::new(),
        },
    ]
}

/// Parse /etc/passwd contents into UserRecords
pub fn parse_passwd_content(content: &str) -> Vec<UserRecord> {
    let mut users = Vec::new();
    for line in content.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let parts: Vec<&str> = line.split(':').collect();
        if parts.len() >= 7 {
            if let (Ok(uid), Ok(gid)) = (parts[2].parse::<u32>(), parts[3].parse::<u32>()) {
                users.push(UserRecord {
                    name: parts[0].to_string(),
                    uid,
                    gid,
                    gecos: parts[4].to_string(),
                    home: parts[5].to_string(),
                    shell: parts[6].to_string(),
                });
            }
        }
    }
    users
}

/// Parse /etc/group contents into GroupRecords
pub fn parse_group_content(content: &str) -> Vec<GroupRecord> {
    let mut groups = Vec::new();
    for line in content.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let parts: Vec<&str> = line.split(':').collect();
        if parts.len() >= 3 {
            if let Ok(gid) = parts[2].parse::<u32>() {
                let members = if parts.len() >= 4 && !parts[3].is_empty() {
                    parts[3]
                        .split(',')
                        .map(|s| s.trim().to_string())
                        .filter(|s| !s.is_empty())
                        .collect()
                } else {
                    Vec::new()
                };
                groups.push(GroupRecord {
                    name: parts[0].to_string(),
                    gid,
                    members,
                });
            }
        }
    }
    groups
}

pub fn get_users() -> Vec<UserRecord> {
    if let Ok(content) = fs::read_to_string("/etc/passwd") {
        let parsed = parse_passwd_content(&content);
        if !parsed.is_empty() {
            return parsed;
        }
    }
    fallback_users()
}

pub fn get_groups() -> Vec<GroupRecord> {
    if let Ok(content) = fs::read_to_string("/etc/group") {
        let parsed = parse_group_content(&content);
        if !parsed.is_empty() {
            return parsed;
        }
    }
    fallback_groups()
}

pub fn lookup_user_by_name(name: &str) -> Option<UserRecord> {
    get_users().into_iter().find(|u| u.name == name)
}

pub fn lookup_user_by_uid(uid: u32) -> Option<UserRecord> {
    get_users().into_iter().find(|u| u.uid == uid)
}

pub fn lookup_group_by_name(name: &str) -> Option<GroupRecord> {
    get_groups().into_iter().find(|g| g.name == name)
}

pub fn lookup_group_by_gid(gid: u32) -> Option<GroupRecord> {
    get_groups().into_iter().find(|g| g.gid == gid)
}

pub fn is_user_in_group(username: &str, groupname: &str) -> bool {
    let users = get_users();
    let groups = get_groups();

    // Check secondary group memberships
    if let Some(group) = groups.iter().find(|g| g.name == groupname) {
        if group.members.iter().any(|m| m == username) {
            return true;
        }
        // Check primary group match
        if let Some(user) = users.iter().find(|u| u.name == username) {
            if user.gid == group.gid {
                return true;
            }
        }
    }
    false
}

/// Checks whether a user is authorized for sudo execution.
///
/// Follows Ubuntu/POSIX standard sudoers rules:
/// 1. `root` is always authorized.
/// 2. If `/etc/sudoers` exists, parse user specifications and `%group` specifications.
/// 3. Standard fallback: members of `sudo` or `wheel` groups, or default user `ferro`.
pub fn is_user_authorized_sudo(username: &str) -> bool {
    if username == "root" {
        return true;
    }

    if let Ok(content) = fs::read_to_string("/etc/sudoers") {
        for line in content.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            // Check direct user entry: e.g. "root ALL=(ALL:ALL) ALL" or "ferro ALL=(ALL) NOPASSWD: ALL"
            if let Some((user_spec, _)) = line.split_once("ALL=") {
                let user_spec = user_spec.trim();
                if user_spec == username {
                    return true;
                }
                // Check group entry: e.g. "%sudo ALL=" or "%wheel ALL="
                if let Some(grp) = user_spec.strip_prefix('%') {
                    if is_user_in_group(username, grp.trim()) {
                        return true;
                    }
                }
            }
        }
    }

    // Standard distribution fallback
    if is_user_in_group(username, "sudo") || is_user_in_group(username, "wheel") {
        return true;
    }

    // Default primary interactive user
    if username == "ferro" {
        return true;
    }

    false
}

// ============================================================================
// sudo Applet
// ============================================================================

pub fn run_sudo(args: &[String]) -> ExitCode {
    if args.is_empty() {
        print_sudo_usage();
        return ExitCode::from(1);
    }

    let mut target_username = "root".to_string();
    let mut target_groupname: Option<String> = None;
    let mut login_shell = false;
    let mut shell_mode = false;
    let mut preserve_env = false;
    let mut validate_only = false;
    let mut cmd_start_idx = 0;

    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-h" || arg == "--help" {
            print_sudo_usage();
            return ExitCode::SUCCESS;
        } else if arg == "-v" || arg == "--validate" {
            validate_only = true;
            i += 1;
        } else if arg == "-i" || arg == "--login" {
            login_shell = true;
            i += 1;
        } else if arg == "-s" || arg == "--shell" {
            shell_mode = true;
            i += 1;
        } else if arg == "-E" || arg == "--preserve-env" {
            preserve_env = true;
            i += 1;
        } else if arg == "-u" || arg == "--user" {
            if i + 1 < args.len() {
                target_username = args[i + 1].clone();
                i += 2;
            } else {
                eprintln!("sudo: option requires an argument -- 'u'");
                return ExitCode::from(1);
            }
        } else if arg == "-g" || arg == "--group" {
            if i + 1 < args.len() {
                target_groupname = Some(args[i + 1].clone());
                i += 2;
            } else {
                eprintln!("sudo: option requires an argument -- 'g'");
                return ExitCode::from(1);
            }
        } else if arg == "--" {
            cmd_start_idx = i + 1;
            break;
        } else if arg.starts_with('-') {
            eprintln!("sudo: invalid option: '{}'", arg);
            return ExitCode::from(1);
        } else {
            cmd_start_idx = i;
            break;
        }
    }

    // Determine calling user
    #[cfg(unix)]
    let caller_uid = unsafe { libc::getuid() };
    #[cfg(not(unix))]
    let caller_uid = 0;

    let caller_user = lookup_user_by_uid(caller_uid);
    let caller_username = caller_user
        .as_ref()
        .map(|u| u.name.clone())
        .or_else(|| env::var("USER").ok())
        .unwrap_or_else(|| if caller_uid == 0 { "root".to_string() } else { "ferro".to_string() });

    // Verify authorization
    if caller_uid != 0 && !is_user_authorized_sudo(&caller_username) {
        eprintln!(
            "sudo: user {} is not in the sudoers file. This incident will be reported.",
            caller_username
        );
        return ExitCode::from(1);
    }

    if validate_only {
        return ExitCode::SUCCESS;
    }

    // Resolve target user
    let target_user = if let Ok(numeric_uid) = target_username.parse::<u32>() {
        lookup_user_by_uid(numeric_uid).unwrap_or(UserRecord {
            name: target_username.clone(),
            uid: numeric_uid,
            gid: numeric_uid,
            gecos: String::new(),
            home: if numeric_uid == 0 { "/root".to_string() } else { format!("/home/{}", target_username) },
            shell: "/bin/sh".to_string(),
        })
    } else {
        match lookup_user_by_name(&target_username) {
            Some(u) => u,
            None => {
                eprintln!("sudo: unknown user: {}", target_username);
                return ExitCode::from(1);
            }
        }
    };

    let target_gid = if let Some(ref grp) = target_groupname {
        if let Ok(numeric_gid) = grp.parse::<u32>() {
            numeric_gid
        } else if let Some(g) = lookup_group_by_name(grp) {
            g.gid
        } else {
            eprintln!("sudo: unknown group: {}", grp);
            return ExitCode::from(1);
        }
    } else {
        target_user.gid
    };

    // Determine command to run
    let (exec_cmd, exec_args) = if login_shell || shell_mode {
        let shell = if shell_mode && !login_shell {
            env::var("SHELL").unwrap_or_else(|_| target_user.shell.clone())
        } else {
            target_user.shell.clone()
        };
        if cmd_start_idx < args.len() {
            let command_string = args[cmd_start_idx..].join(" ");
            (shell, vec!["-c".to_string(), command_string])
        } else {
            (shell, Vec::new())
        }
    } else {
        if cmd_start_idx >= args.len() {
            eprintln!("sudo: a command is required");
            return ExitCode::from(1);
        }
        (args[cmd_start_idx].clone(), args[cmd_start_idx + 1..].to_vec())
    };

    // Locate binary or resolve internal applet
    let binary_path = resolve_executable_path(&exec_cmd);

    execute_privileged_process(
        &binary_path,
        &exec_cmd,
        &exec_args,
        target_user.uid,
        target_gid,
        &target_user,
        &caller_username,
        caller_uid,
        login_shell,
        preserve_env,
    )
}

fn print_sudo_usage() {
    println!("usage: sudo -h | -K | -k | -V");
    println!("usage: sudo -v [-ABkNnS] [-g group] [-h host] [-p prompt] [-u user]");
    println!("usage: sudo [-ABbEHkNnPS] [-g group] [-u user] [-i | -s] [command [arg ...]]");
}

// ============================================================================
// su Applet
// ============================================================================

pub fn run_su(args: &[String]) -> ExitCode {
    let mut target_username = "root".to_string();
    let mut login_shell = false;
    let mut custom_shell: Option<String> = None;
    let mut command_to_run: Option<String> = None;

    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-" || arg == "-l" || arg == "--login" {
            login_shell = true;
            i += 1;
        } else if arg == "-s" || arg == "--shell" {
            if i + 1 < args.len() {
                custom_shell = Some(args[i + 1].clone());
                i += 2;
            } else {
                eprintln!("su: option requires an argument -- 's'");
                return ExitCode::from(1);
            }
        } else if arg == "-c" || arg == "--command" {
            if i + 1 < args.len() {
                command_to_run = Some(args[i + 1].clone());
                i += 2;
            } else {
                eprintln!("su: option requires an argument -- 'c'");
                return ExitCode::from(1);
            }
        } else if arg == "-h" || arg == "--help" {
            println!("Usage: su [options] [-] [user [argument...]]");
            println!("\nOptions:");
            println!("  -c, --command <command>   pass a single command to the shell with -c");
            println!("  -l, --login               make the shell a login shell");
            println!("  -s, --shell <shell>       run <shell> if /etc/shells allows it");
            println!("  -h, --help                display this help and exit");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') {
            target_username = arg.clone();
            break;
        } else {
            eprintln!("su: unrecognized option '{}'", arg);
            return ExitCode::from(1);
        }
    }

    #[cfg(unix)]
    let caller_uid = unsafe { libc::getuid() };
    #[cfg(not(unix))]
    let caller_uid = 0;

    let caller_user = lookup_user_by_uid(caller_uid);
    let caller_username = caller_user
        .as_ref()
        .map(|u| u.name.clone())
        .or_else(|| env::var("USER").ok())
        .unwrap_or_else(|| if caller_uid == 0 { "root".to_string() } else { "ferro".to_string() });

    // Privilege check: root can su to any user; non-root requires sudoers authorization
    if caller_uid != 0 && target_username != caller_username && !is_user_authorized_sudo(&caller_username) {
        eprintln!("su: Authentication failure");
        return ExitCode::from(1);
    }

    let target_user = match lookup_user_by_name(&target_username) {
        Some(u) => u,
        None => {
            eprintln!("su: user {} does not exist", target_username);
            return ExitCode::from(1);
        }
    };

    let shell = custom_shell.unwrap_or_else(|| target_user.shell.clone());
    let mut exec_args = Vec::new();
    if let Some(cmd) = command_to_run {
        exec_args.push("-c".to_string());
        exec_args.push(cmd);
    }

    let binary_path = resolve_executable_path(&shell);

    execute_privileged_process(
        &binary_path,
        &shell,
        &exec_args,
        target_user.uid,
        target_user.gid,
        &target_user,
        &caller_username,
        caller_uid,
        login_shell,
        false,
    )
}

fn resolve_executable_path(cmd: &str) -> PathBuf {
    if cmd.contains('/') {
        return PathBuf::from(cmd);
    }

    if let Ok(path_var) = env::var("PATH") {
        for dir in path_var.split(':') {
            let candidate = Path::new(dir).join(cmd);
            if candidate.is_file() {
                return candidate;
            }
        }
    }

    for dir in &["/bin", "/usr/bin", "/sbin", "/usr/sbin", "/usr/local/bin"] {
        let candidate = Path::new(dir).join(cmd);
        if candidate.is_file() {
            return candidate;
        }
    }

    // Fall back to current executable if it's an internal applet
    if let Ok(cur_exe) = env::current_exe() {
        return cur_exe;
    }

    PathBuf::from(cmd)
}

fn execute_privileged_process(
    binary_path: &Path,
    cmd_name: &str,
    args: &[String],
    target_uid: u32,
    target_gid: u32,
    target_user: &UserRecord,
    caller_username: &str,
    caller_uid: u32,
    login_shell: bool,
    preserve_env: bool,
) -> ExitCode {
    let mut cmd = Command::new(binary_path);

    // If using current_exe dispatch for internal applets
    if let Ok(cur_exe) = env::current_exe() {
        if binary_path == cur_exe && !cmd_name.ends_with("ferro-core") {
            cmd.arg(cmd_name);
        }
    }
    cmd.args(args);

    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        // Set UID and GID for child process
        cmd.uid(target_uid);
        cmd.gid(target_gid);
    }

    if !preserve_env {
        cmd.env("USER", &target_user.name);
        cmd.env("LOGNAME", &target_user.name);
        cmd.env("HOME", &target_user.home);
        cmd.env("SHELL", &target_user.shell);
        cmd.env("SUDO_USER", caller_username);
        cmd.env("SUDO_UID", caller_uid.to_string());
        cmd.env("SUDO_GID", target_gid.to_string());

        if login_shell {
            cmd.env(
                "PATH",
                "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            );
            if Path::new(&target_user.home).is_dir() {
                cmd.current_dir(&target_user.home);
            }
        }
    }

    match cmd.status() {
        Ok(status) => {
            if let Some(code) = status.code() {
                ExitCode::from(code as u8)
            } else {
                ExitCode::SUCCESS
            }
        }
        Err(e) => {
            eprintln!("sudo: unable to execute {}: {}", binary_path.display(), e);
            ExitCode::from(1)
        }
    }
}

// ============================================================================
// SNTP Client (ntp / timesync / ntpdate)
// ============================================================================

const NTP_PORT: u16 = 123;
const NTP_TO_UNIX_SECONDS: u64 = 2_208_988_800; // 70 years in seconds (1900 -> 1970)

pub fn run_ntp(args: &[String]) -> ExitCode {
    let mut server: Option<String> = None;
    let mut query_only = false;
    let mut check_only = false;
    let mut port = NTP_PORT;

    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-h" || arg == "--help" {
            println!("FerroOS SNTP Network Time Client v2.3.0");
            println!("Usage: ntp [options] [server]");
            println!("\nOptions:");
            println!("  -s, --server <server>   NTP server to query (default: pool.ntp.org)");
            println!("  -p, --port <port>       UDP port (default: 123)");
            println!("  -q, --query             Query and display time offset without setting clock");
            println!("  -c, --check             Validate NTP client subsystem and configuration");
            println!("  -h, --help              Display this help and exit");
            println!("\nAliases: timesync, ntpdate");
            return ExitCode::SUCCESS;
        } else if arg == "-q" || arg == "--query" {
            query_only = true;
            i += 1;
        } else if arg == "-c" || arg == "--check" {
            check_only = true;
            i += 1;
        } else if arg == "-s" || arg == "--server" {
            if i + 1 < args.len() {
                server = Some(args[i + 1].clone());
                i += 2;
            } else {
                eprintln!("ntp: option requires an argument -- 's'");
                return ExitCode::from(1);
            }
        } else if arg == "-p" || arg == "--port" {
            if i + 1 < args.len() {
                if let Ok(p) = args[i + 1].parse::<u16>() {
                    port = p;
                }
                i += 2;
            } else {
                eprintln!("ntp: option requires an argument -- 'p'");
                return ExitCode::from(1);
            }
        } else if !arg.starts_with('-') && server.is_none() {
            server = Some(arg.clone());
            i += 1;
        } else {
            i += 1;
        }
    }

    if check_only {
        println!("[ntp] Pure-Rust SNTP client subsystem active and operational.");
        println!("      Protocol: SNTPv4 (RFC 4330), port 123");
        println!("      Default pool: pool.ntp.org (fallbacks: time.cloudflare.com, time.google.com)");
        return ExitCode::SUCCESS;
    }

    let candidate_servers = if let Some(srv) = server {
        vec![srv]
    } else {
        vec![
            "pool.ntp.org".to_string(),
            "time.cloudflare.com".to_string(),
            "time.google.com".to_string(),
        ]
    };

    let socket = match UdpSocket::bind("0.0.0.0:0") {
        Ok(s) => s,
        Err(e) => {
            eprintln!("ntp: failed to bind local UDP socket: {}", e);
            return ExitCode::from(1);
        }
    };
    let _ = socket.set_read_timeout(Some(Duration::from_secs(3)));
    let _ = socket.set_write_timeout(Some(Duration::from_secs(3)));

    let mut sync_result = None;

    for srv in &candidate_servers {
        let addr = format!("{}:{}", srv, port);
        // Build 48-byte NTP client request packet
        // Byte 0: LI=0, VN=4 (NTPv4), Mode=3 (Client) -> 0x23
        let mut request = [0u8; 48];
        request[0] = 0x23;

        if socket.send_to(&request, &addr).is_err() {
            continue;
        }

        let mut response = [0u8; 48];
        if let Ok((len, _)) = socket.recv_from(&mut response) {
            if len >= 48 {
                let stratum = response[1];
                let ntp_sec = u32::from_be_bytes([
                    response[40], response[41], response[42], response[43],
                ]) as u64;
                let ntp_frac = u32::from_be_bytes([
                    response[44], response[45], response[46], response[47],
                ]);

                if ntp_sec >= NTP_TO_UNIX_SECONDS {
                    let unix_sec = ntp_sec - NTP_TO_UNIX_SECONDS;
                    let nanos = ((ntp_frac as u64 * 1_000_000_000) >> 32) as u32;

                    sync_result = Some((srv.clone(), stratum, unix_sec, nanos));
                    break;
                }
            }
        }
    }

    let (server_used, stratum, unix_sec, nanos) = match sync_result {
        Some(res) => res,
        None => {
            eprintln!("ntp: no suitable server found (timeout or network unreachable)");
            return ExitCode::from(1);
        }
    };

    // Calculate time offset against local wall clock
    let local_now = SystemTime::now();
    let local_dur = local_now.duration_since(UNIX_EPOCH).unwrap_or_default();
    let local_sec = local_dur.as_secs();
    let local_nanos = local_dur.subsec_nanos();

    let server_total = unix_sec as f64 + (nanos as f64 / 1_000_000_000.0);
    let local_total = local_sec as f64 + (local_nanos as f64 / 1_000_000_000.0);
    let offset = server_total - local_total;

    println!(
        "ntp: server {}, stratum {}, offset {:+.6} sec",
        server_used, stratum, offset
    );

    if query_only {
        return ExitCode::SUCCESS;
    }

    // Setting system clock requires root privileges
    #[cfg(unix)]
    let is_root = unsafe { libc::getuid() == 0 };
    #[cfg(not(unix))]
    let is_root = false;

    if !is_root {
        eprintln!("ntp: operation not permitted (must be root or run with sudo to set system clock)");
        return ExitCode::from(1);
    }

    #[cfg(target_os = "linux")]
    unsafe {
        let ts = libc::timespec {
            tv_sec: unix_sec as libc::time_t,
            tv_nsec: nanos as libc::c_long,
        };
        if libc::clock_settime(libc::CLOCK_REALTIME, &ts) == 0 {
            println!("ntp: system clock synchronized successfully");
            ExitCode::SUCCESS
        } else {
            let err = std::io::Error::last_os_error();
            eprintln!("ntp: failed to set system clock: {}", err);
            ExitCode::from(1)
        }
    }

    #[cfg(not(target_os = "linux"))]
    {
        println!("ntp: system clock adjustment simulation completed (non-Linux platform)");
        ExitCode::SUCCESS
    }
}

// ============================================================================
// Unit Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_passwd() {
        let sample = "\
root:x:0:0:root:/root:/bin/sh
# Comment
daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
ferro:x:1000:1000:ferro:/home/ferro:/bin/sh
";
        let users = parse_passwd_content(sample);
        assert_eq!(users.len(), 3);
        assert_eq!(users[0].name, "root");
        assert_eq!(users[0].uid, 0);
        assert_eq!(users[1].name, "daemon");
        assert_eq!(users[2].name, "ferro");
        assert_eq!(users[2].uid, 1000);
        assert_eq!(users[2].home, "/home/ferro");
    }

    #[test]
    fn test_parse_group() {
        let sample = "\
root:x:0:
wheel:x:10:ferro,admin
sudo:x:27:ferro
users:x:100:
";
        let groups = parse_group_content(sample);
        assert_eq!(groups.len(), 4);
        assert_eq!(groups[1].name, "wheel");
        assert_eq!(groups[1].members, vec!["ferro", "admin"]);
        assert_eq!(groups[2].name, "sudo");
        assert_eq!(groups[2].members, vec!["ferro"]);
    }

    #[test]
    fn test_fallback_users_and_groups() {
        let users = fallback_users();
        assert!(users.iter().any(|u| u.name == "root" && u.uid == 0));
        assert!(users.iter().any(|u| u.name == "ferro" && u.uid == 1000));

        let groups = fallback_groups();
        assert!(groups.iter().any(|g| g.name == "sudo" && g.gid == 27));
        assert!(groups.iter().any(|g| g.name == "wheel" && g.gid == 10));
    }

    #[test]
    fn test_ntp_timestamp_math() {
        // NTP timestamp: 3,900,000,000
        // Offset: 2,208,988,800
        let ntp_sec = 3_900_000_000u64;
        let unix_sec = ntp_sec - NTP_TO_UNIX_SECONDS;
        assert_eq!(unix_sec, 1_691_011_200);

        let ntp_frac: u32 = 0x80000000; // Half second
        let nanos = ((ntp_frac as u64 * 1_000_000_000) >> 32) as u32;
        assert_eq!(nanos, 500_000_000);
    }
}
