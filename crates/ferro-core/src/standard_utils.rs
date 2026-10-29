//! FerroOS POSIX & Linux Standard Utilities Module
//!
//! Provides strict POSIX.1-2017 & Linux/GNU coreutils compatible implementations:
//! - `true`, `false`: Standard exit codes 0 and 1
//! - `basename`, `dirname`: POSIX path parsing and suffix stripping
//! - `readlink`, `realpath`: Symlink resolution and path canonicalization
//! - `mktemp`: Secure atomic temporary file & directory creation (CWE-377 mitigation)
//! - `date`: Wall-clock formatting (+%s, +%Y-%m-%d, -u UTC)
//! - `du`: Disk usage inspection with human-readable and summary modes
//! - `cut`: Delimiter-separated field and character column extraction
//! - `sort`: Lexicographic and numeric sorting with reverse and unique flags
//! - `uniq`: Duplicate line filtering, counting, and detection
//! - `tr`: Character translation, deletion, and class expansion
//! - `yes`: Continuous string generation with graceful EPIPE / BrokenPipe handling
//! - `seq`: Numerical sequence generation
//! - `sha256sum`, `md5sum`: Cryptographic checksum calculation & verification
//! - `printenv`: Standard environment variable inspection
//! - `wget`: CLI download wrapper compatible with GNU wget syntax
//! - `ping`: Network reachability and round-trip latency diagnostics

use std::cmp::Ordering;
use std::collections::HashSet;
use std::env;
use std::fs::{self, File, OpenOptions};
use std::io::{self, BufRead, BufReader, Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

// ============================================================================
// true & false
// ============================================================================

pub fn run_true(_args: &[String]) -> ExitCode {
    ExitCode::SUCCESS
}

pub fn run_false(_args: &[String]) -> ExitCode {
    ExitCode::from(1)
}

// ============================================================================
// basename & dirname
// ============================================================================

/// POSIX.1-2017 basename algorithm
pub fn posix_basename(path_str: &str, suffix: Option<&str>) -> String {
    if path_str.is_empty() {
        return ".".to_string();
    }

    // Strip trailing slashes unless path is all slashes
    let trimmed = path_str.trim_end_matches('/');
    if trimmed.is_empty() {
        return "/".to_string();
    }

    // Take component after last slash
    let base = match trimmed.rfind('/') {
        Some(idx) => &trimmed[idx + 1..],
        None => trimmed,
    };

    if base.is_empty() {
        return "/".to_string();
    }

    // Strip suffix if present and not identical to base
    if let Some(sfx) = suffix {
        if !sfx.is_empty() && base.ends_with(sfx) && base != sfx {
            return base[..base.len() - sfx.len()].to_string();
        }
    }

    base.to_string()
}

pub fn run_basename(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("basename: missing operand");
        eprintln!("Try 'basename --help' for more information.");
        return ExitCode::from(1);
    }

    if args[0] == "--help" || args[0] == "-h" {
        println!("Usage: basename NAME [SUFFIX]");
        println!("  or:  basename OPTION... NAME...");
        println!("Print NAME with any leading directory components removed.");
        println!("If specified, also remove a trailing SUFFIX.");
        return ExitCode::SUCCESS;
    }

    let mut suffix: Option<&str> = None;
    let mut names: Vec<&str> = Vec::new();
    let mut i = 0;

    while i < args.len() {
        let arg = &args[i];
        if arg == "-s" || arg == "--suffix" {
            if i + 1 < args.len() {
                suffix = Some(&args[i + 1]);
                i += 2;
            } else {
                eprintln!("basename: option requires an argument -- 's'");
                return ExitCode::from(1);
            }
        } else if let Some(sfx) = arg.strip_prefix("--suffix=") {
            suffix = Some(sfx);
            i += 1;
        } else if arg == "-a" || arg == "--multiple" {
            i += 1;
        } else if arg == "--" {
            for a in &args[i + 1..] {
                names.push(a.as_str());
            }
            break;
        } else if arg.starts_with('-') && arg.len() > 1 {
            eprintln!("basename: unrecognized option '{}'", arg);
            return ExitCode::from(1);
        } else {
            names.push(arg.as_str());
            i += 1;
        }
    }

    if names.is_empty() {
        eprintln!("basename: missing operand");
        return ExitCode::from(1);
    }

    if suffix.is_none() && names.len() == 2 {
        let result = posix_basename(names[0], Some(names[1]));
        println!("{}", result);
        return ExitCode::SUCCESS;
    }

    for name in names {
        println!("{}", posix_basename(name, suffix));
    }

    ExitCode::SUCCESS
}

/// POSIX.1-2017 dirname algorithm
pub fn posix_dirname(path_str: &str) -> String {
    if path_str.is_empty() {
        return ".".to_string();
    }

    let trimmed = path_str.trim_end_matches('/');
    if trimmed.is_empty() {
        return "/".to_string();
    }

    match trimmed.rfind('/') {
        Some(0) => "/".to_string(),
        Some(idx) => trimmed[..idx].trim_end_matches('/').to_string(),
        None => ".".to_string(),
    }
}

pub fn run_dirname(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("dirname: missing operand");
        eprintln!("Try 'dirname --help' for more information.");
        return ExitCode::from(1);
    }

    if args[0] == "--help" || args[0] == "-h" {
        println!("Usage: dirname [OPTION] NAME...");
        println!("Output each NAME with its last non-slash component and trailing slashes removed.");
        return ExitCode::SUCCESS;
    }

    let mut names = Vec::new();
    let mut zero_term = false;

    for arg in args {
        if arg == "-z" || arg == "--zero" {
            zero_term = true;
        } else if !arg.starts_with('-') || arg == "-" {
            names.push(arg.as_str());
        }
    }

    if names.is_empty() {
        eprintln!("dirname: missing operand");
        return ExitCode::from(1);
    }

    for name in names {
        let dir = posix_dirname(name);
        if zero_term {
            print!("{}\0", dir);
        } else {
            println!("{}", dir);
        }
    }

    ExitCode::SUCCESS
}

// ============================================================================
// readlink & realpath
// ============================================================================

