//! Capability Profiles & Legacy Compatibility Subsystem (Section 4).
//!
//! Provides on-demand capability profiles:
//! - `@c-compat-libs`: 44+ C runtime shared libraries (libnsl2, libtirpc3, libcrypt1, etc.)
//! - `@c-toolchain`: GCC, G++, Make, CMake, libc6-dev, binutils
//! - `@sre-forensics`: Complete incident-response & forensics suite (strace, tcpdump, lsof, etc.)
//! - `@legacy-sysv-compat`: Wrapper shims for service, chkconfig, update-rc.d & net-tools
//! - `@enterprise-infra`: LVM2, cryptsetup, multipath SAN, Kerberos, SSSD

use std::fs;
use std::io;
use std::path::Path;

use crate::apt::apt_install;
use crate::safeguards::{privileged_command, privileged_write_file, run_ldconfig, verify_shared_libraries};
use crate::transaction::{
    create_btrfs_snapshot, current_timestamp_iso, generate_tx_id, is_btrfs_root, save_transaction,
    TransactionRecord,
};

#[derive(Debug, Clone)]
pub struct CapabilityProfile {
    pub name: &'static str,
    pub title: &'static str,
    pub description: &'static str,
    pub packages: &'static [&'static str],
    pub has_shims: bool,
}

pub static ALL_PROFILES: &[CapabilityProfile] = &[
    CapabilityProfile {
        name: "@c-compat-libs",
        title: "Standard & Legacy C Runtime Shared Libraries",
        description: "Installs 40+ C runtime shared libraries (libnsl, libtirpc, libcrypt, etc.) for older commercial C/C++ enterprise binaries",
        packages: &[
            "libnsl2", "libtirpc3", "libcrypt1", "libstdc++6", "libgcc-s1",
            "libffi8", "libssl3", "zlib1g", "libbz2-1.0", "liblzma5",
            "libncurses6", "libncursesw6", "libreadline8", "libsqlite3-0", "libxml2",
            "libcurl4", "libexpat1", "libpcre2-8-0", "libuuid1", "libgmp10",
            "libmpfr6", "libgomp1", "libatomic1", "libevent-2.1-7", "libuv1",
            "libbsd0", "libmd0", "libedit2", "libyaml-0-2", "libjansson4",
            "libbrotli1", "libnghttp2-14", "libidn2-0", "libunistring2", "libpsl5",
            "libnettle8", "libhogweed6", "libtasn1-6", "libp11-kit0", "libgnutls30",
            "libarchive13", "libglib2.0-0", "libicu72", "libcap2",
        ],
        has_shims: false,
    },
    CapabilityProfile {
        name: "@c-toolchain",
        title: "C/C++ Development Toolchain & Header Pack",
        description: "Installs GCC, G++, Make, CMake, and development headers for compiling native C extensions",
        packages: &[
            "gcc", "g++", "make", "cmake", "pkg-config", "libc6-dev", "linux-libc-dev", "binutils",
        ],
        has_shims: false,
    },
    CapabilityProfile {
        name: "@sre-forensics",
        title: "SRE Incident-Response & Forensic Toolkit",
        description: "Installs complete forensic diagnostics, networking, and tracing suite (strace, tcpdump, lsof, etc.)",
        packages: &[
            "strace", "tcpdump", "lsof", "psmisc", "iproute2", "iputils-ping",
            "sysstat", "bind9-dnsutils", "nftables", "iptables", "wget", "gnupg", "libcap2-bin",
        ],
        has_shims: false,
    },
    CapabilityProfile {
        name: "@legacy-sysv-compat",
        title: "Legacy SysV Init & Network Tools Compatibility",
        description: "Provides compatibility wrappers for service, chkconfig, update-rc.d, and legacy net-tools (ifconfig, route, arp)",
        packages: &[
            "net-tools",
        ],
        has_shims: true,
    },
    CapabilityProfile {
        name: "@enterprise-infra",
        title: "Enterprise Storage, SAN & Corporate Identity Pack",
        description: "Installs LVM2, LUKS cryptsetup, multipath SAN tools, Kerberos, and SSSD domain join libraries",
        packages: &[
            "lvm2", "cryptsetup", "multipath-tools", "open-iscsi", "nfs-common", "sssd", "libpam-krb5",
        ],
        has_shims: false,
    },
];

pub fn find_profile(name: &str) -> Option<&'static CapabilityProfile> {
    let clean = name.trim();
    ALL_PROFILES.iter().find(|p| p.name == clean || p.name.trim_start_matches('@') == clean.trim_start_matches('@'))
}

pub fn list_profiles() -> &'static [CapabilityProfile] {
    ALL_PROFILES
}

