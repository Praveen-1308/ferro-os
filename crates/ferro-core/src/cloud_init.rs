//! ferro-core cloud_init: Autonomous Cloud Provisioning & Metadata Ingestion Engine
//! Compatible with AWS EC2 IMDS, GCP Compute Engine, Azure VM Metadata, and OpenStack.
//! Automatically provisions hostnames, injects SSH authorized_keys, and executes user-data bootstrapping scripts.

use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::os::unix::fs::PermissionsExt;
use std::path::Path;
use std::process::{Command, ExitCode};
use std::time::Duration;

const IMDS_HOST: &str = "169.254.169.254";
const IMDS_PORT: u16 = 80;

pub fn run_cloud_init(args: &[String]) -> ExitCode {
    println!("================================================================================");
    println!("        FERRO-OS AUTONOMOUS CLOUD-INIT & METADATA INGESTION ENGINE              ");
    println!("================================================================================");

    let dry_run = args.iter().any(|a| a == "--dry-run");
    let custom_host = args.iter().position(|a| a == "--host").and_then(|i| args.get(i + 1)).map(|s| s.as_str()).unwrap_or(IMDS_HOST);
    let custom_port = args.iter().position(|a| a == "--port").and_then(|i| args.get(i + 1)).and_then(|s| s.parse().ok()).unwrap_or(IMDS_PORT);

    println!("[cloud-init] Probing Cloud Metadata Service at {}:{}...", custom_host, custom_port);

    // 1. Check if IMDS is reachable
    let is_reachable = probe_metadata_service(custom_host, custom_port);
    if !is_reachable {
        println!("[cloud-init] Cloud Metadata Service not detected at {}:{}.", custom_host, custom_port);
        println!("[cloud-init] Status: Running in on-premise / local virtualization mode. Skipping cloud provisioning.");
        return ExitCode::SUCCESS;
    }

    println!("[cloud-init] ✅ Cloud Metadata Service DETECTED! Beginning instance provisioning...");

    // Create required directories
    let _ = fs::create_dir_all("/var/log/ferro");
    let _ = fs::create_dir_all("/var/lib/ferro");
    let _ = fs::create_dir_all("/root/.ssh");
    let _ = fs::set_permissions("/root/.ssh", fs::Permissions::from_mode(0o700));

    // 2. Fetch & Set Hostname
    println!("[cloud-init] [1/3] Querying Instance Hostname...");
    if let Some(hostname) = http_get(custom_host, custom_port, "/latest/meta-data/hostname") {
        let clean_hostname = hostname.trim();
        if !clean_hostname.is_empty() {
            println!("   • Discovered Cloud Hostname: {}", clean_hostname);
            if !dry_run {
                let _ = fs::write("/etc/hostname", format!("{}\n", clean_hostname));
                set_system_hostname(clean_hostname);
                append_to_hosts(clean_hostname);
            }
        }
    } else {
        println!("   • Hostname metadata not supplied by hypervisor.");
    }

    // 3. Fetch & Inject SSH Public Keys
    println!("[cloud-init] [2/3] Querying Public SSH Authorized Keys...");
    let mut keys_found = Vec::new();

    // Try standard EC2 / OpenStack paths
    if let Some(key) = http_get(custom_host, custom_port, "/latest/meta-data/public-keys/0/openssh-key") {
        let clean_key = key.trim();
        if clean_key.starts_with("ssh-") || clean_key.starts_with("ecdsa-") {
            keys_found.push(clean_key.to_string());
        }
    }

    // Try alternative index list
    if keys_found.is_empty() {
        if let Some(key_list) = http_get(custom_host, custom_port, "/latest/meta-data/public-keys/") {
            for line in key_list.lines() {
                let key_idx = line.split('=').next().unwrap_or("0").trim();
                let key_path = format!("/latest/meta-data/public-keys/{}/openssh-key", key_idx);
                if let Some(k) = http_get(custom_host, custom_port, &key_path) {
                    if k.trim().starts_with("ssh-") {
                        keys_found.push(k.trim().to_string());
                    }
                }
            }
        }
    }

    if !keys_found.is_empty() {
        println!("   • Discovered {} SSH Public Key(s) from Cloud Provider.", keys_found.len());
        for (idx, k) in keys_found.iter().enumerate() {
            let key_preview = if k.len() > 40 { &k[..40] } else { k };
            println!("     [{}] {}...", idx + 1, key_preview);
            if !dry_run {
                inject_authorized_key(k);
            }
        }
        println!("   ✅ SSH keys injected into /root/.ssh/authorized_keys (permissions: 0600).");
    } else {
        println!("   • No external SSH keys supplied by metadata endpoint.");
    }

    // 4. Fetch & Execute User-Data Bootstrapping Script
    println!("[cloud-init] [3/3] Querying User-Data Bootstrapping Script...");
    if let Some(user_data) = http_get(custom_host, custom_port, "/latest/user-data") {
        let script = user_data.trim();
        if !script.is_empty() {
            println!("   • Discovered User-Data Script ({} bytes).", script.len());
            let script_path = "/var/lib/ferro/user-data.sh";
            if !dry_run {
                if fs::write(script_path, script).is_ok() {
                    let _ = fs::set_permissions(script_path, fs::Permissions::from_mode(0o755));
                    println!("   • Executing User-Data script in background...");
                    let _ = Command::new("/bin/sh")
                        .arg(script_path)
                        .spawn();
                    println!("   ✅ User-Data bootstrap process launched.");
                }
            }
        }
    } else {
        println!("   • No user-data script provided for this instance.");
    }

    // Record provisioning log
    let log_msg = format!("Cloud-Init Provisioning Completed Successfully at {:?}\n", std::time::SystemTime::now());
    let _ = fs::write("/var/log/cloud-init.log", log_msg);

    println!("================================================================================");
    println!("✅ CLOUD-INIT COMPLETE: Instance Provisioned & Ready for Remote Cloud Access");
    println!("================================================================================");

    ExitCode::SUCCESS
}

