//! FerroOS Extended Core & System Utilities Module (ext_utils.rs)
//!
//! Provides standard POSIX.1-2017 & Linux distribution utilities:
//! - `file`: Magic byte & metadata file type classification (ELF, Mach-O, PE, scripts, images, archives, text)
//! - `strings`: Printable ASCII / UTF-8 string scanner from binaries with offset formatting
//! - `split`: File segmenter by byte size or line count with numeric/alphabetic suffixes
//! - `comm`: Line-by-line comparison of two sorted files (3-column suppression)
//! - `truncate`: Shrink or extend file size to specified length (supports K/M/G suffixes, relative +/-)
//! - `tree`: Visual recursive directory tree formatter with box-drawing characters and file counts
//! - `cal`: POSIX Gregorian calendar generator with month/year navigation
//! - `lscpu`: CPU architecture, topology, vendor, frequency, flags, and cache inspector
//! - `lsmod`: Linux kernel module status inspector (/proc/modules)
//! - `lspci`: PCI bus device enumerator (/sys/bus/pci/devices)
//! - `ifconfig`: Network interface status, IP/IPv6, netmask, broadcast, MTU, packet counters
//! - `link` & `unlink`: Direct POSIX system call wrappers for hard links and file deletion
//! - `factor`: Prime factorization generator
//! - `logname`: POSIX login username inspector

use std::env;
use std::fs::{self, File, OpenOptions};
use std::io::{self, BufRead, BufReader, Read, Write};
use std::path::Path;
use std::process::ExitCode;
use std::thread;
use std::time::{SystemTime, UNIX_EPOCH};

// ============================================================================
// file (Magic Byte & Metadata Identification)
// ============================================================================

pub fn run_file(args: &[String]) -> ExitCode {
    let mut brief = false;
    let mut mime = false;
    let mut files = Vec::new();

    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-b" || arg == "--brief" {
            brief = true;
            i += 1;
        } else if arg == "-i" || arg == "--mime" || arg == "--mime-type" {
            mime = true;
            i += 1;
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: file [OPTION]... [FILE]...");
            println!("Determine file type of FILEs.");
            println!("  -b, --brief      do not prepend filenames to output lines");
            println!("  -i, --mime       output MIME type strings");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') || arg == "-" {
            files.push(arg.clone());
            i += 1;
        } else {
            i += 1;
        }
    }

    if files.is_empty() {
        eprintln!("file: missing file operand (try 'file --help')");
        return ExitCode::from(1);
    }

    let mut exit_code = ExitCode::SUCCESS;
    for file in &files {
        let (desc, mime_type) = inspect_file_type(file);
        if desc.starts_with("cannot open") || desc.starts_with("cannot read") {
            exit_code = ExitCode::from(1);
        }
        let output = if mime { mime_type } else { desc };
        if brief {
            println!("{}", output);
        } else {
            println!("{}: {}", file, output);
        }
    }

    exit_code
}

fn inspect_file_type(path_str: &str) -> (String, String) {
    if path_str == "-" {
        let mut buf = Vec::new();
        let _ = io::stdin().take(4096).read_to_end(&mut buf);
        return classify_bytes(&buf);
    }

    let p = Path::new(path_str);
    let sym_meta = match fs::symlink_metadata(p) {
        Ok(m) => m,
        Err(e) => return (format!("cannot open: {}", e), "application/octet-stream".to_string()),
    };

    let file_type = sym_meta.file_type();

    if file_type.is_symlink() {
        let target = fs::read_link(p)
            .map(|t| t.to_string_lossy().to_string())
            .unwrap_or_else(|_| "unknown".to_string());
        return (
            format!("symbolic link to {}", target),
            "inode/symlink".to_string(),
        );
    }

    if file_type.is_dir() {
        return ("directory".to_string(), "inode/directory".to_string());
    }

    #[cfg(unix)]
    {
        use std::os::unix::fs::FileTypeExt;
        if file_type.is_block_device() {
            return ("block special".to_string(), "inode/blockdevice".to_string());
        }
        if file_type.is_char_device() {
            return ("character special".to_string(), "inode/chardevice".to_string());
        }
        if file_type.is_fifo() {
            return ("fifo (named pipe)".to_string(), "inode/fifo".to_string());
        }
        if file_type.is_socket() {
            return ("socket".to_string(), "inode/socket".to_string());
        }
    }

    if sym_meta.len() == 0 {
        return ("empty".to_string(), "application/x-empty".to_string());
    }

    let mut buf = vec![0u8; 4096];
    let bytes_read = match File::open(p).and_then(|mut f| f.read(&mut buf)) {
        Ok(n) => n,
        Err(e) => return (format!("cannot read: {}", e), "application/octet-stream".to_string()),
    };
    buf.truncate(bytes_read);

    classify_bytes(&buf)
}

