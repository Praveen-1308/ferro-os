# FerroOS Service Supervision (`ferro-superd`)

[`ferro-superd`](file:///home/tarun-kumar/Desktop/sample%20os%20/crates/ferro-superd/src/main.rs) is the primary service manager and process supervisor for FerroOS. It is a lightweight, single-process, asynchronous daemon compiled in 483 KB of pure Rust.

---

## 1. Supervisor Architecture

Unlike `systemd` which requires dozens of background daemons and complex D-Bus IPC brokers, `ferro-superd` operates over a clean Unix Domain Socket:
* **Control Socket**: `/run/ferro/superd.sock`
* **Protocol**: Line-delimited JSON-RPC 2.0 payloads.
* **Declarative Service Manifests**: Automatically watches and loads `/etc/ferro/services/*.toml`.
* **State Machine**: Tracks service states: `Stopped`, `Starting`, `Running`, `Degraded`, `Failed`.

---

## 2. Declarative Service Manifest Specification

Services are defined as standard TOML files:

```toml
[service]
name = "api-gateway"
description = "High-Performance Cloud API Gateway"
command = ["/usr/bin/ferro-core", "server-suite", "--port", "8080"]
working_dir = "/home/ferro"
user = "ferro"
group = "ferro"
restart = "always"             # Options: "always", "on-failure", "never"
restart_delay_ms = 500

# Cgroups v2 Resource Governance
memory_max_mb = 128            # Hard limit written to memory.max
cpu_quota = "200%"             # Up to 2 full CPU cores (cpu.max)
pids_max = 64                  # Maximum processes / threads (pids.max)

# Linux Capabilities
capabilities = ["CAP_NET_BIND_SERVICE"]

# Health Probes
health_check_http = "http://127.0.0.1:8080/api/health"
health_interval_sec = 5
```

---

## 3. Cgroups v2 Resource Enforcement Mechanics

When `ferro-superd` spawns a service, it creates a dedicated control group under `/sys/fs/cgroup/ferro/<service_name>/`:
1. **Deterministic OOM Termination**:
   - `memory.max` is set to `memory_max_mb * 1024 * 1024`.
   - **`memory.swap.max = 0`**: Explicitly disables swap spilling for the cgroup. Rogue memory leaks immediately invoke the Linux OOM killer (exit code 137) rather than grinding the host system to a halt through swap thrashing.
2. **Fork-Bomb Immunity**:
   - `pids.max` sets a strict upper bound on thread creation. Recursive process attacks hit `EAGAIN` immediately at the quota boundary.
3. **CPU Quotas**:
   - Translated to `cpu.max` format: `quota_usec period_usec` (e.g. `200000 100000` for 200%).

---

## 4. Sysadmin CLI Reference (`ferro service`)

The `ferro service` applet in `ferro-core` communicates directly with `ferro-superd`:

### List Active Services
```bash
ferro service list
```
*Output:*
```
SERVICE              STATE        PID       UPTIME    RESTARTS   MEMORY
twelve-dollar        Running      412       12m 45s   0          24.5 MB
dns                  Running      414       12m 45s   0          3.1 MB
supervise            Running      388       12m 47s   0          2.6 MB
```

### Inspect Detailed Service Status
```bash
ferro service status twelve-dollar
```
*With JSON output for automated scripting:*
```bash
ferro service status twelve-dollar --json
```

### Control Service Lifecycle
```bash
# Gracefully stop a service (SIGTERM followed by SIGKILL if timeout exceeds 5s)
ferro service stop twelve-dollar

# Start or restart a service
ferro service start twelve-dollar
ferro service restart twelve-dollar
```

### Stream Live Service Logs
```bash
# Read in-memory ring-buffer logs
ferro service logs twelve-dollar --tail 50
```
