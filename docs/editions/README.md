# The Three Connected Editions of FerroOS

FerroOS provides a single, high-performance, memory-safe pure-Rust core that specializes into three distinct operating system profiles, plus a universal master distribution. Each edition shares the identical Linux ABI, standard GNU coreutils parity, unprivileged Landlock LSM sandboxing, and Cgroups v2 resource governance, but is tuned with domain-specific daemons, kernel parameters, and services.

---

## Edition Matrix & Quick Comparison

| Edition | Primary Focus | Target Environments | RootFS Size | Supervisor RSS | Key Distinguishing Technologies | Documentation |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Cloud Server** | Micro-Appliance & Cloud VMs | AWS EC2, GCP Compute, Azure VMs, Edge | **3.61 MB** | **< 3 MB** | `ferro-superd`, `ferrocage`, `io_uring` POSIX shim, Cloud-Init | [Read Guide](CLOUD_SERVER.md) • [Compliance](CLOUD_STANDARDS_AND_COMPLIANCE.md) |
| **Desktop & Web** | High-Performance Workstation | Laptops, Thin Clients, Remote Workstations | **4.10 MB** | **~15 MB** | `ferro-compositor` (Wayland), `ferro-gui` (/dev/fb0), noVNC port 6080 | [Read Guide](DESKTOP_WEB.md) |
| **Gaming & Proton** | Real-Time Gaming & Emulation | Gaming PCs, Handhelds (Steam Deck), Cloud Gaming | **4.10 MB** | **~12 MB** | `sched_ext` (500µs slice), GameMode (nice -10), Proton runner, DXVK | [Read Guide](GAMING_PROTON.md) |
| **Universal Pure-Rust** | Master Distribution | General Purpose, Development, All Profiles | **4.10 MB** | **Dynamic** | All 8 pure-Rust binaries, all 90+ applets, runtime profile switching | [Build Guide](../developer/BUILD_AND_PACKAGING.md) |

---

## Architectural Shared Foundation

Every edition of FerroOS is built upon the same fundamental pillars:

```mermaid
graph TD
    Kernel["Hardened Linux Kernel (6.1 LTS / 7.0 ABI)"]
    LSM["Landlock LSM Unprivileged Path Governance"]
    Cgroups["Cgroups v2 Resource Controller (swap.max=0, pids.max)"]
    
    Kernel --> LSM
    Kernel --> Cgroups
    
    subgraph Core ["Shared Pure-Rust Core"]
        Init["ferro-init (PID 1)"]
        Coreutils["ferro-core (Multi-Call 30/30 Parity)"]
        Pkg["ferro-pkg (rpk Package Keeper)"]
        IO["libferro_io.so (io_uring Shim)"]
    end
    
    LSM & Cgroups --> Core
    
    Core --> Cloud["1. Cloud Server Edition<br/>ferro-superd + ferrocage"]
    Core --> Desktop["2. Desktop & Web Edition<br/>ferro-compositor + ferro-gui + xdg-portal"]
    Core --> Gaming["3. Gaming & Proton Edition<br/>sched_ext + GameMode + Proton"]
```

---

## Selecting the Right Edition

* Choose **[Cloud Server](CLOUD_SERVER.md)** if you are deploying microservices, web APIs, or running on budget cloud instances ($12 challenge).
* Review **[Cloud Standards & Compliance](CLOUD_STANDARDS_AND_COMPLIANCE.md)** for our POSIX.1, FHS 3.0, OCI runtime spec, CIS Benchmark Level 1/2, and hypervisor guest standards.
* Choose **[Desktop & Web](DESKTOP_WEB.md)** if you need an interactive graphical desktop with zero X11/C bloat that can be accessed locally via DRM/KMS or remotely via a browser.
* Choose **[Gaming & Proton](GAMING_PROTON.md)** if your workload requires sub-50µs scheduler latency, Windows PE binary execution via Proton, or real-time game prioritization.
* Choose **[Universal Master](../developer/BUILD_AND_PACKAGING.md)** if you are building container images or evaluating the full capabilities of FerroOS in one package.
