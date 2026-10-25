//! CMP-003 and CMP-004 Safeguards for FerroOS Package Engine.
//!
//! CMP-003: Check binary ELF requirements (`glibc` version) to prevent
//! launches failing with `version 'GLIBC_2.38' not found` on Debian 12 Bookworm (glibc 2.36).
//!
//! CMP-004: Always invoke `ldconfig` automatically after package or profile installations
//! and verify dynamic linker integrity (unresolved shared libraries check).

use std::fmt;
use std::fs::{self, File};
use std::io::{self, Read};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

// ==============================================================================
// Glibc Version Representation & Parsing
// ==============================================================================

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct GlibcVersion {
    pub major: u32,
    pub minor: u32,
}

impl GlibcVersion {
    pub const fn new(major: u32, minor: u32) -> Self {
        Self { major, minor }
    }

    pub fn parse_str(s: &str) -> Option<Self> {
        let clean = s.trim();
        let target = if let Some(stripped) = clean.strip_prefix("GLIBC_") {
            stripped
        } else {
            clean
        };

        let mut parts = target.split('.');
        let major = parts.next()?.parse::<u32>().ok()?;
        let minor_part = parts.next()?;
        // Take digits only in case of suffixes like "2.36-9+deb12u14"
        let minor_digits: String = minor_part.chars().take_while(|c| c.is_ascii_digit()).collect();
        let minor = minor_digits.parse::<u32>().ok()?;
        Some(Self { major, minor })
    }
}

impl fmt::Display for GlibcVersion {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}.{}", self.major, self.minor)
    }
}

// ==============================================================================
// CMP-003: Host Glibc Detection & Foreign ELF Requirements Check
// ==============================================================================

#[cfg(all(target_os = "linux", target_env = "gnu"))]
extern "C" {
    fn gnu_get_libc_version() -> *const libc::c_char;
}

/// Detect the host glibc version.
/// On Debian 12 (Bookworm), this is 2.36.
pub fn get_host_glibc_version() -> GlibcVersion {
    #[cfg(all(target_os = "linux", target_env = "gnu"))]
    {
        unsafe {
            let ptr = gnu_get_libc_version();
            if !ptr.is_null() {
                if let Ok(s) = std::ffi::CStr::from_ptr(ptr).to_str() {
                    if let Some(v) = GlibcVersion::parse_str(s) {
                        return v;
                    }
                }
            }
        }
    }

    // Attempt 1: Parse from ldd --version
    if let Ok(output) = Command::new("ldd").arg("--version").output() {
        if output.status.success() {
            let text = String::from_utf8_lossy(&output.stdout);
            if let Some(first_line) = text.lines().next() {
                // e.g., "ldd (Debian GLIBC 2.36-9+deb12u14) 2.36"
                for word in first_line.split_whitespace().rev() {
                    if let Some(v) = GlibcVersion::parse_str(word) {
                        return v;
                    }
                }
            }
        }
    }

    // Attempt 2: Probe libc.so.6 symlink or file
    let candidate_paths = [
        "/lib/aarch64-linux-gnu/libc.so.6",
        "/lib/x86_64-linux-gnu/libc.so.6",
        "/lib64/libc.so.6",
        "/lib/libc.so.6",
    ];

    for path_str in &candidate_paths {
        let p = Path::new(path_str);
        if let Ok(target) = std::fs::read_link(p) {
            let target_str = target.to_string_lossy();
            // e.g. "libc-2.36.so"
            if let Some(pos) = target_str.find("libc-") {
                let sub = &target_str[pos + 5..];
                if let Some(v) = GlibcVersion::parse_str(sub) {
                    return v;
                }
            }
        }
    }

    // Default Debian 12 Bookworm baseline
    GlibcVersion::new(2, 36)
}

