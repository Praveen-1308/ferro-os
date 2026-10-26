#!/usr/bin/env bash
# tools/benchmarks/sustained_realworld_matrix/tests/run_e2e_tests.sh
# Strict pipefail shell wrapper for Sustained Real-World Benchmark Matrix E2E Test Suite.

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"

echo "[*] Invoking Python E2E Test Runner with strict pipefail..."
python3 "${SCRIPT_DIR}/run_e2e_tests.py" "$@"
EXIT_CODE=$?

exit "${EXIT_CODE}"