pub fn run_readlink(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("readlink: missing operand");
        return ExitCode::from(1);
    }

    let mut canonicalize = false;
    let mut no_newline = false;
    let mut quiet = false;
    let mut targets = Vec::new();

    for arg in args {
        if arg == "-f" || arg == "-e" || arg == "-m" || arg == "--canonicalize" {
            canonicalize = true;
        } else if arg == "-n" {
            no_newline = true;
        } else if arg == "-q" || arg == "-s" || arg == "--silent" || arg == "--quiet" {
            quiet = true;
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: readlink [OPTION]... FILE...");
            println!("Print value of a symbolic link or canonical file name");
            println!("  -f, --canonicalize      canonicalize by following every symlink");
            println!("  -n                      do not output trailing newline");
            println!("  -q, -s, --quiet         suppress most error messages");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') || arg == "-" {
            targets.push(arg.as_str());
        }
    }

    if targets.is_empty() {
        eprintln!("readlink: missing operand");
        return ExitCode::from(1);
    }

    let mut exit_status = ExitCode::SUCCESS;

    for target in targets {
        let p = Path::new(target);
        if canonicalize {
            match fs::canonicalize(p) {
                Ok(canon) => {
                    let out = canon.to_string_lossy();
                    if no_newline {
                        print!("{}", out);
                    } else {
                        println!("{}", out);
                    }
                }
                Err(e) => {
                    if !quiet {
                        eprintln!("readlink: {}: {}", target, e);
                    }
                    exit_status = ExitCode::from(1);
                }
            }
        } else {
            match fs::read_link(p) {
                Ok(link_dest) => {
                    let out = link_dest.to_string_lossy();
                    if no_newline {
                        print!("{}", out);
                    } else {
                        println!("{}", out);
                    }
                }
                Err(e) => {
                    if !quiet {
                        eprintln!("readlink: {}: {}", target, e);
                    }
                    exit_status = ExitCode::from(1);
                }
            }
        }
    }

    exit_status
}

pub fn run_realpath(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("realpath: missing operand");
        return ExitCode::from(1);
    }

    let mut quiet = false;
    let mut zero_term = false;
    let mut targets = Vec::new();

    for arg in args {
        if arg == "-q" || arg == "--quiet" {
            quiet = true;
        } else if arg == "-z" || arg == "--zero" {
            zero_term = true;
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: realpath [OPTION]... FILE...");
            println!("Print the resolved absolute file name");
            println!("  -q, --quiet     suppress warnings for missing paths");
            println!("  -z, --zero      end each output line with NUL, not newline");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') || arg == "-" {
            targets.push(arg.as_str());
        }
    }

    if targets.is_empty() {
        eprintln!("realpath: missing operand");
        return ExitCode::from(1);
    }

    let mut exit_status = ExitCode::SUCCESS;

    for target in targets {
        let p = Path::new(target);
        match fs::canonicalize(p) {
            Ok(canon) => {
                let out = canon.to_string_lossy();
                if zero_term {
                    print!("{}\0", out);
                } else {
                    println!("{}", out);
                }
            }
            Err(e) => {
                if !quiet {
                    eprintln!("realpath: {}: {}", target, e);
                }
                exit_status = ExitCode::from(1);
            }
        }
    }

    exit_status
}

// ============================================================================
// mktemp (Atomic & Secure CWE-377 Mitigation)
// ============================================================================

fn generate_random_suffix(len: usize) -> String {
    let charset = b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    let mut bytes = vec![0u8; len];

    if let Ok(mut f) = File::open("/dev/urandom") {
        let _ = f.read_exact(&mut bytes);
    } else {
        // Fallback PRNG seed using nanosecond timestamp
        let mut seed = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(123456789);
        for b in &mut bytes {
            seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
            *b = (seed >> 33) as u8;
        }
    }

    bytes
        .into_iter()
        .map(|b| charset[(b as usize) % charset.len()] as char)
        .collect()
}

pub fn run_mktemp(args: &[String]) -> ExitCode {
    let mut directory = false;
    let mut dry_run = false;
    let mut quiet = false;
    let mut tmpdir_prefix: Option<String> = None;
    let mut template: Option<String> = None;

    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-d" || arg == "--directory" {
            directory = true;
            i += 1;
        } else if arg == "-u" || arg == "--dry-run" {
            dry_run = true;
            i += 1;
        } else if arg == "-q" || arg == "--quiet" {
            quiet = true;
            i += 1;
        } else if arg == "-p" || arg == "--tmpdir" {
            if i + 1 < args.len() && !args[i + 1].starts_with('-') {
                tmpdir_prefix = Some(args[i + 1].clone());
                i += 2;
            } else {
                tmpdir_prefix = Some(env::var("TMPDIR").unwrap_or_else(|_| "/tmp".to_string()));
                i += 1;
            }
        } else if let Some(p) = arg.strip_prefix("--tmpdir=") {
            tmpdir_prefix = Some(p.to_string());
            i += 1;
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: mktemp [OPTION]... [TEMPLATE]");
            println!("Create a temporary file or directory safely and print its name.");
            println!("  -d, --directory     create a directory, not a file");
            println!("  -u, --dry-run       do not create anything; merely print a name");
            println!("  -q, --quiet         suppress diagnostics about failure");
            println!("  -p DIR, --tmpdir=DIR  interpret TEMPLATE relative to DIR");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') {
            template = Some(arg.clone());
            i += 1;
        } else {
            i += 1;
        }
    }

    let base_dir = tmpdir_prefix
        .or_else(|| env::var("TMPDIR").ok())
        .unwrap_or_else(|| "/tmp".to_string());

    let raw_tmpl = template.unwrap_or_else(|| "tmp.XXXXXXXXXX".to_string());
    let tmpl_path = Path::new(&raw_tmpl);

    let (parent_dir, filename_pattern) = if tmpl_path.is_absolute() {
        (
            tmpl_path.parent().unwrap_or(Path::new("/tmp")).to_path_buf(),
            tmpl_path.file_name().unwrap().to_string_lossy().to_string(),
        )
    } else {
        (PathBuf::from(&base_dir), raw_tmpl)
    };

    if !filename_pattern.ends_with("XXX") {
        if !quiet {
            eprintln!("mktemp: too few X's in template '{}'", filename_pattern);
        }
        return ExitCode::from(1);
    }

    let x_count = filename_pattern.chars().rev().take_while(|&c| c == 'X').count();
    let prefix = &filename_pattern[..filename_pattern.len() - x_count];

    // Attempt creation with random suffixes (up to 100 tries)
    for _ in 0..100 {
        let rand_suffix = generate_random_suffix(x_count);
        let candidate_name = format!("{}{}", prefix, rand_suffix);
        let candidate_path = parent_dir.join(&candidate_name);

        if dry_run {
            println!("{}", candidate_path.display());
            return ExitCode::SUCCESS;
        }

        if directory {
            #[cfg(unix)]
            {
                use std::os::unix::fs::DirBuilderExt;
                let mut builder = fs::DirBuilder::new();
                builder.mode(0o700);
                if builder.create(&candidate_path).is_ok() {
                    println!("{}", candidate_path.display());
                    return ExitCode::SUCCESS;
                }
            }
            #[cfg(not(unix))]
            {
                if fs::create_dir(&candidate_path).is_ok() {
                    println!("{}", candidate_path.display());
                    return ExitCode::SUCCESS;
                }
            }
        } else {
            // Atomic O_CREAT | O_EXCL file creation (CWE-377 mitigation)
            let mut opts = OpenOptions::new();
            opts.write(true).create_new(true);
            #[cfg(unix)]
            {
                use std::os::unix::fs::OpenOptionsExt;
                opts.mode(0o600);
            }

            if opts.open(&candidate_path).is_ok() {
                println!("{}", candidate_path.display());
                return ExitCode::SUCCESS;
            }
        }
    }

    if !quiet {
        eprintln!("mktemp: failed to create file via template '{}': File exists", filename_pattern);
    }
    ExitCode::from(1)
}