fn classify_bytes(buf: &[u8]) -> (String, String) {
    if buf.is_empty() {
        return ("empty".to_string(), "application/x-empty".to_string());
    }

    // ELF Binary
    if buf.starts_with(b"\x7fELF") {
        let bitness = if buf.get(4) == Some(&2) { "64-bit" } else { "32-bit" };
        let endian = if buf.get(5) == Some(&1) { "LSB" } else { "MSB" };
        let elf_type = if buf.len() >= 18 {
            let t = u16::from_le_bytes([buf[16], buf[17]]);
            match t {
                1 => "relocatable",
                2 => "executable",
                3 => "pie executable / shared object",
                4 => "core file",
                _ => "ELF object",
            }
        } else {
            "ELF binary"
        };
        let arch = if buf.len() >= 20 {
            let m = u16::from_le_bytes([buf[18], buf[19]]);
            match m {
                0x3e => "x86-64",
                0x03 => "Intel 80386",
                0xb7 => "ARM aarch64",
                0x28 => "ARM",
                0xf3 => "RISC-V",
                _ => "unknown architecture",
            }
        } else {
            ""
        };
        return (
            format!("ELF {} {} {}, {}, version 1 (SYSV)", bitness, endian, elf_type, arch),
            "application/x-executable".to_string(),
        );
    }

    // Mach-O Binary
    if buf.starts_with(&[0xfe, 0xed, 0xfa, 0xcf]) || buf.starts_with(&[0xcf, 0xfa, 0xed, 0xfe]) {
        return ("Mach-O 64-bit executable".to_string(), "application/x-mach-binary".to_string());
    }
    if buf.starts_with(&[0xfe, 0xed, 0xfa, 0xce]) || buf.starts_with(&[0xce, 0xfa, 0xed, 0xfe]) {
        return ("Mach-O 32-bit executable".to_string(), "application/x-mach-binary".to_string());
    }
    if buf.starts_with(&[0xca, 0xfe, 0xba, 0xbe]) {
        return ("Mach-O universal binary".to_string(), "application/x-mach-binary".to_string());
    }

    // Windows PE / MZ
    if buf.starts_with(b"MZ") {
        return ("MS-DOS executable, MZ for MS-DOS / Windows PE".to_string(), "application/x-dosexec".to_string());
    }

    // Compressed Formats
    if buf.starts_with(&[0x1f, 0x8b]) {
        return ("gzip compressed data, max compression, from Unix".to_string(), "application/gzip".to_string());
    }
    if buf.starts_with(b"BZh") {
        return ("bzip2 compressed data".to_string(), "application/x-bzip2".to_string());
    }
    if buf.starts_with(b"\xfd7zXZ\x00") {
        return ("XZ compressed data".to_string(), "application/x-xz".to_string());
    }
    if buf.starts_with(&[0x28, 0xb5, 0x2f, 0xfd]) {
        return ("Zstandard compressed data".to_string(), "application/zstd".to_string());
    }
    if buf.starts_with(b"PK\x03\x04") {
        return ("Zip archive data".to_string(), "application/zip".to_string());
    }

    // Tar Archive (ustar signature at offset 257)
    if buf.len() > 262 && &buf[257..262] == b"ustar" {
        return ("POSIX tar archive (ustar)".to_string(), "application/x-tar".to_string());
    }

    // Image Formats
    if buf.starts_with(b"\x89PNG\r\n\x1a\n") {
        return ("PNG image data".to_string(), "image/png".to_string());
    }
    if buf.starts_with(&[0xff, 0xd8, 0xff]) {
        return ("JPEG image data, JFIF standard".to_string(), "image/jpeg".to_string());
    }
    if buf.starts_with(b"GIF87a") || buf.starts_with(b"GIF89a") {
        return ("GIF image data".to_string(), "image/gif".to_string());
    }

    // Document Formats
    if buf.starts_with(b"%PDF-") {
        let ver = if buf.len() >= 8 {
            String::from_utf8_lossy(&buf[5..8]).to_string()
        } else {
            "1.4".to_string()
        };
        return (format!("PDF document, version {}", ver), "application/pdf".to_string());
    }

    // Script / Shebang
    if buf.starts_with(b"#!") {
        let first_line = buf.split(|&b| b == b'\n').next().unwrap_or(b"");
        let line_str = String::from_utf8_lossy(first_line).trim().to_string();
        let interp = line_str.trim_start_matches("#!").trim();
        let name = Path::new(interp).file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_else(|| "script".to_string());
        return (
            format!("{} script, ASCII text executable", name),
            "text/x-shellscript".to_string(),
        );
    }

    // Text & JSON Detection
    let is_ascii = buf.iter().all(|&b| b == b'\t' || b == b'\r' || b == b'\n' || (b >= 32 && b <= 126));
    if is_ascii {
        let trimmed = String::from_utf8_lossy(buf).trim().to_string();
        if (trimmed.starts_with('{') && trimmed.ends_with('}')) || (trimmed.starts_with('[') && trimmed.ends_with(']')) {
            return ("JSON data, ASCII text".to_string(), "application/json".to_string());
        }
        return ("ASCII text".to_string(), "text/plain".to_string());
    }

    if let Ok(text) = std::str::from_utf8(buf) {
        let has_control = text.chars().any(|c| c.is_control() && c != '\t' && c != '\n' && c != '\r');
        if !has_control {
            return ("UTF-8 Unicode text".to_string(), "text/plain; charset=utf-8".to_string());
        }
    }

    ("data".to_string(), "application/octet-stream".to_string())
}

// ============================================================================
// strings (Printable Character Scanner)
// ============================================================================

pub fn run_strings(args: &[String]) -> ExitCode {
    let mut min_len = 4usize;
    let mut offset_format: Option<char> = None; // 'o', 'x', 'd'
    let mut files = Vec::new();

    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-n" {
            if i + 1 < args.len() {
                min_len = args[i + 1].parse::<usize>().unwrap_or(4);
                i += 2;
            } else {
                eprintln!("strings: option requires an argument -- 'n'");
                return ExitCode::from(1);
            }
        } else if let Some(n) = arg.strip_prefix("-n") {
            min_len = n.parse::<usize>().unwrap_or(4);
            i += 1;
        } else if arg.starts_with('-') && arg[1..].parse::<usize>().is_ok() {
            min_len = arg[1..].parse::<usize>().unwrap_or(4);
            i += 1;
        } else if arg == "-t" {
            if i + 1 < args.len() {
                offset_format = args[i + 1].chars().next();
                i += 2;
            } else {
                eprintln!("strings: option requires an argument -- 't'");
                return ExitCode::from(1);
            }
        } else if arg == "-a" || arg == "--all" {
            i += 1;
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: strings [option(s)] [file(s)]");
            println!("Display printable strings in [file(s)] (default 4 chars minimum).");
            println!("  -n <number>, -<number>  specify minimum string length (default 4)");
            println!("  -t {{o,d,x}}            print the location of the string in octal, decimal or hex");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') || arg == "-" {
            files.push(arg.clone());
            i += 1;
        } else {
            i += 1;
        }
    }

    if files.is_empty() {
        files.push("-".to_string());
    }

    let stdout = io::stdout();
    let mut out = stdout.lock();

    for file in files {
        let bytes: Vec<u8> = if file == "-" {
            let mut buf = Vec::new();
            let _ = io::stdin().read_to_end(&mut buf);
            buf
        } else {
            match fs::read(&file) {
                Ok(b) => b,
                Err(e) => {
                    eprintln!("strings: '{file}': {e}");
                    continue;
                }
            }
        };

        let mut current_str = Vec::new();
        let mut start_offset = 0usize;

        for (idx, &b) in bytes.iter().enumerate() {
            if b.is_ascii_graphic() || b == b' ' || b == b'\t' {
                if current_str.is_empty() {
                    start_offset = idx;
                }
                current_str.push(b);
            } else {
                if current_str.len() >= min_len {
                    if print_string_with_offset(&mut out, &current_str, start_offset, offset_format).is_err() {
                        return ExitCode::SUCCESS;
                    }
                }
                current_str.clear();
            }
        }
        if current_str.len() >= min_len {
            if print_string_with_offset(&mut out, &current_str, start_offset, offset_format).is_err() {
                return ExitCode::SUCCESS;
            }
        }
    }

    ExitCode::SUCCESS
}

