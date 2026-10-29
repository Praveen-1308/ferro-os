# FerroOS Chaos Engineering & Negative Scenarios

How does an operating system behave under unexpected faults, sudden power cuts, malicious exploits, or broken internal communications?

To prove that FerroOS is resilient against real-world production failures, we constructed an empirical adversarial test suite in [`tools/test_negative_scenarios_and_chaos.py`](file:///home/tarun-kumar/Desktop/sample%20os%20/tools/test_negative_scenarios_and_chaos.py). All 9 scenarios are verified automatically in CI.

---

## The 9 Adversarial Threat Models & Outcomes

```mermaid
graph TD
    subgraph Attacks ["Adversarial Chaos & Negative Scenarios"]
        S1["Scenario 1: Sudden SIGKILL on Critical Daemon"]
        S2["Scenario 2: Malformed / Corrupted TOML Manifest"]
        S3["Scenario 3: Garbage RPC Payload on Unix Socket"]
        S4["Scenario 4: Rogue Memory Bomb (OOM Attack)"]
        S5["Scenario 5: Malicious Fork Bomb (PID Exhaustion)"]
        S6["Scenario 6: Sandbox Escape & Privilege Escalation"]
        S7["Scenario 7: Read-Only Path Traversal Attack"]
        S8["Scenario 8: Non-Existent Executable Invocation"]
        S9["Scenario 9: Abrupt IPC Broker Crash (Broken Pipe)"]
    end

    subgraph Defenses ["FerroOS Autonomous Defenses"]
        D1["< 200ms Instant Supervised Respawn"]
        D2["Zero-Panic TOML Parser Fallback"]
        D3["Graceful JSON-RPC Error -32700"]
        D4["Kernel OOM Exit 137 (memory.swap.max=0)"]
        D5["Cgroups pids.max=128 (Host Preserved)"]
        D6["Kernel Landlock Permission Denied (EACCES)"]
        D7["Read-Only Block on System Root (EROFS)"]
        D8["Safe Exit Code 127 Handled Gracefully"]
        D9["EPIPE Handled with Zero Hanging Sockets"]
    end

    S1 --> D1
    S2 --> D2
    S3 --> D3
    S4 --> D4
    S5 --> D5
    S6 --> D6
    S7 --> D7
    S8 --> D8
    S9 --> D9
```

---

## Detailed Scenario Breakdown

### Scenario 1: Sudden Process Termination (`SIGKILL -9`)
* **Adversarial Action**: A critical production service (`qa-worker`) is abruptly terminated via uncatchable `kill -9`.
* **Expected Failure in Legacy OS**: Service remains dead or requires manual systemctl intervention.
* **FerroOS Defense**: `ferro-superd` catches the child exit signal (`SIGCHLD`), detects ungraceful termination, logs the event to the in-memory ring buffer, and automatically respawns the daemon with a fresh PID in **< 200 ms**.

### Scenario 2: Corrupted TOML Service Manifest
* **Adversarial Action**: A damaged, partially written, or malformed TOML file (`corrupted.toml`) containing invalid syntax is placed in `/etc/ferro/services/`.
* **Expected Failure in Legacy OS**: Supervisor crashes on startup, preventing legitimate services from booting.
* **FerroOS Defense**: `ferro-superd` uses safe parser combinators with error recovery; the malformed file is quarantined and logged as an error, while all healthy services continue uninterrupted.

### Scenario 3: Malformed RPC Payloads on Control Socket
* **Adversarial Action**: High-frequency random garbage bytes and invalid JSON structures are written to `/run/ferro/superd.sock`.
* **FerroOS Defense**: The JSON-RPC handler parses streams safely, returning JSON-RPC error `-32700 (Parse error)` without panicking or dropping the socket connection.

### Scenario 4: Rogue Memory Bomb (OOM Quota Exhaustion)
* **Adversarial Action**: A runaway memory leak attempts to allocate 100 GB of RAM.
* **Expected Failure in Legacy OS**: Anonymous pages spill into swap disk, freezing all host processes and causing minutes of disk thrashing.
* **FerroOS Defense**: `ferro-superd` sets `memory.swap.max = 0` on every service cgroup. The rogue process is terminated immediately by the Linux kernel OOM killer (exit code 137) at its quota boundary (e.g. 64 MB), without affecting other system services.

### Scenario 5: Fork Bomb Attack (`:(){ :|:& };:`)
* **Adversarial Action**: A rogue script recursively spawns endless child processes to exhaust host process table slots.
* **Expected Failure in Legacy OS**: System PID table exhausted; sysadmin cannot open an SSH terminal or issue `kill`.
* **FerroOS Defense**: `ferro-superd` enforces `pids.max = 128`. The 129th fork call returns `EAGAIN` (`Resource temporarily unavailable`), containing the attack within its private cgroup.

### Scenario 6: Unprivileged Sandbox Escape Attempt
* **Adversarial Action**: A sandboxed process attempts to write directly into `/etc/passwd` or `/root/.ssh/authorized_keys`.
* **FerroOS Defense**: Landlock LSM denies permission at the VFS layer (`EACCES`), blocking the write in **2.0 ms**.

### Scenario 7: Path Traversal Attack (`../../etc/shadow`)
* **Adversarial Action**: A sandboxed worker uses directory traversal sequences (`/tmp/scratch/../../etc/shadow`) to escape read-only boundaries.
* **FerroOS Defense**: Path resolution is canonicalized before syscall dispatch, blocking traversal at the root barrier (`EACCES`).

### Scenario 8: Non-Existent Executable Invocation
* **Adversarial Action**: Service manifest references a missing binary (`/usr/bin/missing_binary_404`).
* **FerroOS Defense**: `ferro-superd` detects execution failure, transitions state to `Failed`, and returns standard exit code 127 without supervisor crash.

### Scenario 9: Abrupt IPC Broker Crash & Broken Pipe Recovery
* **Adversarial Action**: The message broker terminates while client applications are actively streaming payloads.
* **Expected Failure in Legacy OS**: Clients hang indefinitely on blocking writes or crash from unhandled `SIGPIPE`.
* **FerroOS Defense**: Clients catch `EPIPE` / `BrokenPipeError` gracefully, close the stale file descriptor, and back off to exponential reconnect intervals.