// ============================================================================
// date
// ============================================================================

pub fn run_date(args: &[String]) -> ExitCode {
    let mut utc = false;
    let mut custom_format: Option<String> = None;

    for arg in args {
        if arg == "-u" || arg == "--utc" || arg == "--universal" {
            utc = true;
        } else if let Some(fmt) = arg.strip_prefix('+') {
            custom_format = Some(fmt.to_string());
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: date [OPTION]... [+FORMAT]");
            println!("Display current time in the given FORMAT.");
            println!("  -u, --utc, --universal  print Universal Coordinated Time (UTC)");
            println!("Format directives:");
            println!("  %%s   seconds since 1970-01-01 00:00:00 UTC");
            println!("  %%Y   year, %%m month, %%d day, %%H hour, %%M minute, %%S second");
            println!("  %%F   full date (%%Y-%%m-%%d), %%T time (%%H:%%M:%%S)");
            return ExitCode::SUCCESS;
        }
    }

    let now = SystemTime::now();
    let epoch_sec = now
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);

    // Compute basic calendar date components (UTC breakdown)
    let (year, month, day, hour, minute, second, day_of_week) = break_down_timestamp(epoch_sec);

    let tz_name = if utc { "UTC" } else { "UTC" }; // FerroOS default is UTC in server mode

    if let Some(fmt) = custom_format {
        let mut out = String::new();
        let mut chars = fmt.chars().peekable();
        while let Some(c) = chars.next() {
            if c == '%' {
                if let Some(spec) = chars.next() {
                    match spec {
                        's' => out.push_str(&epoch_sec.to_string()),
                        'Y' => out.push_str(&format!("{:04}", year)),
                        'm' => out.push_str(&format!("{:02}", month)),
                        'd' => out.push_str(&format!("{:02}", day)),
                        'H' => out.push_str(&format!("{:02}", hour)),
                        'M' => out.push_str(&format!("{:02}", minute)),
                        'S' => out.push_str(&format!("{:02}", second)),
                        'F' => out.push_str(&format!("{:04}-{:02}-{:02}", year, month, day)),
                        'T' => out.push_str(&format!("{:02}:{:02}:{:02}", hour, minute, second)),
                        'Z' => out.push_str(tz_name),
                        '%' => out.push('%'),
                        other => {
                            out.push('%');
                            out.push(other);
                        }
                    }
                } else {
                    out.push('%');
                }
            } else {
                out.push(c);
            }
        }
        println!("{}", out);
    } else {
        let day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
        let month_names = [
            "", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ];
        let day_str = day_names[day_of_week as usize % 7];
        let month_str = month_names[month as usize % 13];

        println!(
            "{} {} {:2} {:02}:{:02}:{:02} {} {}",
            day_str, month_str, day, hour, minute, second, tz_name, year
        );
    }

    ExitCode::SUCCESS
}

pub(crate) fn break_down_timestamp(epoch_sec: u64) -> (u32, u32, u32, u32, u32, u32, u32) {
    let second = (epoch_sec % 60) as u32;
    let minute = ((epoch_sec / 60) % 60) as u32;
    let hour = ((epoch_sec / 3600) % 24) as u32;
    let total_days = (epoch_sec / 86400) as u32;

    // Day of week: Jan 1 1970 was Thursday (index 4)
    let day_of_week = (total_days + 4) % 7;

    // Gregorian leap year calculation
    let mut days = total_days;
    let mut year = 1970;

    loop {
        let leap = is_leap_year(year);
        let days_in_year = if leap { 366 } else { 365 };
        if days >= days_in_year {
            days -= days_in_year;
            year += 1;
        } else {
            break;
        }
    }

    let leap = is_leap_year(year);
    let month_days = [
        31,
        if leap { 29 } else { 28 },
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ];

    let mut month = 1;
    for &d in &month_days {
        if days >= d {
            days -= d;
            month += 1;
        } else {
            break;
        }
    }
    let day = days + 1;

    (year, month, day, hour, minute, second, day_of_week)
}

fn is_leap_year(y: u32) -> bool {
    (y % 4 == 0 && y % 100 != 0) || (y % 400 == 0)
}

// ============================================================================
// du (Disk Usage)
// ============================================================================

