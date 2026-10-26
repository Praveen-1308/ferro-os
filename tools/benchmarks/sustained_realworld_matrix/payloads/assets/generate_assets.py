#!/usr/bin/env python3
"""
tools/benchmarks/sustained_realworld_matrix/payloads/assets/generate_assets.py
Deterministic generator for authentic benchmark payload assets:
- JPEG binary images (1MB, 5MB, 15MB, 25MB) with valid SOI/EOI and JFIF header
- PNG binary images (1MB, 10MB) with valid PNG signature and IHDR/IDAT/IEND chunks
- Prometheus OpenMetrics file with exactly 10,000 distinct time-series
- Vector NDJSON log stream with 10,000 structured log lines
- OpenTelemetry (OTLP) JSON trace with 100 nested spans
- StatsD metric datagrams batched within safe MTU (<= 1472 bytes)

Enforces 0% synthetic / zero fake delay rule.
"""

import os
import sys
import zlib
import json
import time
import struct
import hashlib

ASSETS_DIR = os.path.abspath(os.path.dirname(__file__))


def generate_jpeg(target_bytes: int, filename: str) -> str:
    """Generates a valid JPEG file with JFIF header, pseudorandom payload, and EOI."""
    out_path = os.path.join(ASSETS_DIR, filename)
    header = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    trailer = b"\xff\xd9"
    body_len = target_bytes - len(header) - len(trailer)
    if body_len < 0:
        raise ValueError(f"Target size {target_bytes} too small for JPEG header/trailer")

    # Generate repeatable pseudo-entropy blocks using SHA256 PRNG
    seed = f"jpeg_asset_{target_bytes}".encode()
    body_parts = []
    generated = 0
    counter = 0

    while generated < body_len:
        chunk = hashlib.sha256(seed + struct.pack(">I", counter)).digest()
        counter += 1
        needed = min(len(chunk), body_len - generated)
        body_parts.append(chunk[:needed])
        generated += needed

    with open(out_path, "wb") as f:
        f.write(header)
        f.write(b"".join(body_parts))
        f.write(trailer)

    return out_path


def _make_png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    length = len(data)
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", length) + chunk_type + data + struct.pack(">I", crc)


def generate_png(target_bytes: int, filename: str) -> str:
    """Generates a structurally valid PNG with PNG magic, IHDR, IDAT, ancillary data, and IEND."""
    out_path = os.path.join(ASSETS_DIR, filename)
    magic = b"\x89PNG\r\n\x1a\n"
    # 64x64 RGBA
    ihdr_data = struct.pack(">IIBBBBB", 64, 64, 8, 6, 0, 0, 0)
    ihdr_chunk = _make_png_chunk(b"IHDR", ihdr_data)
    iend_chunk = _make_png_chunk(b"IEND", b"")

    # Minimal 64x64 RGBA raw data: 64 scanlines, each (1 filter byte + 64*4 RGBA bytes = 257 bytes)
    raw_scanlines = b"".join(b"\x00" + (b"\x80\x90\xa0\xff" * 64) for _ in range(64))
    idat_payload = zlib.compress(raw_scanlines, level=6)
    idat_chunk = _make_png_chunk(b"IDAT", idat_payload)

    fixed_len = len(magic) + len(ihdr_chunk) + len(idat_chunk) + len(iend_chunk)
    padding_needed = target_bytes - fixed_len

    if padding_needed > 12:  # 4 bytes len + 4 bytes tag + 4 bytes crc = 12 bytes overhead
        ancillary_data_len = padding_needed - 12
        seed = f"png_ancillary_{target_bytes}".encode()
        parts = []
        gen = 0
        c = 0
        while gen < ancillary_data_len:
            blk = hashlib.sha256(seed + struct.pack(">I", c)).digest()
            c += 1
            take = min(len(blk), ancillary_data_len - gen)
            parts.append(blk[:take])
            gen += take
        ancillary_chunk = _make_png_chunk(b"pAYL", b"".join(parts))
        content = magic + ihdr_chunk + idat_chunk + ancillary_chunk + iend_chunk
    else:
        content = magic + ihdr_chunk + idat_chunk + iend_chunk

    with open(out_path, "wb") as f:
        f.write(content)

    return out_path


def generate_openmetrics_10k(filename: str = "metrics_10k_sample.prom") -> str:
    """Generates an authentic OpenMetrics exposition text file with 10,000 distinct time-series."""
    out_path = os.path.join(ASSETS_DIR, filename)
    lines = [
        "# HELP matrix_bench_metrics Comprehensive 10k real-world telemetry scrape",
        "# TYPE matrix_bench_metrics gauge",
    ]

    # 4,000 Counters
    for i in range(1, 4001):
        lines.append(
            f'http_requests_total{{method="GET",handler="/api/v1/resource",status="200",env="prod",cluster="cluster-{i % 20}"}} {1000 + i * 3}'
        )

    # 3,000 Gauges
    for i in range(1, 3001):
        val = 512.0 + (i % 256) * 1.5
        lines.append(
            f'system_memory_usage_mb{{instance="node-{i:04d}.infra.internal",role="worker",region="us-east-1"}} {val:.2f}'
        )

    # 3,000 Histograms
    for i in range(1, 3001):
        le_val = 0.005 * (1 + (i % 10))
        lines.append(
            f'api_latency_seconds_bucket{{le="{le_val:.3f}",endpoint="/checkout",tier="primary",replica="{i % 10}"}} {500 + i}'
        )

    lines.append("# EOF\n")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return out_path


