FROM rust:1.80-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    clang \
    llvm \
    libbpf-dev \
    bpftool \
    linux-libc-dev \
    liburing-dev \
    liburing2 \
    gcc \
    libc6-dev \
    make \
    python3 \
    xorriso \
    isolinux \
    syslinux-common \
    cpio \
    binutils \
    qemu-system-x86 \
    linux-image-amd64 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