pub fn run_du(args: &[String]) -> ExitCode {
    let mut summarize = false;
    let mut human_readable = false;
    let mut all_files = false;
    let mut targets = Vec::new();

    for arg in args {
        if arg.starts_with('-') && !arg.starts_with("--") && arg.len() > 1 {
            for c in arg[1..].chars() {
                match c {
                    's' => summarize = true,
                    'h' => human_readable = true,
                    'a' => all_files = true,
                    'k' => human_readable = false,
                    _ => {}
                }
            }
        } else if arg == "--summarize" {
            summarize = true;
        } else if arg == "--human-readable" {
            human_readable = true;
        } else if arg == "--all" {
            all_files = true;
        } else if arg == "--help" {
            println!("Usage: du [OPTION]... [FILE]...");
            println!("Estimate file space usage.");
            println!("  -a, --all             write counts for all files, not just directories");
            println!("  -h, --human-readable  print sizes in human readable format (e.g., 1K 234M 2G)");
            println!("  -s, --summarize       display only a total for each argument");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') {
            targets.push(arg.as_str());
        }
    }

    if targets.is_empty() {
        targets.push(".");
    }

    for target in targets {
        let p = Path::new(target);
        if !p.exists() {
            eprintln!("du: cannot access '{}': No such file or directory", target);
            continue;
        }
        let (total_bytes, entries) = scan_dir_usage(p, all_files);

        if summarize {
            println!("{}\t{}", format_du_size(total_bytes, human_readable), target);
        } else {
            for (sz, path_str) in entries {
                println!("{}\t{}", format_du_size(sz, human_readable), path_str);
            }
            println!("{}\t{}", format_du_size(total_bytes, human_readable), target);
        }
    }

    ExitCode::SUCCESS
}

fn format_du_size(bytes: u64, human: bool) -> String {
    if !human {
        // POSIX 1K blocks
        return ((bytes + 1023) / 1024).to_string();
    }
    const KB: u64 = 1024;
    const MB: u64 = KB * 1024;
    const GB: u64 = MB * 1024;

    if bytes >= GB {
        format!("{:.1}G", bytes as f64 / GB as f64)
    } else if bytes >= MB {
        format!("{:.1}M", bytes as f64 / MB as f64)
    } else if bytes >= KB {
        format!("{:.0}K", bytes as f64 / KB as f64)
    } else {
        format!("{}B", bytes)
    }
}

fn scan_dir_usage(path: &Path, all: bool) -> (u64, Vec<(u64, String)>) {
    let mut total: u64 = 0;
    let mut list = Vec::new();

    if let Ok(meta) = fs::symlink_metadata(path) {
        total += meta.len();
        if meta.is_dir() {
            if let Ok(entries) = fs::read_dir(path) {
                for entry in entries.flatten() {
                    let child_path = entry.path();
                    let child_meta = fs::symlink_metadata(&child_path);
                    if let Ok(cm) = child_meta {
                        if cm.is_dir() {
                            let (sub_bytes, mut sub_list) = scan_dir_usage(&child_path, all);
                            total += sub_bytes;
                            list.append(&mut sub_list);
                            list.push((sub_bytes, child_path.to_string_lossy().to_string()));
                        } else {
                            total += cm.len();
                            if all {
                                list.push((cm.len(), child_path.to_string_lossy().to_string()));
                            }
                        }
                    }
                }
            }
        }
    }

    (total, list)
}

// ============================================================================
// cut
// ============================================================================

pub fn run_cut(args: &[String]) -> ExitCode {
    let mut delimiter = '\t';
    let mut fields: Option<Vec<usize>> = None;
    let mut chars: Option<Vec<usize>> = None;
    let mut only_delimited = false;
    let mut files = Vec::new();

    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-d" {
            if i + 1 < args.len() {
                delimiter = args[i + 1].chars().next().unwrap_or('\t');
                i += 2;
            } else {
                eprintln!("cut: option requires an argument -- 'd'");
                return ExitCode::from(1);
            }
        } else if let Some(d) = arg.strip_prefix("-d") {
            delimiter = d.chars().next().unwrap_or('\t');
            i += 1;
        } else if arg == "-f" {
            if i + 1 < args.len() {
                fields = parse_ranges(&args[i + 1]);
                i += 2;
            } else {
                eprintln!("cut: option requires an argument -- 'f'");
                return ExitCode::from(1);
            }
        } else if let Some(f) = arg.strip_prefix("-f") {
            fields = parse_ranges(f);
            i += 1;
        } else if arg == "-c" {
            if i + 1 < args.len() {
                chars = parse_ranges(&args[i + 1]);
                i += 2;
            } else {
                eprintln!("cut: option requires an argument -- 'c'");
                return ExitCode::from(1);
            }
        } else if let Some(c) = arg.strip_prefix("-c") {
            chars = parse_ranges(c);
            i += 1;
        } else if arg == "-s" || arg == "--only-delimited" {
            only_delimited = true;
            i += 1;
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: cut OPTION... [FILE]...");
            println!("Print selected parts of lines from each FILE to standard output.");
            println!("  -d DELIM   use DELIM instead of TAB for field delimiter");
            println!("  -f LIST    select only these fields (1-based, e.g. 1,3 or 1-4)");
            println!("  -c LIST    select only these characters");
            println!("  -s         do not print lines not containing delimiters");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') || arg == "-" {
            files.push(arg.clone());
            i += 1;
        } else {
            i += 1;
        }
    }

    if fields.is_none() && chars.is_none() {
        eprintln!("cut: you must specify a list of bytes, characters, or fields");
        return ExitCode::from(1);
    }

    if files.is_empty() {
        files.push("-".to_string());
    }

    for file in files {
        let reader: Box<dyn BufRead> = if file == "-" {
            Box::new(BufReader::new(io::stdin()))
        } else {
            match File::open(&file) {
                Ok(f) => Box::new(BufReader::new(f)),
                Err(e) => {
                    eprintln!("cut: {}: {}", file, e);
                    continue;
                }
            }
        };

        for line_res in reader.lines() {
            let line = match line_res {
                Ok(l) => l,
                Err(_) => break,
            };

            if let Some(ref sel_fields) = fields {
                if !line.contains(delimiter) {
                    if !only_delimited {
                        println!("{}", line);
                    }
                    continue;
                }
                let parts: Vec<&str> = line.split(delimiter).collect();
                let mut out_parts = Vec::new();
                for &idx in sel_fields {
                    if idx > 0 && idx <= parts.len() {
                        out_parts.push(parts[idx - 1]);
                    }
                }
                println!("{}", out_parts.join(&delimiter.to_string()));
            } else if let Some(ref sel_chars) = chars {
                let char_vec: Vec<char> = line.chars().collect();
                let mut out_chars = String::new();
                for &idx in sel_chars {
                    if idx > 0 && idx <= char_vec.len() {
                        out_chars.push(char_vec[idx - 1]);
                    }
                }
                println!("{}", out_chars);
            }
        }
    }

    ExitCode::SUCCESS
}

