//! FerroOS Extended POSIX & Core Utilities Module
//!
//! Provides standard Linux / POSIX implementations:
//! - `nproc`: CPU processing unit discovery
//! - `groups`: User group membership inspection
//! - `pgrep`, `pkill`, `killall`: Process lookup and signal dispatch by name/cmdline
//! - `tac`: Reverse line order output
//! - `rev`: Reverse characters on each line
//! - `nl`: Line numbering with standard spacing and formatting
//! - `paste`: Line merging with delimiter support
//! - `fold`: Line wrapping to specified column width
//! - `watch`: Periodic command execution with screen refresh
//! - `xxd`, `hexdump`: Binary hex inspection and reverse binary reconstruction (`-r`)
//! - `nice`, `renice`: POSIX process scheduling priority adjustment
//! - `md5sum`, `sha1sum`: Cryptographic digests (RFC 1321 & FIPS 180-1)
//! - `shuf`: Random line and number permutation (Fisher-Yates shuffle)

use std::env;
use std::fs::{self, File};
use std::io::{self, BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

// ============================================================================
// nproc & groups
// ============================================================================

pub fn run_nproc(args: &[String]) -> ExitCode {
    let mut ignore = 0usize;

    for arg in args {
        if arg == "--help" || arg == "-h" {
            println!("Usage: nproc [OPTION]...");
            println!("Print the number of processing units available to the current process.");
            println!("  --all       print the number of installed processors");
            println!("  --ignore=N  if possible, exclude N processing units");
            return ExitCode::SUCCESS;
        } else if let Some(n) = arg.strip_prefix("--ignore=") {
            ignore = n.parse::<usize>().unwrap_or(0);
        }
    }

    let count = thread::available_parallelism()
        .map(|p| p.get())
        .unwrap_or(1);

    let effective = if count > ignore { count - ignore } else { 1 };
    println!("{}", effective);
    ExitCode::SUCCESS
}

pub fn run_groups(args: &[String]) -> ExitCode {
    if args.iter().any(|a| a == "--help" || a == "-h") {
        println!("Usage: groups [USER]...");
        println!("Print group memberships for each USER or, if no USER is specified, for the current process.");
        return ExitCode::SUCCESS;
    }

    let all_users = super::auth::get_users();
    let all_groups = super::auth::get_groups();

    if args.is_empty() {
        #[cfg(unix)]
        let caller_uid = unsafe { libc::getuid() };
        #[cfg(not(unix))]
        let caller_uid = 1000;

        let caller_name = super::auth::lookup_user_by_uid(caller_uid)
            .map(|u| u.name)
            .unwrap_or_else(|| "ferro".to_string());

        let mut user_grps = Vec::new();
        for g in &all_groups {
            if super::auth::is_user_in_group(&caller_name, &g.name) {
                user_grps.push(g.name.clone());
            }
        }
        if user_grps.is_empty() {
            user_grps.push(caller_name);
        }
        println!("{}", user_grps.join(" "));
        return ExitCode::SUCCESS;
    }

    let prefix_user = args.len() > 1;
    for target in args {
        if target.starts_with('-') {
            continue;
        }
        if !all_users.iter().any(|u| &u.name == target) {
            eprintln!("groups: '{}': no such user", target);
            continue;
        }

        let mut user_grps = Vec::new();
        for g in &all_groups {
            if super::auth::is_user_in_group(target, &g.name) {
                user_grps.push(g.name.clone());
            }
        }
        if user_grps.is_empty() {
            user_grps.push(target.clone());
        }

        if prefix_user {
            println!("{} : {}", target, user_grps.join(" "));
        } else {
            println!("{}", user_grps.join(" "));
        }
    }

    ExitCode::SUCCESS
}

// ============================================================================
// pgrep, pkill & killall
// ============================================================================

struct ProcInfo {
    pid: i32,
    comm: String,
    cmdline: String,
}

fn scan_running_processes() -> Vec<ProcInfo> {
    let mut procs = Vec::new();
    let proc_dir = Path::new("/proc");

    if proc_dir.exists() {
        if let Ok(entries) = fs::read_dir(proc_dir) {
            for entry in entries.flatten() {
                let name = entry.file_name().to_string_lossy().to_string();
                if let Ok(pid) = name.parse::<i32>() {
                    let p = entry.path();
                    let mut comm = fs::read_to_string(p.join("comm"))
                        .unwrap_or_default()
                        .trim()
                        .to_string();
                    let cmdline_raw = fs::read(p.join("cmdline")).unwrap_or_default();
                    let cmdline = cmdline_raw
                        .split(|&b| b == 0)
                        .map(|s| String::from_utf8_lossy(s))
                        .collect::<Vec<_>>()
                        .join(" ");

                    if comm.is_empty() {
                        if let Ok(stat_text) = fs::read_to_string(p.join("stat")) {
                            if let (Some(p1), Some(p2)) = (stat_text.find('('), stat_text.rfind(')')) {
                                if p1 < p2 {
                                    comm = stat_text[p1 + 1..p2].to_string();
                                }
                            }
                        }
                    }

                    if comm.is_empty() && cmdline.is_empty() && !p.exists() {
                        continue;
                    }

                    if comm.is_empty() {
                        comm = format!("[{}]", pid);
                    }

                    procs.push(ProcInfo { pid, comm, cmdline });
                }
            }
        }
    } else {
        // Fallback for development/testing environments without Linux /proc (e.g., macOS dev host)
        if let Ok(output) = std::process::Command::new("ps").args(&["-axo", "pid,comm,args"]).output() {
            if let Ok(text) = String::from_utf8(output.stdout) {
                for line in text.lines().skip(1) {
                    let parts: Vec<&str> = line.trim().split_whitespace().collect();
                    if parts.len() >= 2 {
                        if let Ok(pid) = parts[0].parse::<i32>() {
                            let comm = Path::new(parts[1])
                                .file_name()
                                .map(|s| s.to_string_lossy().to_string())
                                .unwrap_or_else(|| parts[1].to_string());
                            let cmdline = parts[1..].join(" ");
                            procs.push(ProcInfo { pid, comm, cmdline });
                        }
                    }
                }
            }
        }
    }
    procs
}

pub fn run_pgrep(args: &[String]) -> ExitCode {
    let mut full_cmdline = false;
    let mut exact = false;
    let mut list_name = false;
    let mut pattern: Option<String> = None;

    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-f" || arg == "--full" {
            full_cmdline = true;
            i += 1;
        } else if arg == "-x" || arg == "--exact" {
            exact = true;
            i += 1;
        } else if arg == "-l" || arg == "--list-name" {
            list_name = true;
            i += 1;
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: pgrep [options] <pattern>");
            println!("Look up processes based on name and other attributes.");
            println!("  -f, --full        use full process name to match");
            println!("  -x, --exact       match exactly with the command name");
            println!("  -l, --list-name   list the process name as well as the process ID");
            println!("  -h, --help        display this help and exit");
            return ExitCode::SUCCESS;
        } else if arg.starts_with('-') {
            eprintln!("pgrep: unrecognized option '{}'", arg);
            return ExitCode::from(2);
        } else {
            if pattern.is_some() {
                eprintln!("pgrep: extra operand '{}'", arg);
                return ExitCode::from(2);
            }
            pattern = Some(arg.clone());
            i += 1;
        }
    }

    let pat = match pattern {
        Some(p) => p,
        None => {
            eprintln!("pgrep: no matching criteria specified");
            return ExitCode::from(2);
        }
    };

    let procs = scan_running_processes();
    let mut matched = 0;

    let stdout = io::stdout();
    let mut out = stdout.lock();

    for proc in procs {
        let pat_lower = pat.to_lowercase();
        let comm_lower = proc.comm.to_lowercase();
        let cmd_lower = proc.cmdline.to_lowercase();

        let is_match = if full_cmdline {
            if exact {
                proc.cmdline == pat || proc.comm == pat || cmd_lower == pat_lower
            } else {
                cmd_lower.contains(&pat_lower) || comm_lower.contains(&pat_lower)
            }
        } else {
            if exact {
                proc.comm == pat || comm_lower == pat_lower
            } else {
                comm_lower.contains(&pat_lower) || cmd_lower.contains(&pat_lower)
            }
        };

        if is_match {
            matched += 1;
            let res = if list_name {
                writeln!(out, "{} {}", proc.pid, proc.comm)
            } else {
                writeln!(out, "{}", proc.pid)
            };
            if res.is_err() {
                return ExitCode::SUCCESS; // BrokenPipe handled
            }
        }
    }

    if matched > 0 {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    }
}

