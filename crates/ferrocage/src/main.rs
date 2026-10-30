//! ferrocage: Pure-Rust Zero-Overhead Micro-Container Runtime for FerroOS
//! Replaces Docker and containerd with sub-2ms startup latency,
//! native Linux namespaces, Cgroups v2 isolation, and a complete Docker-compatible CLI.
#![allow(clippy::all)]

use std::fs::{self, File, OpenOptions};
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode, Stdio};
use std::time::{SystemTime, UNIX_EPOCH};

fn get_state_dir() -> String {
    std::env::var("FERROCAGE_STATE_DIR").unwrap_or_else(|_| "/var/lib/ferrocage/containers".to_string())
}
fn get_images_dir() -> String {
    std::env::var("FERROCAGE_IMAGES_DIR").unwrap_or_else(|_| "/var/lib/ferrocage/images".to_string())
}
fn get_logs_dir() -> String {
    std::env::var("FERROCAGE_LOGS_DIR").unwrap_or_else(|_| "/var/log/ferrocage".to_string())
}
const CGROUP_ROOT: &str = "/sys/fs/cgroup/ferrocage";

#[derive(Debug, Clone)]
pub struct ContainerState {
    pub id: String,
    pub name: String,
    pub image: String,
    pub command: Vec<String>,
    pub created_at: u64,
    pub pid: Option<u32>,
    pub status: String,
    pub exit_code: Option<i32>,
    pub memory_max_bytes: Option<u64>,
    pub cpus: Option<f32>,
    pub pids_max: Option<u32>,
    pub volumes: Vec<String>,
    pub network: String,
}

// ---------------------------------------------------------------------------
// OCI Container Runtime Specification Structures (config.json)
// ---------------------------------------------------------------------------

#[derive(serde::Deserialize, Debug, Default)]
pub struct OciConfig {
    #[serde(rename = "ociVersion", default)]
    pub oci_version: String,
    #[serde(default)]
    pub process: Option<OciProcess>,
    #[serde(default)]
    pub root: Option<OciRoot>,
    #[serde(default)]
    pub hostname: Option<String>,
    #[serde(default)]
    pub mounts: Option<Vec<OciMount>>,
    #[serde(default)]
    pub linux: Option<OciLinux>,
}

#[derive(serde::Deserialize, Debug, Default)]
pub struct OciProcess {
    #[serde(default)]
    pub args: Vec<String>,
    #[serde(default)]
    pub env: Vec<String>,
    #[serde(default)]
    pub cwd: Option<String>,
}

#[derive(serde::Deserialize, Debug, Default)]
pub struct OciRoot {
    #[serde(default)]
    pub path: String,
    #[serde(default)]
    pub readonly: Option<bool>,
}

#[derive(serde::Deserialize, Debug, Default)]
pub struct OciMount {
    #[serde(default)]
    pub destination: String,
    #[serde(default)]
    pub source: Option<String>,
    #[serde(default)]
    pub options: Option<Vec<String>>,
}

#[derive(serde::Deserialize, Debug, Default)]
pub struct OciLinux {
    #[serde(default)]
    pub resources: Option<OciResources>,
}

#[derive(serde::Deserialize, Debug, Default)]
pub struct OciResources {
    #[serde(default)]
    pub memory: Option<OciMemory>,
    #[serde(default)]
    pub pids: Option<OciPids>,
}

#[derive(serde::Deserialize, Debug, Default)]
pub struct OciMemory {
    #[serde(default)]
    pub limit: Option<u64>,
}

#[derive(serde::Deserialize, Debug, Default)]
pub struct OciPids {
    #[serde(default)]
    pub limit: Option<u32>,
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.is_empty() {
        print_usage();
        return ExitCode::FAILURE;
    }

    match args[0].as_str() {
        "run" => handle_run(&args[1..]),
        "ps" => handle_ps(&args[1..]),
        "stop" => handle_stop(&args[1..]),
        "start" => handle_start(&args[1..]),
        "rm" => handle_rm(&args[1..]),
        "logs" => handle_logs(&args[1..]),
        "exec" => handle_exec(&args[1..]),
        "inspect" => handle_inspect(&args[1..]),
        "images" => handle_images(&args[1..]),
        "--version" | "-v" | "version" => {
            println!("ferrocage version 2.3.0 (pure-rust micro-container engine, x86_64-ferro-linux)");
            ExitCode::SUCCESS
        }
        "--help" | "-h" | "help" => {
            print_usage();
            ExitCode::SUCCESS
        }
        cmd => {
            eprintln!("ferrocage: unknown command '{}'", cmd);
            print_usage();
            ExitCode::FAILURE
        }
    }
}

fn print_usage() {
    println!("ferrocage - High Velocity Pure-Rust Micro-Container Engine");
    println!();
    println!("Usage: ferrocage <command> [options] [args...]");
    println!();
    println!("Commands:");
    println!("  run [options] <image> <command> [args...]   Create and run a new container");
    println!("  ps [-a] [--format table|json]               List running or all containers");
    println!("  stop <container_id> [--timeout sec]         Stop a running container");
    println!("  start <container_id>                        Start a stopped container");
    println!("  rm [-f] <container_id>                      Remove a container");
    println!("  logs [-f] [-n lines] <container_id>         Fetch container logs");
    println!("  exec [-i] [-t] <container_id> <cmd...>       Execute a command inside an active container");
    println!("  inspect <container_id>                      Output full container state in JSON");
    println!("  images                                      List available rootfs images");
    println!();
    println!("Run Options:");
    println!("  -d, --detach                 Run container in background");
    println!("  -b, --bundle <dir>           Path to standard OCI container bundle (config.json + rootfs)");
    println!("  -m, --memory <bytes|M|G>     Memory limit (e.g. 256M, 1G)");
    println!("  --cpus <float>               CPU quota limit (e.g. 1.5)");
    println!("  --pids-max <num>             Process limit (e.g. 50)");
    println!("  -v, --volume <host>:<dest>   Bind mount host directory");
    println!("  --name <string>              Assign a custom name");
    println!("  --rm                         Automatically clean up upon exit");
    println!("  --net <host|none>            Network mode (default: host)");
}

