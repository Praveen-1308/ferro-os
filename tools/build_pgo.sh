#!/usr/bin/env bash
set -euo pipefail

# FerroOS Profile-Guided Optimization (PGO) Build Pipeline
# Instruments userland binaries, collects real-world runtime profiling data
# from behavioral stress workloads, and recompiles with branch and layout optimization.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PGO_DATA_DIR="/tmp/ferro-pgo-data"

echo "================================================================================"
echo "          FERRO-OS PROFILE-GUIDED OPTIMIZATION (PGO) COMPILER                   "
echo "================================================================================"

rm -rf "$PGO_DATA_DIR"
mkdir -p "$PGO_DATA_DIR"

cd "$PROJECT_ROOT"

echo "--> [Step 1/4] Compiling ferro-core with PGO Instrumentation..."
RUSTFLAGS="-C profile-generate=$PGO_DATA_DIR" cargo build --release -p ferro-core

echo "--> [Step 2/4] Exercising Behavioral Workloads (Terminal-Bench & Direct Applets)..."
LLVM_PROFILE_FILE="$PGO_DATA_DIR/ferro_%m_%p.profraw" \
FERRO_CORE_BIN="$PROJECT_ROOT/target/release/ferro-core" \
python3 "$PROJECT_ROOT/tools/test_terminal_bench.py" || true

# Direct workload exercising to guarantee profraw capture:
for i in $(seq 1 10); do
    LLVM_PROFILE_FILE="$PGO_DATA_DIR/ferro_direct_${i}_%p.profraw" "$PROJECT_ROOT/target/release/ferro-core" echo "training $i" >/dev/null
    LLVM_PROFILE_FILE="$PGO_DATA_DIR/ferro_sh_${i}_%p.profraw" "$PROJECT_ROOT/target/release/ferro-core" sh -c "exit 0" >/dev/null
    LLVM_PROFILE_FILE="$PGO_DATA_DIR/ferro_pipe_${i}_%p.profraw" "$PROJECT_ROOT/target/release/ferro-core" sh -c "echo test | grep test" >/dev/null
done

echo "--> [Step 3/4] Merging Raw Execution Profiles with llvm-profdata..."
if command -v llvm-profdata >/dev/null 2>&1; then
    PROFDATA_BIN="llvm-profdata"
elif command -v xcrun >/dev/null 2>&1; then
    PROFDATA_BIN="xcrun llvm-profdata"
else
    echo "Error: llvm-profdata not found."
    exit 1
fi

$PROFDATA_BIN merge -output="$PGO_DATA_DIR/ferro.profdata" "$PGO_DATA_DIR"/*.profraw

echo "--> [Step 4/4] Recompiling ferro-core with Profile Feedback Optimization..."
RUSTFLAGS="-C profile-use=$PGO_DATA_DIR/ferro.profdata" cargo build --release -p ferro-core

FINAL_SIZE=$(ls -lh "$PROJECT_ROOT/target/release/ferro-core" | awk '{print $5}')
echo "================================================================================"
echo "✅ PGO Complete: High-efficiency binary generated at target/release/ferro-core"
echo "   Optimized Binary Footprint: $FINAL_SIZE"
echo "================================================================================"