/// Scan an ELF binary for all referenced `GLIBC_X.Y` symbol versions,
/// returning the maximum required GLIBC version if it is an ELF file.
pub fn scan_elf_glibc_requirements(file_path: &Path) -> io::Result<Option<GlibcVersion>> {
    let mut file = File::open(file_path)?;
    let mut header = [0u8; 4];
    if file.read_exact(&mut header).is_err() {
        return Ok(None);
    }

    // Check ELF magic: 0x7F, 'E', 'L', 'F'
    if header != [0x7f, b'E', b'L', b'F'] {
        return Ok(None);
    }

    // Read file contents (limit scan to 16MB for safety)
    let file_len = file.metadata()?.len();
    let read_limit = std::cmp::min(file_len, 16 * 1024 * 1024) as usize;
    let mut buffer = Vec::with_capacity(read_limit);
    buffer.extend_from_slice(&header);

    let mut remaining = vec![0u8; read_limit - 4];
    let bytes_read = file.read(&mut remaining)?;
    buffer.extend_from_slice(&remaining[..bytes_read]);

    let mut max_version: Option<GlibcVersion> = None;

    // Scan for ASCII "GLIBC_" pattern
    let needle = b"GLIBC_";
    let mut i = 0;
    while i + needle.len() < buffer.len() {
        if &buffer[i..i + needle.len()] == needle {
            let start = i + needle.len();
            let mut end = start;
            while end < buffer.len() && end < start + 12 {
                let b = buffer[end];
                if b.is_ascii_digit() || b == b'.' {
                    end += 1;
                } else {
                    break;
                }
            }
            if end > start {
                if let Ok(ver_str) = std::str::from_utf8(&buffer[start..end]) {
                    if let Some(v) = GlibcVersion::parse_str(ver_str) {
                        max_version = match max_version {
                            None => Some(v),
                            Some(current) => Some(std::cmp::max(current, v)),
                        };
                    }
                }
            }
            i = end;
        } else {
            i += 1;
        }
    }

    Ok(max_version)
}

/// CMP-003 Guard: Verify an ELF binary does not exceed host glibc capability.
pub fn verify_elf_glibc_compat(file_path: &Path, force: bool) -> Result<Option<GlibcVersion>, String> {
    match scan_elf_glibc_requirements(file_path) {
        Ok(Some(required)) => {
            let host = get_host_glibc_version();
            if required > host {
                let msg = format!(
                    "CMP-003 Safeguard: Binary '{}' requires GLIBC_{} which exceeds host glibc ({}) on Debian 12 Bookworm. Execution may fail with 'version GLIBC_{} not found'.",
                    file_path.display(),
                    required,
                    host,
                    required
                );
                if force {
                    eprintln!("⚠️  [CMP-003 Warning] {} (--force / --allow-foreign active, proceeding anyway)", msg);
                    Ok(Some(required))
                } else {
                    Err(format!("{}\nTo override, pass --allow-foreign-glibc or --force.", msg))
                }
            } else {
                Ok(Some(required))
            }
        }
        Ok(None) => Ok(None),
        Err(_e) => {
            // Non-critical if not an ELF file or cannot read
            Ok(None)
        }
    }
}

// ==============================================================================
// CMP-004: Shared-Library Cache (ldconfig) & Dynamic Link Integrity Checks
// ==============================================================================

/// Check if running as root or need sudo elevation.
pub fn needs_elevation() -> bool {
    #[cfg(unix)]
    {
        unsafe { libc::geteuid() != 0 }
    }
    #[cfg(not(unix))]
    {
        false
    }
}

/// Helper to build a command with sudo if non-root and sudo exists.
pub fn privileged_command(cmd: &str) -> Command {
    if needs_elevation() && which_bin("sudo").is_some() {
        let mut c = Command::new("sudo");
        c.arg("-n");
        c.arg(cmd);
        c
    } else {
        Command::new(cmd)
    }
}

/// Helper to write a file with sudo elevation if standard write fails due to permissions.
pub fn privileged_write_file(target: &Path, content: &str) -> io::Result<()> {
    if let Some(parent) = target.parent() {
        if fs::create_dir_all(parent).is_err() && needs_elevation() {
            let _ = privileged_command("mkdir")
                .args(["-p", &parent.to_string_lossy()])
                .status();
            let _ = privileged_command("chmod")
                .args(["777", &parent.to_string_lossy()])
                .status();
        }
    }

    if fs::write(target, content).is_err() && needs_elevation() {
        let temp_file = std::env::temp_dir().join(format!(
            "ferro_tmp_{}_{}",
            std::process::id(),
            SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_nanos()
        ));
        fs::write(&temp_file, content)?;
        let _ = privileged_command("cp")
            .arg(&temp_file)
            .arg(target)
            .status();
        let _ = privileged_command("chmod")
            .args(["666", &target.to_string_lossy()])
            .status();
        let _ = fs::remove_file(&temp_file);
    }
    Ok(())
}

fn which_bin(name: &str) -> Option<PathBuf> {
    if let Ok(paths) = std::env::var("PATH") {
        for dir in std::env::split_paths(&paths) {
            let candidate = dir.join(name);
            if candidate.is_file() {
                return Some(candidate);
            }
        }
    }
    None
}

