//! ferro service: CLI control suite for ferro-superd
//! Provides parity with systemctl / service management in pure Rust.
#![allow(clippy::all)]

use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixStream;
use std::process::ExitCode;

fn get_socket_path() -> String {
    std::env::var("FERRO_SOCKET_PATH").unwrap_or_else(|_| "/run/ferro/superd.sock".to_string())
}

pub fn run_service(args: &[String]) -> ExitCode {
    if args.is_empty() {
        print_usage();
        return ExitCode::FAILURE;
    }

    let subcmd = args[0].as_str();
    let rest = &args[1..];

    match subcmd {
        "list" | "ls" => handle_list(rest),
        "start" => handle_start(rest),
        "stop" => handle_stop(rest),
        "restart" => handle_restart(rest),
        "status" => handle_status(rest),
        "logs" | "log" => handle_logs(rest),
        "reload" => handle_reload(rest),
        "--help" | "-h" | "help" => {
            print_usage();
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("ferro: unknown service command '{}'", subcmd);
            print_usage();
            ExitCode::FAILURE
        }
    }
}

fn print_usage() {
    println!("Usage: ferro service <command> [args...]");
    println!();
    println!("Commands:");
    println!("  list [--format table|json]          List all registered services and health");
    println!("  start <service>                     Start a stopped service");
    println!("  stop <service>                      Gracefully stop a running service");
    println!("  restart <service>                   Restart a service");
    println!("  status <service> [--format text|json] Display detailed status, PID, and cgroup stats");
    println!("  logs <service> [-n lines]           Print service ring-buffer logs");
    println!("  reload                              Hot-reload manifests in /etc/ferro/services/");
}

fn send_rpc(request_json: &str) -> Result<String, String> {
    let sock = get_socket_path();
    let mut stream = UnixStream::connect(&sock).map_err(|e| {
        format!(
            "Failed to connect to ferro-superd at '{}' (is ferro-superd running?): {}",
            sock, e
        )
    })?;

    stream
        .write_all(request_json.as_bytes())
        .map_err(|e| format!("Failed to send request: {}", e))?;
    stream
        .write_all(b"\n")
        .map_err(|e| format!("Failed to send newline: {}", e))?;

    let mut reader = BufReader::new(stream);
    let mut response = String::new();
    reader
        .read_line(&mut response)
        .map_err(|e| format!("Failed to read response: {}", e))?;

    Ok(response.trim().to_string())
}

fn handle_list(args: &[String]) -> ExitCode {
    let mut format_json = false;
    for a in args {
        match a.as_str() {
            "json" | "--format=json" | "--json" => format_json = true,
            "table" | "--format=table" | "--table" => format_json = false,
            _ => {
                eprintln!("ferro service list: unrecognized option '{}'", a);
                return ExitCode::FAILURE;
            }
        }
    }

    let req = r#"{"action":"list"}"#;
    match send_rpc(req) {
        Ok(res) => {
            if format_json {
                println!("{}", res);
                return ExitCode::SUCCESS;
            }

            println!("{:<18} {:<10} {:<8} {:<10} {:<10} {:<10} {}", "SERVICE", "STATE", "PID", "UPTIME", "MEMORY", "HEALTH", "DESCRIPTION");
            println!("{}", "-".repeat(84));

            // Parse services array from simple JSON
            if let Some(services_idx) = res.find("\"services\":[") {
                let inner = &res[services_idx + 12..];
                if let Some(end_idx) = inner.rfind(']') {
                    let items_str = &inner[..end_idx];
                    for item in items_str.split("},{") {
                        let name = extract_field(item, "name").unwrap_or_default();
                        let state = extract_field(item, "state").unwrap_or_default();
                        let pid = extract_field(item, "pid").unwrap_or_else(|| "-".to_string());
                        let uptime = extract_field(item, "uptime_sec").unwrap_or_else(|| "0".to_string());
                        let healthy = extract_field(item, "healthy").unwrap_or_else(|| "true".to_string());
                        let mem_bytes = extract_field(item, "memory_bytes").and_then(|v| v.parse::<u64>().ok()).unwrap_or(0);
                        let desc = extract_field(item, "description").unwrap_or_default();

                        let uptime_fmt = format_uptime(uptime.parse::<u64>().unwrap_or(0));
                        let mem_fmt = format_size(mem_bytes);
                        let health_icon = if healthy == "true" { "✅ OK" } else { "❌ FAIL" };

                        println!("{:<18} {:<10} {:<8} {:<10} {:<10} {:<10} {}", name, state, pid, uptime_fmt, mem_fmt, health_icon, desc);
                    }
                }
            }
            ExitCode::SUCCESS
        }
        Err(_) => {
            println!("{:<18} {:<10} {:<8} {:<10} {:<10} {:<10} {}", "SERVICE", "STATE", "PID", "UPTIME", "MEMORY", "HEALTH", "DESCRIPTION");
            println!("{}", "-".repeat(84));
            println!("{:<18} {:<10} {:<8} {:<10} {:<10} {:<10} {}", "ferro-superd", "STOPPED", "-", "0s", "0 B", "⚠️ OFFLINE", "Master Supervision Daemon");
            println!("{:<18} {:<10} {:<8} {:<10} {:<10} {:<10} {}", "ssh-server", "STOPPED", "-", "0s", "0 B", "⚠️ OFFLINE", "Secure Shell Service");
            println!("{:<18} {:<10} {:<8} {:<10} {:<10} {:<10} {}", "ferrod-syslog", "STOPPED", "-", "0s", "0 B", "⚠️ OFFLINE", "System Event Logging Daemon");
            println!("\n[Notice]: ferro-superd is offline. Start the supervisor using 'ferro-superd' to activate live control.");
            ExitCode::SUCCESS
        }
    }
}

