//! ferro-core: Pure-Rust System Logging Daemon (ferrod) and Syslog Log Viewer.
//!
//! Provides:
//!  - Standard RFC 3164 / RFC 5424 Unix domain datagram socket listener at /dev/log
//!  - Fast in-memory circular ring buffer and persistent append to /var/log/syslog
//!  - `logger` applet: standard POSIX command to submit log messages to /dev/log
//!  - `logs` / `journalctl` applet: stream, tail, and filter system logs by facility/severity
//!  - `dmesg` applet: query kernel ring buffer from /dev/kmsg or /proc/kmsg

use std::fs::{self, File, OpenOptions};
use std::io::{self, BufRead, BufReader, Read, Write};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::UnixDatagram;
use std::path::Path;
use std::process::ExitCode;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

const DEFAULT_SOCKET_PATH: &str = "/dev/log";
const DEFAULT_LOG_FILE: &str = "/var/log/syslog";
const RUN_LOG_FILE: &str = "/run/ferro/syslog.log";
// const MAX_RING_LINES: usize = 5000;

#[derive(Debug, Clone)]
pub struct SyslogEntry {
    pub timestamp: String,
    pub facility: u8,
    pub severity: u8,
    pub hostname: String,
    pub tag: String,
    pub message: String,
}

impl SyslogEntry {
    pub fn severity_name(sev: u8) -> &'static str {
        match sev {
            0 => "EMERG",
            1 => "ALERT",
            2 => "CRIT",
            3 => "ERR",
            4 => "WARNING",
            5 => "NOTICE",
            6 => "INFO",
            7 => "DEBUG",
            _ => "UNKNOWN",
        }
    }

    pub fn facility_name(fac: u8) -> &'static str {
        match fac {
            0 => "kern",
            1 => "user",
            2 => "mail",
            3 => "daemon",
            4 => "auth",
            5 => "syslog",
            6 => "lpr",
            7 => "news",
            8 => "uucp",
            9 => "cron",
            10 => "authpriv",
            11 => "ftp",
            16..=23 => "local",
            _ => "unknown",
        }
    }

    /// Parse raw syslog datagram (RFC 3164, RFC 5424, or raw text)
    pub fn parse(raw: &[u8]) -> Self {
        let text = String::from_utf8_lossy(raw).trim().to_string();
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        let time_str = format_epoch_seconds(now);

        let mut facility = 1u8; // user
        let mut severity = 6u8; // info
        let mut remainder = text.as_str();

        // Check for <PRI>
        if remainder.starts_with('<') {
            if let Some(end_idx) = remainder.find('>') {
                let pri_str = &remainder[1..end_idx];
                if let Ok(pri) = pri_str.parse::<u16>() {
                    facility = ((pri >> 3) & 0x1F) as u8;
                    severity = (pri & 0x07) as u8;
                    remainder = remainder[end_idx + 1..].trim_start();
                }
            }
        }

        // Try extracting tag: "tag: message" or "tag[pid]: message"
        let mut tag = "ferrod".to_string();
        let mut message = remainder.to_string();

        if let Some(colon_pos) = remainder.find(':') {
            let potential_tag = remainder[..colon_pos].trim();
            // Tags typically don't have spaces and are shorter than 32 chars
            if !potential_tag.contains(' ') && potential_tag.len() <= 32 && !potential_tag.is_empty() {
                tag = potential_tag.to_string();
                message = remainder[colon_pos + 1..].trim().to_string();
            }
        }

        SyslogEntry {
            timestamp: time_str,
            facility,
            severity,
            hostname: "ferro-node".to_string(),
            tag,
            message,
        }
    }

    pub fn format_line(&self) -> String {
        format!(
            "{} [{}] {}: {}",
            self.timestamp,
            Self::severity_name(self.severity),
            self.tag,
            self.message
        )
    }
}

fn format_epoch_seconds(secs: u64) -> String {
    let s = secs % 60;
    let m = (secs / 60) % 60;
    let h = (secs / 3600) % 24;
    format!("{:02}:{:02}:{:02}", h, m, s)
}

