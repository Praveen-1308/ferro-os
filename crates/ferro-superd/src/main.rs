//! ferro-superd: High-Velocity Pure-Rust Cgroup v2 Service Supervisor for FerroOS
//! Replaces systemd with an ultra-lightweight, declarative process supervisor,
//! enforcing Cgroup v2 resource limits, health monitoring, and ring-buffer logging.
#![allow(clippy::all)]

use std::collections::{HashMap, VecDeque};
use std::fs::{self, File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const SOCKET_PATH: &str = "/run/ferro/superd.sock";
const SERVICES_DIR: &str = "/etc/ferro/services";
const LOGS_DIR: &str = "/var/log/ferro";
const CGROUP_ROOT: &str = "/sys/fs/cgroup/ferro.slice";
const MAX_LOG_LINES: usize = 500;

static RUNNING: AtomicBool = AtomicBool::new(true);

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RestartPolicy {
    Always,
    OnFailure,
    Never,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ServiceState {
    Stopped,
    Starting,
    Running,
    Stopping,
    Failed,
    Backoff,
}

impl ServiceState {
    pub fn as_str(&self) -> &'static str {
        match self {
            ServiceState::Stopped => "stopped",
            ServiceState::Starting => "starting",
            ServiceState::Running => "running",
            ServiceState::Stopping => "stopping",
            ServiceState::Failed => "failed",
            ServiceState::Backoff => "backoff",
        }
    }
}

#[derive(Debug, Clone)]
pub struct ServiceConfig {
    pub name: String,
    pub description: String,
    pub command: Vec<String>,
    pub working_dir: String,
    pub user: Option<String>,
    pub group: Option<String>,
    pub restart_policy: RestartPolicy,
    pub max_retries: u32,
    pub backoff_ms: u64,
    pub memory_max_mb: Option<u64>,
    pub memory_high_mb: Option<u64>,
    pub cpu_weight: Option<u32>,
    pub pids_max: Option<u32>,
    pub health_interval_sec: Option<u64>,
    pub health_command: Option<Vec<String>>,
    pub health_timeout_sec: u64,
    pub restart_on_unhealthy: bool,
}

#[derive(Debug)]
pub struct ManagedService {
    pub config: ServiceConfig,
    pub state: ServiceState,
    pub pid: Option<u32>,
    pub child: Option<Child>,
    pub started_at: Option<Instant>,
    pub uptime_seconds: u64,
    pub restart_count: u32,
    pub consecutive_health_failures: u32,
    pub is_healthy: bool,
    pub last_health_check: Option<Instant>,
    pub log_buffer: VecDeque<String>,
    pub log_file: Option<File>,
}

impl ManagedService {
    pub fn new(config: ServiceConfig) -> Self {
        let log_file_path = format!("{}/{}.log", LOGS_DIR, config.name);
        let log_file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_file_path)
            .ok();

        ManagedService {
            config,
            state: ServiceState::Stopped,
            pid: None,
            child: None,
            started_at: None,
            uptime_seconds: 0,
            restart_count: 0,
            consecutive_health_failures: 0,
            is_healthy: true,
            last_health_check: None,
            log_buffer: VecDeque::with_capacity(MAX_LOG_LINES),
            log_file,
        }
    }

    pub fn append_log(&mut self, line: &str) {
        let ts = current_iso_timestamp();
        let formatted = format!("{} [{}] {}", ts, self.config.name, line);
        if self.log_buffer.len() >= MAX_LOG_LINES {
            self.log_buffer.pop_front();
        }
        self.log_buffer.push_back(formatted.clone());

        if let Some(ref mut f) = self.log_file {
            let _ = writeln!(f, "{}", formatted);
        }
    }
}

pub struct Supervisor {
    pub services: Mutex<HashMap<String, ManagedService>>,
}

impl Supervisor {
    pub fn new() -> Arc<Self> {
        Arc::new(Supervisor {
            services: Mutex::new(HashMap::new()),
        })
    }