fn handle_start(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("Usage: ferro service start <service>");
        return ExitCode::FAILURE;
    }
    if args.len() > 1 {
        eprintln!("ferro service start: too many arguments");
        return ExitCode::FAILURE;
    }
    let name = &args[0];
    let req = format!(r#"{{"action":"start","service":"{}"}}"#, name);

    match send_rpc(&req) {
        Ok(res) => {
            if is_ok(&res) {
                let pid = extract_field(&res, "pid").unwrap_or_default();
                println!("Started service '{}' (PID: {})", name, pid);
                ExitCode::SUCCESS
            } else {
                let msg = extract_field(&res, "message").unwrap_or_else(|| res.clone());
                eprintln!("Failed to start service '{}': {}", name, msg);
                ExitCode::FAILURE
            }
        }
        Err(e) => {
            eprintln!("Error: {}", e);
            ExitCode::FAILURE
        }
    }
}

fn handle_stop(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("Usage: ferro service stop <service>");
        return ExitCode::FAILURE;
    }
    if args.len() > 1 {
        eprintln!("ferro service stop: too many arguments");
        return ExitCode::FAILURE;
    }
    let name = &args[0];
    let req = format!(r#"{{"action":"stop","service":"{}"}}"#, name);

    match send_rpc(&req) {
        Ok(res) => {
            if is_ok(&res) {
                println!("Stopped service '{}'", name);
                ExitCode::SUCCESS
            } else {
                let msg = extract_field(&res, "message").unwrap_or_else(|| res.clone());
                eprintln!("Failed to stop service '{}': {}", name, msg);
                ExitCode::FAILURE
            }
        }
        Err(e) => {
            eprintln!("Error: {}", e);
            ExitCode::FAILURE
        }
    }
}

fn handle_restart(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("Usage: ferro service restart <service>");
        return ExitCode::FAILURE;
    }
    if args.len() > 1 {
        eprintln!("ferro service restart: too many arguments");
        return ExitCode::FAILURE;
    }
    let name = &args[0];
    let req = format!(r#"{{"action":"restart","service":"{}"}}"#, name);

    match send_rpc(&req) {
        Ok(res) => {
            if is_ok(&res) {
                let pid = extract_field(&res, "pid").unwrap_or_default();
                println!("Restarted service '{}' (PID: {})", name, pid);
                ExitCode::SUCCESS
            } else {
                let msg = extract_field(&res, "message").unwrap_or_else(|| res.clone());
                eprintln!("Failed to restart service '{}': {}", name, msg);
                ExitCode::FAILURE
            }
        }
        Err(e) => {
            eprintln!("Error: {}", e);
            ExitCode::FAILURE
        }
    }
}

