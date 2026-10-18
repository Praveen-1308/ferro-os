//! ferro-core: Multi-call core utilities and shell for FerroOS in Rust.
//! Inspired by BusyBox and uutils coreutils.

use std::env;
use std::fs;
use std::io::{self, BufRead, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();
    if args.is_empty() {
        return ExitCode::FAILURE;
    }

    // Determine the command name from argv[0] (or first argument if invoked as ferro-core)
    let program_path = Path::new(&args[0]);
    let mut command_name = program_path
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("ferro-core")
        .to_string();

    let mut command_args = args[1..].to_vec();

    if command_name == "ferro-core" {
        if command_args.is_empty() {
            print_usage();
            return ExitCode::SUCCESS;
        }
        command_name = command_args.remove(0);
    }

    match command_name.as_str() {
        "sh" => run_sh(&command_args),
        "ls" => run_ls(&command_args),
        "cat" => run_cat(&command_args),
        "echo" => run_echo(&command_args),
        "pwd" => run_pwd(&command_args),
        "uname" => run_uname(&command_args),
        "clear" => run_clear(&command_args),
        "mkdir" => run_mkdir(&command_args),
        "rm" => run_rm(&command_args),
        "reboot" => run_reboot(),
        "poweroff" => run_poweroff(),
        "help" => {
            print_usage();
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("ferro-core: unknown applet '{}'", command_name);
            print_usage();
            ExitCode::FAILURE
        }
    }
}

fn print_usage() {
    println!("FerroOS Core Utilities v0.1.0 (Rust multi-call binary)");
    println!("Usage: ferro-core <applet> [arguments...]");
    println!("\nCurrently defined applets:");
    println!("  sh, ls, cat, echo, pwd, uname, clear, mkdir, rm, reboot, poweroff");
}

// -------------------------------------------------------------
// Interactive Shell (sh)
// -------------------------------------------------------------
fn run_sh(args: &[String]) -> ExitCode {
    // If invoked with -c "command"
    if args.len() >= 2 && args[0] == "-c" {
        return execute_line(&args[1..].join(" "));
    }

    // If invoked with a script file path
    if !args.is_empty() && !args[0].starts_with('-') {
        let script_path = &args[0];
        if let Ok(content) = fs::read_to_string(script_path) {
            for line in content.lines() {
                let trimmed = line.trim();
                if trimmed.is_empty() || trimmed.starts_with('#') {
                    continue;
                }
                execute_line(trimmed);
            }
            return ExitCode::SUCCESS;
        } else {
            eprintln!("sh: cannot open file: {}", script_path);
            return ExitCode::FAILURE;
        }
    }

    // Interactive prompt
    println!("Welcome to FerroOS Shell (Rust)");
    println!("Type 'help' for builtins, or run any system command (e.g. python3).");

    let stdin = io::stdin();
    let mut stdout = io::stdout();

    loop {
        let cwd = env::current_dir().unwrap_or_else(|_| PathBuf::from("/"));
        print!("ferro-os:{}$ ", cwd.display());
        let _ = stdout.flush();

        let mut line = String::new();
        match stdin.lock().read_line(&mut line) {
            Ok(0) => break, // EOF
            Ok(_) => {
                let trimmed = line.trim();
                if trimmed.is_empty() {
                    continue;
                }
                if trimmed == "exit" {
                    break;
                }
                execute_line(trimmed);
            }
            Err(_) => break,
        }
    }

    ExitCode::SUCCESS
}

fn parse_command_line(line: &str) -> Vec<String> {
    let mut tokens = Vec::new();
    let mut current = String::new();
    let mut in_quotes = false;
    let mut quote_char = ' ';

    for c in line.chars() {
        match c {
            '"' | '\'' if !in_quotes => {
                in_quotes = true;
                quote_char = c;
            }
            c if in_quotes && c == quote_char => {
                in_quotes = false;
            }
            c if c.is_whitespace() && !in_quotes => {
                if !current.is_empty() {
                    tokens.push(current.clone());
                    current.clear();
                }
            }
            _ => {
                current.push(c);
            }
        }
    }
    if !current.is_empty() {
        tokens.push(current);
    }
    tokens
}

