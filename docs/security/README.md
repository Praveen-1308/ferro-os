# FerroOS Security & Isolation Architecture

FerroOS enforces a **Zero-Trust, Memory-Safe Security Architecture** spanning the Linux kernel, system calls, and userspace daemons. By replacing legacy C userspace components with 100% safe Rust and combining kernel-level **Landlock LSM sandboxing** with **Cgroups v2 resource quotas**, FerroOS completely eliminates whole classes of memory corruption vulnerabilities and multi-tenant resource exhaustion exploits.

---

## Security Documentation Index

| Topic | Document | Summary |
| :--- | :--- | :--- |
| **OS Principles & Vulnerability Taxonomy** | [OS_DESIGN_PRINCIPLES_AND_VULNERABILITY_TAXONOMY.md](OS_DESIGN_PRINCIPLES_AND_VULNERABILITY_TAXONOMY.md) | Classical systems literature (Saltzer-Schroeder, OSTEP, TLPI, seL4), 6 universal OS vulnerability classes, and cloud defense rules. |
| **Landlock Sandboxing & Profiles** | [LANDLOCK_SANDBOXING.md](LANDLOCK_SANDBOXING.md) | Unprivileged path delegation, selectable sandbox profiles (`strict`, `shared`, `broker`, `dev`), multi-sandbox shared memory pools. |
| **Kernel Hardening & CWE Defenses**| [SYSTEM_HARDENING_AND_CWE.md](SYSTEM_HARDENING_AND_CWE.md) | KSPP sysctls, zeroize memory wiping, non-root execution (UID 1000), CWE mitigation matrix. |
| **Chaos & Threat Models** | [../testing/CHAOS_AND_NEGATIVE_SCENARIOS.md](../testing/CHAOS_AND_NEGATIVE_SCENARIOS.md) | Empirical testing of 9 negative scenarios: OOM bombs, fork bombs, broker crashes, malformed configs, path traversals. |

---

## Defense-in-Depth Layer Stack

```
+--------------------------------------------------------------------------+
| Layer 4: Pure-Rust Userspace Memory Safety                               |
|   - Zero buffer overflows, use-after-free, or double-free in pure Rust. |
|   - Zeroize memory wiping on cryptographic keys and credentials.         |
+--------------------------------------------------------------------------+
| Layer 3: Unprivileged Landlock LSM Sandboxing                            |
|   - Path delegation (--ro, --rw) enforced directly by Linux kernel.      |
|   - Complete lockdown of /etc, /root, /sys, /proc/kcore without root.    |
+--------------------------------------------------------------------------+
| Layer 2: Cgroups v2 Resource Governance                                  |
|   - memory.max & memory.swap.max = 0 (deterministic OOM killing).        |
|   - pids.max = 128 (immunity against fork bombs).                       |
|   - cpu.max bandwidth quotas (prevents CPU starvation).                  |
+--------------------------------------------------------------------------+
| Layer 1: Hardened Kernel KSPP Parameters                                 |
|   - Restrict dmesg, bpf_jit_harden = 2, kptr_restrict = 2.               |
|   - W^X memory protection, unprivileged eBPF disabled.                   |
+--------------------------------------------------------------------------+
```