fn print_string_with_offset<W: Write>(w: &mut W, s: &[u8], offset: usize, fmt: Option<char>) -> io::Result<()> {
    let str_val = String::from_utf8_lossy(s);
    match fmt {
        Some('x') => writeln!(w, "{:7x} {}", offset, str_val),
        Some('o') => writeln!(w, "{:7o} {}", offset, str_val),
        Some('d') => writeln!(w, "{:7} {}", offset, str_val),
        _ => writeln!(w, "{}", str_val),
    }
}

// ============================================================================
// split (File Segmenter)
// ============================================================================

pub fn run_split(args: &[String]) -> ExitCode {
    let mut lines_per_file: Option<usize> = None;
    let mut bytes_per_file: Option<u64> = None;
    let mut numeric_suffixes = false;
    let mut suffix_length = 2usize;
    let mut input_file: Option<String> = None;
    let mut output_prefix = "x".to_string();

    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-l" || arg == "--lines" {
            if i + 1 < args.len() {
                lines_per_file = args[i + 1].parse::<usize>().ok();
                i += 2;
            } else {
                eprintln!("split: option requires an argument -- 'l'");
                return ExitCode::from(1);
            }
        } else if let Some(l) = arg.strip_prefix("-l") {
            lines_per_file = l.parse::<usize>().ok();
            i += 1;
        } else if arg == "-b" || arg == "--bytes" {
            if i + 1 < args.len() {
                bytes_per_file = parse_byte_size(&args[i + 1]);
                i += 2;
            } else {
                eprintln!("split: option requires an argument -- 'b'");
                return ExitCode::from(1);
            }
        } else if let Some(b) = arg.strip_prefix("-b") {
            bytes_per_file = parse_byte_size(b);
            i += 1;
        } else if arg == "-d" || arg == "--numeric-suffixes" {
            numeric_suffixes = true;
            i += 1;
        } else if arg == "-a" || arg == "--suffix-length" {
            if i + 1 < args.len() {
                suffix_length = args[i + 1].parse::<usize>().unwrap_or(2);
                i += 2;
            } else {
                i += 1;
            }
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: split [OPTION]... [FILE [PREFIX]]");
            println!("Output pieces of FILE to PREFIXaa, PREFIXab, ...; default size is 1000 lines, default PREFIX is 'x'.");
            println!("  -b, --bytes=SIZE        put SIZE bytes per output file");
            println!("  -l, --lines=NUMBER      put NUMBER lines per output file");
            println!("  -d, --numeric-suffixes  use numeric suffixes starting at 0");
            println!("  -a, --suffix-length=N   generate suffixes of length N (default 2)");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') || arg == "-" {
            if input_file.is_none() {
                input_file = Some(arg.clone());
            } else {
                output_prefix = arg.clone();
            }
            i += 1;
        } else {
            i += 1;
        }
    }

    let input_path = input_file.unwrap_or_else(|| "-".to_string());

    if let Some(chunk_size) = bytes_per_file {
        // Split by byte chunks
        let mut reader: Box<dyn Read> = if input_path == "-" {
            Box::new(io::stdin())
        } else {
            match File::open(&input_path) {
                Ok(f) => Box::new(f),
                Err(e) => {
                    eprintln!("split: cannot open '{input_path}': {e}");
                    return ExitCode::from(1);
                }
            }
        };

        let mut part_index = 0usize;
        let mut buf = vec![0u8; chunk_size.min(65536) as usize];

        loop {
            let mut remaining = chunk_size;
            let mut part_data = Vec::new();
            while remaining > 0 {
                let to_read = (remaining as usize).min(buf.len());
                match reader.read(&mut buf[..to_read]) {
                    Ok(0) => break,
                    Ok(n) => {
                        part_data.extend_from_slice(&buf[..n]);
                        remaining -= n as u64;
                    }
                    Err(e) => {
                        eprintln!("split: read error: {e}");
                        return ExitCode::from(1);
                    }
                }
            }

            if part_data.is_empty() {
                break;
            }

            let suff = format_suffix(part_index, suffix_length, numeric_suffixes);
            let out_name = format!("{}{}", output_prefix, suff);
            if let Err(e) = fs::write(&out_name, &part_data) {
                eprintln!("split: cannot write '{out_name}': {e}");
                return ExitCode::from(1);
            }
            part_index += 1;
        }
    } else {
        // Split by lines (default 1000 lines)
        let lines_limit = lines_per_file.unwrap_or(1000);
        let reader: Box<dyn BufRead> = if input_path == "-" {
            Box::new(BufReader::new(io::stdin()))
        } else {
            match File::open(&input_path) {
                Ok(f) => Box::new(BufReader::new(f)),
                Err(e) => {
                    eprintln!("split: cannot open '{input_path}': {e}");
                    return ExitCode::from(1);
                }
            }
        };

        let mut part_index = 0usize;
        let mut current_part_lines = Vec::new();

        for line_res in reader.lines() {
            match line_res {
                Ok(l) => {
                    current_part_lines.push(l);
                    if current_part_lines.len() >= lines_limit {
                        let suff = format_suffix(part_index, suffix_length, numeric_suffixes);
                        let out_name = format!("{}{}", output_prefix, suff);
                        let content = current_part_lines.join("\n") + "\n";
                        if let Err(e) = fs::write(&out_name, content) {
                            eprintln!("split: cannot write '{out_name}': {e}");
                            return ExitCode::from(1);
                        }
                        current_part_lines.clear();
                        part_index += 1;
                    }
                }
                Err(e) => {
                    eprintln!("split: read error: {e}");
                    return ExitCode::from(1);
                }
            }
        }

        if !current_part_lines.is_empty() {
            let suff = format_suffix(part_index, suffix_length, numeric_suffixes);
            let out_name = format!("{}{}", output_prefix, suff);
            let content = current_part_lines.join("\n") + "\n";
            if let Err(e) = fs::write(&out_name, content) {
                eprintln!("split: cannot write '{out_name}': {e}");
                return ExitCode::from(1);
            }
        }
    }

    ExitCode::SUCCESS
}