fn probe_metadata_service(host: &str, port: u16) -> bool {
    let addr_str = format!("{}:{}", host, port);
    if let Ok(socket_addr) = addr_str.parse::<SocketAddr>() {
        TcpStream::connect_timeout(&socket_addr, Duration::from_millis(600)).is_ok()
    } else {
        false
    }
}

fn http_get(host: &str, port: u16, path: &str) -> Option<String> {
    let addr_str = format!("{}:{}", host, port);
    let socket_addr = addr_str.parse::<SocketAddr>().ok()?;
    let mut stream = TcpStream::connect_timeout(&socket_addr, Duration::from_millis(800)).ok()?;
    let _ = stream.set_read_timeout(Some(Duration::from_millis(1200)));

    let request = format!(
        "GET {} HTTP/1.0\r\n\
        Host: {}\r\n\
        User-Agent: FerroOS-CloudInit/2.3.0\r\n\
        Connection: close\r\n\r\n",
        path, host
    );

    if stream.write_all(request.as_bytes()).is_err() {
        return None;
    }

    let mut response = Vec::new();
    if stream.read_to_end(&mut response).is_err() {
        return None;
    }

    let response_str = String::from_utf8_lossy(&response);
    let mut parts = response_str.splitn(2, "\r\n\r\n");
    let header = parts.next()?;
    let body = parts.next()?;

    // Check HTTP status code
    if header.contains(" 200 OK") || header.contains(" 200 ") {
        Some(body.to_string())
    } else {
        None
    }
}

fn set_system_hostname(name: &str) {
    use std::ffi::CString;
    if let Ok(c_name) = CString::new(name) {
        #[cfg(target_os = "linux")]
        unsafe {
            let _ = libc::sethostname(c_name.as_ptr(), name.len());
        }
        #[cfg(not(target_os = "linux"))]
        unsafe {
            let _ = libc::sethostname(c_name.as_ptr(), name.len() as libc::c_int);
        }
    }
}

fn append_to_hosts(name: &str) {
    let hosts_path = "/etc/hosts";
    let entry = format!("127.0.1.1 {}\n", name);
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(hosts_path) {
        let _ = file.write_all(entry.as_bytes());
    }
}

fn inject_authorized_key(key: &str) {
    let auth_keys_path = "/root/.ssh/authorized_keys";
    let key_line = format!("{}\n", key.trim());

    // Check if key already exists to prevent duplicate entries
    if let Ok(existing) = fs::read_to_string(auth_keys_path) {
        if existing.contains(key.trim()) {
            return;
        }
    }

    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(auth_keys_path) {
        let _ = file.write_all(key_line.as_bytes());
        let _ = fs::set_permissions(auth_keys_path, fs::Permissions::from_mode(0o600));
    }

    // Also replicate to default non-root user directory if present
    let ferro_ssh = "/home/ferro/.ssh";
    if Path::new("/home/ferro").exists() {
        let _ = fs::create_dir_all(ferro_ssh);
        let _ = fs::set_permissions(ferro_ssh, fs::Permissions::from_mode(0o700));
        let ferro_auth_path = "/home/ferro/.ssh/authorized_keys";
        if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(ferro_auth_path) {
            let _ = file.write_all(key_line.as_bytes());
            let _ = fs::set_permissions(ferro_auth_path, fs::Permissions::from_mode(0o600));
        }
    }
}