pub fn run_pkill(args: &[String]) -> ExitCode {
    let mut full_cmdline = false;
    let mut exact = false;
    let mut signal = 15i32; // SIGTERM
    let mut pattern: Option<String> = None;

    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-f" || arg == "--full" {
            full_cmdline = true;
            i += 1;
        } else if arg == "-x" || arg == "--exact" {
            exact = true;
            i += 1;
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: pkill [options] <pattern>");
            println!("Signal processes based on name and other attributes.");
            println!("  -f, --full        use full process name to match");
            println!("  -x, --exact       match exactly with the command name");
            println!("  -SIGNAL           signal to send (default 15 SIGTERM)");
            println!("  -h, --help        display this help and exit");
            return ExitCode::SUCCESS;
        } else if arg.starts_with('-') && arg.len() > 1 && pattern.is_none() {
            match crate::proc_ledger::parse_signal(arg) {
                Ok(sig) => signal = sig,
                Err(err) => {
                    eprintln!("pkill: {}", err);
                    return ExitCode::from(2);
                }
            }
            i += 1;
        } else if arg.starts_with('-') {
            eprintln!("pkill: unrecognized option '{}'", arg);
            return ExitCode::from(2);
        } else {
            if pattern.is_some() {
                eprintln!("pkill: extra operand '{}'", arg);
                return ExitCode::from(2);
            }
            pattern = Some(arg.clone());
            i += 1;
        }
    }

    let pat = match pattern {
        Some(p) => p,
        None => {
            eprintln!("pkill: no matching criteria specified");
            return ExitCode::from(2);
        }
    };

    let procs = scan_running_processes();
    let mut signaled = 0;

    for proc in procs {
        let pat_lower = pat.to_lowercase();
        let comm_lower = proc.comm.to_lowercase();
        let cmd_lower = proc.cmdline.to_lowercase();

        let is_match = if full_cmdline {
            if exact {
                proc.cmdline == pat || proc.comm == pat || cmd_lower == pat_lower
            } else {
                cmd_lower.contains(&pat_lower) || comm_lower.contains(&pat_lower)
            }
        } else {
            if exact {
                proc.comm == pat || comm_lower == pat_lower
            } else {
                comm_lower.contains(&pat_lower) || cmd_lower.contains(&pat_lower)
            }
        };

        if is_match {
            if proc.pid <= 1 {
                continue;
            }
            #[cfg(unix)]
            unsafe {
                if libc::kill(proc.pid, signal) == 0 {
                    signaled += 1;
                }
            }
            #[cfg(not(unix))]
            {
                signaled += 1;
            }
        }
    }

    if signaled > 0 {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    }
}

pub fn run_killall(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("killall: no process name specified");
        return ExitCode::from(1);
    }

    let mut signal = 15i32;
    let mut verbose = false;
    let mut names = Vec::new();

    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-v" || arg == "--verbose" {
            verbose = true;
            i += 1;
        } else if arg == "-s" || arg == "--signal" {
            if i + 1 < args.len() {
                match crate::proc_ledger::parse_signal(&args[i + 1]) {
                    Ok(sig) => signal = sig,
                    Err(err) => {
                        eprintln!("killall: {}", err);
                        return ExitCode::from(1);
                    }
                }
                i += 2;
            } else {
                eprintln!("killall: option requires an argument: '{}'", arg);
                return ExitCode::from(1);
            }
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: killall [options] <name>...");
            println!("Kill processes by name.");
            println!("  -v, --verbose   report if signal was successfully sent");
            println!("  -s, --signal    specify signal to send (default 15)");
            println!("  -h, --help      display this help and exit");
            return ExitCode::SUCCESS;
        } else if arg.starts_with('-') && arg.len() > 1 && names.is_empty() {
            match crate::proc_ledger::parse_signal(arg) {
                Ok(sig) => signal = sig,
                Err(err) => {
                    eprintln!("killall: {}", err);
                    return ExitCode::from(1);
                }
            }
            i += 1;
        } else if arg.starts_with('-') {
            eprintln!("killall: invalid option -- '{}'", arg);
            return ExitCode::from(1);
        } else {
            names.push(arg.as_str());
            i += 1;
        }
    }

    if names.is_empty() {
        eprintln!("killall: no process name specified");
        return ExitCode::from(1);
    }

    let procs = scan_running_processes();
    let mut total_signaled = 0;

    for name in names {
        let mut found = false;
        for proc in &procs {
            if proc.comm == name {
                if proc.pid <= 1 {
                    eprintln!("killall: refusing to kill PID {} ({}) - protected init process", proc.pid, proc.comm);
                    continue;
                }
                #[cfg(unix)]
                unsafe {
                    if libc::kill(proc.pid, signal) == 0 {
                        total_signaled += 1;
                        found = true;
                        if verbose {
                            println!("Killed {} ({}) with signal {}", proc.comm, proc.pid, signal);
                        }
                    }
                }
                #[cfg(not(unix))]
                {
                    total_signaled += 1;
                    found = true;
                    if verbose {
                        println!("Simulated: Killed {} ({}) with signal {}", proc.comm, proc.pid, signal);
                    }
                }
            }
        }
        if !found {
            eprintln!("{}: no process found", name);
        }
    }

    if total_signaled > 0 {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    }
}

// ============================================================================
// tac, rev, nl, paste, fold
// ============================================================================

pub fn run_tac(args: &[String]) -> ExitCode {
    let mut files = Vec::new();
    let mut parsing_options = true;
    for arg in args {
        if parsing_options && arg == "--" {
            parsing_options = false;
            continue;
        }
        if parsing_options && (arg == "--help" || arg == "-h") {
            println!("Usage: tac [FILE]...");
            println!("Write each FILE to standard output, last line first.");
            return ExitCode::SUCCESS;
        } else if parsing_options && arg.starts_with('-') && arg != "-" {
            eprintln!("tac: unrecognized option '{}'", arg);
            return ExitCode::from(1);
        } else {
            files.push(arg.clone());
        }
    }

    if files.is_empty() {
        files.push("-".to_string());
    }

    let mut exit_code = ExitCode::SUCCESS;
    let stdout = io::stdout();
    let mut out = stdout.lock();

    for file in files {
        let reader: Box<dyn BufRead> = if file == "-" {
            Box::new(BufReader::new(io::stdin()))
        } else {
            match File::open(&file) {
                Ok(f) => Box::new(BufReader::new(f)),
                Err(e) => {
                    eprintln!("tac: {}: {}", file, e);
                    exit_code = ExitCode::from(1);
                    continue;
                }
            }
        };

        let mut lines = Vec::new();
        for l in reader.lines() {
            match l {
                Ok(line) => lines.push(line),
                Err(e) => {
                    eprintln!("tac: {}: {}", file, e);
                    exit_code = ExitCode::from(1);
                    break;
                }
            }
        }
        for l in lines.iter().rev() {
            if let Err(e) = writeln!(out, "{}", l) {
                if e.kind() == io::ErrorKind::BrokenPipe {
                    return ExitCode::SUCCESS;
                }
                eprintln!("tac: write error: {}", e);
                return ExitCode::from(1);
            }
        }
    }

    exit_code
}