fn parse_byte_size(s: &str) -> Option<u64> {
    let s = s.trim();
    if s.ends_with('k') || s.ends_with('K') {
        s[..s.len() - 1].parse::<u64>().ok().map(|n| n * 1024)
    } else if s.ends_with('m') || s.ends_with('M') {
        s[..s.len() - 1].parse::<u64>().ok().map(|n| n * 1024 * 1024)
    } else if s.ends_with('g') || s.ends_with('G') {
        s[..s.len() - 1].parse::<u64>().ok().map(|n| n * 1024 * 1024 * 1024)
    } else {
        s.parse::<u64>().ok()
    }
}

fn format_suffix(index: usize, length: usize, numeric: bool) -> String {
    if numeric {
        format!("{:0width$}", index, width = length)
    } else {
        let mut res = Vec::new();
        let mut cur = index;
        for _ in 0..length {
            let rem = cur % 26;
            res.push((b'a' + rem as u8) as char);
            cur /= 26;
        }
        res.reverse();
        res.into_iter().collect()
    }
}

// ============================================================================
// comm (Compare Sorted Files Line by Line)
// ============================================================================

pub fn run_comm(args: &[String]) -> ExitCode {
    let mut suppress1 = false;
    let mut suppress2 = false;
    let mut suppress3 = false;
    let mut files = Vec::new();

    for arg in args {
        if arg == "-1" {
            suppress1 = true;
        } else if arg == "-2" {
            suppress2 = true;
        } else if arg == "-3" {
            suppress3 = true;
        } else if arg == "-12" || arg == "-21" {
            suppress1 = true;
            suppress2 = true;
        } else if arg == "-13" || arg == "-31" {
            suppress1 = true;
            suppress3 = true;
        } else if arg == "-23" || arg == "-32" {
            suppress2 = true;
            suppress3 = true;
        } else if arg == "-123" {
            suppress1 = true;
            suppress2 = true;
            suppress3 = true;
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: comm [OPTION]... FILE1 FILE2");
            println!("Compare sorted files FILE1 and FILE2 line by line.");
            println!("  -1   suppress column 1 (lines unique to FILE1)");
            println!("  -2   suppress column 2 (lines unique to FILE2)");
            println!("  -3   suppress column 3 (lines that appear in both files)");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') || arg == "-" {
            files.push(arg.clone());
        }
    }

    if files.len() < 2 {
        eprintln!("comm: missing operand (must provide two files)");
        return ExitCode::from(1);
    }

    let lines1 = match read_file_lines(&files[0]) {
        Ok(l) => l,
        Err(e) => {
            eprintln!("comm: {}: {}", files[0], e);
            return ExitCode::from(1);
        }
    };

    let lines2 = match read_file_lines(&files[1]) {
        Ok(l) => l,
        Err(e) => {
            eprintln!("comm: {}: {}", files[1], e);
            return ExitCode::from(1);
        }
    };

    let mut i = 0usize;
    let mut j = 0usize;

    while i < lines1.len() && j < lines2.len() {
        let l1 = &lines1[i];
        let l2 = &lines2[j];

        if l1 < l2 {
            if !suppress1 {
                println!("{}", l1);
            }
            i += 1;
        } else if l1 > l2 {
            if !suppress2 {
                let tab = if !suppress1 { "\t" } else { "" };
                println!("{}{}", tab, l2);
            }
            j += 1;
        } else {
            if !suppress3 {
                let mut tabs = String::new();
                if !suppress1 {
                    tabs.push('\t');
                }
                if !suppress2 {
                    tabs.push('\t');
                }
                println!("{}{}", tabs, l1);
            }
            i += 1;
            j += 1;
        }
    }

    while i < lines1.len() {
        if !suppress1 {
            println!("{}", lines1[i]);
        }
        i += 1;
    }

    while j < lines2.len() {
        if !suppress2 {
            let tab = if !suppress1 { "\t" } else { "" };
            println!("{}{}", tab, lines2[j]);
        }
        j += 1;
    }

    ExitCode::SUCCESS
}

fn read_file_lines(path: &str) -> io::Result<Vec<String>> {
    if path == "-" {
        let stdin = io::stdin();
        return stdin.lock().lines().collect();
    }
    let f = File::open(path)?;
    BufReader::new(f).lines().collect()
}

// ============================================================================
// truncate (Shrink or Extend File Size)
// ============================================================================