    pub fn load_manifests(&self) {
        if !Path::new(SERVICES_DIR).exists() {
            let _ = fs::create_dir_all(SERVICES_DIR);
        }
        if !Path::new(LOGS_DIR).exists() {
            let _ = fs::create_dir_all(LOGS_DIR);
        }

        let entries = match fs::read_dir(SERVICES_DIR) {
            Ok(e) => e,
            Err(_) => return,
        };

        let mut lock = self.services.lock().unwrap();
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().and_then(|s| s.to_str()) == Some("toml") {
                if let Ok(config) = parse_service_toml(&path) {
                    if !lock.contains_key(&config.name) {
                        println!("[ferro-superd] Loaded manifest for service: {}", config.name);
                        let name = config.name.clone();
                        let svc = ManagedService::new(config);
                        lock.insert(name, svc);
                    }
                }
            }
        }
    }

    pub fn start_service(&self, name: &str) -> Result<u32, String> {
        let mut lock = self.services.lock().unwrap();
        let svc = lock.get_mut(name).ok_or_else(|| format!("Service '{}' not found", name))?;

        if svc.state == ServiceState::Running {
            if let Some(pid) = svc.pid {
                return Ok(pid);
            }
        }

        svc.state = ServiceState::Starting;
        let cmd_parts = &svc.config.command;
        if cmd_parts.is_empty() {
            svc.state = ServiceState::Failed;
            return Err("Empty command specification".to_string());
        }

        let mut cmd = Command::new(&cmd_parts[0]);
        if cmd_parts.len() > 1 {
            cmd.args(&cmd_parts[1..]);
        }
        if !svc.config.working_dir.is_empty() && Path::new(&svc.config.working_dir).exists() {
            cmd.current_dir(&svc.config.working_dir);
        }

        cmd.stdout(Stdio::piped());
        cmd.stderr(Stdio::piped());

        match cmd.spawn() {
            Ok(mut child) => {
                let pid = child.id();
                svc.pid = Some(pid);
                svc.state = ServiceState::Running;
                svc.started_at = Some(Instant::now());
                svc.uptime_seconds = 0;
                svc.is_healthy = true;

                // Setup cgroup v2 limits
                setup_cgroup_v2(&svc.config, pid);

                svc.append_log(&format!("Service spawned with PID {}", pid));

                // Spawn stream readers for stdout and stderr
                let name_clone = name.to_string();
                if let Some(stdout) = child.stdout.take() {
                    let name_out = name_clone.clone();
                    thread::spawn(move || {
                        let reader = BufReader::new(stdout);
                        for line in reader.lines().flatten() {
                            println!("[ferro-superd:{}] {}", name_out, line);
                        }
                    });
                }

                svc.child = Some(child);
                println!("[ferro-superd] Started service '{}' (PID: {})", name, pid);
                Ok(pid)
            }
            Err(e) => {
                svc.state = ServiceState::Failed;
                let err_msg = format!("Failed to spawn {}: {}", &cmd_parts[0], e);
                svc.append_log(&err_msg);
                Err(err_msg)
            }
        }
    }

    pub fn stop_service(&self, name: &str, timeout_sec: u64) -> Result<(), String> {
        let mut lock = self.services.lock().unwrap();
        let svc = lock.get_mut(name).ok_or_else(|| format!("Service '{}' not found", name))?;

        if svc.state == ServiceState::Stopped {
            return Ok(());
        }

        svc.state = ServiceState::Stopping;
        if let Some(pid) = svc.pid {
            svc.append_log(&format!("Sending SIGTERM to PID {}", pid));
            unsafe {
                libc::kill(pid as i32, libc::SIGTERM);
            }

            // Wait loop for termination
            let start = Instant::now();
            let mut terminated = false;
            while start.elapsed() < Duration::from_secs(timeout_sec) {
                if let Some(ref mut child) = svc.child {
                    if let Ok(Some(_)) = child.try_wait() {
                        terminated = true;
                        break;
                    }
                }
                thread::sleep(Duration::from_millis(50));
            }

            if !terminated {
                svc.append_log(&format!("Timeout exceeded; sending SIGKILL to PID {}", pid));
                unsafe {
                    libc::kill(pid as i32, libc::SIGKILL);
                }
                if let Some(ref mut child) = svc.child {
                    let _ = child.wait();
                }
            }

            cleanup_cgroup_v2(&svc.config);
        }

        svc.child = None;
        svc.pid = None;
        svc.state = ServiceState::Stopped;
        svc.started_at = None;
        svc.append_log("Service stopped successfully");
        println!("[ferro-superd] Stopped service '{}'", name);
        Ok(())
    }

    pub fn restart_service(&self, name: &str) -> Result<u32, String> {
        let _ = self.stop_service(name, 3);
        self.start_service(name)
    }
}