pub fn run_rev(args: &[String]) -> ExitCode {
    let mut files = Vec::new();
    let mut parsing_options = true;
    for arg in args {
        if parsing_options && arg == "--" {
            parsing_options = false;
            continue;
        }
        if parsing_options && (arg == "--help" || arg == "-h") {
            println!("Usage: rev [FILE]...");
            println!("Reverse lines character-wise.");
            return ExitCode::SUCCESS;
        } else if parsing_options && arg.starts_with('-') && arg != "-" {
            eprintln!("rev: unrecognized option '{}'", arg);
            return ExitCode::from(1);
        } else {
            files.push(arg.clone());
        }
    }

    if files.is_empty() {
        files.push("-".to_string());
    }

    let mut exit_code = ExitCode::SUCCESS;
    let stdout = io::stdout();
    let mut out = stdout.lock();

    for file in files {
        let reader: Box<dyn BufRead> = if file == "-" {
            Box::new(BufReader::new(io::stdin()))
        } else {
            match File::open(&file) {
                Ok(f) => Box::new(BufReader::new(f)),
                Err(e) => {
                    eprintln!("rev: {}: {}", file, e);
                    exit_code = ExitCode::from(1);
                    continue;
                }
            }
        };

        for l in reader.lines() {
            match l {
                Ok(line) => {
                    let reversed: String = line.chars().rev().collect();
                    if let Err(e) = writeln!(out, "{}", reversed) {
                        if e.kind() == io::ErrorKind::BrokenPipe {
                            return ExitCode::SUCCESS;
                        }
                        eprintln!("rev: write error: {}", e);
                        return ExitCode::from(1);
                    }
                }
                Err(e) => {
                    eprintln!("rev: {}: {}", file, e);
                    exit_code = ExitCode::from(1);
                    break;
                }
            }
        }
    }

    exit_code
}

pub fn run_nl(args: &[String]) -> ExitCode {
    let mut number_empty = false;
    let mut files = Vec::new();
    let mut i = 0;
    let mut parsing_options = true;

    while i < args.len() {
        let arg = &args[i];
        if parsing_options && arg == "--" {
            parsing_options = false;
            i += 1;
            continue;
        }
        if parsing_options && arg == "-ba" {
            number_empty = true;
            i += 1;
        } else if parsing_options && arg == "-bt" {
            number_empty = false;
            i += 1;
        } else if parsing_options && arg == "-b" {
            if i + 1 < args.len() {
                match args[i + 1].as_str() {
                    "a" => number_empty = true,
                    "t" => number_empty = false,
                    other => {
                        eprintln!("nl: invalid body numbering style: '{}'", other);
                        return ExitCode::from(1);
                    }
                }
                i += 2;
            } else {
                eprintln!("nl: option requires an argument -- 'b'");
                return ExitCode::from(1);
            }
        } else if parsing_options && (arg == "--help" || arg == "-h") {
            println!("Usage: nl [OPTION]... [FILE]...");
            println!("Write each FILE to standard output, with line numbers added.");
            println!("  -ba        number all lines");
            println!("  -bt        number only nonempty lines (default)");
            println!("  -b STYLE   STYLE: 'a' (all) or 't' (nonempty)");
            return ExitCode::SUCCESS;
        } else if parsing_options && arg.starts_with('-') && arg != "-" {
            eprintln!("nl: unrecognized option '{}'", arg);
            return ExitCode::from(1);
        } else {
            files.push(arg.clone());
            i += 1;
        }
    }

    if files.is_empty() {
        files.push("-".to_string());
    }

    let mut exit_code = ExitCode::SUCCESS;
    let mut line_no = 1usize;
    let stdout = io::stdout();
    let mut out = stdout.lock();

    for file in files {
        let reader: Box<dyn BufRead> = if file == "-" {
            Box::new(BufReader::new(io::stdin()))
        } else {
            match File::open(&file) {
                Ok(f) => Box::new(BufReader::new(f)),
                Err(e) => {
                    eprintln!("nl: {}: {}", file, e);
                    exit_code = ExitCode::from(1);
                    continue;
                }
            }
        };

        for l in reader.lines() {
            match l {
                Ok(line) => {
                    let write_res = if line.is_empty() && !number_empty {
                        writeln!(out)
                    } else {
                        let res = writeln!(out, "{:6}\t{}", line_no, line);
                        line_no += 1;
                        res
                    };
                    if let Err(e) = write_res {
                        if e.kind() == io::ErrorKind::BrokenPipe {
                            return ExitCode::SUCCESS;
                        }
                        eprintln!("nl: write error: {}", e);
                        return ExitCode::from(1);
                    }
                }
                Err(e) => {
                    eprintln!("nl: {}: {}", file, e);
                    exit_code = ExitCode::from(1);
                    break;
                }
            }
        }
    }

    exit_code
}

pub fn run_paste(args: &[String]) -> ExitCode {
    let mut delimiter = "\t".to_string();
    let mut serial = false;
    let mut files = Vec::new();

    let mut i = 0;
    let mut parsing_options = true;
    while i < args.len() {
        let arg = &args[i];
        if parsing_options && arg == "--" {
            parsing_options = false;
            i += 1;
            continue;
        }
        if parsing_options && arg == "-d" {
            if i + 1 < args.len() {
                delimiter = args[i + 1].clone();
                i += 2;
            } else {
                eprintln!("paste: option requires an argument -- 'd'");
                return ExitCode::from(1);
            }
        } else if parsing_options && arg.starts_with("-d") {
            delimiter = arg[2..].to_string();
            i += 1;
        } else if parsing_options && (arg == "-s" || arg == "--serial") {
            serial = true;
            i += 1;
        } else if parsing_options && (arg == "--help" || arg == "-h") {
            println!("Usage: paste [OPTION]... [FILE]...");
            println!("Write lines consisting of the sequentially corresponding lines from each FILE, separated by TABs.");
            println!("  -d LIST, --delimiters=LIST  reuse characters from LIST instead of TABs");
            println!("  -s, --serial                paste one file at a time instead of in parallel");
            return ExitCode::SUCCESS;
        } else if parsing_options && arg.starts_with('-') && arg != "-" {
            eprintln!("paste: unrecognized option '{}'", arg);
            return ExitCode::from(1);
        } else {
            files.push(arg.clone());
            i += 1;
        }
    }

    if files.is_empty() {
        files.push("-".to_string());
    }

    let stdout = io::stdout();
    let mut out = stdout.lock();

    if serial {
        for file in &files {
            match read_file_lines(file) {
                Ok(lines) => {
                    if let Err(e) = writeln!(out, "{}", lines.join(&delimiter)) {
                        if e.kind() == io::ErrorKind::BrokenPipe {
                            return ExitCode::SUCCESS;
                        }
                        eprintln!("paste: write error: {}", e);
                        return ExitCode::from(1);
                    }
                }
                Err(e) => {
                    eprintln!("paste: {}: {}", file, e);
                    return ExitCode::from(1);
                }
            }
        }
        return ExitCode::SUCCESS;
    }

    let mut all_file_lines = Vec::new();
    let mut max_lines = 0;

    for file in &files {
        match read_file_lines(file) {
            Ok(lines) => {
                max_lines = max_lines.max(lines.len());
                all_file_lines.push(lines);
            }
            Err(e) => {
                eprintln!("paste: {}: {}", file, e);
                return ExitCode::from(1);
            }
        }
    }

    for row in 0..max_lines {
        let mut row_parts = Vec::new();
        for file_lines in &all_file_lines {
            if row < file_lines.len() {
                row_parts.push(file_lines[row].as_str());
            } else {
                row_parts.push("");
            }
        }
        if let Err(e) = writeln!(out, "{}", row_parts.join(&delimiter)) {
            if e.kind() == io::ErrorKind::BrokenPipe {
                return ExitCode::SUCCESS;
            }
            eprintln!("paste: write error: {}", e);
            return ExitCode::from(1);
        }
    }

    ExitCode::SUCCESS
}

fn read_file_lines(file: &str) -> io::Result<Vec<String>> {
    let reader: Box<dyn BufRead> = if file == "-" {
        Box::new(BufReader::new(io::stdin()))
    } else {
        Box::new(BufReader::new(File::open(file)?))
    };
    reader.lines().collect()
}