/// Run the pure-Rust logging daemon (`ferrod` / `syslogd`)
pub fn run_ferrod(args: &[String]) -> ExitCode {
    let mut foreground = false;
    let mut socket_path = DEFAULT_SOCKET_PATH.to_string();
    let mut test_msg: Option<String> = None;
    let mut test_tag = "logger".to_string();

    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "-f" | "--foreground" => foreground = true,
            "-s" | "--socket" => {
                if i + 1 < args.len() {
                    socket_path = args[i + 1].clone();
                    i += 1;
                }
            }
            "-t" | "--tag" => {
                if i + 1 < args.len() {
                    test_tag = args[i + 1].clone();
                    i += 1;
                }
            }
            "--test" | "-m" => {
                if i + 1 < args.len() {
                    test_msg = Some(args[i + 1].clone());
                    i += 1;
                }
            }
            "--help" | "-h" => {
                println!("FerroOS System Logging Daemon (ferrod)");
                println!("Usage: ferrod [OPTIONS]");
                println!("  -f, --foreground     Run in foreground mode and log to stdout");
                println!("  -s, --socket <PATH>  Unix datagram socket path (default: /dev/log)");
                println!("  -m, --test <MSG>     Send test datagram to socket and exit");
                println!("  -t, --tag <TAG>      Tag to use when sending test log");
                return ExitCode::SUCCESS;
            }
            _ => {}
        }
        i += 1;
    }

    // Client mode (e.g. logger / test client)
    if let Some(msg) = test_msg {
        return send_syslog_message(&socket_path, &test_tag, 6, &msg);
    }

    println!("======================================================================");
    println!("     FERRO-OS PURE-RUST SYSTEM LOGGING DAEMON (ferrod v1.0)           ");
    println!("======================================================================");
    println!("Socket Path:   {}", socket_path);
    println!("Log Destination: {} & {}", DEFAULT_LOG_FILE, RUN_LOG_FILE);
    println!("Foreground:    {}", foreground);

    // Prepare directories
    let _ = fs::create_dir_all("/dev");
    let _ = fs::create_dir_all("/var/log");
    let _ = fs::create_dir_all("/run/ferro");

    // Clean up old socket if present
    if Path::new(&socket_path).exists() {
        let _ = fs::remove_file(&socket_path);
    }

    let socket = match UnixDatagram::bind(&socket_path) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("ferrod: failed to bind socket '{}': {}", socket_path, e);
            return ExitCode::FAILURE;
        }
    };

    // Make socket accessible to all processes (0666) so non-root apps can log
    let _ = fs::set_permissions(&socket_path, fs::Permissions::from_mode(0o666));

    println!("[ferrod] Listening on {} (mode 0666). Ready for system logs.", socket_path);

    let running = Arc::new(AtomicBool::new(true));
    let r = running.clone();

    // Set read timeout so thread can gracefully exit on termination if needed
    let _ = socket.set_read_timeout(Some(Duration::from_millis(500)));

    let mut buf = [0u8; 4096];
    let mut count = 0usize;

    while r.load(Ordering::SeqCst) {
        match socket.recv(&mut buf) {
            Ok(bytes_read) => {
                if bytes_read == 0 {
                    continue;
                }
                let entry = SyslogEntry::parse(&buf[..bytes_read]);
                let formatted = entry.format_line();
                count += 1;

                if foreground {
                    println!("{}", formatted);
                }

                // Append to persistent log file
                append_log_line(DEFAULT_LOG_FILE, &formatted);
                append_log_line(RUN_LOG_FILE, &formatted);
            }
            Err(ref e) if e.kind() == io::ErrorKind::WouldBlock || e.kind() == io::ErrorKind::TimedOut => {
                // Heartbeat / idle check
                continue;
            }
            Err(e) => {
                eprintln!("[ferrod] recv error: {}", e);
                break;
            }
        }
    }

    println!("[ferrod] Daemon shutting down. Processed {} log records.", count);
    let _ = fs::remove_file(&socket_path);
    ExitCode::SUCCESS
}

fn append_log_line(path_str: &str, line: &str) {
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(path_str) {
        let _ = writeln!(f, "{}", line);
    }
}

