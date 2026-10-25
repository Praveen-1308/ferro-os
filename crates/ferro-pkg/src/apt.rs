//! Debian `apt` Fallback Wrapper & Repository Engine (PKG-002 & PKG-004).
//!
//! Provides seamless hybrid package management:
//! - If a requested package is not a native `.rpk` recipe, delegates to Debian `apt-get`.
//! - Searches Debian package database via `apt-cache search`.
//! - Manages updates (`rpk update`) and system-wide upgrades (`rpk upgrade`).
//! - Implements `rpk upgrade --security` targeting Debian security updates.

use std::fs;
use std::io;
use std::path::Path;
use std::process::Command;

use crate::safeguards::privileged_command;
use crate::transaction::{compute_package_diff, query_installed_apt_packages};

/// Check if Debian's `apt-get` package manager is present on the system.
pub fn is_apt_available() -> bool {
    Command::new("apt-get").arg("--version").output().is_ok()
}

/// Ensure apt package lists exist, running `apt-get update` automatically if empty.
pub fn ensure_apt_updated_if_needed() -> io::Result<()> {
    let lists_dir = Path::new("/var/lib/apt/lists");
    let needs_update = if lists_dir.exists() {
        let count = fs::read_dir(lists_dir)?
            .flatten()
            .filter(|e| {
                let name = e.file_name().to_string_lossy().to_string();
                name != "lock" && name != "partial"
            })
            .count();
        count == 0
    } else {
        true
    };

    if needs_update {
        println!("⚡ [RPK Hybrid Engine] Initializing Debian Bookworm package index cache...");
        let mut cmd = privileged_command("apt-get");
        cmd.arg("update");
        cmd.env("DEBIAN_FRONTEND", "noninteractive");
        let _ = cmd.status();
    }
    Ok(())
}

/// Search Debian package repositories via `apt-cache search`.
pub fn apt_search(query: &str) -> io::Result<Vec<(String, String)>> {
    let mut results = Vec::new();
    let mut cmd = Command::new("apt-cache");
    cmd.args(["search", query]);

    if let Ok(output) = cmd.output() {
        if output.status.success() {
            let text = String::from_utf8_lossy(&output.stdout);
            for line in text.lines() {
                if let Some((pkg, desc)) = line.split_once(" - ") {
                    results.push((pkg.trim().to_string(), desc.trim().to_string()));
                }
            }
        }
    }
    Ok(results)
}

/// Install one or more packages via Debian `apt-get install -y`.
/// Returns the list of newly installed packages.
pub fn apt_install(packages: &[String], _root: &Path) -> Result<Vec<String>, String> {
    if packages.is_empty() {
        return Ok(Vec::new());
    }

    let _ = ensure_apt_updated_if_needed();

    let before_packages = query_installed_apt_packages();

    println!("⚡ [RPK Hybrid Engine] Delegating to Debian Bookworm substrate: apt-get install -y");
    for p in packages {
        println!("  • Requesting: {}", p);
    }

    let mut cmd = privileged_command("apt-get");
    cmd.args(["install", "-y"]);
    cmd.args(packages);
    cmd.env("DEBIAN_FRONTEND", "noninteractive");

    match cmd.status() {
        Ok(status) => {
            if status.success() {
                let after_packages = query_installed_apt_packages();
                let newly_installed = compute_package_diff(&before_packages, &after_packages);
                println!(
                    "✅ [RPK Hybrid Engine] Successfully installed {} packages (including dependencies).",
                    newly_installed.len()
                );
                Ok(newly_installed)
            } else {
                Err(format!(
                    "apt-get install failed with exit code: {:?}",
                    status.code()
                ))
            }
        }
        Err(e) => Err(format!("Failed to execute apt-get: {}", e)),
    }
}