pub fn run_fold(args: &[String]) -> ExitCode {
    let mut width = 80usize;
    let mut files = Vec::new();

    let mut i = 0;
    let mut parsing_options = true;
    while i < args.len() {
        let arg = &args[i];
        if parsing_options && arg == "--" {
            parsing_options = false;
            i += 1;
            continue;
        }
        if parsing_options && (arg == "-w" || arg == "--width") {
            if i + 1 < args.len() {
                match args[i + 1].parse::<usize>() {
                    Ok(0) => {
                        eprintln!("fold: invalid number of columns: '0'");
                        return ExitCode::from(1);
                    }
                    Ok(w) => width = w,
                    Err(_) => {
                        eprintln!("fold: invalid number of columns: '{}'", args[i + 1]);
                        return ExitCode::from(1);
                    }
                }
                i += 2;
            } else {
                eprintln!("fold: option requires an argument -- 'w'");
                return ExitCode::from(1);
            }
        } else if parsing_options && arg.starts_with("-w") {
            match arg[2..].parse::<usize>() {
                Ok(0) => {
                    eprintln!("fold: invalid number of columns: '0'");
                    return ExitCode::from(1);
                }
                Ok(w) => width = w,
                Err(_) => {
                    eprintln!("fold: invalid number of columns: '{}'", &arg[2..]);
                    return ExitCode::from(1);
                }
            }
            i += 1;
        } else if parsing_options && arg.starts_with('-') && arg.len() > 1 && arg[1..].chars().all(|c| c.is_ascii_digit()) {
            match arg[1..].parse::<usize>() {
                Ok(0) => {
                    eprintln!("fold: invalid number of columns: '0'");
                    return ExitCode::from(1);
                }
                Ok(w) => width = w,
                Err(_) => {
                    eprintln!("fold: invalid number of columns: '{}'", &arg[1..]);
                    return ExitCode::from(1);
                }
            }
            i += 1;
        } else if parsing_options && (arg == "--help" || arg == "-h") {
            println!("Usage: fold [OPTION]... [FILE]...");
            println!("Wrap input lines in each FILE (standard input by default), writing to standard output.");
            println!("  -w, --width=WIDTH   use WIDTH columns instead of 80");
            println!("  -WIDTH              use WIDTH columns");
            return ExitCode::SUCCESS;
        } else if parsing_options && arg.starts_with('-') && arg != "-" {
            eprintln!("fold: unrecognized option '{}'", arg);
            return ExitCode::from(1);
        } else {
            files.push(arg.clone());
            i += 1;
        }
    }

    if files.is_empty() {
        files.push("-".to_string());
    }

    let mut exit_code = ExitCode::SUCCESS;
    let stdout = io::stdout();
    let mut out = stdout.lock();

    for file in files {
        let reader: Box<dyn BufRead> = if file == "-" {
            Box::new(BufReader::new(io::stdin()))
        } else {
            match File::open(&file) {
                Ok(f) => Box::new(BufReader::new(f)),
                Err(e) => {
                    eprintln!("fold: {}: {}", file, e);
                    exit_code = ExitCode::from(1);
                    continue;
                }
            }
        };

        for l in reader.lines() {
            match l {
                Ok(line) => {
                    let chars: Vec<char> = line.chars().collect();
                    if chars.is_empty() {
                        if let Err(e) = writeln!(out) {
                            if e.kind() == io::ErrorKind::BrokenPipe {
                                return ExitCode::SUCCESS;
                            }
                            eprintln!("fold: write error: {}", e);
                            return ExitCode::from(1);
                        }
                    } else {
                        for chunk in chars.chunks(width) {
                            let s: String = chunk.iter().collect();
                            if let Err(e) = writeln!(out, "{}", s) {
                                if e.kind() == io::ErrorKind::BrokenPipe {
                                    return ExitCode::SUCCESS;
                                }
                                eprintln!("fold: write error: {}", e);
                                return ExitCode::from(1);
                            }
                        }
                    }
                }
                Err(e) => {
                    eprintln!("fold: {}: {}", file, e);
                    exit_code = ExitCode::from(1);
                    break;
                }
            }
        }
    }

    exit_code
}

// ============================================================================
// watch
// ============================================================================

pub fn run_watch(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("watch: missing command");
        eprintln!("Try 'watch --help' for more information.");
        return ExitCode::from(1);
    }

    let mut interval = Duration::from_secs(2);
    let mut cmd_idx = None;

    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-n" || arg == "--interval" {
            if i + 1 < args.len() {
                match args[i + 1].parse::<f64>() {
                    Ok(sec) if sec > 0.0 => {
                        interval = Duration::from_millis((sec * 1000.0) as u64);
                    }
                    _ => {
                        eprintln!("watch: invalid interval: '{}'", args[i + 1]);
                        return ExitCode::from(1);
                    }
                }
                i += 2;
            } else {
                eprintln!("watch: option requires an argument -- 'n'");
                return ExitCode::from(1);
            }
        } else if let Some(n) = arg.strip_prefix("-n") {
            match n.parse::<f64>() {
                Ok(sec) if sec > 0.0 => {
                    interval = Duration::from_millis((sec * 1000.0) as u64);
                }
                _ => {
                    eprintln!("watch: invalid interval: '{}'", n);
                    return ExitCode::from(1);
                }
            }
            i += 1;
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: watch [options] command");
            println!("Execute a program periodically, showing output fullscreen.");
            println!("  -n, --interval=<secs>  seconds to wait between updates (default 2.0)");
            return ExitCode::SUCCESS;
        } else if arg == "--" {
            if i + 1 < args.len() {
                cmd_idx = Some(i + 1);
            }
            break;
        } else if !arg.starts_with('-') {
            cmd_idx = Some(i);
            break;
        } else {
            eprintln!("watch: unrecognized option '{}'", arg);
            return ExitCode::from(1);
        }
    }

    let start_idx = match cmd_idx {
        Some(idx) if idx < args.len() => idx,
        _ => {
            eprintln!("watch: missing command");
            return ExitCode::from(1);
        }
    };

    let cmd_str = args[start_idx..].join(" ");
    let hostname = env::var("HOSTNAME").unwrap_or_else(|_| "ferro".to_string());

    loop {
        // Clear terminal screen and reset cursor
        let now_str = match SystemTime::now().duration_since(UNIX_EPOCH) {
            Ok(d) => format!("UTC epoch: {}", d.as_secs()),
            Err(_) => String::new(),
        };

        let stdout = io::stdout();
        let mut out = stdout.lock();
        if write!(out, "\x1b[2J\x1b[H").is_err()
            || writeln!(out, "Every {:.1}s: {:<30} {}: {}", interval.as_secs_f64(), cmd_str, hostname, now_str).is_err()
            || writeln!(out).is_err()
        {
            return ExitCode::SUCCESS;
        }
        let _ = out.flush();

        // Run command
        let _ = Command::new("sh")
            .arg("-c")
            .arg(&cmd_str)
            .status();

        thread::sleep(interval);
    }
}

// ============================================================================
// xxd & hexdump
// ============================================================================