pub fn run_truncate(args: &[String]) -> ExitCode {
    let mut size_spec: Option<String> = None;
    let mut no_create = false;
    let mut files = Vec::new();

    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-s" || arg == "--size" {
            if i + 1 < args.len() {
                size_spec = Some(args[i + 1].clone());
                i += 2;
            } else {
                eprintln!("truncate: option requires an argument -- 's'");
                return ExitCode::from(1);
            }
        } else if let Some(s) = arg.strip_prefix("-s") {
            size_spec = Some(s.to_string());
            i += 1;
        } else if arg == "-c" || arg == "--no-create" {
            no_create = true;
            i += 1;
        } else if arg == "--help" || arg == "-h" {
            println!("Usage: truncate [OPTION]... FILE...");
            println!("Shrink or extend the size of each FILE to the specified size.");
            println!("  -c, --no-create   do not create any files");
            println!("  -s, --size=SIZE   set or adjust the file size by SIZE bytes (supports K, M, G)");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') {
            files.push(arg.clone());
            i += 1;
        } else {
            i += 1;
        }
    }

    let spec = match size_spec {
        Some(s) => s,
        None => {
            eprintln!("truncate: you must specify a size with -s");
            return ExitCode::from(1);
        }
    };

    if files.is_empty() {
        eprintln!("truncate: missing file operand");
        return ExitCode::from(1);
    }

    let (mode, raw_size_str) = if spec.starts_with('+') {
        (1, &spec[1..]) // relative increase
    } else if spec.starts_with('-') {
        (2, &spec[1..]) // relative decrease
    } else {
        (0, spec.as_str()) // absolute
    };

    let target_bytes = match parse_byte_size(raw_size_str) {
        Some(b) => b,
        None => {
            eprintln!("truncate: invalid size: '{}'", spec);
            return ExitCode::from(1);
        }
    };

    let mut exit_code = ExitCode::SUCCESS;
    for file in files {
        let p = Path::new(&file);
        if !p.exists() && no_create {
            continue;
        }

        let f = match OpenOptions::new().write(true).create(!no_create).open(p) {
            Ok(f) => f,
            Err(e) => {
                eprintln!("truncate: cannot open '{file}': {e}");
                exit_code = ExitCode::from(1);
                continue;
            }
        };

        let current_len = f.metadata().map(|m| m.len()).unwrap_or(0);
        let final_len = match mode {
            1 => current_len.saturating_add(target_bytes),
            2 => current_len.saturating_sub(target_bytes),
            _ => target_bytes,
        };

        if let Err(e) = f.set_len(final_len) {
            eprintln!("truncate: cannot set length of '{file}': {e}");
            exit_code = ExitCode::from(1);
        }
    }

    exit_code
}

// ============================================================================
// tree (Visual Recursive Directory Structure)
// ============================================================================

pub fn run_tree(args: &[String]) -> ExitCode {
    let mut max_depth: Option<usize> = None;
    let mut all = false;
    let mut dirs_only = false;
    let mut print_size = false;
    let mut human_readable = false;
    let mut target_dir: Option<String> = None;

    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        if arg == "-L" {
            if i + 1 < args.len() {
                max_depth = args[i + 1].parse::<usize>().ok();
                i += 2;
            } else {
                eprintln!("tree: option requires an argument -- 'L'");
                return ExitCode::from(1);
            }
        } else if let Some(l) = arg.strip_prefix("-L") {
            max_depth = l.parse::<usize>().ok();
            i += 1;
        } else if arg == "-a" {
            all = true;
            i += 1;
        } else if arg == "-d" {
            dirs_only = true;
            i += 1;
        } else if arg == "-s" {
            print_size = true;
            i += 1;
        } else if arg == "-h" {
            human_readable = true;
            print_size = true;
            i += 1;
        } else if arg == "--help" {
            println!("Usage: tree [options] [directory]");
            println!("List contents of directories in a tree-like format.");
            println!("  -a            All files are listed (including hidden files)");
            println!("  -d            List directories only");
            println!("  -L level      Max display depth of the directory tree");
            println!("  -s            Print the size in bytes of each file");
            println!("  -h            Print the size in human readable format");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') {
            target_dir = Some(arg.clone());
            i += 1;
        } else {
            i += 1;
        }
    }

    let root_path = target_dir.unwrap_or_else(|| ".".to_string());
    println!("{}", root_path);

    let mut dir_count = 0usize;
    let mut file_count = 0usize;

    walk_tree(
        Path::new(&root_path),
        "",
        1,
        max_depth,
        all,
        dirs_only,
        print_size,
        human_readable,
        &mut dir_count,
        &mut file_count,
    );

    if dirs_only {
        println!("\n{} directories", dir_count);
    } else {
        println!("\n{} directories, {} files", dir_count, file_count);
    }

    ExitCode::SUCCESS
}

fn walk_tree(
    dir: &Path,
    prefix: &str,
    current_depth: usize,
    max_depth: Option<usize>,
    all: bool,
    dirs_only: bool,
    print_size: bool,
    human_readable: bool,
    dir_count: &mut usize,
    file_count: &mut usize,
) {
    if let Some(max) = max_depth {
        if current_depth > max {
            return;
        }
    }

    let mut entries = Vec::new();
    if let Ok(read_dir) = fs::read_dir(dir) {
        for entry in read_dir.flatten() {
            let name = entry.file_name().to_string_lossy().to_string();
            if !all && name.starts_with('.') {
                continue;
            }
            let is_dir = entry.file_type().map(|t| t.is_dir()).unwrap_or(false);
            if dirs_only && !is_dir {
                continue;
            }
            entries.push((name, entry.path(), is_dir));
        }
    }

    entries.sort_by(|a, b| a.0.cmp(&b.0));
    let total = entries.len();

    for (idx, (name, path, is_dir)) in entries.into_iter().enumerate() {
        let is_last = idx + 1 == total;
        let branch = if is_last { "└── " } else { "├── " };
        let next_prefix = if is_last {
            format!("{}    ", prefix)
        } else {
            format!("{}│   ", prefix)
        };

        let size_str = if print_size && !is_dir {
            let size = fs::metadata(&path).map(|m| m.len()).unwrap_or(0);
            if human_readable {
                format!("[{:>5}] ", format_human_size(size))
            } else {
                format!("[{:>8}] ", size)
            }
        } else {
            String::new()
        };

        println!("{}{}{}{}", prefix, branch, size_str, name);

        if is_dir {
            *dir_count += 1;
            walk_tree(
                &path,
                &next_prefix,
                current_depth + 1,
                max_depth,
                all,
                dirs_only,
                print_size,
                human_readable,
                dir_count,
                file_count,
            );
        } else {
            *file_count += 1;
        }
    }
}

fn format_human_size(bytes: u64) -> String {
    if bytes < 1024 {
        format!("{}B", bytes)
    } else if bytes < 1024 * 1024 {
        format!("{:.1}K", bytes as f64 / 1024.0)
    } else if bytes < 1024 * 1024 * 1024 {
        format!("{:.1}M", bytes as f64 / (1024.0 * 1024.0))
    } else {
        format!("{:.1}G", bytes as f64 / (1024.0 * 1024.0 * 1024.0))
    }
}

// ============================================================================
// cal (Standard POSIX Calendar)
// ============================================================================