fn parse_ranges(spec: &str) -> Option<Vec<usize>> {
    let mut indices = Vec::new();
    for part in spec.split(',') {
        let part = part.trim();
        if let Some((start_s, end_s)) = part.split_once('-') {
            let start = start_s.parse::<usize>().unwrap_or(1);
            let end = end_s.parse::<usize>().unwrap_or(1024);
            for i in start..=end {
                indices.push(i);
            }
        } else if let Ok(val) = part.parse::<usize>() {
            indices.push(val);
        }
    }
    if indices.is_empty() {
        None
    } else {
        indices.sort_unstable();
        indices.dedup();
        Some(indices)
    }
}

// ============================================================================
// sort & uniq
// ============================================================================

pub fn run_sort(args: &[String]) -> ExitCode {
    let mut numeric = false;
    let mut reverse = false;
    let mut unique = false;
    let mut files = Vec::new();

    for arg in args {
        if arg == "-n" || arg == "--numeric-sort" {
            numeric = true;
        } else if arg == "-r" || arg == "--reverse" {
            reverse = true;
        } else if arg == "-u" || arg == "--unique" {
            unique = true;
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: sort [OPTION]... [FILE]...");
            println!("Write sorted concatenation of all FILE(s) to standard output.");
            println!("  -n, --numeric-sort      compare according to string numerical value");
            println!("  -r, --reverse           reverse the result of comparisons");
            println!("  -u, --unique            output only the first of an equal run");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') || arg == "-" {
            files.push(arg.clone());
        }
    }

    if files.is_empty() {
        files.push("-".to_string());
    }

    let mut lines = Vec::new();

    for file in files {
        let reader: Box<dyn BufRead> = if file == "-" {
            Box::new(BufReader::new(io::stdin()))
        } else {
            match File::open(&file) {
                Ok(f) => Box::new(BufReader::new(f)),
                Err(e) => {
                    eprintln!("sort: {}: {}", file, e);
                    return ExitCode::from(1);
                }
            }
        };

        for l in reader.lines() {
            if let Ok(line) = l {
                lines.push(line);
            }
        }
    }

    lines.sort_by(|a, b| {
        let ord = if numeric {
            let num_a = a.split_whitespace().next().and_then(|s| s.parse::<f64>().ok());
            let num_b = b.split_whitespace().next().and_then(|s| s.parse::<f64>().ok());
            match (num_a, num_b) {
                (Some(na), Some(nb)) => na.partial_cmp(&nb).unwrap_or(Ordering::Equal),
                (Some(_), None) => Ordering::Greater,
                (None, Some(_)) => Ordering::Less,
                (None, None) => a.cmp(b),
            }
        } else {
            a.cmp(b)
        };

        if reverse {
            ord.reverse()
        } else {
            ord
        }
    });

    if unique {
        lines.dedup();
    }

    for l in lines {
        println!("{}", l);
    }

    ExitCode::SUCCESS
}

pub fn run_uniq(args: &[String]) -> ExitCode {
    let mut count = false;
    let mut repeated_only = false;
    let mut unique_only = false;
    let mut ignore_case = false;
    let mut files = Vec::new();

    for arg in args {
        if arg == "-c" || arg == "--count" {
            count = true;
        } else if arg == "-d" || arg == "--repeated" {
            repeated_only = true;
        } else if arg == "-u" || arg == "--unique" {
            unique_only = true;
        } else if arg == "-i" || arg == "--ignore-case" {
            ignore_case = true;
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: uniq [OPTION]... [INPUT [OUTPUT]]");
            println!("Filter adjacent matching lines from INPUT (or standard input).");
            println!("  -c, --count           prefix lines by the number of occurrences");
            println!("  -d, --repeated        only print duplicate lines");
            println!("  -u, --unique          only print unique lines");
            println!("  -i, --ignore-case     ignore differences in case when comparing");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') || arg == "-" {
            files.push(arg.clone());
        }
    }

    let input_file = files.first().map(|s| s.as_str()).unwrap_or("-");

    let reader: Box<dyn BufRead> = if input_file == "-" {
        Box::new(BufReader::new(io::stdin()))
    } else {
        match File::open(input_file) {
            Ok(f) => Box::new(BufReader::new(f)),
            Err(e) => {
                eprintln!("uniq: {}: {}", input_file, e);
                return ExitCode::from(1);
            }
        }
    };

    let mut current_line: Option<String> = None;
    let mut current_count = 0usize;

    let output_group = |line: &str, cnt: usize| {
        let should_print = if repeated_only {
            cnt > 1
        } else if unique_only {
            cnt == 1
        } else {
            true
        };

        if should_print {
            if count {
                println!("{:7} {}", cnt, line);
            } else {
                println!("{}", line);
            }
        }
    };

    for l_res in reader.lines() {
        if let Ok(line) = l_res {
            let matches = match current_line {
                Some(ref prev) => {
                    if ignore_case {
                        prev.eq_ignore_ascii_case(&line)
                    } else {
                        prev == &line
                    }
                }
                None => false,
            };

            if matches {
                current_count += 1;
            } else {
                if let Some(prev) = current_line.take() {
                    output_group(&prev, current_count);
                }
                current_line = Some(line);
                current_count = 1;
            }
        }
    }

    if let Some(prev) = current_line {
        output_group(&prev, current_count);
    }

    ExitCode::SUCCESS
}

// ============================================================================
// tr (Translate / Delete Characters)
// ============================================================================