// ---------------------------------------------------------------------------
// Cgroup v2 Resource Controller
// ---------------------------------------------------------------------------

fn setup_cgroup_v2(config: &ServiceConfig, pid: u32) {
    let cg_path = PathBuf::from(CGROUP_ROOT).join(&config.name);
    if !Path::new("/sys/fs/cgroup").exists() {
        return;
    }

    if let Err(_) = fs::create_dir_all(&cg_path) {
        return;
    }

    // Attach PID
    let procs_file = cg_path.join("cgroup.procs");
    let _ = fs::write(procs_file, format!("{}\n", pid));

    // Memory ceiling
    if let Some(mb) = config.memory_max_mb {
        let bytes = mb * 1024 * 1024;
        let mem_file = cg_path.join("memory.max");
        let _ = fs::write(mem_file, format!("{}\n", bytes));
    }

    // Memory high warning
    if let Some(mb) = config.memory_high_mb {
        let bytes = mb * 1024 * 1024;
        let high_file = cg_path.join("memory.high");
        let _ = fs::write(high_file, format!("{}\n", bytes));
    }

    // CPU Weight
    if let Some(weight) = config.cpu_weight {
        let cpu_file = cg_path.join("cpu.weight");
        let _ = fs::write(cpu_file, format!("{}\n", weight));
    }

    // PIDs Max
    if let Some(max_pids) = config.pids_max {
        let pids_file = cg_path.join("pids.max");
        let _ = fs::write(pids_file, format!("{}\n", max_pids));
    }
}

fn cleanup_cgroup_v2(config: &ServiceConfig) {
    let cg_path = PathBuf::from(CGROUP_ROOT).join(&config.name);
    if cg_path.exists() {
        let _ = fs::remove_dir(&cg_path);
    }
}

fn read_cgroup_metrics(name: &str) -> (u64, u64) {
    let cg_path = PathBuf::from(CGROUP_ROOT).join(name);
    let mut mem_bytes = 0;
    let mut cpu_usec = 0;

    if let Ok(content) = fs::read_to_string(cg_path.join("memory.current")) {
        mem_bytes = content.trim().parse::<u64>().unwrap_or(0);
    }

    if let Ok(content) = fs::read_to_string(cg_path.join("cpu.stat")) {
        for line in content.lines() {
            if line.starts_with("usage_usec ") {
                if let Some(val) = line.split_whitespace().nth(1) {
                    cpu_usec = val.parse::<u64>().unwrap_or(0);
                }
            }
        }
    }

    (mem_bytes, cpu_usec)
}

// ---------------------------------------------------------------------------
// Background Monitoring & Health Engine
// ---------------------------------------------------------------------------