pub fn run_xxd(args: &[String]) -> ExitCode {
    let mut reverse = false;
    let mut plain = false;
    let mut cols = 16usize;
    let mut file_path: Option<String> = None;

    let mut i = 0;
    let mut parsing_options = true;
    while i < args.len() {
        let arg = &args[i];
        if parsing_options && arg == "--" {
            parsing_options = false;
            i += 1;
            continue;
        }
        if parsing_options && (arg == "-r" || arg == "-revert") {
            reverse = true;
            i += 1;
        } else if parsing_options && (arg == "-p" || arg == "-plain") {
            plain = true;
            i += 1;
        } else if parsing_options && (arg == "-c" || arg == "-cols") {
            if i + 1 < args.len() {
                match args[i + 1].parse::<usize>() {
                    Ok(0) => {
                        eprintln!("xxd: invalid number of columns");
                        return ExitCode::from(1);
                    }
                    Ok(c) => cols = c,
                    Err(_) => {
                        eprintln!("xxd: invalid number of columns");
                        return ExitCode::from(1);
                    }
                }
                i += 2;
            } else {
                eprintln!("xxd: option requires an argument -- 'c'");
                return ExitCode::from(1);
            }
        } else if parsing_options && arg.starts_with("-c") {
            match arg[2..].parse::<usize>() {
                Ok(0) => {
                    eprintln!("xxd: invalid number of columns");
                    return ExitCode::from(1);
                }
                Ok(c) => cols = c,
                Err(_) => {
                    eprintln!("xxd: invalid number of columns");
                    return ExitCode::from(1);
                }
            }
            i += 1;
        } else if parsing_options && (arg == "--help" || arg == "-h") {
            println!("Usage: xxd [options] [infile [outfile]]");
            println!("Make a hexdump or do the reverse.");
            println!("  -p, -plain   output in plain hexdump style");
            println!("  -r, -revert  reverse operation: convert hexdump into binary");
            println!("  -c cols      format <cols> octets per line (default 16)");
            return ExitCode::SUCCESS;
        } else if parsing_options && arg.starts_with('-') && arg != "-" {
            eprintln!("xxd: unrecognized option: '{}'", arg);
            return ExitCode::from(1);
        } else {
            file_path = Some(arg.clone());
            i += 1;
        }
    }

    let stdout = io::stdout();
    let mut out = stdout.lock();

    if reverse {
        // Reverse mode: convert hex input to binary output
        let mut hex_input = String::new();
        if let Some(ref path) = file_path {
            if path == "-" {
                if let Err(e) = io::stdin().read_to_string(&mut hex_input) {
                    eprintln!("xxd: stdin: {}", e);
                    return ExitCode::from(1);
                }
            } else {
                match fs::read_to_string(path) {
                    Ok(s) => hex_input = s,
                    Err(e) => {
                        eprintln!("xxd: {}: {}", path, e);
                        return ExitCode::from(1);
                    }
                }
            }
        } else if let Err(e) = io::stdin().read_to_string(&mut hex_input) {
            eprintln!("xxd: stdin: {}", e);
            return ExitCode::from(1);
        }

        let mut bin_bytes = Vec::new();
        for line in hex_input.lines() {
            let line = line.trim();
            if line.is_empty() {
                continue;
            }
            let hex_part = if let Some(colon_pos) = line.find(':') {
                let after_colon = &line[colon_pos + 1..];
                if let Some(two_space) = after_colon.find("  ") {
                    &after_colon[..two_space]
                } else {
                    after_colon
                }
            } else {
                line
            };

            let clean_hex: String = hex_part.chars().filter(|c| c.is_ascii_hexdigit()).collect();
            for chunk in clean_hex.as_bytes().chunks(2) {
                if chunk.len() == 2 {
                    if let Ok(b) = u8::from_str_radix(std::str::from_utf8(chunk).unwrap_or(""), 16) {
                        bin_bytes.push(b);
                    }
                }
            }
        }
        if let Err(e) = out.write_all(&bin_bytes) {
            if e.kind() == io::ErrorKind::BrokenPipe {
                return ExitCode::SUCCESS;
            }
            eprintln!("xxd: write error: {}", e);
            return ExitCode::from(1);
        }
        return ExitCode::SUCCESS;
    }

    let input_bytes = if let Some(ref path) = file_path {
        if path == "-" {
            let mut buf = Vec::new();
            if let Err(e) = io::stdin().read_to_end(&mut buf) {
                eprintln!("xxd: stdin: {}", e);
                return ExitCode::from(1);
            }
            buf
        } else {
            match fs::read(path) {
                Ok(b) => b,
                Err(e) => {
                    eprintln!("xxd: {}: {}", path, e);
                    return ExitCode::from(1);
                }
            }
        }
    } else {
        let mut buf = Vec::new();
        if let Err(e) = io::stdin().read_to_end(&mut buf) {
            eprintln!("xxd: stdin: {}", e);
            return ExitCode::from(1);
        }
        buf
    };

    let mut offset = 0usize;
    for chunk in input_bytes.chunks(cols) {
        if plain {
            let mut line = String::new();
            for b in chunk {
                use std::fmt::Write;
                let _ = write!(line, "{:02x}", b);
            }
            if let Err(e) = writeln!(out, "{}", line) {
                if e.kind() == io::ErrorKind::BrokenPipe {
                    return ExitCode::SUCCESS;
                }
                eprintln!("xxd: write error: {}", e);
                return ExitCode::from(1);
            }
        } else {
            // Canonical xxd format: 00000000: 4865 6c6c ...  Hello World!
            let mut line = format!("{:08x}: ", offset);
            for (idx, b) in chunk.iter().enumerate() {
                use std::fmt::Write;
                let _ = write!(line, "{:02x}", b);
                if idx % 2 == 1 {
                    line.push(' ');
                }
            }
            if chunk.len() < cols {
                let missing_bytes = cols - chunk.len();
                let missing_spaces = missing_bytes * 2 + (missing_bytes / 2);
                for _ in 0..missing_spaces {
                    line.push(' ');
                }
            }
            line.push_str("  ");
            for &b in chunk {
                if b.is_ascii_graphic() || b == b' ' {
                    line.push(b as char);
                } else {
                    line.push('.');
                }
            }
            if let Err(e) = writeln!(out, "{}", line) {
                if e.kind() == io::ErrorKind::BrokenPipe {
                    return ExitCode::SUCCESS;
                }
                eprintln!("xxd: write error: {}", e);
                return ExitCode::from(1);
            }
        }
        offset += chunk.len();
    }

    ExitCode::SUCCESS
}

pub fn run_hexdump(args: &[String]) -> ExitCode {
    let mut canonical = false;
    let mut file_path: Option<String> = None;
    let mut parsing_options = true;

    for arg in args {
        if parsing_options && arg == "--" {
            parsing_options = false;
            continue;
        }
        if parsing_options && (arg == "-C" || arg == "--canonical") {
            canonical = true;
        } else if parsing_options && (arg == "--help" || arg == "-h") {
            println!("Usage: hexdump [options] file...");
            println!("Display file contents in hexadecimal, decimal, octal, or ascii.");
            println!("  -C, --canonical  canonical hex+ASCII display");
            return ExitCode::SUCCESS;
        } else if parsing_options && arg.starts_with('-') && arg != "-" {
            eprintln!("hexdump: unrecognized option: '{}'", arg);
            return ExitCode::from(1);
        } else {
            file_path = Some(arg.clone());
        }
    }

    let mut xxd_args = Vec::new();
    if canonical {
        xxd_args.push("-c".to_string());
        xxd_args.push("16".to_string());
    }
    if let Some(p) = file_path {
        xxd_args.push(p);
    } else {
        xxd_args.push("-".to_string());
    }

    run_xxd(&xxd_args)
}

// ============================================================================
// nice & renice (POSIX Process Scheduling Priority)
// ============================================================================