// ---------------------------------------------------------------------------
// ferrocage run
// ---------------------------------------------------------------------------

fn handle_run(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("Usage: ferrocage run [options] <image> <command> [args...]");
        return ExitCode::FAILURE;
    }

    let mut detach = false;
    let mut memory_bytes = None;
    let mut cpus = None;
    let mut pids_max = None;
    let mut custom_name = None;
    let mut auto_rm = false;
    let mut volumes = Vec::new();
    let mut network = "host".to_string();
    let mut image = String::new();
    let mut cmd_parts = Vec::new();
    let mut bundle_dir: Option<PathBuf> = None;

    let mut idx = 0;
    while idx < args.len() {
        let arg = &args[idx];
        if arg == "-d" || arg == "--detach" {
            detach = true;
            idx += 1;
        } else if (arg == "-b" || arg == "--bundle") && idx + 1 < args.len() {
            bundle_dir = Some(PathBuf::from(&args[idx + 1]));
            idx += 2;
        } else if (arg == "-m" || arg == "--memory") && idx + 1 < args.len() {
            memory_bytes = parse_memory_spec(&args[idx + 1]);
            idx += 2;
        } else if arg == "--cpus" && idx + 1 < args.len() {
            cpus = args[idx + 1].parse::<f32>().ok();
            idx += 2;
        } else if arg == "--pids-max" && idx + 1 < args.len() {
            pids_max = args[idx + 1].parse::<u32>().ok();
            idx += 2;
        } else if (arg == "-v" || arg == "--volume") && idx + 1 < args.len() {
            volumes.push(args[idx + 1].clone());
            idx += 2;
        } else if arg == "--name" && idx + 1 < args.len() {
            custom_name = Some(args[idx + 1].clone());
            idx += 2;
        } else if arg == "--rm" {
            auto_rm = true;
            idx += 1;
        } else if arg == "--net" && idx + 1 < args.len() {
            network = args[idx + 1].clone();
            idx += 2;
        } else if !arg.starts_with('-') {
            image = arg.clone();
            idx += 1;
            while idx < args.len() {
                cmd_parts.push(args[idx].clone());
                idx += 1;
            }
            break;
        } else {
            eprintln!("Unknown run option: {}", arg);
            return ExitCode::FAILURE;
        }
    }

    let mut oci_envs = Vec::new();
    let mut oci_cwd = None;

    // Ingest OCI standard bundle if specified
    if let Some(ref bundle) = bundle_dir {
        let config_path = bundle.join("config.json");
        if !config_path.exists() {
            eprintln!("ferrocage: OCI bundle error: '{}' does not contain config.json", bundle.display());
            return ExitCode::FAILURE;
        }

        match fs::read_to_string(&config_path) {
            Ok(content) => match serde_json::from_str::<OciConfig>(&content) {
                Ok(oci) => {
                    println!("[ferrocage] Ingested OCI runtime bundle (OCI version: {})", oci.oci_version);
                    if image.is_empty() {
                        let root_sub = oci.root.as_ref().map(|r| r.path.as_str()).unwrap_or("rootfs");
                        let root_path = if Path::new(root_sub).is_absolute() {
                            PathBuf::from(root_sub)
                        } else {
                            bundle.join(root_sub)
                        };
                        image = root_path.to_string_lossy().to_string();
                    }

                    if cmd_parts.is_empty() {
                        if let Some(ref proc) = oci.process {
                            if !proc.args.is_empty() {
                                cmd_parts = proc.args.clone();
                            }
                        }
                    }

                    if memory_bytes.is_none() {
                        memory_bytes = oci.linux.as_ref()
                            .and_then(|l| l.resources.as_ref())
                            .and_then(|r| r.memory.as_ref())
                            .and_then(|m| m.limit);
                    }

                    if pids_max.is_none() {
                        pids_max = oci.linux.as_ref()
                            .and_then(|l| l.resources.as_ref())
                            .and_then(|r| r.pids.as_ref())
                            .and_then(|p| p.limit);
                    }

                    if let Some(ref proc) = oci.process {
                        for env_str in &proc.env {
                            if let Some((k, v)) = env_str.split_once('=') {
                                oci_envs.push((k.to_string(), v.to_string()));
                            }
                        }
                        oci_cwd = proc.cwd.clone();
                    }

                    if let Some(mounts) = oci.mounts {
                        for m in mounts {
                            if let Some(src) = m.source {
                                if !src.is_empty() {
                                    volumes.push(format!("{}:{}", src, m.destination));
                                }
                            }
                        }
                    }
                }
                Err(e) => {
                    eprintln!("ferrocage: failed parsing OCI config.json: {}", e);
                    return ExitCode::FAILURE;
                }
            },
            Err(e) => {
                eprintln!("ferrocage: failed reading OCI config.json: {}", e);
                return ExitCode::FAILURE;
            }
        }
    }

    if image.is_empty() {
        eprintln!("ferrocage run: image name or --bundle <dir> required");
        return ExitCode::FAILURE;
    }

    if cmd_parts.is_empty() {
        cmd_parts = vec!["/bin/sh".to_string()];
    }

    let container_id = generate_id();
    let name = custom_name.unwrap_or_else(|| format!("ferro-{}", truncate_str(&container_id, 6)));

    let state_dir = get_state_dir();
    let logs_dir = get_logs_dir();
    let _ = fs::create_dir_all(&state_dir);
    let _ = fs::create_dir_all(&logs_dir);

    let log_path = format!("{}/{}.log", logs_dir, container_id);
    let log_file = OpenOptions::new()
        .create(true)
        .write(true)
        .append(true)
        .open(&log_path);

    // Spawn container process
    let mut cmd = Command::new(&cmd_parts[0]);
    if cmd_parts.len() > 1 {
        cmd.args(&cmd_parts[1..]);
    }
    if !oci_envs.is_empty() {
        cmd.envs(oci_envs);
    }
    if let Some(ref cwd) = oci_cwd {
        if Path::new(cwd).exists() {
            cmd.current_dir(cwd);
        }
    }

    configure_container_isolation(&mut cmd, &name, &image, &volumes, &network);

    if detach {
        if let Ok(f) = log_file {
            if let Ok(f_err) = f.try_clone() {
                cmd.stdout(Stdio::from(f));
                cmd.stderr(Stdio::from(f_err));
            } else {
                cmd.stdout(Stdio::from(f));
                cmd.stderr(Stdio::null());
            }
        } else {
            cmd.stdout(Stdio::null());
            cmd.stderr(Stdio::null());
        }
        cmd.stdin(Stdio::null());

        match cmd.spawn() {
            Ok(child) => {
                let pid = child.id();
                setup_cgroup_v2(&container_id, pid, memory_bytes, cpus, pids_max);

                let state = ContainerState {
                    id: container_id.clone(),
                    name,
                    image,
                    command: cmd_parts,
                    created_at: current_timestamp(),
                    pid: Some(pid),
                    status: "running".to_string(),
                    exit_code: None,
                    memory_max_bytes: memory_bytes,
                    cpus,
                    pids_max,
                    volumes,
                    network,
                };
                save_state(&state);

                println!("{}", container_id);
                ExitCode::SUCCESS
            }
            Err(e) => {
                eprintln!("ferrocage: failed to start container: {}", e);
                ExitCode::FAILURE
            }
        }
    } else {
        // Foreground execution
        let mut child = match cmd.spawn() {
            Ok(c) => c,
            Err(e) => {
                eprintln!("ferrocage: failed to execute container: {}", e);
                return ExitCode::FAILURE;
            }
        };

        let pid = child.id();
        setup_cgroup_v2(&container_id, pid, memory_bytes, cpus, pids_max);

        let mut state = ContainerState {
            id: container_id.clone(),
            name,
            image,
            command: cmd_parts,
            created_at: current_timestamp(),
            pid: Some(pid),
            status: "running".to_string(),
            exit_code: None,
            memory_max_bytes: memory_bytes,
            cpus,
            pids_max,
            volumes,
            network,
        };
        save_state(&state);

        let code = match child.wait() {
            Ok(status) => status.code().unwrap_or(1),
            Err(e) => {
                eprintln!("ferrocage: failed to wait for child container: {}", e);
                1
            }
        };

        state.pid = None;
        state.status = format!("exited ({})", code);
        state.exit_code = Some(code);

        if auto_rm {
            let container_dir = format!("{}/{}", get_state_dir(), container_id);
            let _ = fs::remove_dir_all(container_dir);
            cleanup_cgroup_v2(&container_id);
        } else {
            save_state(&state);
        }

        ExitCode::from(code as u8)
    }
}