fn execute_line(line: &str) -> ExitCode {
    let parts = parse_command_line(line);
    if parts.is_empty() {
        return ExitCode::SUCCESS;
    }

    let cmd = &parts[0];
    let args = &parts[1..];

    // Shell Builtins
    match cmd.as_str() {
        "cd" => {
            let target = if args.is_empty() { "/" } else { &args[0] };
            if let Err(e) = env::set_current_dir(target) {
                eprintln!("cd: {}: {}", target, e);
                return ExitCode::FAILURE;
            }
            return ExitCode::SUCCESS;
        }
        "help" => {
            print_usage();
            return ExitCode::SUCCESS;
        }
        "exit" => {
            std::process::exit(0);
        }
        _ => {}
    }

    // Execute External or Built-in Applet
    let mut child = Command::new(cmd);
    child.args(args);

    match child.status() {
        Ok(status) => {
            if status.success() {
                ExitCode::SUCCESS
            } else {
                ExitCode::FAILURE
            }
        }
        Err(_) => {
            // Fallback: try executing via ferro-core internal applet
            match cmd.as_str() {
                "ls" => run_ls(args),
                "cat" => run_cat(args),
                "echo" => run_echo(args),
                "pwd" => run_pwd(&[]),
                "uname" => run_uname(args),
                "clear" => run_clear(&[]),
                _ => {
                    eprintln!("sh: {}: command not found", cmd);
                    ExitCode::FAILURE
                }
            }
        }
    }
}

// -------------------------------------------------------------
// Applets
// -------------------------------------------------------------
fn run_ls(args: &[String]) -> ExitCode {
    let target_dir = if args.is_empty() { "." } else { &args[0] };
    match fs::read_dir(target_dir) {
        Ok(entries) => {
            for entry in entries.flatten() {
                let file_name = entry.file_name();
                let file_type = entry.file_type().ok();
                let is_dir = file_type.map_or(false, |t| t.is_dir());
                if is_dir {
                    print!("\x1b[1;34m{}/\x1b[0m  ", file_name.to_string_lossy());
                } else {
                    print!("{}  ", file_name.to_string_lossy());
                }
            }
            println!();
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("ls: cannot access '{}': {}", target_dir, e);
            ExitCode::FAILURE
        }
    }
}

fn run_cat(args: &[String]) -> ExitCode {
    if args.is_empty() {
        let _ = io::copy(&mut io::stdin(), &mut io::stdout());
        return ExitCode::SUCCESS;
    }
    for file in args {
        match fs::read_to_string(file) {
            Ok(content) => print!("{}", content),
            Err(e) => eprintln!("cat: {}: {}", file, e),
        }
    }
    ExitCode::SUCCESS
}

fn run_echo(args: &[String]) -> ExitCode {
    println!("{}", args.join(" "));
    ExitCode::SUCCESS
}

fn run_pwd(_args: &[String]) -> ExitCode {
    match env::current_dir() {
        Ok(path) => {
            println!("{}", path.display());
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("pwd: {}", e);
            ExitCode::FAILURE
        }
    }
}

fn run_uname(args: &[String]) -> ExitCode {
    let all = args.contains(&"-a".to_string());
    if all {
        println!("Linux ferro-os 6.1.0-ferro #1 SMP PREEMPT Rust x86_64 GNU/Linux");
    } else {
        println!("Linux");
    }
    ExitCode::SUCCESS
}

fn run_clear(_args: &[String]) -> ExitCode {
    print!("\x1b[2J\x1b[H");
    let _ = io::stdout().flush();
    ExitCode::SUCCESS
}

fn run_mkdir(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("mkdir: missing operand");
        return ExitCode::FAILURE;
    }
    for dir in args {
        if let Err(e) = fs::create_dir_all(dir) {
            eprintln!("mkdir: cannot create directory '{}': {}", dir, e);
        }
    }
    ExitCode::SUCCESS
}

fn run_rm(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("rm: missing operand");
        return ExitCode::FAILURE;
    }
    for path in args {
        let p = Path::new(path);
        if p.is_dir() {
            let _ = fs::remove_dir_all(p);
        } else {
            let _ = fs::remove_file(p);
        }
    }
    ExitCode::SUCCESS
}

fn run_reboot() -> ExitCode {
    println!("[ferro-core] Rebooting system...");
    #[cfg(target_os = "linux")]
    unsafe {
        libc::sync();
        libc::reboot(libc::LINUX_REBOOT_CMD_RESTART);
    }
    ExitCode::SUCCESS
}

fn run_poweroff() -> ExitCode {
    println!("[ferro-core] Powering off system...");
    #[cfg(target_os = "linux")]
    unsafe {
        libc::sync();
        libc::reboot(libc::LINUX_REBOOT_CMD_POWER_OFF);
    }
    ExitCode::SUCCESS
}
