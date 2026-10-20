#!/bin/bash
set -e

echo "=== Building Comparison Server Benchmark Containers ==="

# 1. Ubuntu Server 24.04 LTS
cat << 'EOF' | docker build -t bench-ubuntu:latest -
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    python3 \
    gcc \
    libc6-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /bench
EOF

# 2. Debian 12 Bookworm
cat << 'EOF' | docker build -t bench-debian:latest -
FROM debian:12-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    python3 \
    gcc \
    libc6-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /bench
EOF

# 3. Alpine Linux 3.20/3.24
cat << 'EOF' | docker build -t bench-alpine:latest -
FROM alpine:latest
RUN apk update && apk add --no-cache \
    python3 \
    gcc \
    musl-dev \
    curl
WORKDIR /bench
EOF

# 4. Rocky Linux 9 Minimal (RHEL 9 derivative)
cat << 'EOF' | docker build -t bench-rocky:latest -
FROM rockylinux:9-minimal
RUN microdnf install -y \
    python3 \
    gcc \
    glibc-devel \
    tar \
    && microdnf clean all
WORKDIR /bench
EOF

echo "=== All Comparison Images Successfully Built! ==="