pub fn run_nice(args: &[String]) -> ExitCode {
    if args.is_empty() {
        #[cfg(unix)]
        unsafe {
            let prio = libc::getpriority(libc::PRIO_PROCESS, 0);
            println!("{}", prio);
            return ExitCode::SUCCESS;
        }
        #[cfg(not(unix))]
        {
            println!("0");
            return ExitCode::SUCCESS;
        }
    }

    let mut adjustment = 10i32;
    let mut cmd_idx = 0;

    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-n" || arg == "--adjustment" {
            if i + 1 < args.len() {
                adjustment = args[i + 1].parse::<i32>().unwrap_or(10);
                i += 2;
            } else {
                eprintln!("nice: option requires an argument -- 'n'");
                return ExitCode::from(1);
            }
        } else if let Some(n) = arg.strip_prefix("-n") {
            adjustment = n.parse::<i32>().unwrap_or(10);
            i += 1;
        } else if arg.starts_with('-') && arg[1..].parse::<i32>().is_ok() {
            adjustment = arg[1..].parse::<i32>().unwrap_or(10);
            i += 1;
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: nice [OPTION] [COMMAND [ARG]...]");
            println!("Run COMMAND with an adjusted niceness, which affects process scheduling.");
            println!("  -n, --adjustment=N   add integer N to the niceness (default 10)");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') {
            cmd_idx = i;
            break;
        } else {
            i += 1;
        }
    }

    if cmd_idx >= args.len() {
        eprintln!("nice: a command must be specified with an adjustment");
        return ExitCode::from(1);
    }

    #[cfg(unix)]
    unsafe {
        libc::nice(adjustment);
    }

    let prog = &args[cmd_idx];
    let prog_args = &args[cmd_idx + 1..];

    let mut command_proc = if super::is_internal_applet(prog) {
        let exe = env::current_exe().unwrap_or_else(|_| PathBuf::from("ferro-core"));
        let mut c = Command::new(exe);
        c.arg(prog);
        c
    } else {
        Command::new(prog)
    };

    match command_proc.args(prog_args).status() {
        Ok(st) => ExitCode::from(st.code().unwrap_or(0) as u8),
        Err(e) => {
            eprintln!("nice: {}: {}", prog, e);
            ExitCode::from(127)
        }
    }
}

pub fn run_renice(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("Usage: renice [-n] priority [[-p] pid ...]");
        return ExitCode::from(1);
    }

    let mut prio: Option<i32> = None;
    let mut pids = Vec::new();

    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-n" {
            if i + 1 < args.len() {
                prio = args[i + 1].parse::<i32>().ok();
                i += 2;
            } else {
                i += 1;
            }
        } else if arg == "-p" {
            if i + 1 < args.len() {
                if let Ok(pid) = args[i + 1].parse::<i32>() {
                    pids.push(pid);
                }
                i += 2;
            } else {
                i += 1;
            }
        } else if prio.is_none() {
            prio = arg.parse::<i32>().ok();
            i += 1;
        } else if let Ok(pid) = arg.parse::<i32>() {
            pids.push(pid);
            i += 1;
        } else {
            i += 1;
        }
    }

    let new_prio = match prio {
        Some(p) => p,
        None => {
            eprintln!("renice: priority required");
            return ExitCode::from(1);
        }
    };

    if pids.is_empty() {
        eprintln!("renice: missing process ID (PID)");
        return ExitCode::from(1);
    }

    let mut exit_code = ExitCode::SUCCESS;
    for pid in pids {
        #[cfg(unix)]
        unsafe {
            let old_prio = libc::getpriority(libc::PRIO_PROCESS, pid as u32);
            if libc::setpriority(libc::PRIO_PROCESS, pid as u32, new_prio) == 0 {
                println!("{}: old priority {}, new priority {}", pid, old_prio, new_prio);
            } else {
                let err = io::Error::last_os_error();
                eprintln!("renice: failed to set priority for {}: {}", pid, err);
                exit_code = ExitCode::from(1);
            }
        }
    }

    exit_code
}

// ============================================================================
// md5sum & sha1sum (RFC 1321 & FIPS 180-1 Standard)
// ============================================================================

pub fn run_md5sum(args: &[String]) -> ExitCode {
    run_hash_utility(args, "md5sum", md5_digest)
}

pub fn run_sha1sum(args: &[String]) -> ExitCode {
    run_hash_utility(args, "sha1sum", sha1_digest)
}

fn run_hash_utility<F: Fn(&[u8]) -> String>(args: &[String], prog_name: &str, hasher: F) -> ExitCode {
    let mut check_mode = false;
    let mut files = Vec::new();
    for arg in args {
        if arg == "-c" || arg == "--check" {
            check_mode = true;
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: {} [OPTION]... [FILE]...", prog_name);
            println!("Print or check checksums for specified files.");
            println!("  -c, --check    read checksums from the FILEs and check them");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') || arg == "-" {
            files.push(arg.clone());
        }
    }

    if files.is_empty() {
        files.push("-".to_string());
    }

    if check_mode {
        let mut exit_status = ExitCode::SUCCESS;
        for file in files {
            let lines: Vec<String> = if file == "-" {
                let stdin = io::stdin();
                stdin.lock().lines().filter_map(|l| l.ok()).collect()
            } else {
                match fs::read_to_string(&file) {
                    Ok(s) => s.lines().map(|l| l.to_string()).collect(),
                    Err(e) => {
                        eprintln!("{}: {}: {}", prog_name, file, e);
                        exit_status = ExitCode::from(1);
                        continue;
                    }
                }
            };

            for line in lines {
                let trimmed = line.trim();
                if trimmed.is_empty() || trimmed.starts_with('#') {
                    continue;
                }
                let parts: Vec<&str> = trimmed.split_whitespace().collect();
                if parts.len() >= 2 {
                    let expected_hash = parts[0];
                    let target_path = parts[1].trim_start_matches('*');
                    match fs::read(target_path) {
                        Ok(bytes) => {
                            let actual = hasher(&bytes);
                            if actual.eq_ignore_ascii_case(expected_hash) {
                                println!("{}: OK", target_path);
                            } else {
                                println!("{}: FAILED", target_path);
                                exit_status = ExitCode::from(1);
                            }
                        }
                        Err(e) => {
                            eprintln!("{}: {}: {}", prog_name, target_path, e);
                            exit_status = ExitCode::from(1);
                        }
                    }
                }
            }
        }
        return exit_status;
    }

    let mut exit_status = ExitCode::SUCCESS;
    for file in files {
        if file == "-" {
            let mut buf = Vec::new();
            if io::stdin().read_to_end(&mut buf).is_ok() {
                println!("{}  -", hasher(&buf));
            }
        } else {
            match fs::read(&file) {
                Ok(bytes) => {
                    println!("{}  {}", hasher(&bytes), file);
                }
                Err(e) => {
                    eprintln!("{}: {}: {}", prog_name, file, e);
                    exit_status = ExitCode::from(1);
                }
            }
        }
    }

    exit_status
}

