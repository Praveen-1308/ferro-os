# FerroOS Developer & Contributor Guide

Welcome to the FerroOS developer documentation. FerroOS is 100% open-source, written in pure Rust, and designed for rapid local compilation, reproducible container builds, and straightforward bare-metal deployments.

---

## Developer Documentation Index

| Topic | Document | Summary |
| :--- | :--- | :--- |
| **Build & Appliance Packaging** | [BUILD_AND_PACKAGING.md](BUILD_AND_PACKAGING.md) | Compiling the 9 Rust crates, building specialized appliance images, ISO generation, and QEMU hardware emulation. |
| **Codebase Survey & Visual Graph** | [CODEBASE_SURVEY_AND_GRAPH.md](CODEBASE_SURVEY_AND_GRAPH.md) | Full audit of the 22,824 lines of code, 519 functions, 49 structs, and interactive SVG architecture graph. |

---

## Workspace Structure at a Glance

The FerroOS codebase is structured as a cargo workspace with 9 member crates:

```
crates/
  ├── ferro-init/                 # The pure-Rust PID 1 init system & early mount coordinator
  ├── ferro-core/                 # Multi-call binary: shell, 30/30 coreutils, Landlock sandbox
  ├── ferro-superd/               # Cgroups v2 declarative service supervisor & JSON-RPC manager
  ├── ferrocage/                  # Sub-2ms pure-Rust micro-containerization runtime
  ├── ferro-pkg/                  # "rpk" multi-arch package keeper & PE/MSI introspector
  ├── ferro-gui/                  # Direct /dev/fb0 pure-Rust double-buffered window manager
  ├── ferro-compositor/           # Pure-Rust Wayland DRM/KMS compositor with dual-Kawase shaders
  ├── xdg-desktop-portal-ferro/   # Native Wayland XDG Desktop Portal backend
  └── ferro-io/                   # Pure-Rust io_uring asynchronous POSIX acceleration shim
```
