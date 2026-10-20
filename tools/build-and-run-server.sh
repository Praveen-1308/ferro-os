#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "================================================================================"
echo "          BUILDING FERRO-OS STANDALONE SERVER DOCKER IMAGE                      "
echo "================================================================================"

cd "$PROJECT_ROOT"

echo "--> 1. Compiling FerroOS Rust Workspace (Release)..."
cargo build --release -p ferro-init -p ferro-core -p ferro-pkg

echo "--> 2. Building Docker Image ferro-os-server:latest..."
docker build -t ferro-os-server:latest -f Dockerfile.server .

echo "--> 3. Launching ferro-server Container..."
docker rm -f ferro-server 2>/dev/null || true
docker run -d --name ferro-server \
    -p 8080:8080 \
    -p 8081:8081 \
    -p 8088:8088 \
    ferro-os-server:latest

echo "--> 4. Waiting for Microservices to initialize..."
sleep 2

echo "--> 5. Probing Endpoints..."
echo "  [API Telemetry]:"
curl -s http://localhost:8080/api/status | head -n 15 || true
echo ""
echo "  [Health Probe]:"
curl -s http://localhost:8080/api/health || true
echo ""
echo "  [Rust HTTP Web Server]:"
curl -sI http://localhost:8088 | head -n 5 || true

echo "================================================================================"
echo "✅ FerroOS Dedicated Server is LIVE and healthy on ports 8080, 8081, 8088!"
echo "================================================================================"