/// CMP-004 Guard: Automatically rebuild the dynamic linker cache via `ldconfig`.
pub fn run_ldconfig(root: &Path) -> Result<(), String> {
    println!("[CMP-004] Rebuilding dynamic shared library cache (/etc/ld.so.cache)...");

    let ldconfig_bin = which_bin("ldconfig")
        .or_else(|| {
            let candidates = ["/sbin/ldconfig", "/usr/sbin/ldconfig"];
            candidates.iter().map(Path::new).find(|p| p.is_file()).map(Path::to_path_buf)
        });

    let bin_path = match ldconfig_bin {
        Some(b) => b,
        None => {
            println!("  ℹ️  ldconfig not found on system path; skipping cache rebuild.");
            return Ok(());
        }
    };

    let mut cmd = privileged_command(&bin_path.to_string_lossy());
    if root != Path::new("/") {
        cmd.arg("-r").arg(root);
    }

    match cmd.status() {
        Ok(status) => {
            if status.success() {
                println!("  ✅ ldconfig cache successfully rebuilt.");
                Ok(())
            } else {
                Err(format!("ldconfig exited with error status: {:?}", status.code()))
            }
        }
        Err(e) => Err(format!("Failed to execute ldconfig: {}", e)),
    }
}

/// Checks dynamic links of an ELF executable or shared library using `ldd`.
/// Returns a list of unresolved shared libraries (`not found`).
pub fn check_binary_dynamic_links(bin_path: &Path) -> Vec<String> {
    let mut unresolved = Vec::new();
    if !bin_path.is_file() {
        return unresolved;
    }

    if let Ok(output) = Command::new("ldd").arg(bin_path).output() {
        if output.status.success() {
            let text = String::from_utf8_lossy(&output.stdout);
            for line in text.lines() {
                if line.contains("not found") {
                    let parts: Vec<&str> = line.split_whitespace().collect();
                    if let Some(first) = parts.first() {
                        unresolved.push(first.to_string());
                    } else {
                        unresolved.push(line.trim().to_string());
                    }
                }
            }
        }
    }

    unresolved
}

/// CMP-004 Guard: Verify shared library dependencies across target binaries.
pub fn verify_shared_libraries(check_bins: &[PathBuf]) -> Result<usize, String> {
    println!("[CMP-004] Auditing shared library resolution integrity...");
    let mut broken_total = 0;

    for bin in check_bins {
        if !bin.exists() {
            continue;
        }
        let missing = check_binary_dynamic_links(bin);
        if !missing.is_empty() {
            eprintln!(
                "  ❌ Broken dynamic link in '{}': Missing libraries: {:?}",
                bin.display(),
                missing
            );
            broken_total += missing.len();
        }
    }

    if broken_total == 0 {
        println!("  ✅ Dynamic linker cache updated & 0 unresolved shared library links.");
        Ok(0)
    } else {
        Err(format!(
            "CMP-004 Integrity Alert: Found {} unresolved shared library dependencies!",
            broken_total
        ))
    }
}

// ==============================================================================
// Unit Tests
// ==============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_glibc_version_parsing_and_ordering() {
        let v236 = GlibcVersion::parse_str("2.36").unwrap();
        let v238 = GlibcVersion::parse_str("GLIBC_2.38").unwrap();
        let v217 = GlibcVersion::parse_str("2.17-0ubuntu1").unwrap();

        assert_eq!(v236, GlibcVersion::new(2, 36));
        assert_eq!(v238, GlibcVersion::new(2, 38));
        assert_eq!(v217, GlibcVersion::new(2, 17));

        assert!(v236 < v238);
        assert!(v238 > v236);
        assert!(v217 < v236);
        assert_eq!(v236.to_string(), "2.36");
    }

    #[test]
    fn test_host_glibc_detection() {
        let host = get_host_glibc_version();
        // Major version must be at least 2
        assert!(host.major >= 2);
    }

    #[test]
    fn test_synthetic_elf_glibc_scanning() {
        let mut synthetic_elf = vec![0x7f, b'E', b'L', b'F', 0, 0, 0, 0];
        // Embed some symbol strings
        synthetic_elf.extend_from_slice(b"\0GLIBC_2.17\0GLIBC_2.34\0GLIBC_2.38\0");

        let temp_path = std::env::temp_dir().join("ferro_test_synthetic.elf");
        std::fs::write(&temp_path, &synthetic_elf).unwrap();

        let req = scan_elf_glibc_requirements(&temp_path).unwrap();
        assert_eq!(req, Some(GlibcVersion::new(2, 38)));

        let _ = std::fs::remove_file(temp_path);
    }
}