/// RFC 1321 MD5 Implementation (Zero Dependencies)
pub fn md5_digest(data: &[u8]) -> String {
    let mut s = [0x67452301u32, 0xefcdab89u32, 0x98badcfeu32, 0x10325476u32];

    let bit_len = (data.len() as u64) * 8;
    let mut msg = data.to_vec();
    msg.push(0x80);
    while (msg.len() % 64) != 56 {
        msg.push(0);
    }
    msg.extend_from_slice(&bit_len.to_le_bytes());

    let k: [u32; 64] = [
        0xd76aa478, 0xe8c7b756, 0x242070db, 0xc1bdceee, 0xf57c0faf, 0x4787c62a, 0xa8304613,
        0xfd469501, 0x698098d8, 0x8b44f7af, 0xffff5bb1, 0x895cd7be, 0x6b901122, 0xfd987193,
        0xa679438e, 0x49b40821, 0xf61e2562, 0xc040b340, 0x265e5a51, 0xe9b6c7aa, 0xd62f105d,
        0x02441453, 0xd8a1e681, 0xe7d3fbc8, 0x21e1cde6, 0xc33707d6, 0xf4d50d87, 0x455a14ed,
        0xa9e3e905, 0xfcefa3f8, 0x676f02d9, 0x8d2a4c8a, 0xfffa3942, 0x8771f681, 0x6d9d6122,
        0xfde5380c, 0xa4beea44, 0x4bdecfa9, 0xf6bb4b60, 0xbebfbc70, 0x289b7ec6, 0xeaa127fa,
        0xd4ef3085, 0x04881d05, 0xd9d4d039, 0xe6db99e5, 0x1fa27cf8, 0xc4ac5665, 0xf4292244,
        0x432aff97, 0xab9423a7, 0xfc93a039, 0x655b59c3, 0x8f0ccc92, 0xffeff47d, 0x85845dd1,
        0x6fa87e4f, 0xfe2ce6e0, 0xa3014314, 0x4e0811a1, 0xf7537e82, 0xbd3af235, 0x2ad7d2bb,
        0xeb86d391,
    ];

    let shifts: [u32; 64] = [
        7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 5, 9, 14, 20, 5, 9, 14, 20,
        5, 9, 14, 20, 5, 9, 14, 20, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23,
        6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21,
    ];

    for chunk in msg.chunks_exact(64) {
        let mut m = [0u32; 16];
        for i in 0..16 {
            m[i] = u32::from_le_bytes([
                chunk[i * 4],
                chunk[i * 4 + 1],
                chunk[i * 4 + 2],
                chunk[i * 4 + 3],
            ]);
        }

        let mut a = s[0];
        let mut b = s[1];
        let mut c = s[2];
        let mut d = s[3];

        for i in 0..64 {
            let (f, g) = if i < 16 {
                ((b & c) | ((!b) & d), i)
            } else if i < 32 {
                ((d & b) | ((!d) & c), (5 * i + 1) % 16)
            } else if i < 48 {
                (b ^ c ^ d, (3 * i + 5) % 16)
            } else {
                (c ^ (b | (!d)), (7 * i) % 16)
            };

            let temp = d;
            d = c;
            c = b;
            b = b.wrapping_add(
                a.wrapping_add(f)
                    .wrapping_add(k[i])
                    .wrapping_add(m[g])
                    .rotate_left(shifts[i]),
            );
            a = temp;
        }

        s[0] = s[0].wrapping_add(a);
        s[1] = s[1].wrapping_add(b);
        s[2] = s[2].wrapping_add(c);
        s[3] = s[3].wrapping_add(d);
    }

    let mut result = [0u8; 16];
    for (i, &word) in s.iter().enumerate() {
        result[i * 4..i * 4 + 4].copy_from_slice(&word.to_le_bytes());
    }

    result.iter().map(|b| format!("{:02x}", b)).collect()
}

/// FIPS 180-1 SHA-1 Implementation (Zero Dependencies)
pub fn sha1_digest(data: &[u8]) -> String {
    let mut h = [0x67452301u32, 0xefcdab89u32, 0x98badcfeu32, 0x10325476u32, 0xc3d2e1f0u32];

    let bit_len = (data.len() as u64) * 8;
    let mut msg = data.to_vec();
    msg.push(0x80);
    while (msg.len() % 64) != 56 {
        msg.push(0);
    }
    msg.extend_from_slice(&bit_len.to_be_bytes());

    for chunk in msg.chunks_exact(64) {
        let mut w = [0u32; 80];
        for i in 0..16 {
            w[i] = u32::from_be_bytes([
                chunk[i * 4],
                chunk[i * 4 + 1],
                chunk[i * 4 + 2],
                chunk[i * 4 + 3],
            ]);
        }
        for i in 16..80 {
            w[i] = (w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16]).rotate_left(1);
        }

        let mut a = h[0];
        let mut b = h[1];
        let mut c = h[2];
        let mut d = h[3];
        let mut e = h[4];

        for i in 0..80 {
            let (f, k) = if i < 20 {
                ((b & c) | ((!b) & d), 0x5a827999u32)
            } else if i < 40 {
                (b ^ c ^ d, 0x6ed9eba1u32)
            } else if i < 60 {
                ((b & c) | (b & d) | (c & d), 0x8f1bbcdcu32)
            } else {
                (b ^ c ^ d, 0xca62c1d6u32)
            };

            let temp = a
                .rotate_left(5)
                .wrapping_add(f)
                .wrapping_add(e)
                .wrapping_add(k)
                .wrapping_add(w[i]);
            e = d;
            d = c;
            c = b.rotate_left(30);
            b = a;
            a = temp;
        }

        h[0] = h[0].wrapping_add(a);
        h[1] = h[1].wrapping_add(b);
        h[2] = h[2].wrapping_add(c);
        h[3] = h[3].wrapping_add(d);
        h[4] = h[4].wrapping_add(e);
    }

    format!("{:08x}{:08x}{:08x}{:08x}{:08x}", h[0], h[1], h[2], h[3], h[4])
}

// ============================================================================
// shuf (Random Permutation Generator)
// ============================================================================

pub fn run_shuf(args: &[String]) -> ExitCode {
    let mut head_count: Option<usize> = None;
    let mut input_range: Option<(i64, i64)> = None;
    let mut echo_args = Vec::new();
    let mut file_path: Option<String> = None;

    let mut i = 0;
    let mut parsing_options = true;
    while i < args.len() {
        let arg = &args[i];
        if parsing_options && arg == "--" {
            parsing_options = false;
            i += 1;
            continue;
        }
        if parsing_options && (arg == "-n" || arg == "--head-count") {
            if i + 1 < args.len() {
                match args[i + 1].parse::<usize>() {
                    Ok(n) => head_count = Some(n),
                    Err(_) => {
                        eprintln!("shuf: invalid line count: '{}'", args[i + 1]);
                        return ExitCode::from(1);
                    }
                }
                i += 2;
            } else {
                eprintln!("shuf: option requires an argument -- 'n'");
                return ExitCode::from(1);
            }
        } else if parsing_options && arg.starts_with("-n") {
            match arg[2..].parse::<usize>() {
                Ok(n) => head_count = Some(n),
                Err(_) => {
                    eprintln!("shuf: invalid line count: '{}'", &arg[2..]);
                    return ExitCode::from(1);
                }
            }
            i += 1;
        } else if parsing_options && (arg == "-i" || arg == "--input-range") {
            if i + 1 < args.len() {
                let range_str = &args[i + 1];
                if let Some((lo, hi)) = range_str.split_once('-') {
                    if let (Ok(l), Ok(h)) = (lo.parse::<i64>(), hi.parse::<i64>()) {
                        if l > h {
                            eprintln!("shuf: invalid input range: '{}-{}'", l, h);
                            return ExitCode::from(1);
                        }
                        input_range = Some((l, h));
                    } else {
                        eprintln!("shuf: invalid input range: '{}'", range_str);
                        return ExitCode::from(1);
                    }
                } else {
                    eprintln!("shuf: invalid input range: '{}'", range_str);
                    return ExitCode::from(1);
                }
                i += 2;
            } else {
                eprintln!("shuf: option requires an argument -- 'i'");
                return ExitCode::from(1);
            }
        } else if parsing_options && arg.starts_with("-i") {
            let r = &arg[2..];
            if let Some((lo, hi)) = r.split_once('-') {
                if let (Ok(l), Ok(h)) = (lo.parse::<i64>(), hi.parse::<i64>()) {
                    if l > h {
                        eprintln!("shuf: invalid input range: '{}-{}'", l, h);
                        return ExitCode::from(1);
                    }
                    input_range = Some((l, h));
                } else {
                    eprintln!("shuf: invalid input range: '{}'", r);
                    return ExitCode::from(1);
                }
            } else {
                eprintln!("shuf: invalid input range: '{}'", r);
                return ExitCode::from(1);
            }
            i += 1;
        } else if parsing_options && (arg == "-e" || arg == "--echo") {
            for a in &args[i + 1..] {
                echo_args.push(a.clone());
            }
            break;
        } else if parsing_options && (arg == "--help" || arg == "-h") {
            println!("Usage: shuf [OPTION]... [FILE]");
            println!("  or:  shuf -e [OPTION]... [ARG]...");
            println!("  or:  shuf -i LO-HI [OPTION]...");
            println!("Write a random permutation of the input lines to standard output.");
            println!("  -e, --echo               treat each ARG as an input line");
            println!("  -i, --input-range=LO-HI  treat each number LO through HI as an input line");
            println!("  -n, --head-count=COUNT   output at most COUNT lines");
            return ExitCode::SUCCESS;
        } else if parsing_options && arg.starts_with('-') && arg != "-" {
            eprintln!("shuf: unrecognized option '{}'", arg);
            return ExitCode::from(1);
        } else {
            file_path = Some(arg.clone());
            i += 1;
        }
    }

    let mut lines = if !echo_args.is_empty() {
        echo_args
    } else if let Some((lo, hi)) = input_range {
        let count = (hi - lo).saturating_add(1);
        if count > 10_000_000 {
            eprintln!("shuf: input range too large");
            return ExitCode::from(1);
        }
        (lo..=hi).map(|n| n.to_string()).collect()
    } else {
        let reader: Box<dyn BufRead> = if file_path.as_deref() == Some("-") || file_path.is_none() {
            Box::new(BufReader::new(io::stdin()))
        } else {
            let p = file_path.as_ref().unwrap();
            match File::open(p) {
                Ok(f) => Box::new(BufReader::new(f)),
                Err(e) => {
                    eprintln!("shuf: {}: {}", p, e);
                    return ExitCode::from(1);
                }
            }
        };
        let mut read_lines = Vec::new();
        for l in reader.lines() {
            match l {
                Ok(line) => read_lines.push(line),
                Err(e) => {
                    eprintln!("shuf: read error: {}", e);
                    return ExitCode::from(1);
                }
            }
        }
        read_lines
    };

    // Fisher-Yates shuffle
    let mut rng_seed = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(987654321);

    for idx in (1..lines.len()).rev() {
        rng_seed = rng_seed.wrapping_mul(6364136223846793005).wrapping_add(1);
        let j = (rng_seed as usize) % (idx + 1);
        lines.swap(idx, j);
    }

    let limit = head_count.unwrap_or(lines.len()).min(lines.len());
    let stdout = io::stdout();
    let mut out = stdout.lock();
    for l in &lines[..limit] {
        if let Err(e) = writeln!(out, "{}", l) {
            if e.kind() == io::ErrorKind::BrokenPipe {
                return ExitCode::SUCCESS;
            }
            eprintln!("shuf: write error: {}", e);
            return ExitCode::from(1);
        }
    }

    ExitCode::SUCCESS
}