fn run_supervision_loop(supervisor: Arc<Supervisor>) {
    while RUNNING.load(Ordering::Relaxed) {
        thread::sleep(Duration::from_millis(250));

        let mut restarts_to_trigger: Vec<String> = Vec::new();

        {
            let mut lock = supervisor.services.lock().unwrap();
            for (name, svc) in lock.iter_mut() {
                if svc.state == ServiceState::Running {
                    if let Some(ref mut child) = svc.child {
                        match child.try_wait() {
                            Ok(Some(status)) => {
                                let exit_code = status.code().unwrap_or(-1);
                                svc.append_log(&format!("Process exited with status {}", exit_code));
                                svc.state = if exit_code == 0 {
                                    ServiceState::Stopped
                                } else {
                                    ServiceState::Failed
                                };
                                svc.pid = None;
                                svc.child = None;

                                let should_restart = match svc.config.restart_policy {
                                    RestartPolicy::Always => true,
                                    RestartPolicy::OnFailure => exit_code != 0,
                                    RestartPolicy::Never => false,
                                };

                                if should_restart && svc.restart_count < svc.config.max_retries {
                                    svc.restart_count += 1;
                                    svc.state = ServiceState::Backoff;
                                    svc.append_log(&format!(
                                        "Scheduling restart #{} in {}ms",
                                        svc.restart_count, svc.config.backoff_ms
                                    ));
                                    restarts_to_trigger.push(name.clone());
                                }
                            }
                            Ok(None) => {
                                // Still running; update uptime
                                if let Some(started) = svc.started_at {
                                    svc.uptime_seconds = started.elapsed().as_secs();
                                }
                            }
                            Err(_) => {}
                        }
                    }
                }
            }
        }

        // Handle scheduled restarts
        for svc_name in restarts_to_trigger {
            let sup = Arc::clone(&supervisor);
            thread::spawn(move || {
                let backoff = {
                    let lock = sup.services.lock().unwrap();
                    lock.get(&svc_name).map(|s| s.config.backoff_ms).unwrap_or(1000)
                };
                thread::sleep(Duration::from_millis(backoff));
                let _ = sup.start_service(&svc_name);
            });
        }
    }
}