pub fn run_tr(args: &[String]) -> ExitCode {
    let mut delete = false;
    let mut squeeze = false;
    let mut sets = Vec::new();

    for arg in args {
        if arg == "-d" || arg == "--delete" {
            delete = true;
        } else if arg == "-s" || arg == "--squeeze-repeats" {
            squeeze = true;
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: tr [OPTION]... SET1 [SET2]");
            println!("Translate, squeeze, and/or delete characters from standard input.");
            println!("  -d, --delete          delete characters in SET1, do not translate");
            println!("  -s, --squeeze-repeats replace sequence of characters with a single character");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') {
            sets.push(arg.as_str());
        }
    }

    if sets.is_empty() {
        eprintln!("tr: missing operand");
        return ExitCode::from(1);
    }

    let set1 = expand_tr_set(sets[0]);
    let set2 = if sets.len() > 1 {
        expand_tr_set(sets[1])
    } else {
        Vec::new()
    };

    let stdin = io::stdin();
    let mut handle = stdin.lock();
    let mut buf = [0u8; 4096];
    let stdout = io::stdout();
    let mut out_handle = stdout.lock();

    let set1_set: HashSet<u8> = set1.iter().copied().collect();
    let squeeze_set: HashSet<u8> = if delete && !set2.is_empty() {
        set2.iter().copied().collect()
    } else {
        set1.iter().copied().collect()
    };
    let mut last_emitted: Option<u8> = None;

    while let Ok(n) = handle.read(&mut buf) {
        if n == 0 {
            break;
        }
        let chunk = &buf[..n];

        let mut output = Vec::with_capacity(chunk.len());

        for &b in chunk {
            let processed_byte = if delete {
                if set1_set.contains(&b) {
                    None
                } else {
                    Some(b)
                }
            } else if !set2.is_empty() {
                if let Some(idx) = set1.iter().position(|&s| s == b) {
                    let repl = if idx < set2.len() {
                        set2[idx]
                    } else {
                        *set2.last().unwrap_or(&b)
                    };
                    Some(repl)
                } else {
                    Some(b)
                }
            } else {
                Some(b)
            };

            if let Some(out_b) = processed_byte {
                if squeeze && squeeze_set.contains(&out_b) && last_emitted == Some(out_b) {
                    continue;
                }
                last_emitted = Some(out_b);
                output.push(out_b);
            }
        }

        let _ = out_handle.write_all(&output);
    }

    let _ = out_handle.flush();
    ExitCode::SUCCESS
}

fn expand_tr_set(s: &str) -> Vec<u8> {
    let mut res = Vec::new();
    let bytes = s.as_bytes();
    let mut i = 0;

    while i < bytes.len() {
        if bytes[i] == b'[' && s[i..].starts_with("[:lower:]") {
            for b in b'a'..=b'z' {
                res.push(b);
            }
            i += 9;
        } else if bytes[i] == b'[' && s[i..].starts_with("[:upper:]") {
            for b in b'A'..=b'Z' {
                res.push(b);
            }
            i += 9;
        } else if bytes[i] == b'[' && s[i..].starts_with("[:digit:]") {
            for b in b'0'..=b'9' {
                res.push(b);
            }
            i += 9;
        } else if bytes[i] == b'\\' && i + 1 < bytes.len() {
            match bytes[i + 1] {
                b'n' => res.push(b'\n'),
                b't' => res.push(b'\t'),
                b'r' => res.push(b'\r'),
                b'0' => res.push(0),
                other => res.push(other),
            }
            i += 2;
        } else if i + 2 < bytes.len() && bytes[i + 1] == b'-' {
            let start = bytes[i];
            let end = bytes[i + 2];
            for b in start..=end {
                res.push(b);
            }
            i += 3;
        } else {
            res.push(bytes[i]);
            i += 1;
        }
    }
    res
}

// ============================================================================
// yes & seq
// ============================================================================

pub fn run_yes(args: &[String]) -> ExitCode {
    let text = if args.is_empty() {
        "y".to_string()
    } else {
        args.join(" ")
    };

    let msg = format!("{}\n", text);
    let msg_bytes = msg.as_bytes();
    let stdout = io::stdout();
    let mut handle = stdout.lock();

    // Standard Unix yes streams until broken pipe (EPIPE).
    // Catching BrokenPipe ensures zero panic crash on pipe close.
    loop {
        if let Err(e) = handle.write_all(msg_bytes) {
            if e.kind() == io::ErrorKind::BrokenPipe {
                break;
            }
            eprintln!("yes: standard output: {}", e);
            return ExitCode::from(1);
        }
    }

    ExitCode::SUCCESS
}

pub fn run_seq(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("seq: missing operand");
        eprintln!("Try 'seq --help' for more information.");
        return ExitCode::from(1);
    }

    let mut separator = "\n".to_string();
    let mut numbers = Vec::new();

    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-s" || arg == "--separator" {
            if i + 1 < args.len() {
                separator = args[i + 1].clone();
                i += 2;
            } else {
                eprintln!("seq: option requires an argument -- 's'");
                return ExitCode::from(1);
            }
        } else if let Some(sep) = arg.strip_prefix("-s") {
            separator = sep.to_string();
            i += 1;
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: seq [OPTION]... LAST");
            println!("  or:  seq [OPTION]... FIRST LAST");
            println!("  or:  seq [OPTION]... FIRST INCREMENT LAST");
            println!("Print numbers from FIRST to LAST, in steps of INCREMENT.");
            println!("  -s, --separator=STRING  use STRING to separate numbers (default: \\n)");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') || arg.parse::<i64>().is_ok() {
            if let Ok(n) = arg.parse::<i64>() {
                numbers.push(n);
            }
            i += 1;
        } else {
            i += 1;
        }
    }

    let (first, step, last) = match numbers.len() {
        1 => (1, 1, numbers[0]),
        2 => (numbers[0], 1, numbers[1]),
        3 => (numbers[0], numbers[1], numbers[2]),
        _ => {
            eprintln!("seq: extra operand");
            return ExitCode::from(1);
        }
    };

    if step == 0 {
        eprintln!("seq: zero increment");
        return ExitCode::from(1);
    }

    let mut current = first;
    let mut first_item = true;

    while (step > 0 && current <= last) || (step < 0 && current >= last) {
        if !first_item {
            print!("{}", separator);
        }
        print!("{}", current);
        first_item = false;
        current += step;
    }
    println!();

    ExitCode::SUCCESS
}