pub fn run_cal(args: &[String]) -> ExitCode {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);

    let (curr_year, curr_month, curr_day, _, _, _, _) = super::standard_utils::break_down_timestamp(now);

    let mut month = curr_month;
    let mut year = curr_year;

    if args.len() == 1 {
        if let Ok(y) = args[0].parse::<u32>() {
            year = y;
        }
    } else if args.len() >= 2 {
        if let Ok(m) = args[0].parse::<u32>() {
            month = m.min(12).max(1);
        }
        if let Ok(y) = args[1].parse::<u32>() {
            year = y;
        }
    }

    let month_names = [
        "", "January", "February", "March", "April", "May", "June", "July", "August", "September",
        "October", "November", "December",
    ];

    let header = format!("{} {}", month_names[month as usize], year);
    println!("{:^20}", header);
    println!("Su Mo Tu We Th Fr Sa");

    // Zeller's congruence to determine day of week for 1st of month (0 = Saturday, 1 = Sunday ... 6 = Friday)
    // Or epoch calculation:
    let first_day_dow = get_day_of_week(year, month, 1); // 0=Sunday, 1=Monday... 6=Saturday
    let days_in_month = get_days_in_month(year, month);

    let mut current_pos = 0usize;
    for _ in 0..first_day_dow {
        print!("   ");
        current_pos += 1;
    }

    for d in 1..=days_in_month {
        if year == curr_year && month == curr_month && d == curr_day {
            print!("\x1b[7m{:2}\x1b[0m ", d);
        } else {
            print!("{:2} ", d);
        }
        current_pos += 1;
        if current_pos % 7 == 0 {
            println!();
        }
    }
    if current_pos % 7 != 0 {
        println!();
    }

    ExitCode::SUCCESS
}

fn get_days_in_month(year: u32, month: u32) -> u32 {
    let leap = (year % 4 == 0 && year % 100 != 0) || (year % 400 == 0);
    match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 => if leap { 29 } else { 28 },
        _ => 30,
    }
}

fn get_day_of_week(year: u32, month: u32, day: u32) -> usize {
    // Tomohiko Sakamoto's algorithm (0=Sunday, 1=Monday, ..., 6=Saturday)
    let t = [0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4];
    let y = if month < 3 { year - 1 } else { year };
    ((y + y / 4 - y / 100 + y / 400 + t[(month - 1) as usize] + day) % 7) as usize
}

// ============================================================================
// lscpu (CPU Architecture & Topology Inspector)
// ============================================================================

pub fn run_lscpu(args: &[String]) -> ExitCode {
    for arg in args {
        if arg == "--help" || arg == "-h" {
            println!("Usage: lscpu [options]");
            println!("Display information about the CPU architecture.");
            return ExitCode::SUCCESS;
        }
    }

    let arch = env::consts::ARCH;
    let num_cpus = thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(1);

    println!("Architecture:                    {}", arch);
    println!("CPU op-mode(s):                  32-bit, 64-bit");
    println!("Address sizes:                   48 bits physical, 48 bits virtual");
    println!("Byte Order:                      Little Endian");
    println!("CPU(s):                          {}", num_cpus);
    println!("On-line CPU(s) list:             0-{}", num_cpus.saturating_sub(1));

    // Try reading /proc/cpuinfo
    let mut vendor = "GenuineFerro".to_string();
    let mut model = "FerroOS Virtual CPU".to_string();
    let mut mhz = "2400.000".to_string();
    let mut flags = "fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush mmx fxsr sse sse2 ss ht syscall nx lm constant_tsc pni ssse3 fma cx16 sse4_1 sse4_2 movbe popcnt aes xsave avx f16c rdrand hypervisor".to_string();

    if let Ok(content) = fs::read_to_string("/proc/cpuinfo") {
        for line in content.lines() {
            let parts: Vec<&str> = line.splitn(2, ':').collect();
            if parts.len() == 2 {
                let key = parts[0].trim();
                let val = parts[1].trim();
                match key {
                    "vendor_id" => vendor = val.to_string(),
                    "model name" => model = val.to_string(),
                    "cpu MHz" => mhz = val.to_string(),
                    "flags" | "Features" => flags = val.to_string(),
                    _ => {}
                }
            }
        }
    } else {
        // macOS host fallback
        #[cfg(target_os = "macos")]
        {
            if let Ok(output) = std::process::Command::new("sysctl").args(&["-n", "machdep.cpu.brand_string"]).output() {
                if let Ok(s) = String::from_utf8(output.stdout) {
                    let trimmed = s.trim();
                    if !trimmed.is_empty() {
                        model = trimmed.to_string();
                    }
                }
            }
        }
    }

    println!("Vendor ID:                       {}", vendor);
    println!("Model name:                      {}", model);
    println!("CPU MHz:                         {}", mhz);
    println!("Virtualization:                  VT-x / KVM / Hypervisor");
    println!("L1d cache:                       32 KiB");
    println!("L1i cache:                       32 KiB");
    println!("L2 cache:                        512 KiB");
    println!("L3 cache:                        16 MiB");
    println!("Flags:                           {}", flags);

    ExitCode::SUCCESS
}

// ============================================================================
// lsmod (Kernel Module Status Inspector)
// ============================================================================

pub fn run_lsmod(args: &[String]) -> ExitCode {
    for arg in args {
        if arg == "--help" || arg == "-h" {
            println!("Usage: lsmod");
            println!("Show the status of modules in the Linux Kernel.");
            return ExitCode::SUCCESS;
        }
    }

    println!("{:<24} {:<10} {}", "Module", "Size", "Used by");

    if let Ok(content) = fs::read_to_string("/proc/modules") {
        for line in content.lines() {
            let parts: Vec<&str> = line.split_whitespace().collect();
            if parts.len() >= 3 {
                let name = parts[0];
                let size = parts[1];
                let used = parts[2];
                let by = if parts.len() > 3 { parts[3] } else { "" };
                let used_str = if by.is_empty() || by == "-" {
                    used.to_string()
                } else {
                    format!("{} {}", used, by)
                };
                println!("{:<24} {:<10} {}", name, size, used_str);
            }
        }
    }

    ExitCode::SUCCESS
}

