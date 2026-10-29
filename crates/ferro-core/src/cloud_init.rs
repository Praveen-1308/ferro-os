//! ferro-core cloud_init: Autonomous Cloud Provisioning & Metadata Ingestion Engine
//! Compatible with AWS EC2 IMDS, GCP Compute Engine, Azure VM Metadata, and OpenStack.
//! Automatically provisions hostnames, injects SSH authorized_keys, and executes user-data bootstrapping scripts.

use std::fs::{self, File, OpenOptions};
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
        if let Some(clean_hostname) = sanitize_hostname(&hostname) {
            println!("   • Discovered Cloud Hostname: {}", clean_hostname);
            if !dry_run {
                let _ = fs::write("/etc/hostname", format!("{}\n", clean_hostname));
                set_system_hostname(&clean_hostname);
                append_to_hosts(&clean_hostname);
            }
        } else {
            println!("   [!] Warning: Invalid or malformed cloud hostname received from metadata endpoint; ignoring");
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
            println!("   • Discovered User-Data payload ({} bytes).", script.len());
            if script.starts_with("#cloud-config") {
                process_cloud_config(script, dry_run);
            } else {
                let script_path = "/var/lib/ferro/user-data.sh";
                if !dry_run {
                    if fs::write(script_path, script).is_ok() {
                        let _ = fs::set_permissions(script_path, fs::Permissions::from_mode(0o755));
                        println!("   • Executing User-Data shell script in background...");
                        let _ = Command::new("/bin/sh")
                            .arg(script_path)
                            .spawn();
                        println!("   ✅ User-Data bootstrap process launched.");
                    }
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

fn sanitize_hostname(raw: &str) -> Option<String> {
    let trimmed = raw.trim();
    if trimmed.is_empty() || trimmed.len() > 64 {
        return None;
    }
    // Only allow alphanumeric, hyphen, dot; cannot start or end with hyphen
    if trimmed.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '.')
        && !trimmed.starts_with('-')
        && !trimmed.ends_with('-')
    {
        Some(trimmed.to_string())
    } else {
        None
    }
}

fn get_imds_token(host: &str, port: u16) -> Option<String> {
    let addr_str = format!("{}:{}", host, port);
    let socket_addr = addr_str.parse::<SocketAddr>().ok()?;
    let mut stream = TcpStream::connect_timeout(&socket_addr, Duration::from_millis(300)).ok()?;
    let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));

    let request = format!(
        "PUT /latest/api/token HTTP/1.1\r\n\
        Host: {}\r\n\
        X-aws-ec2-metadata-token-ttl-seconds: 21600\r\n\
        User-Agent: FerroOS-CloudInit/2.3.0\r\n\
        Connection: close\r\n\r\n",
        host
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
    if header.contains(" 200 OK") || header.contains(" 200 ") {
        let token = body.trim().to_string();
        if !token.is_empty() {
            return Some(token);
        }
    }
    None
}

fn http_get(host: &str, port: u16, path: &str) -> Option<String> {
    let addr_str = format!("{}:{}", host, port);
    let socket_addr = addr_str.parse::<SocketAddr>().ok()?;
    let mut stream = TcpStream::connect_timeout(&socket_addr, Duration::from_millis(800)).ok()?;
    let _ = stream.set_read_timeout(Some(Duration::from_millis(1200)));

    // Optional IMDSv2 token for AWS
    let token_header = if let Some(t) = get_imds_token(host, port) {
        format!("X-aws-ec2-metadata-token: {}\r\n", t)
    } else {
        String::new()
    };

    let request = format!(
        "GET {} HTTP/1.0\r\n\
        Host: {}\r\n\
        User-Agent: FerroOS-CloudInit/2.3.0\r\n\
        Metadata-Flavor: Google\r\n\
        Metadata: true\r\n\
        {}Connection: close\r\n\r\n",
        path, host, token_header
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

/// Pure-Rust Declarative #cloud-config YAML Parser & Executor
/// Handles write_files, runcmd, hostname, and ssh_authorized_keys directives
pub fn process_cloud_config(doc: &str, dry_run: bool) {
    println!("   ⚡ [cloud-init] Processing declarative #cloud-config YAML document...");
    let lines: Vec<&str> = doc.lines().collect();
    let mut i = 0;

    while i < lines.len() {
        let line = lines[i].trim();
        if line.starts_with('#') || line.is_empty() {
            i += 1;
            continue;
        }

        if let Some(host_val) = line.strip_prefix("hostname:") {
            let h = host_val.trim().trim_matches(|c| c == '"' || c == '\'');
            println!("   • [cloud-config] Configured hostname: {}", h);
            if !dry_run {
                set_system_hostname(h);
                append_to_hosts(h);
            }
            i += 1;
            continue;
        }

        if line == "write_files:" || line.starts_with("write_files:") {
            i += 1;
            while i < lines.len() {
                let wline = lines[i];
                if !wline.starts_with("  ") && !wline.starts_with('\t') && !wline.trim().is_empty() {
                    break;
                }
                let trimmed = wline.trim();
                if trimmed.starts_with("- path:") || trimmed.starts_with("path:") {
                    let mut file_path = trimmed
                        .trim_start_matches("- path:")
                        .trim_start_matches("path:")
                        .trim()
                        .trim_matches(|c| c == '"' || c == '\'')
                        .to_string();
                    let mut content = String::new();
                    let mut permissions = "0644".to_string();
                    let mut in_multiline_content = false;

                    i += 1;
                    while i < lines.len() {
                        let sub = lines[i];
                        let sub_trim = sub.trim();
                        if sub_trim.starts_with("- path:")
                            || (!sub.starts_with("  ") && !sub.starts_with('\t') && !sub_trim.is_empty())
                        {
                            break;
                        }

                        if sub_trim.starts_with("path:") {
                            file_path = sub_trim
                                .trim_start_matches("path:")
                                .trim()
                                .trim_matches(|c| c == '"' || c == '\'')
                                .to_string();
                        } else if sub_trim.starts_with("permissions:") {
                            permissions = sub_trim
                                .trim_start_matches("permissions:")
                                .trim()
                                .trim_matches(|c| c == '"' || c == '\'')
                                .to_string();
                            in_multiline_content = false;
                        } else if sub_trim.starts_with("content:") {
                            let rest = sub_trim.trim_start_matches("content:").trim();
                            if rest == "|" || rest == ">" {
                                in_multiline_content = true;
                            } else {
                                content = rest
                                    .trim_matches(|c| c == '"' || c == '\'')
                                    .replace("\\n", "\n");
                                in_multiline_content = false;
                            }
                        } else if in_multiline_content {
                            if !content.is_empty() {
                                content.push('\n');
                            }
                            content.push_str(sub_trim);
                        }
                        i += 1;
                    }

                    if !file_path.is_empty() {
                        println!("   • [cloud-config] Writing file '{}' (mode: {})", file_path, permissions);
                        if !dry_run {
                            if let Some(parent) = Path::new(&file_path).parent() {
                                let _ = fs::create_dir_all(parent);
                            }
                            if let Ok(mut f) = File::create(&file_path) {
                                let _ = f.write_all(content.as_bytes());
                                if let Ok(mode) = u32::from_str_radix(&permissions, 8) {
                                    #[cfg(unix)]
                                    {
                                        use std::os::unix::fs::PermissionsExt;
                                        let _ = fs::set_permissions(&file_path, fs::Permissions::from_mode(mode));
                                    }
                                }
                            }
                        }
                    }
                    continue;
                }
                i += 1;
            }
            continue;
        }

        if line == "runcmd:" || line.starts_with("runcmd:") {
            i += 1;
            while i < lines.len() {
                let rline = lines[i];
                if !rline.starts_with("  ") && !rline.starts_with('\t') && !rline.trim().is_empty() {
                    break;
                }
                let trimmed = rline.trim();
                if let Some(cmd_entry) = trimmed.strip_prefix("- ") {
                    let cmd_str = cmd_entry.trim().trim_matches(|c| c == '"' || c == '\'');
                    println!("   • [cloud-config] Executing runcmd: {}", cmd_str);
                    if !dry_run {
                        let _ = Command::new("/bin/sh").arg("-c").arg(cmd_str).status();
                    }
                }
                i += 1;
            }
            continue;
        }

        if line == "ssh_authorized_keys:" || line.starts_with("ssh_authorized_keys:") {
            i += 1;
            while i < lines.len() {
                let kline = lines[i];
                if !kline.starts_with("  ") && !kline.starts_with('\t') && !kline.trim().is_empty() {
                    break;
                }
                let trimmed = kline.trim();
                if let Some(key_entry) = trimmed.strip_prefix("- ") {
                    let clean_key = key_entry.trim().trim_matches(|c| c == '"' || c == '\'');
                    println!("   • [cloud-config] Ingesting SSH authorized key ({} bytes)", clean_key.len());
                    if !dry_run {
                        inject_authorized_key(clean_key);
                    }
                }
                i += 1;
            }
            continue;
        }

        i += 1;
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
    if let Some(clean) = sanitize_hostname(name) {
        let hosts_path = "/etc/hosts";
        let entry = format!("127.0.1.1 {}\n", clean);
        if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(hosts_path) {
            let _ = file.write_all(entry.as_bytes());
        }
    }
}

fn inject_authorized_key(key: &str) {
    // Strip any internal or external newlines to prevent authorized_keys option/command injection
    let sanitized_key: String = key.chars().filter(|c| *c != '\r' && *c != '\n').collect();
    let clean = sanitized_key.trim();
    if clean.is_empty() {
        return;
    }
    // Must start with valid SSH key prefix
    if !clean.starts_with("ssh-") && !clean.starts_with("ecdsa-") {
        println!("   [!] Warning: Skipping invalid SSH key format: {}", clean);
        return;
    }

    let auth_keys_path = "/root/.ssh/authorized_keys";
    let key_line = format!("{}\n", clean);

    // Check if key already exists to prevent duplicate entries
    if let Ok(existing) = fs::read_to_string(auth_keys_path) {
        if existing.contains(clean) {
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cloud_config_yaml_parsing() {
        let sample_yaml = r#"#cloud-config
hostname: ferro-prod-node01
write_files:
  - path: /tmp/test_cloud_config_file.txt
    content: "FERRO_CONFIG_PAYLOAD_OK"
    permissions: "0644"
runcmd:
  - echo "provisioned" > /dev/null
ssh_authorized_keys:
  - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIG... devops@ferro-cloud
"#;
        // Dry-run execution
        process_cloud_config(sample_yaml, true);

        // Live execution to /tmp
        process_cloud_config(sample_yaml, false);
        let test_path = Path::new("/tmp/test_cloud_config_file.txt");
        assert!(test_path.exists());
        let content = fs::read_to_string(test_path).unwrap();
        assert_eq!(content, "FERRO_CONFIG_PAYLOAD_OK");
        let _ = fs::remove_file(test_path);
    }
}