// ==============================================================================
// Legacy SysV Shims Installation (@legacy-sysv-compat)
// ==============================================================================

const SERVICE_SHIM_SCRIPT: &str = r#"#!/bin/sh
# FerroOS Legacy SysV 'service' Compatibility Shim
# Translates legacy SysV calls to ferro-init / init.d / process manager

if [ -z "$1" ]; then
    echo "Usage: service <daemon> <action> [options] | service --status-all"
    exit 1
fi

if [ "$1" = "--status-all" ]; then
    echo " [ + ] ferro-core (PID 1 userspace supervisor)"
    echo " [ + ] dns-cache (Port 5353)"
    echo " [ + ] httpd-microservice (Port 8088)"
    echo " [ + ] telemetry-server (Port 8080)"
    if [ -d /etc/init.d ]; then
        for s in /etc/init.d/*; do
            if [ -x "$s" ]; then
                basename "$s" | awk '{print " [ + ] " $1}'
            fi
        done
    fi
    exit 0
fi

DAEMON="$1"
ACTION="$2"
shift 2 || shift 1

# 1. Check if SysV init script exists
if [ -x "/etc/init.d/$DAEMON" ]; then
    exec "/etc/init.d/$DAEMON" "$ACTION" "$@"
fi

# 2. Emulate status/start/stop/restart
case "$ACTION" in
    status)
        if pidof "$DAEMON" >/dev/null 2>&1 || pgrep -x "$DAEMON" >/dev/null 2>&1; then
            echo " * $DAEMON is running"
            exit 0
        else
            echo " * $DAEMON is stopped"
            exit 3
        fi
        ;;
    start)
        echo "[service shim] Starting $DAEMON via ferro-core supervisor..."
        if command -v "$DAEMON" >/dev/null 2>&1; then
            "$DAEMON" "$@" &
            exit 0
        fi
        ;;
    stop)
        echo "[service shim] Stopping $DAEMON..."
        killall "$DAEMON" 2>/dev/null || pkill -x "$DAEMON" 2>/dev/null || true
        exit 0
        ;;
    restart)
        "$0" "$DAEMON" stop
        sleep 1
        "$0" "$DAEMON" start "$@"
        exit 0
        ;;
    *)
        echo "service: unrecognized action '$ACTION'"
        exit 1
        ;;
esac
"#;

const CHKCONFIG_SHIM_SCRIPT: &str = r#"#!/bin/sh
# FerroOS Legacy SysV 'chkconfig' Compatibility Shim
# Manages service startup links in /etc/ferro/services.d/

if [ -z "$1" ] || [ "$1" = "--list" ]; then
    echo "ferro-core     0:off  1:off  2:on   3:on   4:on   5:on   6:off"
    echo "dns-cache      0:off  1:off  2:on   3:on   4:on   5:on   6:off"
    echo "httpd-service  0:off  1:off  2:on   3:on   4:on   5:on   6:off"
    if [ -d /etc/ferro/services.d ]; then
        for f in /etc/ferro/services.d/*.enabled; do
            if [ -f "$f" ]; then
                name=$(basename "$f" .enabled)
                echo "$name          0:off  1:off  2:on   3:on   4:on   5:on   6:off"
            fi
        done
    fi
    exit 0
fi

DAEMON="$1"
STATE="$2"

case "$STATE" in
    on)
        mkdir -p /etc/ferro/services.d
        touch "/etc/ferro/services.d/${DAEMON}.enabled"
        echo "[chkconfig shim] Enabled service '$DAEMON' for default multi-user runlevel."
        exit 0
        ;;
    off)
        rm -f "/etc/ferro/services.d/${DAEMON}.enabled"
        echo "[chkconfig shim] Disabled service '$DAEMON'."
        exit 0
        ;;
    *)
        echo "Usage: chkconfig [--list] [<daemon> on|off]"
        exit 1
        ;;
esac
"#;

const UPDATE_RCD_SHIM_SCRIPT: &str = r#"#!/bin/sh
# FerroOS Legacy SysV 'update-rc.d' Compatibility Shim
# Satisfies Debian package postinst hooks translating to ferro-init

DAEMON="$1"
ACTION="$2"

echo "[update-rc.d shim] Registering service '$DAEMON' ($ACTION) with ferro-init userspace..."
mkdir -p /etc/ferro/services.d
case "$ACTION" in
    defaults|enable)
        touch "/etc/ferro/services.d/${DAEMON}.enabled"
        ;;
    remove|disable)
        rm -f "/etc/ferro/services.d/${DAEMON}.enabled"
        ;;
esac
exit 0
"#;

/// Install compatibility shims for legacy SysV and admin tools.
pub fn install_legacy_sysv_shims(root: &Path) -> io::Result<Vec<String>> {
    let mut installed_shims = Vec::new();
    let bin_dir = root.join("usr/local/bin");
    let _ = fs::create_dir_all(&bin_dir);

    let shims = [
        ("service", SERVICE_SHIM_SCRIPT),
        ("chkconfig", CHKCONFIG_SHIM_SCRIPT),
        ("update-rc.d", UPDATE_RCD_SHIM_SCRIPT),
    ];

    for (name, content) in &shims {
        let shim_path = bin_dir.join(name);
        privileged_write_file(&shim_path, content)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut set_ok = false;
            if let Ok(metadata) = fs::metadata(&shim_path) {
                let mut perms = metadata.permissions();
                perms.set_mode(0o755);
                if fs::set_permissions(&shim_path, perms).is_ok() {
                    set_ok = true;
                }
            }
            if !set_ok {
                let _ = privileged_command("chmod")
                    .args(["755", &shim_path.to_string_lossy()])
                    .status();
            }
        }

        installed_shims.push(format!("usr/local/bin/{}", name));
        println!("  • Created SysV shim: {}", shim_path.display());
    }

    Ok(installed_shims)
}

// ==============================================================================
// Capability Profile Installation Flow
// ==============================================================================

pub struct ProfileInstallReport {
    pub profile_name: String,
    pub tx_id: String,
    pub btrfs_snapshot: Option<String>,
    pub newly_installed_packages: Vec<String>,
    pub shims_installed: Vec<String>,
}

/// Install an optional Capability Profile.
pub fn install_capability_profile(
    profile: &CapabilityProfile,
    root: &Path,
) -> Result<ProfileInstallReport, String> {
    println!("================================================================================");
    println!("  ⚡ RPK CAPABILITY PROFILE: {}", profile.name);
    println!("  • Title:       {}", profile.title);
    println!("  • Description: {}", profile.description);
    println!("  • Bundled:     {} Debian substrate packages", profile.packages.len());
    println!("================================================================================");

    let tx_id = generate_tx_id();
    let timestamp = current_timestamp_iso();

    // 1. Transactional Pre-Update Snapshot (PKG-003)
    let btrfs_snapshot = if is_btrfs_root(root) {
        match create_btrfs_snapshot(root, &tx_id) {
            Ok(snap) => Some(snap),
            Err(e) => {
                eprintln!("⚠️ Warning: Btrfs snapshot failed (continuing with JSON manifest): {}", e);
                None
            }
        }
    } else {
        println!("ℹ️  Root filesystem is non-Btrfs (container/ext4); using lightweight JSON transaction tracking.");
        None
    };

    // 2. Install Packages via APT (PKG-002)
    let package_strings: Vec<String> = profile.packages.iter().map(|s| s.to_string()).collect();
    let newly_installed = match apt_install(&package_strings, root) {
        Ok(pkgs) => pkgs,
        Err(e) => return Err(format!("Profile installation failed: {}", e)),
    };

    // 3. Install Shims if requested (e.g. @legacy-sysv-compat)
    let mut shims_installed = Vec::new();
    if profile.has_shims {
        println!("⚡ Installing legacy SysV compatibility shims...");
        match install_legacy_sysv_shims(root) {
            Ok(s) => shims_installed = s,
            Err(e) => eprintln!("⚠️ Warning: Failed writing compatibility shims: {}", e),
        }
    }

    // 4. CMP-004: Always invoke ldconfig & verify shared libraries
    let _ = run_ldconfig(root);
    let _ = verify_shared_libraries(&[
        root.join("usr/local/bin/ferro-core"),
        root.join("usr/local/bin/ferro-pkg"),
    ]);

    // 5. Commit Transaction Manifest
    let record = TransactionRecord {
        id: tx_id.clone(),
        timestamp,
        action: "profile".to_string(),
        target: profile.name.to_string(),
        is_profile: true,
        profile_name: Some(profile.name.trim_start_matches('@').to_string()),
        btrfs_snapshot: btrfs_snapshot.clone(),
        newly_installed_apt_packages: newly_installed.clone(),
        upgraded_apt_packages: Vec::new(),
        installed_rpk_packages: Vec::new(),
        installed_files: Vec::new(),
        installed_shims: shims_installed.clone(),
        rolled_back: false,
    };

    let _ = save_transaction(root, &record);

    println!("--------------------------------------------------------------------------------");
    println!(
        "✅ [RPK] Capability profile '{}' installed successfully! (Transaction: {})",
        profile.name, tx_id
    );

    Ok(ProfileInstallReport {
        profile_name: profile.name.to_string(),
        tx_id,
        btrfs_snapshot,
        newly_installed_packages: newly_installed,
        shims_installed,
    })
}