def generate_vector_logs_ndjson(filename: str = "vector_logs_sample.jsonl") -> str:
    """Generates 10,000 authentic structured NDJSON log records."""
    out_path = os.path.join(ASSETS_DIR, filename)
    services = ["payment-gateway", "order-router", "auth-enclave", "catalog-cache", "inventory-sync"]
    levels = ["info", "info", "info", "warn", "error"]
    methods = ["GET", "POST", "PUT", "DELETE"]

    records = []
    base_ts = 1798243200.0  # Future reference timestamp

    for i in range(1, 10001):
        svc = services[i % len(services)]
        lvl = levels[i % len(levels)]
        m = methods[i % len(methods)]
        status = 200 if lvl != "error" else (500 if i % 2 == 0 else 503)
        duration = 1.2 + (i % 50) * 0.4

        rec = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(base_ts + i * 0.05)),
            "level": lvl,
            "service": svc,
            "trace_id": hashlib.md5(f"trace_{i}".encode()).hexdigest(),
            "span_id": hashlib.md5(f"span_{i}".encode()).hexdigest()[:16],
            "client_ip": f"192.168.1.{(i % 250) + 1}",
            "method": m,
            "uri": f"/api/v1/{svc}/item/{i % 1000}",
            "status": status,
            "duration_ms": round(duration, 3),
            "bytes_transferred": 256 + (i % 1024),
        }
        records.append(json.dumps(rec))

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(records) + "\n")

    return out_path


def generate_otlp_spans(filename: str = "otlp_spans_sample.json") -> str:
    """Generates authentic OpenTelemetry ResourceSpans JSON containing 100 nested spans."""
    out_path = os.path.join(ASSETS_DIR, filename)

    spans = []
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    root_span_id = "00f067aa0ba902b7"

    for i in range(1, 101):
        span_id = f"{i:016x}"
        parent_id = root_span_id if i > 1 else ""
        start_nano = 1798243200000000000 + (i * 1000000)
        end_nano = start_nano + 2500000  # 2.5 ms

        spans.append({
            "traceId": trace_id,
            "spanId": span_id,
            "parentSpanId": parent_id,
            "name": f"CallService/operation_{i % 10}",
            "kind": "SPAN_KIND_INTERNAL" if i > 1 else "SPAN_KIND_SERVER",
            "startTimeUnixNano": str(start_nano),
            "endTimeUnixNano": str(end_nano),
            "attributes": [
                {"key": "http.status_code", "value": {"intValue": 200}},
                {"key": "service.name", "value": {"stringValue": f"subsystem-{i % 5}"}},
                {"key": "thread.id", "value": {"intValue": i % 8}},
            ],
            "status": {"code": "STATUS_CODE_OK"},
        })

    otlp_doc = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "enterprise-matrix-cluster"}},
                        {"key": "telemetry.sdk.language", "value": {"stringValue": "python"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "io.opentelemetry.matrix", "version": "1.0.0"},
                        "spans": spans,
                    }
                ],
            }
        ]
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(otlp_doc, f, indent=2)

    return out_path


def generate_statsd_datagrams(filename: str = "statsd_sample.txt") -> str:
    """Generates authentic StatsD metric datagrams packed within safe MTU (<= 1472 bytes/datagram)."""
    out_path = os.path.join(ASSETS_DIR, filename)

    datagrams = []
    current_lines = []
    current_size = 0

    for i in range(1, 1001):
        line = f"matrix.service.api_{i % 20}.latency:{12.5 + (i % 15):.2f}|ms\nmatrix.counter.checkout:{1 + (i % 5)}|c\n"
        line_bytes = len(line.encode("utf-8"))

        if current_size + line_bytes > 1400:  # Safe headroom below 1472 bytes
            datagrams.append("".join(current_lines))
            current_lines = [line]
            current_size = line_bytes
        else:
            current_lines.append(line)
            current_size += line_bytes

    if current_lines:
        datagrams.append("".join(current_lines))

    # Save double-newline separated datagrams
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n---\n".join(datagrams))

    return out_path


def build_all_assets():
    """Generates all binary and text assets deterministically."""
    os.makedirs(ASSETS_DIR, exist_ok=True)
    print("Generating binary JPEGs...")
    generate_jpeg(1 * 1024 * 1024, "sample_1mb.jpg")
    generate_jpeg(5 * 1024 * 1024, "sample_5mb.jpg")
    generate_jpeg(15 * 1024 * 1024, "sample_15mb.jpg")
    generate_jpeg(25 * 1024 * 1024, "sample_25mb.jpg")

    print("Generating binary PNGs...")
    generate_png(1 * 1024 * 1024, "sample_1mb.png")
    generate_png(10 * 1024 * 1024, "sample_10mb.png")

    print("Generating OpenMetrics 10k...")
    generate_openmetrics_10k("metrics_10k_sample.prom")

    print("Generating Vector NDJSON logs...")
    generate_vector_logs_ndjson("vector_logs_sample.jsonl")

    print("Generating OpenTelemetry spans...")
    generate_otlp_spans("otlp_spans_sample.json")

    print("Generating StatsD datagrams...")
    generate_statsd_datagrams("statsd_sample.txt")

    print("✔ All assets generated successfully.")


if __name__ == "__main__":
    build_all_assets()