fn run_health_check_loop(supervisor: Arc<Supervisor>) {
    while RUNNING.load(Ordering::Relaxed) {
        thread::sleep(Duration::from_secs(1));

        let checks_to_run: Vec<(String, Vec<String>, u64, bool)> = {
            let lock = supervisor.services.lock().unwrap();
            let mut list = Vec::new();
            for (name, svc) in lock.iter() {
                if svc.state == ServiceState::Running {
                    if let Some(ref cmd) = svc.config.health_command {
                        let interval = svc.config.health_interval_sec.unwrap_or(15);
                        let should_check = match svc.last_health_check {
                            Some(last) => last.elapsed() >= Duration::from_secs(interval),
                            None => true,
                        };
                        if should_check {
                            list.push((
                                name.clone(),
                                cmd.clone(),
                                svc.config.health_timeout_sec,
                                svc.config.restart_on_unhealthy,
                            ));
                        }
                    }
                }
            }
            list
        };

        for (name, cmd_args, _timeout, restart_on_unhealthy) in checks_to_run {
            if cmd_args.is_empty() {
                continue;
            }
            let success = match Command::new(&cmd_args[0])
                .args(&cmd_args[1..])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status()
            {
                Ok(s) => s.success(),
                Err(_) => false,
            };

            let mut lock = supervisor.services.lock().unwrap();
            if let Some(svc) = lock.get_mut(&name) {
                svc.last_health_check = Some(Instant::now());
                if success {
                    svc.is_healthy = true;
                    svc.consecutive_health_failures = 0;
                } else {
                    svc.consecutive_health_failures += 1;
                    svc.is_healthy = false;
                    svc.append_log(&format!(
                        "Health check failed (consecutive failures: {})",
                        svc.consecutive_health_failures
                    ));

                    if restart_on_unhealthy && svc.consecutive_health_failures >= 3 {
                        svc.append_log("Service exceeded consecutive health check failures; restarting...");
                        let sup = Arc::clone(&supervisor);
                        let n = name.clone();
                        thread::spawn(move || {
                            let _ = sup.restart_service(&n);
                        });
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// IPC Server (UNIX Domain Socket)
// ---------------------------------------------------------------------------

fn run_ipc_server(supervisor: Arc<Supervisor>) {
    let _ = fs::create_dir_all("/run/ferro");
    if Path::new(SOCKET_PATH).exists() {
        let _ = fs::remove_file(SOCKET_PATH);
    }

    let listener = match UnixListener::bind(SOCKET_PATH) {
        Ok(l) => {
            // Set socket permissions 0660
            let _ = fs::set_permissions(SOCKET_PATH, fs::Permissions::from_mode(0o660));
            l
        }
        Err(e) => {
            eprintln!("[ferro-superd] Failed to bind IPC socket {}: {}", SOCKET_PATH, e);
            return;
        }
    };

    println!("[ferro-superd] Listening for CLI commands on {}", SOCKET_PATH);

    for stream in listener.incoming() {
        if !RUNNING.load(Ordering::Relaxed) {
            break;
        }
        if let Ok(mut stream) = stream {
            let sup = Arc::clone(&supervisor);
            thread::spawn(move || {
                handle_client(&mut stream, &sup);
            });
        }
    }
}

fn handle_client(stream: &mut UnixStream, supervisor: &Supervisor) {
    let mut reader = BufReader::new(stream.try_clone().unwrap());
    let mut line = String::new();

    if reader.read_line(&mut line).is_ok() {
        let trimmed = line.trim();
        let response = dispatch_ipc_command(trimmed, supervisor);
        let _ = stream.write_all(response.as_bytes());
        let _ = stream.write_all(b"\n");
    }
}

fn dispatch_ipc_command(cmd_json: &str, supervisor: &Supervisor) -> String {
    // Parse action from simple JSON
    let action = extract_json_field(cmd_json, "action").unwrap_or_default();
    let service = extract_json_field(cmd_json, "service");

    match action.as_str() {
        "list" => {
            let lock = supervisor.services.lock().unwrap();
            let mut list = Vec::new();
            for (name, svc) in lock.iter() {
                let (mem_bytes, cpu_usec) = read_cgroup_metrics(name);
                list.push(format!(
                    r#"{{"name":"{}","description":"{}","state":"{}","pid":{},"uptime_sec":{},"restarts":{},"healthy":{},"memory_bytes":{},"cpu_usec":{}}}"#,
                    svc.config.name,
                    escape_json(&svc.config.description),
                    svc.state.as_str(),
                    svc.pid.map(|p| p.to_string()).unwrap_or_else(|| "null".to_string()),
                    svc.uptime_seconds,
                    svc.restart_count,
                    svc.is_healthy,
                    mem_bytes,
                    cpu_usec
                ));
            }
            format!(r#"{{"status":"ok","services":[{}]}}"#, list.join(","))
        }
        "start" => {
            if let Some(name) = service {
                match supervisor.start_service(&name) {
                    Ok(pid) => format!(r#"{{"status":"ok","message":"Started service {}","pid":{}}}"#, name, pid),
                    Err(e) => format!(r#"{{"status":"error","message":"{}"}}"#, escape_json(&e)),
                }
            } else {
                r#"{"status":"error","message":"Missing 'service' parameter"}"#.to_string()
            }
        }
        "stop" => {
            if let Some(name) = service {
                match supervisor.stop_service(&name, 5) {
                    Ok(_) => format!(r#"{{"status":"ok","message":"Stopped service {}"}}"#, name),
                    Err(e) => format!(r#"{{"status":"error","message":"{}"}}"#, escape_json(&e)),
                }
            } else {
                r#"{"status":"error","message":"Missing 'service' parameter"}"#.to_string()
            }
        }
        "restart" => {
            if let Some(name) = service {
                match supervisor.restart_service(&name) {
                    Ok(pid) => format!(r#"{{"status":"ok","message":"Restarted service {}","pid":{}}}"#, name, pid),
                    Err(e) => format!(r#"{{"status":"error","message":"{}"}}"#, escape_json(&e)),
                }
            } else {
                r#"{"status":"error","message":"Missing 'service' parameter"}"#.to_string()
            }
        }
        "status" => {
            if let Some(name) = service {
                let lock = supervisor.services.lock().unwrap();
                if let Some(svc) = lock.get(&name) {
                    let (mem_bytes, cpu_usec) = read_cgroup_metrics(&name);
                    format!(
                        r#"{{"status":"ok","service":"{}","description":"{}","state":"{}","pid":{},"uptime_sec":{},"restarts":{},"healthy":{},"memory_bytes":{},"cpu_usec":{},"memory_max_mb":{},"cpu_weight":{}}}"#,
                        svc.config.name,
                        escape_json(&svc.config.description),
                        svc.state.as_str(),
                        svc.pid.map(|p| p.to_string()).unwrap_or_else(|| "null".to_string()),
                        svc.uptime_seconds,
                        svc.restart_count,
                        svc.is_healthy,
                        mem_bytes,
                        cpu_usec,
                        svc.config.memory_max_mb.map(|m| m.to_string()).unwrap_or_else(|| "null".to_string()),
                        svc.config.cpu_weight.map(|w| w.to_string()).unwrap_or_else(|| "null".to_string())
                    )
                } else {
                    format!(r#"{{"status":"error","message":"Service '{}' not found"}}"#, escape_json(&name))
                }
            } else {
                r#"{"status":"error","message":"Missing 'service' parameter"}"#.to_string()
            }
        }
        "logs" => {
            if let Some(name) = service {
                let lock = supervisor.services.lock().unwrap();
                if let Some(svc) = lock.get(&name) {
                    let lines: Vec<String> = svc.log_buffer.iter().map(|l| format!(r#""{}""#, escape_json(l))).collect();
                    format!(r#"{{"status":"ok","service":"{}","logs":[{}]}}"#, name, lines.join(","))
                } else {
                    format!(r#"{{"status":"error","message":"Service '{}' not found"}}"#, escape_json(&name))
                }
            } else {
                r#"{"status":"error","message":"Missing 'service' parameter"}"#.to_string()
            }
        }
        "reload" => {
            supervisor.load_manifests();
            r#"{"status":"ok","message":"Manifests reloaded successfully"}"#.to_string()
        }
        _ => format!(r#"{{"status":"error","message":"Unknown action '{}'"}}"#, escape_json(&action)),
    }
}

// ---------------------------------------------------------------------------
// Manifest TOML Parser (Self-Contained Pure Rust)
// ---------------------------------------------------------------------------

fn parse_service_toml(path: &Path) -> Result<ServiceConfig, String> {
    let content = fs::read_to_string(path).map_err(|e| e.to_string())?;

    let default_name = path.file_stem().and_then(|s| s.to_str()).unwrap_or("unknown").to_string();
    let mut name = default_name;
    let mut description = String::new();
    let mut command: Vec<String> = Vec::new();
    let mut working_dir = "/".to_string();
    let mut user = None;
    let mut group = None;
    let mut restart_policy = RestartPolicy::Always;
    let mut max_retries = 5;
    let mut backoff_ms = 1000;
    let mut memory_max_mb = None;
    let mut memory_high_mb = None;
    let mut cpu_weight = None;
    let mut pids_max = None;
    let mut health_interval_sec = None;
    let mut health_command = None;
    let mut health_timeout_sec = 5;
    let mut restart_on_unhealthy = false;

    for raw_line in content.lines() {
        let line = raw_line.trim();
        if line.is_empty() || line.starts_with('#') || line.starts_with('[') {
            continue;
        }

        if let Some((k, v)) = line.split_once('=') {
            let key = k.trim();
            let val = v.trim();

            match key {
                "name" => name = strip_quotes(val),
                "description" => description = strip_quotes(val),
                "working_dir" => working_dir = strip_quotes(val),
                "user" => user = Some(strip_quotes(val)),
                "group" => group = Some(strip_quotes(val)),
                "command" => command = parse_string_array(val),
                "policy" => {
                    let p = strip_quotes(val);
                    restart_policy = match p.as_str() {
                        "always" => RestartPolicy::Always,
                        "on-failure" => RestartPolicy::OnFailure,
                        "never" => RestartPolicy::Never,
                        _ => RestartPolicy::Always,
                    };
                }
                "max_retries" => max_retries = val.parse::<u32>().unwrap_or(5),
                "backoff_ms" => backoff_ms = val.parse::<u64>().unwrap_or(1000),
                "memory_max_mb" => memory_max_mb = val.parse::<u64>().ok(),
                "memory_high_mb" => memory_high_mb = val.parse::<u64>().ok(),
                "cpu_weight" => cpu_weight = val.parse::<u32>().ok(),
                "pids_max" => pids_max = val.parse::<u32>().ok(),
                "check_interval_sec" => health_interval_sec = val.parse::<u64>().ok(),
                "check_command" => health_command = Some(parse_string_array(val)),
                "timeout_sec" => health_timeout_sec = val.parse::<u64>().unwrap_or(5),
                "restart_on_unhealthy" => restart_on_unhealthy = val == "true",
                _ => {}
            }
        }
    }

    if command.is_empty() {
        return Err("Manifest missing 'command'".to_string());
    }

    Ok(ServiceConfig {
        name,
        description,
        command,
        working_dir,
        user,
        group,
        restart_policy,
        max_retries,
        backoff_ms,
        memory_max_mb,
        memory_high_mb,
        cpu_weight,
        pids_max,
        health_interval_sec,
        health_command,
        health_timeout_sec,
        restart_on_unhealthy,
    })
}

fn strip_quotes(s: &str) -> String {
    let t = s.trim();
    if (t.starts_with('"') && t.ends_with('"')) || (t.starts_with('\'') && t.ends_with('\'')) {
        if t.len() >= 2 {
            return t[1..t.len() - 1].to_string();
        }
    }
    t.to_string()
}

fn parse_string_array(s: &str) -> Vec<String> {
    let trimmed = s.trim();
    if !trimmed.starts_with('[') || !trimmed.ends_with(']') {
        return Vec::new();
    }
    let inner = &trimmed[1..trimmed.len() - 1];
    let mut result = Vec::new();
    for part in inner.split(',') {
        let p = part.trim();
        if !p.is_empty() {
            result.push(strip_quotes(p));
        }
    }
    result
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
            let end = rest.find(|c: char| c == ',' || c == '}').unwrap_or(rest.len());
            return Some(rest[..end].trim().to_string());
        }
    }
    None
}

fn escape_json(s: &str) -> String {
    s.replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
}

fn current_iso_timestamp() -> String {
    let d = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default();
    format!("{}.{:03}Z", d.as_secs(), d.subsec_millis())
}

// ---------------------------------------------------------------------------
// Main Entrypoint
// ---------------------------------------------------------------------------

fn main() {
    println!("================================================================");
    println!("   FERRO-SUPERD: Pure-Rust Cgroup v2 Service Supervisor Daemon   ");
    println!("================================================================");

    let supervisor = Supervisor::new();
    supervisor.load_manifests();

    // Auto-start any service configured with restart = "always"
    {
        let services_to_start: Vec<String> = {
            let lock = supervisor.services.lock().unwrap();
            lock.iter()
                .filter(|(_, svc)| svc.config.restart_policy == RestartPolicy::Always)
                .map(|(name, _)| name.clone())
                .collect()
        };

        for name in services_to_start {
            let _ = supervisor.start_service(&name);
        }
    }

    // Spawn background monitoring threads
    let sup1 = Arc::clone(&supervisor);
    thread::spawn(move || {
        run_supervision_loop(sup1);
    });

    let sup2 = Arc::clone(&supervisor);
    thread::spawn(move || {
        run_health_check_loop(sup2);
    });

    // Start IPC server (blocks)
    run_ipc_server(supervisor);
}