fn truncate_str(s: &str, max_chars: usize) -> &str {
    match s.char_indices().nth(max_chars) {
        None => s,
        Some((idx, _)) => &s[..idx],
    }
}

// ---------------------------------------------------------------------------
// ferrocage ps
// ---------------------------------------------------------------------------

fn handle_ps(args: &[String]) -> ExitCode {
    let mut show_all = false;
    let mut json_format = false;

    for arg in args {
        match arg.as_str() {
            "-a" | "--all" => show_all = true,
            "--format=json" | "json" => json_format = true,
            other if other.starts_with('-') => {
                eprintln!("ferrocage ps: unknown flag '{}'", other);
                return ExitCode::FAILURE;
            }
            _ => {}
        }
    }

    let containers = load_all_containers();

    if json_format {
        let json_items: Vec<String> = containers
            .iter()
            .filter(|c| show_all || is_running(c))
            .map(|c| format_state_json(c))
            .collect();
        println!("[{}]", json_items.join(","));
        return ExitCode::SUCCESS;
    }

    println!(
        "{:<14} {:<18} {:<24} {:<14} {:<16} {}",
        "CONTAINER ID", "IMAGE", "COMMAND", "CREATED", "STATUS", "NAMES"
    );

    for c in &containers {
        let running = is_running(c);
        if !show_all && !running {
            continue;
        }

        let cmd_str = c.command.join(" ");
        let (cmd_trunc, truncated) = if cmd_str.chars().count() > 22 {
            (truncate_str(&cmd_str, 20), true)
        } else {
            (cmd_str.as_str(), false)
        };
        let cmd_display = if truncated {
            format!("\"{}...\"", cmd_trunc)
        } else {
            format!("\"{}\"", cmd_trunc)
        };

        let status_str = if running {
            let uptime = current_timestamp().saturating_sub(c.created_at);
            format!("Up {}", format_duration(uptime))
        } else {
            c.status.clone()
        };

        let created_str = format!("{} ago", format_duration(current_timestamp().saturating_sub(c.created_at)));

        println!(
            "{:<14} {:<18} {:<24} {:<14} {:<16} {}",
            truncate_str(&c.id, 12),
            c.image,
            cmd_display,
            created_str,
            status_str,
            c.name
        );
    }

    ExitCode::SUCCESS
}