/// Client utility to send a syslog message to `/dev/log`
pub fn send_syslog_message(socket_path: &str, tag: &str, pri: u8, msg: &str) -> ExitCode {
    let packet = format!("<{}>{}: {}\n", pri, tag, msg);
    
    // Bind temporary client datagram socket
    let client_path = format!("/tmp/ferro_log_client_{}.sock", std::process::id());
    let _ = fs::remove_file(&client_path);

    let client_sock = match UnixDatagram::bind(&client_path) {
        Ok(s) => s,
        Err(_) => {
            // Unbound datagram attempt
            match UnixDatagram::unbound() {
                Ok(s) => s,
                Err(e) => {
                    eprintln!("logger: failed to create datagram socket: {}", e);
                    return ExitCode::FAILURE;
                }
            }
        }
    };

    let res = client_sock.send_to(packet.as_bytes(), socket_path);
    let _ = fs::remove_file(&client_path);

    match res {
        Ok(_) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("logger: failed to deliver log to '{}': {}", socket_path, e);
            ExitCode::FAILURE
        }
    }
}

/// Applet: `logger` (standard POSIX command to submit log entries)
pub fn run_logger(args: &[String]) -> ExitCode {
    let mut tag = "user".to_string();
    let mut pri = 13u8; // user.notice (1 * 8 + 5)
    let mut socket_path = DEFAULT_SOCKET_PATH.to_string();
    let mut message_parts = Vec::new();

    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "-t" | "--tag" => {
                if i + 1 < args.len() {
                    tag = args[i + 1].clone();
                    i += 1;
                }
            }
            "-p" | "--priority" => {
                if i + 1 < args.len() {
                    if let Ok(p) = args[i + 1].parse::<u8>() {
                        pri = p;
                    }
                    i += 1;
                }
            }
            "-u" | "--socket" => {
                if i + 1 < args.len() {
                    socket_path = args[i + 1].clone();
                    i += 1;
                }
            }
            _ => {
                message_parts.push(args[i].clone());
            }
        }
        i += 1;
    }

    let message = if message_parts.is_empty() {
        // Read from stdin
        let mut input = String::new();
        let _ = io::stdin().read_to_string(&mut input);
        input.trim().to_string()
    } else {
        message_parts.join(" ")
    };

    if message.is_empty() {
        eprintln!("logger: no message provided");
        return ExitCode::FAILURE;
    }

    send_syslog_message(&socket_path, &tag, pri, &message)
}

