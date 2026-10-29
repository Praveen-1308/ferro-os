# FerroOS Codebase Survey & Interactive Architecture Graph

To maintain absolute architectural transparency and verify all system invariants, FerroOS includes an automated survey engine in [`tools/survey_full_ferro_os.py`](file:///home/tarun-kumar/Desktop/sample%20os%20/tools/survey_full_ferro_os.py) and an interactive visual HTML graph in [`docs/ferro_os_architecture_graph.html`](file:///home/tarun-kumar/Desktop/sample%20os%20/docs/ferro_os_architecture_graph.html).

---

## 1. Codebase Audit Metrics

* **Survey Engine Execution**: Run `python3 tools/survey_full_ferro_os.py`
* **Audit Dataset**: [`tools/reports/ferro_os_full_codebase_survey.json`](file:///home/tarun-kumar/Desktop/sample%20os%20/tools/reports/ferro_os_full_codebase_survey.json)

| Survey Dimension | Metric Count | Note |
| :--- | :--- | :--- |
| **Rust Source Files Scanned** | **26 files** | Across all 9 workspace crates |
| **Total Lines of Source** | **22,824 lines** | 100% memory-safe pure Rust |
| **Pure Code Lines** | **19,817 lines** | Zero C userspace dependencies |
| **Architectural Invariant Comments** | **860 lines (3.8%)** | Detailed docstrings & safety contracts |
| **Functions Defined (`fn`)** | **519 functions** | Strongly typed, modular logic |
| **Data Structures (`struct`)** | **49 structs** | Domain models & resource controllers |
| **Enumerations (`enum`)** | **12 enums** | State machines & error boundaries |
| **Extracted System Invariants** | **98 invariants** | Verified architectural properties |

---

## 2. Interactive SVG Architecture Graph Visualizer

The complete operating system topology—from hardware peripherals and kernel primitives up through the four specialized editions—is rendered interactively in **[`docs/ferro_os_architecture_graph.html`](file:///home/tarun-kumar/Desktop/sample%20os%20/docs/ferro_os_architecture_graph.html)**:

* **Zero External Dependencies**: 100% standalone and offline-capable (no external CDNs, fonts, or tracking scripts).
* **Dual Layout Modes**:
  - **Hierarchical Layout (10 Layers)**: Clear top-down execution flow from Hardware $\rightarrow$ Kernel $\rightarrow$ POSIX $\rightarrow$ Daemons $\rightarrow$ Editions $\rightarrow$ Workloads.
  - **Radial Force-Directed View**: Clustered graph showing component relationships and cross-edition connections.
* **Edition Filter Bar**: Switch views instantly between:
  - `All Systems (Universal)`
  - `Cloud Server Edition`
  - `Desktop & Web Edition`
  - `Gaming & Proton Edition`
* **Real-Time Search**: Search by component name, layer, struct, or syscall.
* **Interactive Inspector Panel**: Click any node to view exact line counts, key functions, structs, and extracted source code invariants.

---

## 3. Opening the Graph Locally

To view the graph in your browser:
```bash
# Open directly in browser
xdg-open docs/ferro_os_architecture_graph.html
# Or start local static webserver:
python3 -m http.server 8089 -d docs/
# Open http://localhost:8089/ferro_os_architecture_graph.html
```
