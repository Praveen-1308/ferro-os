# How to Use FerroOS 🦀⚡
### *Practical Playbooks, Simple Use Cases, and Customization Guide*

Welcome to the FerroOS practical playbook! This guide provides simple, copy-paste ready recipes to help you run, test, deploy, and customize FerroOS for your own projects.

---

## 📑 Table of Contents
1. [The $12 Server Concurrency Challenge (Low-RAM Droplet)](#1-the-12-server-concurrency-challenge-low-ram-droplet)
2. [Ultra-Fast Cloud Microservices & Web API Engine](#2-ultra-fast-cloud-microservices--web-api-engine)
3. [Zero-Install Cloud Desktop in Your Browser (noVNC)](#3-zero-install-cloud-desktop-in-your-browser-novnc)
4. [Running Windows Apps & Games on ARM64 / Linux (`ferro win-run`)](#4-running-windows-apps--games-on-arm64--linux-ferro-win-run)
5. [1-Click Windows 10/11 WSL2 Appliance (< 1 MB)](#5-1-click-windows-1011-wsl2-appliance--1-mb)
6. [Bare-Metal Bootable ISO & Instant Snapshot Rollbacks](#6-bare-metal-bootable-iso--instant-snapshot-rollbacks)
7. [How to Customize & Modify FerroOS for Your Needs](#7-how-to-customize--modify-ferroos-for-your-needs)

---

## 1. The $12 Server Concurrency Challenge (Low-RAM Droplet)

> **💡 The Pitch:**  
> *"If you want the ultimate base image for your next $12 server concurrency challenge, check out the FerroOS Dedicated Server OCI Container (`ferro-os-server:latest`). It runs 4 active microservices (including a native Rust HTTP server and shared-memory DNS cache) under < 30 MB of idle RAM, preloads mimalloc globally to eliminate allocator lock contention, and routes I/O through io_uring—all while giving you full glibc compatibility so python/C scripts run instantly without build errors. Drop it onto a 1 vCPU / 2 GB droplet and watch how it handles your heavy load tests!"*

*Inspired by software engineer and YouTuber **Arjay McCandless** ([`@arjaythedev`](https://youtube.com/@arjay_the_dev)) and his popular **"Twelve Dollar Server Challenge"** ([`arjaythedev/twelve-dollar-server-challenge`](https://github.com/arjaythedev/twelve-dollar-server-challenge)), FerroOS provides a dedicated test harness reproducing the exact 1 vCPU / 2 GB RAM challenge rules.*

📄 **Read the In-Depth Whitepaper**: [The $12 Server Concurrency Challenge Report](docs/reports/arjay_twelve_dollar_server_challenge.md)

### 🚀 1-Minute Launch
Run the pre-configured server container under strict memory limits:

```bash
# Clone the repository
git clone https://github.com/Praveen-1308/ferro-os.git
cd ferro-os

# Build the ultra-lean dedicated server image (113 MB download)
docker build -f Dockerfile.server -t ferro-os-server:latest .

# Run with a 2 GB memory ceiling (or even 512 MB!)
docker run -d \
  --name ferro-server \
  --memory=2g \
  --cpus=1.0 \
  -p 8080:8080 \
  -p 8081:8081 \
  -p 8088:8088 \
  -p 9123:9123 \
  ferro-os-server:latest
```

### 🧪 Run the Automated Arjay McCandless $12 Challenge Harness
Evaluate SQLite performance across 5 API endpoints (`/users/:id`, `/users/:id/feed`, `/posts/:id`, `/posts/:id/like`, `/metrics`) under concurrent loads of 100 to 1,000 virtual users:
```bash
# Run the automated benchmark suite
python3 tools/benchmark_twelve_dollar_challenge.py
```

### 🔍 Verify How Little RAM It Uses
Check live resource usage inside the container:
```bash
docker stats ferro-server --no-stream
```
*You will observe that all 4 active background microservices idle at **less than 30 MB total RAM**!*

---

## 2. Ultra-Fast Cloud Microservices & Web API Engine

The server container comes pre-equipped with 4 high-concurrency microservices ready to accept production traffic immediately:

### A. Real-Time Hardware Telemetry API (Port 8080)
Retrieve live CPU, core count, memory usage, and kernel telemetry in JSON:
```bash
curl http://localhost:8080/api/status
```
*Sample JSON Response:*
```json
{
  "server": "FerroOS Telemetry Microservice",
  "os": "FerroOS 64-Bit Hybrid",
  "kernel": "6.8.0-generic",
  "arch": "aarch64",
  "cores": 4,
  "ram_total_mb": 2048.0,
  "ram_used_mb": 28.5,
  "ram_percent": 1.4,
  "active_processes": 5
}
```

### B. High-Speed In-Memory Key-Value Store (Port 8081)
Use FerroOS's lock-free memory storage engine for fast session caching:
```bash
# Store a key
curl -X POST -H "Content-Type: application/json" \
  -d '{"key": "session_user_42", "value": {"tier": "enterprise", "credits": 500}}' \
  http://localhost:8081/set

# Retrieve the key instantly
curl "http://localhost:8081/get?key=session_user_42"
```

### C. Native Pure-Rust Zero-Copy Web Server (Port 8088)
Hosts your static assets and web application directly via `ferro-core serve`:
```bash
curl -I http://localhost:8088/
```
*Notice the custom telemetry header `X-Ferro-Server-Time-Us: 42`, reporting server processing latency down to the exact microsecond.*

---

## 3. Zero-Install Cloud Desktop in Your Browser (noVNC)

Want a full graphical Linux workstation with KDE Plasma 5.27, hardware-accelerated 3D graphics (Mesa/Vulkan), VS Code, and Chromium that runs in any browser tab?

```bash
# Build the official desktop edition
docker build -t ferro-os-web:latest .

# Run under a strict 6 GB container limit
docker run -d \
  --name ferro-desktop \
  --memory=6g \
  -p 6080:6080 \
  ferro-os-web:latest
```

👉 **Open your browser and navigate to: `http://localhost:6080`**  
You have immediate mouse, keyboard, and graphical interaction with zero client software required!

---

## 4. Running Windows Apps & Games on ARM64 / Linux (`ferro win-run`)

FerroOS features an integrated Windows compatibility subsystem that allows you to install `.msi` packages in pure Rust and launch 64-bit `.exe` binaries with real-time `sched_ext` gaming priority:

### A. Unpack a Windows `.msi` in Pure Rust (Zero Windows VM Overhead)
```bash
# Inspect the MSI streams and embedded executables
rpk msi-info setup.msi

# Extract files into an isolated prefix in under 50 milliseconds
rpk msi-extract setup.msi --target ~/.ferro/prefixes/myapp
```

### B. Launch Any 64-Bit Windows Executable or 3D Game
```bash
# Launch with lock-free mimalloc 2.1 and 500µs gaming preemption
ferro win-run ~/.ferro/prefixes/myapp/Program.exe --gaming --mimalloc
```
*DirectX 11/12 calls are transparently translated through DXVK / VKD3D directly into native Vulkan shaders.*

---

## 5. 1-Click Windows 10/11 WSL2 Appliance (< 1 MB)

Run FerroOS's pure-Rust userspace natively inside Windows Subsystem for Linux (WSL2):

1. Grab the rootfs archive: [`build_out/ferro-os-wsl2-rootfs.tar.gz`](build_out/ferro-os-wsl2-rootfs.tar.gz) (only **901 KB**).
2. Open PowerShell or Command Prompt on Windows:
   ```cmd
   # Import the appliance
   wsl --import FerroOS C:\FerroOS ferro-os-wsl2-rootfs.tar.gz

   # Launch into FerroOS
   wsl -d FerroOS
   ```
You are now running `ferro-init`, `ferro-core`, and `rpk` natively with sub-millisecond cold boot inside Windows!

---

## 6. Bare-Metal Bootable ISO & Instant Snapshot Rollbacks

### A. Generate a Bootable Hybrid UEFI/BIOS ISO
Generate a standard ISO 9660 image bootable on real hardware or virtual machines (QEMU/VirtualBox/Proxmox):
```bash
# Build bootable Desktop ISO
python3 tools/iso/build_ferro_iso.py --edition desktop --output build_out/ferro-os-desktop-live.iso

# Build bootable Server ISO
python3 tools/iso/build_ferro_iso.py --edition server --output build_out/ferro-os-server-live.iso
```

### B. Instant Btrfs Recovery Snapshots & Rollbacks
Once running on hardware or VM, safeguard your system against update failures:
```bash
# Check Btrfs snapshot acceleration status
ferro-core snapshot status

# Create an instantaneous O(1) golden recovery point
ferro-core snapshot create @golden_checkpoint

# If an update or experimental package breaks something, roll back instantly:
ferro-core snapshot rollback @golden_checkpoint
```

---

## 7. How to Customize & Modify FerroOS for Your Needs

FerroOS is designed to be easily extensible. Here is how you can customize the system:

### A. Modify Server Ports or Add Your Own Microservices
Edit [`tools/entrypoint-server.sh`](tools/entrypoint-server.sh) or [`tools/ferro-server-suite.py`](tools/ferro-server-suite.py):
* To change the web port from `8088`, change `/usr/local/bin/ferro-core serve 8088 /var/www` in `tools/entrypoint-server.sh`.
* To add custom REST endpoints, open `tools/ferro-server-suite.py` and add new paths under `TelemetryAPIHandler` or `KeyValueHandler`.

### B. Put Your Own Static Website in the Server Container
Replace the default `/var/www/index.html` file in [`Dockerfile.server`](Dockerfile.server):
```dockerfile
# Copy your own HTML/JS/CSS site into the server image
COPY my-website/ /var/www/
```

### C. Add Custom Debian Packages
In [`Dockerfile.server`](Dockerfile.server), add any required libraries to the `apt-get install` block:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    npm \
    postgresql-client \
    ...
```

### D. Rebuilding Modified Binaries
If you modify any Rust code in [`crates/`](crates/):
```bash
# Build optimized release binaries
cargo build --release -p ferro-core -p ferro-init -p ferro-pkg

# Rebuild the server container
docker build -f Dockerfile.server -t ferro-os-server:latest .
```

---

## 💬 Questions & Feedback
Have a cool use case or need help tweaking FerroOS for your infrastructure?  
Start a discussion on our **[GitHub Discussions Portal](https://github.com/Praveen-1308/ferro-os/discussions)**!