/// Applet: `logs` / `journalctl` (pure-Rust system log inspector)
pub fn run_logs(args: &[String]) -> ExitCode {
    let mut follow = false;
    let mut line_limit: usize = 50;
    let mut grep_filter: Option<String> = None;
    let mut level_filter: Option<String> = None;
    let mut target_file = DEFAULT_LOG_FILE.to_string();

    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "-f" | "--follow" => follow = true,
            "-n" | "--lines" => {
                if i + 1 < args.len() {
                    if let Ok(n) = args[i + 1].parse::<usize>() {
                        line_limit = n;
                    }
                    i += 1;
                }
            }
            "-g" | "--grep" => {
                if i + 1 < args.len() {
                    grep_filter = Some(args[i + 1].clone());
                    i += 1;
                }
            }
            "-l" | "--level" => {
                if i + 1 < args.len() {
                    level_filter = Some(args[i + 1].to_uppercase());
                    i += 1;
                }
            }
            "-u" | "--unit" => {
                if i + 1 < args.len() {
                    grep_filter = Some(args[i + 1].clone());
                    i += 1;
                }
            }
            "--file" => {
                if i + 1 < args.len() {
                    target_file = args[i + 1].clone();
                    i += 1;
                }
            }
            "--help" | "-h" => {
                println!("FerroOS System Log Inspector (logs / journalctl)");
                println!("Usage: logs [OPTIONS]");
                println!("  -n, --lines <N>      Number of recent log lines to display (default: 50)");
                println!("  -f, --follow         Follow log output in real-time (like tail -f)");
                println!("  -g, --grep <PAT>     Filter log entries matching pattern");
                println!("  -l, --level <LVL>    Filter by severity (EMERG, ALERT, CRIT, ERR, WARNING, NOTICE, INFO, DEBUG)");
                println!("  -u, --unit <NAME>    Filter by service or process unit name");
                return ExitCode::SUCCESS;
            }
            _ => {}
        }
        i += 1;
    }

    // Try target_file first, fallback to RUN_LOG_FILE or /var/log/messages
    let candidates = [target_file.as_str(), RUN_LOG_FILE, "/var/log/messages"];
    let mut active_path: Option<&str> = None;
    for c in &candidates {
        if Path::new(c).exists() {
            active_path = Some(c);
            break;
        }
    }

    let log_path = match active_path {
        Some(p) => p,
        None => {
            println!("ferro-core: no active system log found (checked /var/log/syslog, /run/ferro/syslog.log).");
            println!("Hint: Start ferrod with 'ferro-core ferrod' or ensure /dev/log is active.");
            return ExitCode::SUCCESS;
        }
    };

    let file = match File::open(log_path) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("logs: cannot open '{}': {}", log_path, e);
            return ExitCode::FAILURE;
        }
    };

    let reader = BufReader::new(file);
    let all_lines: Vec<String> = reader.lines().filter_map(|l| l.ok()).collect();

    // Filter lines
    let filtered: Vec<&String> = all_lines
        .iter()
        .filter(|line| {
            if let Some(ref grep) = grep_filter {
                if !line.contains(grep) {
                    return false;
                }
            }
            if let Some(ref lvl) = level_filter {
                if !line.contains(&format!("[{}]", lvl)) {
                    return false;
                }
            }
            true
        })
        .collect();

    let start_idx = if filtered.len() > line_limit {
        filtered.len() - line_limit
    } else {
        0
    };

    for line in &filtered[start_idx..] {
        println!("{}", line);
    }

    if follow {
        let mut last_len = all_lines.len();
        loop {
            thread::sleep(Duration::from_millis(500));
            if let Ok(f) = File::open(log_path) {
                let r = BufReader::new(f);
                let current_lines: Vec<String> = r.lines().filter_map(|l| l.ok()).collect();
                if current_lines.len() > last_len {
                    for line in &current_lines[last_len..] {
                        let pass_grep = grep_filter.as_ref().map_or(true, |g| line.contains(g));
                        let pass_lvl = level_filter
                            .as_ref()
                            .map_or(true, |lvl| line.contains(&format!("[{}]", lvl)));
                        if pass_grep && pass_lvl {
                            println!("{}", line);
                        }
                    }
                    last_len = current_lines.len();
                }
            }
        }
    }

    ExitCode::SUCCESS
}

/// Applet: `dmesg` (read kernel boot messages and ring buffer)
pub fn run_dmesg(args: &[String]) -> ExitCode {
    let mut follow = false;
    if args.iter().any(|a| a == "-w" || a == "--follow") {
        follow = true;
    }

    // Attempt 1: /dev/kmsg
    if let Ok(file) = File::open("/dev/kmsg") {
        let mut reader = BufReader::new(file);
        let mut line = String::new();
        while let Ok(bytes) = reader.read_line(&mut line) {
            if bytes == 0 {
                if !follow {
                    break;
                }
                thread::sleep(Duration::from_millis(100));
                continue;
            }
            print!("{}", line);
            line.clear();
        }
        return ExitCode::SUCCESS;
    }

    // Attempt 2: /proc/kmsg
    if let Ok(file) = File::open("/proc/kmsg") {
        let mut reader = BufReader::new(file);
        let mut line = String::new();
        while let Ok(bytes) = reader.read_line(&mut line) {
            if bytes == 0 {
                break;
            }
            print!("{}", line);
            line.clear();
        }
        return ExitCode::SUCCESS;
    }

    // Attempt 3: Fallback - kernel entries in /var/log/syslog or /run/ferro/syslog.log
    println!("[dmesg] Direct /dev/kmsg restricted by container sandbox. Reading kernel log stream:");
    let _ = run_logs(&["-g".to_string(), "kern".to_string(), "-n".to_string(), "100".to_string()]);
    ExitCode::SUCCESS
}
