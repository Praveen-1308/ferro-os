#!/usr/bin/env bash
# ==============================================================================
# FerroOS Phase 3: Automated 15-OS Devastating Matrix Driver
# Evaluates 15 operating systems under strict cgroup hardware constraints:
#   --memory=4g --cpus=2
# Executes:
#   1. Thundering Herd Accept Saturation (50,000 async clients)
#   2. Multi-Threaded Allocator Contention Hammer (128 threads @ 95% RAM)
#   3. VFS Inode & File Descriptor Starvation (500,000 files until EMFILE)
#   4. Real-Time Wakeup Jitter Under CPU Burn (32 high-priority processes @ nice -20)
# ==============================================================================

set -euo pipefail

MEMORY="4g"
CPUS="2"
OUTDIR="tools/reports"
VISUALIZE=true

usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --memory <mem>    RAM limit per container (default: 4g)
  --cpus <cpus>     CPUs limit per container (default: 2)
  --outdir <dir>    Output directory for CSV/JSON (default: tools/reports)
  --no-viz          Skip chart and bar generation
  -h, --help        Show this help message
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --memory)
            MEMORY="$2"
            shift 2
            ;;
        --cpus)
            CPUS="$2"
            shift 2
            ;;
        --outdir)
            OUTDIR="$2"
            shift 2
            ;;
        --no-viz)
            VISUALIZE=false
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

echo "================================================================================"
echo "      FERRO-OS PHASE 3: 15-OS DOCKERIZED DEVASTATING MATRIX DRIVER             "
echo "================================================================================"
echo "  • Resource Ceiling: ${MEMORY} RAM, ${CPUS} CPUs"
echo "  • Output Directory: ${OUTDIR}"
echo "  • Target Matrix:    15 Operating Systems (Tiers 1, 2, and 3)"
echo "================================================================================"

# 1. Check prerequisites
if ! command -v python3 &> /dev/null; then
    echo "[-] Error: python3 is required." >&2
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo "[-] Error: docker is required." >&2
    exit 1
fi

mkdir -p "${OUTDIR}"

# 2. Run Chaos Matrix Benchmark Engine
echo ""
echo "[*] Launching Devastating Chaos Matrix Engine..."
python3 tools/devastating_chaos_matrix.py \
    --memory "${MEMORY}" \
    --cpus "${CPUS}" \
    --outdir "${OUTDIR}"

# 3. Post-Process Visualizations and Charts
if [ "${VISUALIZE}" = true ]; then
    echo ""
    echo "[*] Rendering Terminal Visual Outcome Bars..."
    if [ -f "tools/reports/visualize_results.py" ]; then
        python3 tools/reports/visualize_results.py
    fi

    echo ""
    echo "[*] Generating High-Resolution Vector & Matplotlib CDF Artifacts..."
    if [ -f "tools/reports/generate_charts.py" ]; then
        python3 tools/reports/generate_charts.py
    fi
fi

echo ""
echo "================================================================================"
echo "✅ 15-OS Devastating Matrix Run Completed Successfully!"
echo "  • CSV Summary:       ${OUTDIR}/master_matrix.csv"
echo "  • JSON Telemetry:    ${OUTDIR}/master_matrix.json"
echo "  • Throughput Chart:  docs/reports/throughput_comparison.svg"
echo "  • Latency CDF Chart: docs/reports/latency_percentiles_cdf.png"
echo "================================================================================"