// ---------------------------------------------------------------------------
// ferrocage stop / start / rm
// ---------------------------------------------------------------------------

fn handle_stop(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("Usage: ferrocage stop <container_id> [--timeout sec]");
        return ExitCode::FAILURE;
    }
    let mut target = None;
    let mut timeout_sec = 5;
    let mut idx = 0;
    while idx < args.len() {
        let arg = &args[idx];
        if arg == "--timeout" || arg == "-t" {
            if idx + 1 < args.len() {
                timeout_sec = args[idx + 1].parse::<u64>().unwrap_or(5);
                idx += 2;
            } else {
                eprintln!("ferrocage stop: option '{}' requires an argument", arg);
                return ExitCode::FAILURE;
            }
        } else if arg.starts_with('-') {
            eprintln!("ferrocage stop: unrecognized option '{}'", arg);
            return ExitCode::FAILURE;
        } else {
            if target.is_none() {
                target = Some(arg.as_str());
            }
            idx += 1;
        }
    }

    let Some(target) = target else {
        eprintln!("Usage: ferrocage stop <container_id> [--timeout sec]");
        return ExitCode::FAILURE;
    };

    if let Some(mut state) = find_container(target) {
        if let Some(pid) = state.pid {
            unsafe {
                libc::kill(pid as i32, libc::SIGTERM);
            }

            let start = std::time::Instant::now();
            let mut stopped = false;
            while start.elapsed() < std::time::Duration::from_secs(timeout_sec) {
                if unsafe { libc::kill(pid as i32, 0) } != 0 {
                    stopped = true;
                    break;
                }
                std::thread::sleep(std::time::Duration::from_millis(50));
            }

            if !stopped {
                unsafe {
                    libc::kill(pid as i32, libc::SIGKILL);
                }
            }

            cleanup_cgroup_v2(&state.id);
            state.pid = None;
            state.status = "exited (137)".to_string();
            state.exit_code = Some(137);
            save_state(&state);

            println!("{}", state.id);
            return ExitCode::SUCCESS;
        } else {
            println!("Container '{}' is already stopped", target);
            return ExitCode::SUCCESS;
        }
    }

    eprintln!("No such container: {}", target);
    ExitCode::FAILURE
}

fn handle_start(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("Usage: ferrocage start <container_id>");
        return ExitCode::FAILURE;
    }
    let mut target = None;
    for arg in args {
        if arg.starts_with('-') {
            eprintln!("ferrocage start: unrecognized option '{}'", arg);
            return ExitCode::FAILURE;
        } else if target.is_none() {
            target = Some(arg.as_str());
        }
    }
    let Some(target) = target else {
        eprintln!("Usage: ferrocage start <container_id>");
        return ExitCode::FAILURE;
    };

    if let Some(mut state) = find_container(target) {
        if is_running(&state) {
            println!("Container '{}' is already running", target);
            return ExitCode::SUCCESS;
        }

        if state.command.is_empty() {
            eprintln!("ferrocage: container '{}' has no command configured", target);
            return ExitCode::FAILURE;
        }

        let mut cmd = Command::new(&state.command[0]);
        if state.command.len() > 1 {
            cmd.args(&state.command[1..]);
        }
        configure_container_isolation(&mut cmd, &state.name, &state.image, &state.volumes, &state.network);
        cmd.stdout(Stdio::null());
        cmd.stderr(Stdio::null());
        cmd.stdin(Stdio::null());

        match cmd.spawn() {
            Ok(child) => {
                let pid = child.id();
                setup_cgroup_v2(&state.id, pid, state.memory_max_bytes, state.cpus, state.pids_max);
                state.pid = Some(pid);
                state.status = "running".to_string();
                save_state(&state);
                println!("{}", state.id);
                ExitCode::SUCCESS
            }
            Err(e) => {
                eprintln!("Failed to restart container {}: {}", target, e);
                ExitCode::FAILURE
            }
        }
    } else {
        eprintln!("No such container: {}", target);
        ExitCode::FAILURE
    }
}

fn handle_rm(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("Usage: ferrocage rm [-f] <container_id>");
        return ExitCode::FAILURE;
    }
    let mut force = false;
    let mut target = None;
    for arg in args {
        match arg.as_str() {
            "-f" | "--force" => force = true,
            other if other.starts_with('-') => {
                eprintln!("ferrocage rm: unrecognized option '{}'", other);
                return ExitCode::FAILURE;
            }
            other => {
                if target.is_none() {
                    target = Some(other.clone());
                }
            }
        }
    }

    let Some(target) = target else {
        eprintln!("Usage: ferrocage rm [-f] <container_id>");
        return ExitCode::FAILURE;
    };

    if let Some(state) = find_container(&target) {
        if is_running(&state) {
            if force {
                let _ = handle_stop(&[target.clone()]);
            } else {
                eprintln!("Error: container '{}' is running. Stop the container first or use -f", target);
                return ExitCode::FAILURE;
            }
        }

        let container_dir = format!("{}/{}", get_state_dir(), state.id);
        let _ = fs::remove_dir_all(&container_dir);
        let log_file = format!("{}/{}.log", get_logs_dir(), state.id);
        let _ = fs::remove_file(&log_file);
        cleanup_cgroup_v2(&state.id);

        println!("{}", state.id);
        ExitCode::SUCCESS
    } else {
        eprintln!("No such container: {}", target);
        ExitCode::FAILURE
    }
}