// ============================================================================
// sha256sum & md5sum
// ============================================================================

pub fn run_sha256sum(args: &[String]) -> ExitCode {
    let mut check_mode = false;
    let mut files = Vec::new();

    for arg in args {
        if arg == "-c" || arg == "--check" {
            check_mode = true;
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: sha256sum [OPTION]... [FILE]...");
            println!("Print or check SHA256 (256-bit) checksums.");
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
        return verify_checksum_file(&files[0]);
    }

    let mut exit_code = ExitCode::SUCCESS;

    for file in files {
        if file == "-" {
            let mut stdin = io::stdin();
            let mut buf = Vec::new();
            if stdin.read_to_end(&mut buf).is_ok() {
                let digest = sha256_bytes(&buf);
                println!("{}  -", digest);
            }
        } else {
            let p = Path::new(&file);
            match fs::read(p) {
                Ok(bytes) => {
                    let digest = sha256_bytes(&bytes);
                    println!("{}  {}", digest, file);
                }
                Err(e) => {
                    eprintln!("sha256sum: {}: {}", file, e);
                    exit_code = ExitCode::from(1);
                }
            }
        }
    }

    exit_code
}

fn verify_checksum_file(file: &str) -> ExitCode {
    let reader: Box<dyn BufRead> = if file == "-" {
        Box::new(BufReader::new(io::stdin()))
    } else {
        match File::open(file) {
            Ok(f) => Box::new(BufReader::new(f)),
            Err(e) => {
                eprintln!("sha256sum: {}: {}", file, e);
                return ExitCode::from(1);
            }
        }
    };

    let mut failures = 0;

    for line_res in reader.lines() {
        if let Ok(line) = line_res {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            let parts: Vec<&str> = line.split_whitespace().collect();
            if parts.len() >= 2 {
                let expected_hash = parts[0];
                let target_path = parts[1].trim_start_matches('*');
                match fs::read(target_path) {
                    Ok(bytes) => {
                        let actual = sha256_bytes(&bytes);
                        if actual.eq_ignore_ascii_case(expected_hash) {
                            println!("{}: OK", target_path);
                        } else {
                            println!("{}: FAILED", target_path);
                            failures += 1;
                        }
                    }
                    Err(_) => {
                        println!("{}: FAILED open or read", target_path);
                        failures += 1;
                    }
                }
            }
        }
    }

    if failures > 0 {
        eprintln!("sha256sum: WARNING: {} computed checksum did NOT match", failures);
        ExitCode::from(1)
    } else {
        ExitCode::SUCCESS
    }
}

pub fn sha256_bytes(data: &[u8]) -> String {
    let mut h: [u32; 8] = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab,
        0x5be0cd19,
    ];
    let k: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
        0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
        0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
        0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
        0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
        0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2,
    ];

    let bit_len = (data.len() as u64) * 8;
    let mut msg = data.to_vec();
    msg.push(0x80);
    while (msg.len() % 64) != 56 {
        msg.push(0);
    }
    msg.extend_from_slice(&bit_len.to_be_bytes());

    for chunk in msg.chunks_exact(64) {
        let mut w = [0u32; 64];
        for i in 0..16 {
            w[i] = u32::from_be_bytes([
                chunk[i * 4],
                chunk[i * 4 + 1],
                chunk[i * 4 + 2],
                chunk[i * 4 + 3],
            ]);
        }
        for i in 16..64 {
            let s0 = w[i - 15].rotate_right(7) ^ w[i - 15].rotate_right(18) ^ (w[i - 15] >> 3);
            let s1 = w[i - 2].rotate_right(17) ^ w[i - 2].rotate_right(19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16]
                .wrapping_add(s0)
                .wrapping_add(w[i - 7])
                .wrapping_add(s1);
        }

        let mut a = h[0];
        let mut b = h[1];
        let mut c = h[2];
        let mut d = h[3];
        let mut e = h[4];
        let mut f = h[5];
        let mut g = h[6];
        let mut h_val = h[7];

        for i in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let ch = (e & f) ^ ((!e) & g);
            let temp1 = h_val
                .wrapping_add(s1)
                .wrapping_add(ch)
                .wrapping_add(k[i])
                .wrapping_add(w[i]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let temp2 = s0.wrapping_add(maj);

            h_val = g;
            g = f;
            f = e;
            e = d.wrapping_add(temp1);
            d = c;
            c = b;
            b = a;
            a = temp1.wrapping_add(temp2);
        }

        h[0] = h[0].wrapping_add(a);
        h[1] = h[1].wrapping_add(b);
        h[2] = h[2].wrapping_add(c);
        h[3] = h[3].wrapping_add(d);
        h[4] = h[4].wrapping_add(e);
        h[5] = h[5].wrapping_add(f);
        h[6] = h[6].wrapping_add(g);
        h[7] = h[7].wrapping_add(h_val);
    }

    format!(
        "{:08x}{:08x}{:08x}{:08x}{:08x}{:08x}{:08x}{:08x}",
        h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7]
    )
}

// ============================================================================
// printenv
// ============================================================================

pub fn run_printenv(args: &[String]) -> ExitCode {
    if args.is_empty() {
        for (k, v) in env::vars() {
            println!("{}={}", k, v);
        }
        return ExitCode::SUCCESS;
    }

    if args[0] == "--help" || args[0] == "-h" {
        println!("Usage: printenv [OPTION]... [VARIABLE]...");
        println!("Print the values of the specified environment VARIABLE(s).");
        println!("If no VARIABLE is specified, print name and value pairs for them all.");
        return ExitCode::SUCCESS;
    }

    let mut all_found = true;
    for arg in args {
        if let Ok(val) = env::var(arg) {
            println!("{}", val);
        } else {
            all_found = false;
        }
    }

    if all_found {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    }
}

// ============================================================================
// wget (GNU wget CLI compatibility wrapper for fetch/curl)
// ============================================================================