/// Update local Debian package metadata via `apt-get update`.
pub fn apt_update() -> Result<(), String> {
    println!("⚡ [rpk update] Synchronizing FerroOS & Debian Bookworm package indexes...");
    let mut cmd = privileged_command("apt-get");
    cmd.arg("update");
    cmd.env("DEBIAN_FRONTEND", "noninteractive");

    match cmd.status() {
        Ok(s) if s.success() => {
            println!("✅ Package index cache successfully updated.");
            Ok(())
        }
        Ok(s) => Err(format!("apt-get update failed: {:?}", s.code())),
        Err(e) => Err(format!("Failed executing apt-get update: {}", e)),
    }
}

/// Identify pending security update packages by simulating an upgrade.
pub fn find_pending_security_packages() -> Vec<String> {
    let mut sec_pkgs = Vec::new();
    let mut cmd = Command::new("apt-get");
    cmd.args(["-s", "upgrade"]);

    if let Ok(output) = cmd.output() {
        if output.status.success() {
            let text = String::from_utf8_lossy(&output.stdout);
            for line in text.lines() {
                // e.g.: "Inst perl-base [5.36.0-7+deb12u3] (5.36.0-7+deb12u4 Debian-Security:12/oldstable-security [arm64])"
                if line.starts_with("Inst ")
                    && (line.contains("Debian-Security:") || line.contains("security"))
                {
                    let parts: Vec<&str> = line.split_whitespace().collect();
                    if parts.len() >= 2 {
                        sec_pkgs.push(parts[1].to_string());
                    }
                }
            }
        }
    }
    sec_pkgs.sort();
    sec_pkgs.dedup();
    sec_pkgs
}

/// Upgrade packages across the Debian substrate.
/// If `security_only` is true (PKG-004), restricts strictly to Debian security advisories.
pub fn apt_upgrade(security_only: bool) -> Result<(Vec<String>, Vec<String>), String> {
    let _ = ensure_apt_updated_if_needed();
    let before_packages = query_installed_apt_packages();

    if security_only {
        println!("🛡️  [PKG-004] Auditing pending Debian Security Advisories (bookworm-security)...");
        let security_pkgs = find_pending_security_packages();

        if security_pkgs.is_empty() {
            println!("✅ System pristine: All security advisories are up-to-date. Zero patches pending.");
            return Ok((Vec::new(), Vec::new()));
        }

        println!(
            "  • Found {} pending security patches: {:?}",
            security_pkgs.len(),
            security_pkgs
        );

        let mut cmd = privileged_command("apt-get");
        cmd.args(["install", "-y", "--only-upgrade"]);
        cmd.args(&security_pkgs);
        cmd.env("DEBIAN_FRONTEND", "noninteractive");

        match cmd.status() {
            Ok(s) if s.success() => {
                let after_packages = query_installed_apt_packages();
                let newly_installed = compute_package_diff(&before_packages, &after_packages);
                println!(
                    "✅ [PKG-004] Successfully applied {} security updates.",
                    security_pkgs.len()
                );
                Ok((newly_installed, security_pkgs))
            }
            Ok(s) => Err(format!("Security upgrade failed: {:?}", s.code())),
            Err(e) => Err(format!("Failed executing apt-get: {}", e)),
        }
    } else {
        println!("⚡ [rpk upgrade] Performing full system upgrade (FerroOS + Debian substrate)...");
        let mut cmd = privileged_command("apt-get");
        cmd.args(["upgrade", "-y"]);
        cmd.env("DEBIAN_FRONTEND", "noninteractive");

        match cmd.status() {
            Ok(s) if s.success() => {
                let after_packages = query_installed_apt_packages();
                let newly_installed = compute_package_diff(&before_packages, &after_packages);
                println!("✅ Full system upgrade completed successfully.");
                Ok((newly_installed, Vec::new()))
            }
            Ok(s) => Err(format!("apt-get upgrade failed: {:?}", s.code())),
            Err(e) => Err(format!("Failed executing apt-get upgrade: {}", e)),
        }
    }
}