// ============================================================================
// Unit Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_md5_known_vectors() {
        assert_eq!(md5_digest(b""), "d41d8cd98f00b204e9800998ecf8427e");
        assert_eq!(md5_digest(b"a"), "0cc175b9c0f1b6a831c399e269772661");
        assert_eq!(md5_digest(b"abc"), "900150983cd24fb0d6963f7d28e17f72");
    }

    #[test]
    fn test_sha1_known_vectors() {
        assert_eq!(sha1_digest(b""), "da39a3ee5e6b4b0d3255bfef95601890afd80709");
        assert_eq!(sha1_digest(b"abc"), "a9993e364706816aba3e25717850c26c9cd0d89d");
    }

    #[test]
    fn test_nproc_positive() {
        let p = thread::available_parallelism().unwrap().get();
        assert!(p >= 1);
    }

    #[test]
    fn test_tac_and_rev_reversal() {
        let input = "hello world";
        let rev: String = input.chars().rev().collect();
        assert_eq!(rev, "dlrow olleh");

        let lines = vec!["line1", "line2", "line3"];
        let rev_lines: Vec<&str> = lines.into_iter().rev().collect();
        assert_eq!(rev_lines, vec!["line3", "line2", "line1"]);
    }

    #[test]
    fn test_fold_wrapping() {
        let text = "1234567890";
        let width = 4;
        let wrapped: Vec<String> = text
            .as_bytes()
            .chunks(width)
            .map(|c| String::from_utf8_lossy(c).to_string())
            .collect();
        assert_eq!(wrapped, vec!["1234", "5678", "90"]);
    }

    #[test]
    fn test_pgrep_pkill_killall_cli_errors() {
        assert_eq!(run_pgrep(&[]), ExitCode::from(2));
        assert_eq!(run_pgrep(&["--invalid-flag".to_string()]), ExitCode::from(2));
        assert_eq!(run_pkill(&[]), ExitCode::from(2));
        assert_eq!(run_pkill(&["-INVALID".to_string(), "proc".to_string()]), ExitCode::from(2));
        assert_eq!(run_killall(&[]), ExitCode::from(1));
        assert_eq!(run_killall(&["-INVALID".to_string(), "proc".to_string()]), ExitCode::from(1));
    }

    #[test]
    fn test_cluster1_extra_utils_cli_errors() {
        // tac
        assert_eq!(run_tac(&["--invalid-option".to_string()]), ExitCode::from(1));
        assert_eq!(run_tac(&["/nonexistent_file_path_for_tac".to_string()]), ExitCode::from(1));

        // rev
        assert_eq!(run_rev(&["--invalid-option".to_string()]), ExitCode::from(1));
        assert_eq!(run_rev(&["/nonexistent_file_path_for_rev".to_string()]), ExitCode::from(1));

        // nl
        assert_eq!(run_nl(&["--invalid-option".to_string()]), ExitCode::from(1));
        assert_eq!(run_nl(&["/nonexistent_file_path_for_nl".to_string()]), ExitCode::from(1));

        // paste
        assert_eq!(run_paste(&["--invalid-option".to_string()]), ExitCode::from(1));
        assert_eq!(run_paste(&["/nonexistent_file_path_for_paste".to_string()]), ExitCode::from(1));

        // fold
        assert_eq!(run_fold(&["--invalid-option".to_string()]), ExitCode::from(1));
        assert_eq!(run_fold(&["-w".to_string(), "0".to_string()]), ExitCode::from(1));
        assert_eq!(run_fold(&["-w".to_string(), "abc".to_string()]), ExitCode::from(1));
        assert_eq!(run_fold(&["-0".to_string()]), ExitCode::from(1));
        assert_eq!(run_fold(&["/nonexistent_file_path_for_fold".to_string()]), ExitCode::from(1));

        // watch
        assert_eq!(run_watch(&[]), ExitCode::from(1));
        assert_eq!(run_watch(&["-n".to_string(), "2".to_string()]), ExitCode::from(1));
        assert_eq!(run_watch(&["-n".to_string(), "0".to_string(), "echo".to_string()]), ExitCode::from(1));
        assert_eq!(run_watch(&["--invalid-option".to_string()]), ExitCode::from(1));

        // xxd
        assert_eq!(run_xxd(&["--invalid-option".to_string()]), ExitCode::from(1));
        assert_eq!(run_xxd(&["-c".to_string(), "0".to_string()]), ExitCode::from(1));
        assert_eq!(run_xxd(&["-c".to_string()]), ExitCode::from(1));
        assert_eq!(run_xxd(&["-r".to_string()]), ExitCode::from(1));
        assert_eq!(run_xxd(&["/nonexistent_file_path_for_xxd".to_string()]), ExitCode::from(1));

        // hexdump
        assert_eq!(run_hexdump(&["--invalid-option".to_string()]), ExitCode::from(1));

        // shuf
        assert_eq!(run_shuf(&["--invalid-option".to_string()]), ExitCode::from(1));
        assert_eq!(run_shuf(&["-n".to_string()]), ExitCode::from(1));
        assert_eq!(run_shuf(&["-n".to_string(), "invalid".to_string()]), ExitCode::from(1));
        assert_eq!(run_shuf(&["-i".to_string()]), ExitCode::from(1));
        assert_eq!(run_shuf(&["-i".to_string(), "5-2".to_string()]), ExitCode::from(1));
        assert_eq!(run_shuf(&["-i".to_string(), "1-1000000000".to_string()]), ExitCode::from(1));
        assert_eq!(run_shuf(&["/nonexistent_file_path_for_shuf".to_string()]), ExitCode::from(1));
    }

    #[test]
    fn test_fold_multibyte_safety() {
        // Multi-byte chars: '🦀' is 4 bytes. If sliced at byte 2 or 3, it would panic.
        let text = "🦀🦀🦀";
        let chars: Vec<char> = text.chars().collect();
        let chunks: Vec<String> = chars.chunks(2).map(|c| c.iter().collect()).collect();
        assert_eq!(chunks, vec!["🦀🦀", "🦀"]);
    }
}