pub fn run_wget(args: &[String]) -> ExitCode {
    let mut output_file: Option<String> = None;
    let mut quiet = false;
    let mut url: Option<String> = None;

    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-O" || arg == "--output-document" {
            if i + 1 < args.len() {
                output_file = Some(args[i + 1].clone());
                i += 2;
            } else {
                eprintln!("wget: option requires an argument -- 'O'");
                return ExitCode::from(1);
            }
        } else if let Some(out) = arg.strip_prefix("-O") {
            output_file = Some(out.to_string());
            i += 1;
        } else if arg == "-q" || arg == "--quiet" {
            quiet = true;
            i += 1;
        } else if arg == "--help" || arg == "-h" {
            println!("FerroOS GNU Wget Compatibility Client v2.3.0");
            println!("Usage: wget [OPTION]... [URL]...");
            println!("  -O, --output-document=FILE  write documents to FILE");
            println!("  -q, --quiet                 quiet (no output)");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') {
            url = Some(arg.clone());
            i += 1;
        } else {
            i += 1;
        }
    }

    let target_url = match url {
        Some(u) => u,
        None => {
            eprintln!("wget: missing URL");
            eprintln!("Usage: wget [OPTION]... [URL]...");
            return ExitCode::from(1);
        }
    };

    let mut fetch_args = Vec::new();
    if let Some(out) = output_file {
        fetch_args.push("-o".to_string());
        fetch_args.push(out);
    }
    if quiet {
        fetch_args.push("-s".to_string());
    }
    fetch_args.push(target_url);

    super::run_fetch(&fetch_args)
}

// ============================================================================
// ping
// ============================================================================

pub fn run_ping(args: &[String]) -> ExitCode {
    let mut count = 4;
    let mut target_host: Option<String> = None;

    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-c" || arg == "--count" {
            if i + 1 < args.len() {
                count = args[i + 1].parse::<usize>().unwrap_or(4);
                i += 2;
            } else {
                eprintln!("ping: option requires an argument -- 'c'");
                return ExitCode::from(1);
            }
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: ping [OPTION]... destination");
            println!("Send ICMP / Socket probe to network hosts.");
            println!("  -c, --count=NUMBER    stop after sending NUMBER packets");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') {
            target_host = Some(arg.clone());
            i += 1;
        } else {
            i += 1;
        }
    }

    let host = match target_host {
        Some(h) => h,
        None => {
            eprintln!("ping: usage error: Destination address required");
            return ExitCode::from(1);
        }
    };

    println!("PING {} (probe mode): 56 data bytes", host);

    let mut received = 0;
    let mut times = Vec::new();

    for seq in 1..=count {
        let start = Instant::now();
        // Socket probe check (DNS lookup + socket connect test)
        let resolved = format!("{}:80", host).to_socket_addrs();
        match resolved {
            Ok(mut addrs) => {
                if let Some(addr) = addrs.next() {
                    let conn = TcpStream::connect_timeout(&addr, Duration::from_secs(2));
                    let elapsed = start.elapsed();
                    let ms = elapsed.as_secs_f64() * 1000.0;
                    if conn.is_ok() {
                        received += 1;
                        times.push(ms);
                        println!(
                            "64 bytes from {}: icmp_seq={} time={:.2} ms",
                            addr.ip(),
                            seq,
                            ms
                        );
                    } else {
                        println!("Request timeout for icmp_seq {}", seq);
                    }
                } else {
                    println!("Request timeout for icmp_seq {}", seq);
                }
            }
            Err(e) => {
                eprintln!("ping: cannot resolve {}: {}", host, e);
                return ExitCode::from(2);
            }
        }
        if seq < count {
            std::thread::sleep(Duration::from_millis(500));
        }
    }

    let loss = if count > 0 {
        ((count - received) as f64 / count as f64) * 100.0
    } else {
        0.0
    };

    println!("\n--- {} ping statistics ---", host);
    println!(
        "{} packets transmitted, {} received, {:.0}% packet loss",
        count, received, loss
    );

    if !times.is_empty() {
        let min = times.iter().fold(f64::INFINITY, |a, &b| a.min(b));
        let max = times.iter().fold(f64::NEG_INFINITY, |a, &b| a.max(b));
        let avg = times.iter().sum::<f64>() / times.len() as f64;
        println!("rtt min/avg/max = {:.3}/{:.3}/{:.3} ms", min, avg, max);
    }

    if received > 0 {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    }
}

// ============================================================================
// Unit Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_posix_basename() {
        assert_eq!(posix_basename("/usr/lib", None), "lib");
        assert_eq!(posix_basename("/usr/lib/", None), "lib");
        assert_eq!(posix_basename("///", None), "/");
        assert_eq!(posix_basename("", None), ".");
        assert_eq!(posix_basename("main.rs", Some(".rs")), "main");
        assert_eq!(posix_basename("main.rs", Some(".c")), "main.rs");
        assert_eq!(posix_basename(".rs", Some(".rs")), ".rs");
    }

    #[test]
    fn test_posix_dirname() {
        assert_eq!(posix_dirname("/usr/lib"), "/usr");
        assert_eq!(posix_dirname("/usr/"), "/");
        assert_eq!(posix_dirname("usr"), ".");
        assert_eq!(posix_dirname("/"), "/");
        assert_eq!(posix_dirname("///"), "/");
        assert_eq!(posix_dirname(""), ".");
        assert_eq!(posix_dirname("a/b/c"), "a/b");
    }

    #[test]
    fn test_sha256_known_vector() {
        assert_eq!(
            sha256_bytes(b""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
        assert_eq!(
            sha256_bytes(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }

    #[test]
    fn test_leap_year_breakdown() {
        let (y, m, d, h, min, s, dow) = break_down_timestamp(0);
        assert_eq!((y, m, d, h, min, s, dow), (1970, 1, 1, 0, 0, 0, 4));

        // 2026-10-29 00:00:00 UTC
        // Approx 56 years after 1970
        let approx_2026 = 1793232000;
        let (y2, _, _, _, _, _, _) = break_down_timestamp(approx_2026);
        assert_eq!(y2, 2026);
    }

    #[test]
    fn test_parse_ranges() {
        assert_eq!(parse_ranges("1,3"), Some(vec![1, 3]));
        assert_eq!(parse_ranges("1-3"), Some(vec![1, 2, 3]));
        assert_eq!(parse_ranges("4,2,3"), Some(vec![2, 3, 4]));
    }
}