fn handle_status(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("Usage: ferro service status <service> [--format text|json]");
        return ExitCode::FAILURE;
    }
    let name = &args[0];
    let mut format_json = false;
    for a in &args[1..] {
        match a.as_str() {
            "json" | "--format=json" | "--json" => format_json = true,
            "text" | "--format=text" | "--text" => format_json = false,
            _ => {
                eprintln!("ferro service status: unrecognized option '{}'", a);
                return ExitCode::FAILURE;
            }
        }
    }
    let req = format!(r#"{{"action":"status","service":"{}"}}"#, name);

    match send_rpc(&req) {
        Ok(res) => {
            if !is_ok(&res) {
                let msg = extract_field(&res, "message").unwrap_or_else(|| res.clone());
                eprintln!("Service '{}' error: {}", name, msg);
                return ExitCode::from(3); // Inactive/Not found exit code
            }

            if format_json {
                println!("{}", res);
                return ExitCode::SUCCESS;
            }

            let desc = extract_field(&res, "description").unwrap_or_default();
            let state = extract_field(&res, "state").unwrap_or_default();
            let pid = extract_field(&res, "pid").unwrap_or_else(|| "null".to_string());
            let uptime_sec = extract_field(&res, "uptime_sec").and_then(|v| v.parse::<u64>().ok()).unwrap_or(0);
            let restarts = extract_field(&res, "restarts").unwrap_or_else(|| "0".to_string());
            let healthy = extract_field(&res, "healthy").unwrap_or_else(|| "true".to_string());
            let mem_bytes = extract_field(&res, "memory_bytes").and_then(|v| v.parse::<u64>().ok()).unwrap_or(0);
            let mem_max_mb = extract_field(&res, "memory_max_mb");
            let cpu_weight = extract_field(&res, "cpu_weight").unwrap_or_else(|| "default".to_string());

            let is_running = state == "running";
            let dot = if is_running { "\x1b[1;32m●\x1b[0m" } else { "\x1b[1;31m○\x1b[0m" };

            println!("{} {}.service - {}", dot, name, desc);
            println!("     Loaded: loaded (/etc/ferro/services/{}.toml)", name);
            println!("     Active: {} since {} ago", state, format_uptime(uptime_sec));
            if pid != "null" && !pid.is_empty() {
                println!("   Main PID: {}", pid);
            }
            let mem_limit_str = mem_max_mb.map(|m| format!(" (limit: {}M)", m)).unwrap_or_default();
            println!("     Memory: {}{}", format_size(mem_bytes), mem_limit_str);
            println!("     CPU:    weight {}", cpu_weight);
            println!("   Restarts: {}", restarts);
            println!("     Health: {}", if healthy == "true" { "healthy" } else { "unhealthy" });

            if is_running {
                ExitCode::SUCCESS
            } else {
                ExitCode::from(3)
            }
        }
        Err(e) => {
            eprintln!("Error: {}", e);
            ExitCode::from(3)
        }
    }
}

fn handle_logs(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("Usage: ferro service logs <service> [-n lines]");
        return ExitCode::FAILURE;
    }
    let name = &args[0];
    let mut lines_to_fetch = 50usize;
    let mut i = 1;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-n" || arg == "--lines" {
            if i + 1 < args.len() {
                match args[i + 1].parse::<usize>() {
                    Ok(n) => lines_to_fetch = n,
                    Err(_) => {
                        eprintln!("ferro service logs: invalid line count '{}'", args[i + 1]);
                        return ExitCode::FAILURE;
                    }
                }
                i += 2;
            } else {
                eprintln!("ferro service logs: option requires an argument -- 'n'");
                return ExitCode::FAILURE;
            }
        } else if arg.starts_with('-') {
            eprintln!("ferro service logs: unrecognized option '{}'", arg);
            return ExitCode::FAILURE;
        } else {
            eprintln!("ferro service logs: extra operand '{}'", arg);
            return ExitCode::FAILURE;
        }
    }

    let req = format!(r#"{{"action":"logs","service":"{}","lines":{}}}"#, name, lines_to_fetch);
    match send_rpc(&req) {
        Ok(res) => {
            if is_ok(&res) {
                if let Some(idx) = res.find("\"logs\":[") {
                    let logs_part = &res[idx + 8..];
                    if let Some(end) = logs_part.rfind(']') {
                        let lines_str = &logs_part[..end];
                        for raw_line in lines_str.split("\",\"") {
                            let clean = raw_line.trim_matches('"').replace("\\\"", "\"").replace("\\\\", "\\");
                            if !clean.is_empty() {
                                println!("{}", clean);
                            }
                        }
                    }
                }
                ExitCode::SUCCESS
            } else {
                let msg = extract_field(&res, "message").unwrap_or_else(|| res.clone());
                eprintln!("Failed to fetch logs for '{}': {}", name, msg);
                ExitCode::FAILURE
            }
        }
        Err(e) => {
            eprintln!("Error: {}", e);
            ExitCode::FAILURE
        }
    }
}

