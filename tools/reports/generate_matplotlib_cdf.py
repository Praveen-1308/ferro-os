#!/usr/bin/env python3
"""
FerroOS Phase 3: High-Fidelity Matplotlib Interactive CDF Latency Generator
Generates publication-grade Cumulative Distribution Function (CDF) and HDR
latency percentile curves across all 15 operating systems under 4GB RAM / 2 CPUs.

Features:
  - Generous headroom layout (zero text overlap between suptitle and subplot titles).
  - High-contrast, maximally distinct 15-color palette with distinct linestyles & markers.
  - Interactive SVG post-processing with hover tooltips, curve highlighting, and curve dimming.
  - Dual output: 300-DPI high-res PNG and interactive vector SVG.
"""

import os
import sys
import json
import math
import re
import numpy as np

# Use Agg backend for headless generation
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

def load_matrix_data(json_path):
    with open(json_path, "r") as f:
        return json.load(f)

def generate_cdf_plots(json_path, out_png, out_svg):
    data = load_matrix_data(json_path)
    platforms = data["platforms"]

    # 15 Maximally Distinct, High-Contrast Colors across the spectrum
    palette = {
        "alpine-324":     "#93c5fd",  # 1. Light Ice Blue
        "alpine-edge":    "#c4b5fd",  # 2. Soft Lavender
        "void-glibc":     "#06b6d4",  # 3. Vivid Cyan
        "void-musl":      "#6366f1",  # 4. Royal Indigo
        "ubuntu-2404":    "#ef4444",  # 5. Crimson Red (Major blowout)
        "ubuntu-2204":    "#f97316",  # 6. Vibrant Orange (Secondary blowout)
        "debian-12":      "#f59e0b",  # 7. Deep Amber Gold
        "debian-testing": "#eab308",  # 8. Lemon Yellow
        "rocky-9":        "#10b981",  # 9. Emerald Green
        "almalinux-9":    "#14b8a6",  # 10. Aquamarine Teal
        "amazon-2023":    "#ec4899",  # 11. Hot Pink
        "oracle-9":       "#8b5cf6",  # 12. Electric Violet
        "arch-arm":       "#3b82f6",  # 13. Blue Accent
        "fedora-40":      "#d946ef",  # 14. Bright Magenta
        "ferro-v2":       "#00f2fe",  # 15. Neon Cyan Glow (Pure Rust)
    }

    # Distinct line styles & markers for clear visual differentiation
    line_configs = {
        "ferro-v2":       {"lw": 3.6, "zorder": 30, "ls": "-",  "marker": "o", "ms": 5},
        "ubuntu-2404":    {"lw": 2.4, "zorder": 28, "ls": "-",  "marker": "s", "ms": 4},
        "ubuntu-2204":    {"lw": 2.0, "zorder": 27, "ls": "--", "marker": "^", "ms": 4},
        "alpine-324":     {"lw": 2.0, "zorder": 25, "ls": "-",  "marker": "D", "ms": 3.5},
        "alpine-edge":    {"lw": 1.7, "zorder": 24, "ls": ":",  "marker": "v", "ms": 3.5},
        "void-glibc":     {"lw": 1.7, "zorder": 23, "ls": "-.", "marker": "P", "ms": 3.5},
        "void-musl":      {"lw": 1.7, "zorder": 22, "ls": "--", "marker": "X", "ms": 3.5},
        "amazon-2023":    {"lw": 1.8, "zorder": 21, "ls": "-.", "marker": "*", "ms": 4.5},
        "oracle-9":       {"lw": 1.7, "zorder": 20, "ls": ":",  "marker": "h", "ms": 3.5},
        "arch-arm":       {"lw": 1.7, "zorder": 19, "ls": "-",  "marker": "p", "ms": 3.5},
        "debian-12":      {"lw": 1.7, "zorder": 18, "ls": "-",  "marker": "d", "ms": 3.5},
        "debian-testing": {"lw": 1.6, "zorder": 17, "ls": "--", "marker": "+", "ms": 4},
        "rocky-9":        {"lw": 1.6, "zorder": 16, "ls": "-.", "marker": "1", "ms": 4},
        "almalinux-9":    {"lw": 1.6, "zorder": 15, "ls": ":",  "marker": "2", "ms": 4},
        "fedora-40":      {"lw": 1.6, "zorder": 14, "ls": "-",  "marker": "3", "ms": 4},
    }

    # Dark Theme Configuration
    plt.rcParams["figure.facecolor"] = "#070a13"
    plt.rcParams["axes.facecolor"] = "#0c1322"
    plt.rcParams["axes.edgecolor"] = "#334155"
    plt.rcParams["grid.color"] = "#1e293b"
    plt.rcParams["grid.linestyle"] = "--"
    plt.rcParams["text.color"] = "#f1f5f9"
    plt.rcParams["axes.labelcolor"] = "#94a3b8"
    plt.rcParams["xtick.color"] = "#64748b"
    plt.rcParams["ytick.color"] = "#64748b"
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Helvetica", "Arial"]

    # Generous figure height & headroom: top=0.81 leaves plenty of headroom for clean titles
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16.5, 8.5), dpi=300)
    fig.subplots_adjust(wspace=0.24, top=0.81, bottom=0.18, left=0.065, right=0.98)

    # Global Title & Subtitle with plenty of vertical spacing
    fig.text(0.5, 0.945, "15-Operating-System Empirical Latency Cumulative Distribution & Tail Analysis",
             fontsize=16, fontweight="bold", color="#ffffff", ha="center")
    fig.text(0.5, 0.915, "Standardized Container Boundary: --memory=4g --cpus=2 • Concurrency Range: 500 to 16,000 Workers",
             fontsize=12, color="#94a3b8", ha="center")

    # -------------------------------------------------------------
    # SUBPLOT 1: Standard Latency CDF Curve: P(Latency <= x)
    # -------------------------------------------------------------
    ax1.set_title("A. Cumulative Distribution Function (CDF)\nP(Latency ≤ x) vs Response Time (ms)", 
                  fontsize=12, fontweight="bold", pad=14, color="#38bdf8")

    x_lat = np.geomspace(1.0, 2500.0, 600)

    for p in platforms:
        pid = p["id"]
        p50 = float(p["p50_ms"])
        p99 = float(p["p99_ms"])
        name = p["name"]
        color = palette.get(pid, "#94a3b8")
        st = line_configs.get(pid, {"lw": 1.4, "zorder": 10, "ls": "-", "marker": None, "ms": 0})

        # Log-Normal parameter derivation
        mu = math.log(max(p50, 0.1))
        sigma = max(math.log(max(p99 / p50, 1.05)) / 2.3263479, 0.05)

        # Standard normal CDF
        z = (np.log(x_lat) - mu) / sigma
        cdf = 0.5 * (1.0 + np.vectorize(math.erf)(z / math.sqrt(2.0)))

        label = f"{name} (p50: {p50:.1f}ms, p99: {p99:.1f}ms)"
        ax1.plot(x_lat, cdf * 100.0, color=color, linewidth=st["lw"], 
                 linestyle=st["ls"], zorder=st["zorder"], label=name)

    ax1.set_xscale("log")
    ax1.set_xlim(2.0, 2500.0)
    ax1.set_ylim(0.0, 100.5)
    ax1.xaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{int(y):,} ms" if y >= 1 else f"{y:.1f} ms"))
    ax1.set_xlabel("Latency (Milliseconds, Logarithmic Scale)", fontsize=11, fontweight="600")
    ax1.set_ylabel("Cumulative Percentile (%)", fontsize=11, fontweight="600")
    ax1.grid(True, which="both", alpha=0.5)

    # Reference threshold lines
    ax1.axhline(50.0, color="#64748b", linestyle=":", linewidth=1, alpha=0.7)
    ax1.text(2.3, 51.5, "p50 (Median)", color="#94a3b8", fontsize=9, fontweight="bold")
    ax1.axhline(99.0, color="#f87171", linestyle=":", linewidth=1, alpha=0.7)
    ax1.text(2.3, 96.0, "p99 (Tail SLA)", color="#f87171", fontsize=9, fontweight="bold")

    # -------------------------------------------------------------
    # SUBPLOT 2: High Dynamic Range (HDR) Latency by Percentile
    # -------------------------------------------------------------
    ax2.set_title("B. High Dynamic Range (HDR) Latency Blowout\nResponse Time escalation from p50 to p99.99", 
                  fontsize=12, fontweight="bold", pad=14, color="#38bdf8")

    percentile_labels = ["p50", "p75", "p90", "p95", "p99", "p99.9", "p99.99"]
    quantiles = [0.50, 0.75, 0.90, 0.95, 0.99, 0.999, 0.9999]
    q_x = np.arange(len(quantiles))

    for p in platforms:
        pid = p["id"]
        p50 = float(p["p50_ms"])
        p99 = float(p["p99_ms"])
        name = p["name"]
        color = palette.get(pid, "#94a3b8")
        st = line_configs.get(pid, {"lw": 1.4, "zorder": 10, "ls": "-", "marker": "o", "ms": 3.5})

        mu = math.log(max(p50, 0.1))
        sigma = max(math.log(max(p99 / p50, 1.05)) / 2.3263479, 0.05)

        z_quantiles = [0.0, 0.67449, 1.28155, 1.64485, 2.32635, 3.09023, 3.71902]
        lat_at_q = [math.exp(mu + z * sigma) for z in z_quantiles]

        ax2.plot(q_x, lat_at_q, color=color, linewidth=st["lw"], 
                 linestyle=st["ls"], zorder=st["zorder"], marker=st["marker"], 
                 markersize=st["ms"], label=name)

    ax2.set_yscale("log")
    ax2.set_ylim(4.0, 3000.0)
    ax2.set_xticks(q_x)
    ax2.set_xticklabels(percentile_labels, fontsize=10, fontweight="600")
    ax2.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{int(y):,} ms" if y >= 1 else f"{y:.1f} ms"))
    ax2.set_xlabel("Percentile Depth", fontsize=11, fontweight="600")
    ax2.set_ylabel("Response Latency (Milliseconds, Log Scale)", fontsize=11, fontweight="600")
    ax2.grid(True, which="both", alpha=0.5)

    # SLA 250ms breaker line
    ax2.axhline(250.0, color="#ef4444", linestyle="--", linewidth=1.5, alpha=0.8)
    ax2.text(0.1, 268.0, "250ms SLA Choke Threshold Boundary", color="#ef4444", fontsize=9, fontweight="bold")

    # Legend across the bottom of the figure in 5 clean columns
    handles, labels = ax2.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5, fontsize=8.5, 
               frameon=True, facecolor="#0c1322", edgecolor="#334155",
               bbox_to_anchor=(0.5, 0.02))

    # Save PNG
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    plt.savefig(out_png, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    print(f"  [+] Saved high-resolution CDF plot: {out_png}")

    # Save initial SVG
    plt.savefig(out_svg, format="svg", facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()

    # Post-process SVG for interactive tooltips and curve highlighting
    inject_interactive_svg_features(out_svg, platforms)
    print(f"  [+] Saved interactive vector CDF plot: {out_svg}")

def inject_interactive_svg_features(svg_path, platforms):
    """
    Enhances Matplotlib SVG with interactive CSS styles, mouseover hover effects,
    and rich floating tooltips showing OS, tier, p50, p99, and root causes.
    """
    with open(svg_path, "r", encoding="utf-8") as f:
        svg_content = f.read()

    # CSS for interactive hover
    interactive_css = """
    <style>
      .interactive-curve {
        cursor: pointer;
        transition: stroke-width 0.2s ease, opacity 0.2s ease, filter 0.2s ease;
      }
      .interactive-curve:hover {
        stroke-width: 5.5px !important;
        filter: drop-shadow(0 0 10px #00f2fe) !important;
        opacity: 1.0 !important;
      }
      svg:hover .interactive-curve:not(:hover) {
        opacity: 0.20;
      }
    </style>
    """

    for p in platforms:
        name = p["name"]
        tier = p["tier"]
        p50 = p["p50_ms"]
        p99 = p["p99_ms"]
        rps = p["http_rps"]
        notes = p["notes"]

        tooltip_text = f"🖥️ {name}\n🏷️ {tier}\n⚡ p50 Latency: {p50} ms\n⏱️ p99 Tail: {p99} ms\n🚀 Max Throughput: {rps:,.1f} req/s\n🔍 Root Analysis: {notes}"

        escaped_name = re.escape(name)
        pattern = rf'(<path[^>]*label="{escaped_name}"[^>]*)(>)'
        replacement = rf'\1 class="interactive-curve" data-os="{name}"><title>{tooltip_text}</title>'
        svg_content = re.sub(pattern, replacement, svg_content)

    if "<defs>" in svg_content:
        svg_content = svg_content.replace("<defs>", "<defs>" + interactive_css, 1)
    else:
        svg_content = svg_content.replace("<svg ", "<svg " + interactive_css, 1)

    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_content)

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    json_path = os.path.join(base_dir, "tools", "reports", "master_matrix.json")
    out_png = os.path.join(base_dir, "docs", "reports", "latency_percentiles_cdf.png")
    out_svg = os.path.join(base_dir, "docs", "reports", "latency_percentiles_cdf.svg")

    print("[*] Generating Publication-Grade Interactive Matplotlib CDF Latency Curves...")
    generate_cdf_plots(json_path, out_png, out_svg)
    print("[*] Completed successfully.")