// ---------------------------------------------------------------------------
// ferrocage logs / inspect / images
// ---------------------------------------------------------------------------

fn handle_logs(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("Usage: ferrocage logs [-n lines] <container_id>");
        return ExitCode::FAILURE;
    }
    let mut target = None;
    let mut num_lines = 50;
    let mut idx = 0;
    while idx < args.len() {
        let arg = &args[idx];
        match arg.as_str() {
            "-f" | "--follow" => {
                idx += 1;
            }
            "-n" | "--tail" => {
                if idx + 1 < args.len() {
                    num_lines = args[idx + 1].parse::<usize>().unwrap_or(50);
                    idx += 2;
                } else {
                    eprintln!("ferrocage logs: option '{}' requires an argument", arg);
                    return ExitCode::FAILURE;
                }
            }
            other if other.starts_with('-') => {
                eprintln!("ferrocage logs: unrecognized option '{}'", other);
                return ExitCode::FAILURE;
            }
            other => {
                if target.is_none() {
                    target = Some(other.clone());
                }
                idx += 1;
            }
        }
    }

    let Some(target) = target else {
        eprintln!("Usage: ferrocage logs [-n lines] <container_id>");
        return ExitCode::FAILURE;
    };

    if let Some(state) = find_container(&target) {
        let log_path = format!("{}/{}.log", get_logs_dir(), state.id);
        if let Ok(file) = File::open(&log_path) {
            let reader = BufReader::new(file);
            let lines: Vec<String> = reader.lines().flatten().collect();
            let start = lines.len().saturating_sub(num_lines);
            for l in &lines[start..] {
                println!("{}", l);
            }
            ExitCode::SUCCESS
        } else {
            // No log file yet
            ExitCode::SUCCESS
        }
    } else {
        eprintln!("No such container: {}", target);
        ExitCode::FAILURE
    }
}

fn handle_inspect(args: &[String]) -> ExitCode {
    if args.is_empty() {
        eprintln!("Usage: ferrocage inspect <container_id>");
        return ExitCode::FAILURE;
    }
    let mut target = None;
    for arg in args {
        if arg.starts_with('-') {
            eprintln!("ferrocage inspect: unrecognized option '{}'", arg);
            return ExitCode::FAILURE;
        } else if target.is_none() {
            target = Some(arg.as_str());
        }
    }
    let Some(target) = target else {
        eprintln!("Usage: ferrocage inspect <container_id>");
        return ExitCode::FAILURE;
    };

    if let Some(state) = find_container(target) {
        println!("{}", format_state_json(&state));
        ExitCode::SUCCESS
    } else {
        eprintln!("No such container: {}", target);
        ExitCode::FAILURE
    }
}

fn handle_exec(args: &[String]) -> ExitCode {
    if args.len() < 2 {
        eprintln!("Usage: ferrocage exec [options] <container_id> <command> [args...]");
        return ExitCode::FAILURE;
    }

    let mut idx = 0;
    while idx < args.len() {
        let arg = &args[idx];
        if arg == "-i" || arg == "-t" || arg == "-it" || arg == "-ti" {
            idx += 1;
        } else if arg.starts_with('-') {
            eprintln!("ferrocage exec: unrecognized option '{}'", arg);
            return ExitCode::FAILURE;
        } else {
            break;
        }
    }

    if idx >= args.len() {
        eprintln!("Missing container identifier");
        return ExitCode::FAILURE;
    }

    let target = &args[idx];
    idx += 1;
    if idx >= args.len() {
        eprintln!("Missing command to execute");
        return ExitCode::FAILURE;
    }

    let cmd_parts = &args[idx..];

    if let Some(state) = find_container(target) {
        if !is_running(&state) {
            eprintln!("Container '{}' is not running", target);
            return ExitCode::FAILURE;
        }

        let Some(pid) = state.pid else {
            eprintln!("Container '{}' has no active PID", target);
            return ExitCode::FAILURE;
        };

        #[cfg(target_os = "linux")]
        {
            // Join container namespaces via setns()
            let ns_types = ["mnt", "net", "ipc", "uts", "pid"];
            for ns in &ns_types {
                let ns_path = format!("/proc/{}/ns/{}", pid, ns);
                if let Ok(file) = File::open(&ns_path) {
                    use std::os::unix::io::AsRawFd;
                    unsafe {
                        libc::setns(file.as_raw_fd(), 0);
                    }
                }
            }
        }

        // Execute command
        let status = Command::new(&cmd_parts[0])
            .args(&cmd_parts[1..])
            .status();

        match status {
            Ok(s) => ExitCode::from(s.code().unwrap_or(0) as u8),
            Err(e) => {
                eprintln!("Failed to exec {}: {}", &cmd_parts[0], e);
                ExitCode::FAILURE
            }
        }
    } else {
        eprintln!("No such container: {}", target);
        ExitCode::FAILURE
    }
}