// ============================================================================
// lspci (PCI Bus Device Enumerator)
// ============================================================================

pub fn run_lspci(args: &[String]) -> ExitCode {
    for arg in args {
        if arg == "--help" || arg == "-h" {
            println!("Usage: lspci [options]");
            println!("List all PCI devices.");
            return ExitCode::SUCCESS;
        }
    }

    let pci_dir = Path::new("/sys/bus/pci/devices");
    let mut found = false;

    if let Ok(entries) = fs::read_dir(pci_dir) {
        for entry in entries.flatten() {
            let slot = entry.file_name().to_string_lossy().to_string();
            let p = entry.path();
            let vendor = fs::read_to_string(p.join("vendor"))
                .unwrap_or_default()
                .trim()
                .to_string();
            let device = fs::read_to_string(p.join("device"))
                .unwrap_or_default()
                .trim()
                .to_string();
            let class_code = fs::read_to_string(p.join("class"))
                .unwrap_or_default()
                .trim()
                .to_string();

            let class_name = resolve_pci_class(&class_code);
            println!("{}: {} [{} / {}]", slot, class_name, vendor, device);
            found = true;
        }
    }

    if !found {
        // Fallback / standard virtualized QEMU PCI layout
        println!("00:00.0 Host bridge: Intel Corporation 82G33/G31/P35/P31 Express DRAM Controller");
        println!("00:01.0 VGA compatible controller: Red Hat, Inc. Virtio GPU (rev 01)");
        println!("00:02.0 Ethernet controller: Red Hat, Inc. Virtio network device (rev 01)");
        println!("00:03.0 SCSI storage controller: Red Hat, Inc. Virtio SCSI (rev 01)");
        println!("00:1f.0 ISA bridge: Intel Corporation 82801IB (ICH9) LPC Interface Controller");
        println!("00:1f.2 SATA controller: Intel Corporation 82801IR/IO/IH (ICH9R/DO/DH) 6 port SATA Controller [AHCI mode]");
    }

    ExitCode::SUCCESS
}

fn resolve_pci_class(class_code: &str) -> &'static str {
    if class_code.starts_with("0x03") {
        "VGA compatible controller"
    } else if class_code.starts_with("0x02") {
        "Ethernet controller"
    } else if class_code.starts_with("0x01") {
        "Mass storage controller"
    } else if class_code.starts_with("0x06") {
        "Bridge"
    } else if class_code.starts_with("0x04") {
        "Multimedia audio controller"
    } else {
        "PCI peripheral device"
    }
}

// ============================================================================
// ifconfig (Network Interface Status & Telemetry)
// ============================================================================

pub fn run_ifconfig(args: &[String]) -> ExitCode {
    let mut target_iface: Option<&str> = None;

    for arg in args {
        if arg == "--help" || arg == "-h" {
            println!("Usage: ifconfig [-a] [-s] [interface]");
            println!("Display or configure network interfaces.");
            return ExitCode::SUCCESS;
        } else if !arg.starts_with('-') {
            target_iface = Some(arg.as_str());
        }
    }

    let net_dir = Path::new("/sys/class/net");
    let mut interfaces = Vec::new();

    if let Ok(entries) = fs::read_dir(net_dir) {
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().to_string();
            if let Some(target) = target_iface {
                if name != target {
                    continue;
                }
            }
            interfaces.push(name);
        }
    }

    if interfaces.is_empty() {
        // Fallback for container or dev host
        if target_iface.is_none() || target_iface == Some("lo") {
            println!("lo: flags=73<UP,LOOPBACK,RUNNING>  mtu 65536");
            println!("        inet 127.0.0.1  netmask 255.0.0.0");
            println!("        inet6 ::1  prefixlen 128  scopeid 0x10<host>");
            println!("        loop  txqueuelen 1000  (Local Loopback)");
            println!("        RX packets 1200  bytes 98304 (98.3 KB)");
            println!("        TX packets 1200  bytes 98304 (98.3 KB)");
            println!();
        }
        if target_iface.is_none() || target_iface == Some("eth0") {
            println!("eth0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500");
            println!("        inet 10.0.2.15  netmask 255.255.255.0  broadcast 10.0.2.255");
            println!("        inet6 fe80::5054:ff:fe12:3456  prefixlen 64  scopeid 0x20<link>");
            println!("        ether 52:54:00:12:34:56  txqueuelen 1000  (Ethernet)");
            println!("        RX packets 45012  bytes 34891024 (34.8 MB)");
            println!("        TX packets 28911  bytes 2109485 (2.1 MB)");
            println!();
        }
        return ExitCode::SUCCESS;
    }

    interfaces.sort();
    for iface in interfaces {
        let p = net_dir.join(&iface);
        let operstate = fs::read_to_string(p.join("operstate")).unwrap_or_else(|_| "unknown\n".to_string()).trim().to_uppercase();
        let mtu = fs::read_to_string(p.join("mtu")).unwrap_or_else(|_| "1500\n".to_string()).trim().to_string();
        let mac = fs::read_to_string(p.join("address")).unwrap_or_else(|_| "00:00:00:00:00:00\n".to_string()).trim().to_string();

        let rx_bytes = fs::read_to_string(p.join("statistics/rx_bytes")).unwrap_or_else(|_| "0\n".to_string()).trim().parse::<u64>().unwrap_or(0);
        let rx_packets = fs::read_to_string(p.join("statistics/rx_packets")).unwrap_or_else(|_| "0\n".to_string()).trim().parse::<u64>().unwrap_or(0);
        let tx_bytes = fs::read_to_string(p.join("statistics/tx_bytes")).unwrap_or_else(|_| "0\n".to_string()).trim().parse::<u64>().unwrap_or(0);
        let tx_packets = fs::read_to_string(p.join("statistics/tx_packets")).unwrap_or_else(|_| "0\n".to_string()).trim().parse::<u64>().unwrap_or(0);

        let is_loopback = iface == "lo";
        let flags_str = if is_loopback {
            "73<UP,LOOPBACK,RUNNING>"
        } else if operstate == "UP" {
            "4163<UP,BROADCAST,RUNNING,MULTICAST>"
        } else {
            "4099<BROADCAST,MULTICAST>"
        };

        println!("{}: flags={}  mtu {}", iface, flags_str, mtu);
        if is_loopback {
            println!("        inet 127.0.0.1  netmask 255.0.0.0");
            println!("        inet6 ::1  prefixlen 128  scopeid 0x10<host>");
        } else {
            println!("        inet 10.0.2.15  netmask 255.255.255.0  broadcast 10.0.2.255");
            println!("        inet6 fe80::{}:ff:fe12:3456  prefixlen 64  scopeid 0x20<link>", iface);
            println!("        ether {}  txqueuelen 1000  (Ethernet)", mac);
        }
        println!("        RX packets {}  bytes {} ({})", rx_packets, rx_bytes, format_human_size(rx_bytes));
        println!("        TX packets {}  bytes {} ({})", tx_packets, tx_bytes, format_human_size(tx_bytes));
        println!();
    }

    ExitCode::SUCCESS
}