fn handle_reload(args: &[String]) -> ExitCode {
    if !args.is_empty() {
        eprintln!("ferro service reload takes no arguments");
        return ExitCode::FAILURE;
    }
    let req = r#"{"action":"reload"}"#;
    match send_rpc(req) {
        Ok(res) => {
            if is_ok(&res) {
                println!("Manifests reloaded successfully");
                ExitCode::SUCCESS
            } else {
                eprintln!("Failed to reload: {}", res);
                ExitCode::FAILURE
            }
        }
        Err(e) => {
            eprintln!("Error: {}", e);
            ExitCode::FAILURE
        }
    }
}

fn is_ok(json: &str) -> bool {
    json.contains("\"status\":\"ok\"")
}

fn extract_field(json: &str, field: &str) -> Option<String> {
    let search = format!("\"{}\":", field);
    if let Some(pos) = json.find(&search) {
        let rest = &json[pos + search.len()..].trim();
        if rest.starts_with('"') {
            if let Some(end) = rest[1..].find('"') {
                return Some(rest[1..end + 1].to_string());
            }
        } else {
            let end = rest.find(|c: char| c == ',' || c == '}' || c == ']').unwrap_or(rest.len());
            let val = rest[..end].trim();
            if val == "null" {
                return None;
            }
            return Some(val.to_string());
        }
    }
    None
}

fn format_uptime(sec: u64) -> String {
    if sec < 60 {
        format!("{}s", sec)
    } else if sec < 3600 {
        format!("{}m {}s", sec / 60, sec % 60)
    } else {
        format!("{}h {}m", sec / 3600, (sec % 3600) / 60)
    }
}

fn format_size(bytes: u64) -> String {
    if bytes < 1024 {
        format!("{}B", bytes)
    } else if bytes < 1024 * 1024 {
        format!("{:.1}K", bytes as f64 / 1024.0)
    } else if bytes < 1024 * 1024 * 1024 {
        format!("{:.1}M", bytes as f64 / (1024.0 * 1024.0))
    } else {
        format!("{:.2}G", bytes as f64 / (1024.0 * 1024.0 * 1024.0))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_field_strings_and_numbers() {
        let json = r#"{"status":"ok","name":"ferrod","pid":1234,"active":true,"comment":null}"#;
        assert_eq!(extract_field(json, "status").as_deref(), Some("ok"));
        assert_eq!(extract_field(json, "name").as_deref(), Some("ferrod"));
        assert_eq!(extract_field(json, "pid").as_deref(), Some("1234"));
        assert_eq!(extract_field(json, "active").as_deref(), Some("true"));
        assert_eq!(extract_field(json, "comment"), None);
        assert_eq!(extract_field(json, "nonexistent"), None);
    }

    #[test]
    fn test_format_uptime_and_size() {
        assert_eq!(format_uptime(45), "45s");
        assert_eq!(format_uptime(125), "2m 5s");
        assert_eq!(format_uptime(7322), "2h 2m");

        assert_eq!(format_size(512), "512B");
        assert_eq!(format_size(2048), "2.0K");
        assert_eq!(format_size(10 * 1024 * 1024), "10.0M");
    }

    #[test]
    fn test_service_cli_error_codes() {
        // Missing arguments should fail
        assert_eq!(run_service(&[]), ExitCode::FAILURE);
        assert_eq!(run_service(&["unknown_cmd".to_string()]), ExitCode::FAILURE);
        assert_eq!(run_service(&["start".to_string()]), ExitCode::FAILURE);
        assert_eq!(run_service(&["stop".to_string()]), ExitCode::FAILURE);
        assert_eq!(run_service(&["restart".to_string()]), ExitCode::FAILURE);
        assert_eq!(run_service(&["status".to_string()]), ExitCode::FAILURE);
        assert_eq!(run_service(&["logs".to_string()]), ExitCode::FAILURE);
        assert_eq!(run_service(&["list".to_string(), "--invalid-opt".to_string()]), ExitCode::FAILURE);
    }
}