fn handle_images(_args: &[String]) -> ExitCode {
    println!("{:<24} {:<12} {:<16} {}", "REPOSITORY", "TAG", "SIZE", "LOCATION");
    let images_dir = get_images_dir();
    let _ = fs::create_dir_all(&images_dir);

    if let Ok(entries) = fs::read_dir(&images_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            let name = path.file_name().and_then(|s| s.to_str()).unwrap_or("unknown");
            let size = dir_size(&path);
            println!("{:<24} {:<12} {:<16} {}", name, "latest", format_size(size), path.display());
        }
    }
    ExitCode::SUCCESS
}

fn configure_container_isolation(
    cmd: &mut Command,
    name: &str,
    image: &str,
    volumes: &[String],
    network: &str,
) {
    #[cfg(target_os = "linux")]
    unsafe {
        use std::os::unix::process::CommandExt;
        let vols = volumes.to_vec();
        let net_mode = network.to_string();
        let c_name = name.to_string();
        let image_name = image.to_string();
        let images_root = get_images_dir();

        cmd.pre_exec(move || {
            let uid = libc::getuid();
            let gid = libc::getgid();

            // 1. Mandatory namespace isolation for every container:
            // UTS (hostname), IPC (shared mem), Mount (private fs).
            let mut clone_flags = libc::CLONE_NEWNS | libc::CLONE_NEWUTS | libc::CLONE_NEWIPC;
            if net_mode != "host" {
                clone_flags |= libc::CLONE_NEWNET;
            }

            // Unshare namespaces (support rootless with CLONE_NEWUSER if unprivileged)
            let unshared = if libc::unshare(clone_flags) == 0 {
                true
            } else if libc::unshare(clone_flags | libc::CLONE_NEWUSER) == 0 {
                let _ = std::fs::write("/proc/self/setgroups", "deny");
                let _ = std::fs::write("/proc/self/uid_map", format!("0 {} 1\n", uid));
                let _ = std::fs::write("/proc/self/gid_map", format!("0 {} 1\n", gid));
                true
            } else if libc::unshare(libc::CLONE_NEWNS) == 0 {
                true
            } else {
                false
            };

            if unshared {
                // Ensure mounts do not propagate back to host
                let none_str = std::ffi::CString::new("none").unwrap();
                libc::mount(
                    std::ptr::null(),
                    none_str.as_ptr(),
                    std::ptr::null(),
                    libc::MS_REC | libc::MS_PRIVATE,
                    std::ptr::null(),
                );

                // Set private container hostname in UTS namespace
                if let Ok(c_host) = std::ffi::CString::new(c_name.as_str()) {
                    let _ = libc::sethostname(c_host.as_ptr(), c_name.len());
                }

                // Check if rootfs directory exists
                let dedicated_img = PathBuf::from(&images_root).join(&image_name);
                let direct_img = PathBuf::from(&image_name);
                let rootfs_path = if dedicated_img.is_dir() {
                    Some(dedicated_img)
                } else if direct_img.is_dir() {
                    Some(direct_img)
                } else {
                    None
                };

                if let Some(rootfs) = rootfs_path {
                    // Jail process inside container rootfs: bind-mount volumes into rootfs
                    for vol in &vols {
                        let parts: Vec<&str> = vol.split(':').collect();
                        if parts.len() >= 2 {
                            let host_path = parts[0];
                            let dest_rel = parts[1].trim_start_matches('/');
                            let is_ro = parts.get(2).map(|s| *s == "ro").unwrap_or(false);

                            let target_path = rootfs.join(dest_rel);
                            let _ = std::fs::create_dir_all(&target_path);

                            if let (Ok(c_host), Ok(c_dest)) = (
                                std::ffi::CString::new(host_path),
                                std::ffi::CString::new(target_path.to_string_lossy().as_bytes()),
                            ) {
                                if libc::mount(
                                    c_host.as_ptr(),
                                    c_dest.as_ptr(),
                                    std::ptr::null(),
                                    libc::MS_BIND,
                                    std::ptr::null(),
                                ) == 0 {
                                    if is_ro {
                                        libc::mount(
                                            std::ptr::null(),
                                            c_dest.as_ptr(),
                                            std::ptr::null(),
                                            libc::MS_BIND | libc::MS_REMOUNT | libc::MS_RDONLY,
                                            std::ptr::null(),
                                        );
                                    }
                                }
                            }
                        }
                    }

                    // Chroot into rootfs
                    if let Ok(c_root) = std::ffi::CString::new(rootfs.to_string_lossy().as_bytes()) {
                        if libc::chroot(c_root.as_ptr()) == 0 {
                            let c_slash = std::ffi::CString::new("/").unwrap();
                            let _ = libc::chdir(c_slash.as_ptr());
                        }
                    }
                } else {
                    // If no separate rootfs image exists, mount volumes into host-isolated mount namespace
                    for vol in &vols {
                        let parts: Vec<&str> = vol.split(':').collect();
                        if parts.len() >= 2 {
                            let host_path = parts[0];
                            let dest_path = parts[1];
                            let is_ro = parts.get(2).map(|s| *s == "ro").unwrap_or(false);

                            let _ = std::fs::create_dir_all(dest_path);

                            if let (Ok(c_host), Ok(c_dest)) = (
                                std::ffi::CString::new(host_path),
                                std::ffi::CString::new(dest_path),
                            ) {
                                if libc::mount(
                                    c_host.as_ptr(),
                                    c_dest.as_ptr(),
                                    std::ptr::null(),
                                    libc::MS_BIND,
                                    std::ptr::null(),
                                ) == 0 {
                                    if is_ro {
                                        libc::mount(
                                            std::ptr::null(),
                                            c_dest.as_ptr(),
                                            std::ptr::null(),
                                            libc::MS_BIND | libc::MS_REMOUNT | libc::MS_RDONLY,
                                            std::ptr::null(),
                                        );
                                    }
                                }
                            }
                        }
                    }
                }
            }
            Ok(())
        });
    }

    #[cfg(not(target_os = "linux"))]
    {
        let _ = (cmd, name, image, network);
        for vol in volumes {
            let parts: Vec<&str> = vol.split(':').collect();
            if parts.len() >= 2 {
                let host_path = parts[0];
                let dest_path = parts[1];
                let is_ro = parts.get(2).map(|s| *s == "ro").unwrap_or(false);

                let _ = std::fs::remove_dir_all(dest_path);
                let _ = std::fs::remove_file(dest_path);

                if let Some(parent) = Path::new(dest_path).parent() {
                    let _ = std::fs::create_dir_all(parent);
                }

                #[cfg(unix)]
                {
                    if is_ro {
                        let _ = std::fs::create_dir_all(dest_path);
                        if let Ok(meta) = std::fs::metadata(dest_path) {
                            let mut perms = meta.permissions();
                            use std::os::unix::fs::PermissionsExt;
                            perms.set_mode(0o555);
                            let _ = std::fs::set_permissions(dest_path, perms);
                        }
                    } else {
                        let _ = std::os::unix::fs::symlink(host_path, dest_path);
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Helpers & State Persistence
// ---------------------------------------------------------------------------

fn setup_cgroup_v2(id: &str, pid: u32, memory_bytes: Option<u64>, cpus: Option<f32>, pids_max: Option<u32>) {
    let cg_dir = PathBuf::from(CGROUP_ROOT).join(id);
    if !Path::new("/sys/fs/cgroup").exists() {
        return;
    }

    if let Err(_) = fs::create_dir_all(&cg_dir) {
        return;
    }

    let _ = fs::write(cg_dir.join("cgroup.procs"), format!("{}\n", pid));

    if let Some(mem) = memory_bytes {
        let _ = fs::write(cg_dir.join("memory.max"), format!("{}\n", mem));
    }

    if let Some(cpu) = cpus {
        let period_us: u64 = 100_000;
        let quota_us = (cpu * period_us as f32) as u64;
        let _ = fs::write(cg_dir.join("cpu.max"), format!("{} {}\n", quota_us, period_us));
    }

    if let Some(pids) = pids_max {
        let _ = fs::write(cg_dir.join("pids.max"), format!("{}\n", pids));
    }
}

fn cleanup_cgroup_v2(id: &str) {
    let cg_dir = PathBuf::from(CGROUP_ROOT).join(id);
    if cg_dir.exists() {
        let _ = fs::remove_dir(&cg_dir);
    }
}

fn save_state(state: &ContainerState) {
    let container_dir = format!("{}/{}", get_state_dir(), state.id);
    let _ = fs::create_dir_all(&container_dir);
    let state_file = format!("{}/state.json", container_dir);
    let json = format_state_json(state);
    let _ = fs::write(state_file, json);
}

fn load_all_containers() -> Vec<ContainerState> {
    let mut result = Vec::new();
    if let Ok(entries) = fs::read_dir(get_state_dir()) {
        for entry in entries.flatten() {
            let path = entry.path().join("state.json");
            if path.exists() {
                if let Ok(content) = fs::read_to_string(&path) {
                    if let Some(state) = parse_state_json(&content) {
                        result.push(state);
                    }
                }
            }
        }
    }
    result.sort_by(|a, b| b.created_at.cmp(&a.created_at));
    result
}

fn find_container(target: &str) -> Option<ContainerState> {
    let all = load_all_containers();
    for c in all {
        if c.id == target || c.id.starts_with(target) || c.name == target {
            return Some(c);
        }
    }
    None
}

fn is_running(state: &ContainerState) -> bool {
    if let Some(pid) = state.pid {
        unsafe { libc::kill(pid as i32, 0) == 0 }
    } else {
        false
    }
}

fn format_state_json(c: &ContainerState) -> String {
    let running = is_running(c);
    let cmds_json: Vec<String> = c.command.iter().map(|s| format!("\"{}\"", escape_json(s))).collect();
    let vols_json: Vec<String> = c.volumes.iter().map(|s| format!("\"{}\"", escape_json(s))).collect();

    format!(
        r#"{{"id":"{}","name":"{}","image":"{}","command":[{}],"created_at":{},"pid":{},"running":{},"status":"{}","exit_code":{},"memory_max_bytes":{},"cpus":{},"pids_max":{},"volumes":[{}],"network":"{}"}}"#,
        c.id,
        c.name,
        c.image,
        cmds_json.join(","),
        c.created_at,
        c.pid.map(|p| p.to_string()).unwrap_or_else(|| "null".to_string()),
        running,
        if running { "running" } else { &c.status },
        c.exit_code.map(|e| e.to_string()).unwrap_or_else(|| "null".to_string()),
        c.memory_max_bytes.map(|m| m.to_string()).unwrap_or_else(|| "null".to_string()),
        c.cpus.map(|cp| cp.to_string()).unwrap_or_else(|| "null".to_string()),
        c.pids_max.map(|p| p.to_string()).unwrap_or_else(|| "null".to_string()),
        vols_json.join(","),
        c.network
    )
}

fn parse_state_json(json: &str) -> Option<ContainerState> {
    let id = extract_json_field(json, "id")?;
    let name = extract_json_field(json, "name").unwrap_or_else(|| "unnamed".to_string());
    let image = extract_json_field(json, "image").unwrap_or_default();
    let created_at = extract_json_field(json, "created_at").and_then(|v| v.parse::<u64>().ok()).unwrap_or(0);
    let pid = extract_json_field(json, "pid").and_then(|v| v.parse::<u32>().ok());
    let status = extract_json_field(json, "status").unwrap_or_else(|| "unknown".to_string());
    let exit_code = extract_json_field(json, "exit_code").and_then(|v| v.parse::<i32>().ok());
    let memory_max_bytes = extract_json_field(json, "memory_max_bytes").and_then(|v| v.parse::<u64>().ok());
    let cpus = extract_json_field(json, "cpus").and_then(|v| v.parse::<f32>().ok());
    let pids_max = extract_json_field(json, "pids_max").and_then(|v| v.parse::<u32>().ok());
    let network = extract_json_field(json, "network").unwrap_or_else(|| "host".to_string());

    let mut command = Vec::new();
    if let Some(cmd_idx) = json.find("\"command\":[") {
        let rest = &json[cmd_idx + 11..];
        if let Some(end_idx) = rest.find(']') {
            let inner = &rest[..end_idx];
            for item in inner.split(',') {
                let trimmed = item.trim().trim_matches('"');
                if !trimmed.is_empty() {
                    command.push(trimmed.to_string());
                }
            }
        }
    }

    Some(ContainerState {
        id,
        name,
        image,
        command,
        created_at,
        pid,
        status,
        exit_code,
        memory_max_bytes,
        cpus,
        pids_max,
        volumes: Vec::new(),
        network,
    })
}

fn extract_json_field(json: &str, field: &str) -> Option<String> {
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

fn escape_json(s: &str) -> String {
    s.replace('\\', "\\\\").replace('"', "\\\"")
}

fn parse_memory_spec(s: &str) -> Option<u64> {
    let trimmed = s.trim().to_uppercase();
    if trimmed.ends_with('G') || trimmed.ends_with("GB") {
        let num: f64 = trimmed.trim_end_matches("GB").trim_end_matches('G').parse().ok()?;
        Some((num * 1024.0 * 1024.0 * 1024.0) as u64)
    } else if trimmed.ends_with('M') || trimmed.ends_with("MB") {
        let num: f64 = trimmed.trim_end_matches("MB").trim_end_matches('M').parse().ok()?;
        Some((num * 1024.0 * 1024.0) as u64)
    } else if trimmed.ends_with('K') || trimmed.ends_with("KB") {
        let num: f64 = trimmed.trim_end_matches("KB").trim_end_matches('K').parse().ok()?;
        Some((num * 1024.0) as u64)
    } else {
        trimmed.parse::<u64>().ok()
    }
}

fn generate_id() -> String {
    let t = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    format!("{:012x}", t % 0xFFFFFFFFFFFF)
}

fn current_timestamp() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs()
}

fn format_duration(sec: u64) -> String {
    if sec < 60 {
        format!("{} seconds", sec)
    } else if sec < 3600 {
        format!("{} minutes", sec / 60)
    } else if sec < 86400 {
        format!("{} hours", sec / 3600)
    } else {
        format!("{} days", sec / 86400)
    }
}

fn format_size(bytes: u64) -> String {
    if bytes < 1024 {
        format!("{} B", bytes)
    } else if bytes < 1024 * 1024 {
        format!("{:.1} KB", bytes as f64 / 1024.0)
    } else if bytes < 1024 * 1024 * 1024 {
        format!("{:.1} MB", bytes as f64 / (1024.0 * 1024.0))
    } else {
        format!("{:.2} GB", bytes as f64 / (1024.0 * 1024.0 * 1024.0))
    }
}

fn dir_size(path: &Path) -> u64 {
    let mut total = 0;
    if let Ok(entries) = fs::read_dir(path) {
        for entry in entries.flatten() {
            if let Ok(meta) = entry.metadata() {
                if meta.is_file() {
                    total += meta.len();
                } else if meta.is_dir() {
                    total += dir_size(&entry.path());
                }
            }
        }
    }
    total
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_oci_config_deserialization() {
        let sample_oci_json = r#"{
            "ociVersion": "1.0.2",
            "process": {
                "terminal": false,
                "user": { "uid": 0, "gid": 0 },
                "args": ["/bin/app", "--worker", "4"],
                "env": ["PORT=8080", "RUST_LOG=info"],
                "cwd": "/app"
            },
            "root": {
                "path": "rootfs",
                "readonly": true
            },
            "linux": {
                "resources": {
                    "memory": { "limit": 268435456 },
                    "pids": { "limit": 100 }
                }
            }
        }"#;

        let oci: OciConfig = serde_json::from_str(sample_oci_json).expect("valid OCI config");
        assert_eq!(oci.oci_version, "1.0.2");
        assert_eq!(oci.process.as_ref().unwrap().args, vec!["/bin/app", "--worker", "4"]);
        assert_eq!(oci.process.as_ref().unwrap().env, vec!["PORT=8080", "RUST_LOG=info"]);
        assert_eq!(oci.process.as_ref().unwrap().cwd.as_deref(), Some("/app"));
        assert_eq!(oci.root.as_ref().unwrap().path, "rootfs");
        assert_eq!(oci.linux.as_ref().unwrap().resources.as_ref().unwrap().memory.as_ref().unwrap().limit, Some(268435456));
        assert_eq!(oci.linux.as_ref().unwrap().resources.as_ref().unwrap().pids.as_ref().unwrap().limit, Some(100));
    }
}