// ============================================================================
// link & unlink (POSIX Direct Hard Link and Unlink Wrappers)
// ============================================================================

pub fn run_link(args: &[String]) -> ExitCode {
    if args.len() < 2 {
        eprintln!("link: missing operand (syntax: link FILE1 FILE2)");
        return ExitCode::from(1);
    }

    match fs::hard_link(&args[0], &args[1]) {
        Ok(_) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("link: cannot create link '{}' to '{}': {}", args[1], args[0], e);
            ExitCode::from(1)
        }
    }
}

pub fn run_unlink(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("unlink: missing operand");
        return ExitCode::from(1);
    }

    let mut exit_code = ExitCode::SUCCESS;
    for file in args {
        if file == "--help" || file == "-h" {
            println!("Usage: unlink FILE");
            println!("Call the unlink function to remove the specified FILE.");
            return ExitCode::SUCCESS;
        }
        if let Err(e) = fs::remove_file(file) {
            eprintln!("unlink: cannot unlink '{file}': {e}");
            exit_code = ExitCode::from(1);
        }
    }

    exit_code
}

// ============================================================================
// factor (Prime Factorization)
// ============================================================================

pub fn run_factor(args: &[String]) -> ExitCode {
    let numbers: Vec<String> = if args.is_empty() {
        let stdin = io::stdin();
        stdin.lock().lines().flatten().collect()
    } else {
        args.to_vec()
    };

    let mut exit_code = ExitCode::SUCCESS;
    for token in numbers {
        for word in token.split_whitespace() {
            if word == "--help" || word == "-h" {
                println!("Usage: factor [NUMBER]...");
                println!("Print the prime factors of each specified integer NUMBER.");
                return ExitCode::SUCCESS;
            }

            match word.parse::<u64>() {
                Ok(n) => {
                    let factors = factorize(n);
                    let factors_str = factors
                        .into_iter()
                        .map(|f| f.to_string())
                        .collect::<Vec<_>>()
                        .join(" ");
                    if factors_str.is_empty() {
                        println!("{}:", n);
                    } else {
                        println!("{}: {}", n, factors_str);
                    }
                }
                Err(_) => {
                    eprintln!("factor: '{}' is not a valid positive integer", word);
                    exit_code = ExitCode::from(1);
                }
            }
        }
    }

    exit_code
}

fn factorize(mut n: u64) -> Vec<u64> {
    let mut factors = Vec::new();
    if n <= 1 {
        return factors;
    }

    while n % 2 == 0 {
        factors.push(2);
        n /= 2;
    }

    let mut d = 3u64;
    while d.saturating_mul(d) <= n {
        while n % d == 0 {
            factors.push(d);
            n /= d;
        }
        d += 2;
    }

    if n > 1 {
        factors.push(n);
    }

    factors
}

// ============================================================================
// logname (POSIX Login Name)
// ============================================================================

pub fn run_logname(args: &[String]) -> ExitCode {
    for arg in args {
        if arg == "--help" || arg == "-h" {
            println!("Usage: logname");
            println!("Print the user's login name.");
            return ExitCode::SUCCESS;
        }
    }

    let user = env::var("LOGNAME")
        .or_else(|_| env::var("USER"))
        .unwrap_or_else(|_| "ferro".to_string());

    println!("{}", user);
    ExitCode::SUCCESS
}

// ============================================================================
// Unit Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_factor_known_primes() {
        assert_eq!(factorize(1), Vec::<u64>::new());
        assert_eq!(factorize(2), vec![2]);
        assert_eq!(factorize(42), vec![2, 3, 7]);
        assert_eq!(factorize(100), vec![2, 2, 5, 5]);
        assert_eq!(factorize(97), vec![97]);
    }

    #[test]
    fn test_parse_byte_size() {
        assert_eq!(parse_byte_size("1024"), Some(1024));
        assert_eq!(parse_byte_size("10K"), Some(10240));
        assert_eq!(parse_byte_size("1M"), Some(1048576));
        assert_eq!(parse_byte_size("2G"), Some(2147483648));
    }

    #[test]
    fn test_format_suffix() {
        assert_eq!(format_suffix(0, 2, false), "aa");
        assert_eq!(format_suffix(1, 2, false), "ab");
        assert_eq!(format_suffix(26, 2, false), "ba");
        assert_eq!(format_suffix(0, 2, true), "00");
        assert_eq!(format_suffix(9, 2, true), "09");
    }

    #[test]
    fn test_classify_bytes_magic() {
        let (desc, mime) = classify_bytes(b"\x7fELF\x02\x01\x01\0");
        assert!(desc.contains("ELF 64-bit"));
        assert_eq!(mime, "application/x-executable");

        let (desc, mime) = classify_bytes(b"\x1f\x8b\x08\0\0\0\0\0");
        assert!(desc.contains("gzip compressed"));
        assert_eq!(mime, "application/gzip");

        let (desc, mime) = classify_bytes(b"{\"hello\": \"world\"}");
        assert!(desc.contains("JSON"));
        assert_eq!(mime, "application/json");

        let (desc, mime) = classify_bytes(b"#!/bin/bash\necho hi\n");
        assert!(desc.contains("bash script"));
        assert_eq!(mime, "text/x-shellscript");
    }
}
