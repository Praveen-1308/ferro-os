"""
tools/benchmarks/sustained_realworld_matrix/scenarios/queueing_streaming.py
Category 4: Queueing, Telemetry & Streaming (10 Scenarios: SCEN-Q-01 to SCEN-Q-10).
Authoritative, zero-synthetic message queuing, log stream ingestion, and telemetry pull scrapes.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass(frozen=True)
class QueueingScenarioDefinition:
    id: str
    name: str
    category: str = "queueing_telemetry_streaming"
    protocol: str = "AMQP"
    target_port: int = 5672
    sla_p95_ms: float = 10.0
    description: str = ""
    stack: str = ""
    driver_type: str = ""
    driver_script: str = ""
    driver_args: List[str] = field(default_factory=list)
    server_cmd: List[str] = field(default_factory=list)
    verification_keys: List[str] = field(
        default_factory=lambda: ["zero_synthetic", "sla_p95", "rss_stability"]
    )


QUEUEING_SCENARIOS: Dict[str, QueueingScenarioDefinition] = {
    "SCEN-Q-01": QueueingScenarioDefinition(
        id="SCEN-Q-01",
        name="RabbitMQ AMQP 0-9-1 Topic Exchange Fanout",
        protocol="AMQP",
        target_port=5672,
        sla_p95_ms=10.0,
        description="AMQP topic exchange bound to 5 durable queues with wildcard routing keys, testing topic trie matching, disk persistence, and consumer acknowledgments.",
        stack="RabbitMQ 3.13 / AMQP Broker",
        driver_type="amqp_bench",
        driver_script="payloads/drivers/queue/amqp_bench.py",
        driver_args=["--host", "172.30.0.10", "--port", "5672", "--rate", "10000", "--duration", "300"],
        server_cmd=["rabbitmq-server"],
    ),
    "SCEN-Q-02": QueueingScenarioDefinition(
        id="SCEN-Q-02",
        name="NATS Core Pub/Sub High-Velocity Routing",
        protocol="NATS",
        target_port=4222,
        sla_p95_ms=1.0,
        description="Pure in-memory subject hierarchy routing with 50 subscriber worker groups over multiplexed client sockets with sub-millisecond dispatch.",
        stack="NATS Server 2.10",
        driver_type="nats-bench",
        driver_args=["-s", "nats://172.30.0.10:4222", "-np", "10", "-n", "500000", "-ms", "512", "orders.v1.*.created"],
        server_cmd=["nats-server", "-p", "4222"],
    ),
    "SCEN-Q-03": QueueingScenarioDefinition(
        id="SCEN-Q-03",
        name="ZeroMQ PUSH/PULL Lock-Free Socket Pipeline",
        protocol="ZMQ-TCP",
        target_port=5555,
        sla_p95_ms=0.8,
        description="8 pipeline worker threads connected via ZMQ_PULL receiving 1 KB task batches from central ZMQ_PUSH socket, validating HMAC signatures and high water mark (HWM=10,000).",
        stack="libzmq 4.3 / pyzmq",
        driver_type="zmq_bench",
        driver_script="payloads/drivers/queue/zmq_bench.py",
        driver_args=["--target", "tcp://172.30.0.10:5555", "--rate", "50000", "--duration", "300"],
        server_cmd=["python3", "-m", "scenarios.servers.zmq_pipeline_server", "--port", "5555"],
    ),
    "SCEN-Q-04": QueueingScenarioDefinition(
        id="SCEN-Q-04",
        name="Prometheus 10,000 Metrics/Sec Pull Scrapes",
        protocol="HTTP-Prom",
        target_port=9090,
        sla_p95_ms=15.0,
        description="Serves /metrics endpoint emitting 10,000 distinct time-series metrics in OpenMetrics text exposition format (counters, gauges, histograms) under concurrent scrape load.",
        stack="Prometheus Exporter / OpenMetrics",
        driver_type="wrk2",
        driver_script="payloads/drivers/wrk2/web_feed.lua",
        driver_args=["-t4", "-c20", "-d300s", "-R10", "--latency"],
        server_cmd=["python3", "-m", "scenarios.servers.prom_exporter", "--port", "9090", "--metrics-file", "payloads/assets/metrics_10k_sample.prom"],
    ),
    "SCEN-Q-05": QueueingScenarioDefinition(
        id="SCEN-Q-05",
        name="Vector High-Throughput JSON Log Ingestion",
        protocol="TCP-Syslog",
        target_port=9514,
        sla_p95_ms=5.0,
        description="Listens on TCP port 9514 for streaming newline-delimited JSON (NDJSON) logs up to 25,000 events/sec, parsing fields, validating schemas, and writing to disk buffers.",
        stack="Vector / Fluent Bit",
        driver_type="log_streamer",
        driver_script="payloads/drivers/stream/log_streamer.py",
        driver_args=["--target-ip", "172.30.0.10", "--port", "9514", "--file", "payloads/assets/vector_logs_sample.jsonl", "--rate", "25000"],
        server_cmd=["python3", "-m", "scenarios.servers.vector_sink", "--port", "9514"],
    ),
    "SCEN-Q-06": QueueingScenarioDefinition(
        id="SCEN-Q-06",
        name="OpenTelemetry Distributed Span Ingestion",
        protocol="gRPC-OTel",
        target_port=4317,
        sla_p95_ms=8.0,
        description="Ingests OTLP distributed traces over gRPC/HTTP2 on port 4317. Decodes batches of 100 nested spans (ResourceSpans, ScopeSpans, Span) with attributes, events, and status.",
        stack="OpenTelemetry Collector / gRPC",
        driver_type="otel_generator",
        driver_script="payloads/drivers/stream/otel_generator.py",
        driver_args=["--target", "172.30.0.10:4317", "--spans-per-batch", "100", "--duration", "300"],
        server_cmd=["python3", "-m", "scenarios.servers.otel_collector", "--port", "4317"],
    ),
    "SCEN-Q-07": QueueingScenarioDefinition(
        id="SCEN-Q-07",
        name="StatsD UDP High-Rate Metric Aggregation",
        protocol="UDP",
        target_port=8125,
        sla_p95_ms=1.0,
        description="Receives UDP datagrams containing batched metric lines (counter, latency ms, gauge) bounded within 1,472 bytes (safe MTU payload limit) at 100,000 datagrams/sec.",
        stack="StatsD UDP Aggregator",
        driver_type="udp_blaster",
        driver_script="payloads/drivers/stream/statsd_blaster.py",
        driver_args=["--target-ip", "172.30.0.10", "--port", "8125", "--rate", "100000", "--max-packet-size", "1472"],
        server_cmd=["python3", "-m", "scenarios.servers.statsd_server", "--port", "8125"],
    ),
    "SCEN-Q-08": QueueingScenarioDefinition(
        id="SCEN-Q-08",
        name="Kafka-compatible Streaming Partition Writes",
        protocol="Kafka-Wire",
        target_port=9092,
        sla_p95_ms=12.0,
        description="Implements Kafka binary wire protocol ProduceRequest, writing record batches to 16 active topic partitions on disk with CRC32C hardware acceleration.",
        stack="Redpanda / Kafka Append-Only Log",
        driver_type="kafka_bench",
        driver_script="payloads/drivers/stream/kafka_bench.py",
        driver_args=["--bootstrap", "172.30.0.10:9092", "--partitions", "16", "--duration", "300"],
        server_cmd=["python3", "-m", "scenarios.servers.kafka_partition_server", "--port", "9092"],
    ),
    "SCEN-Q-09": QueueingScenarioDefinition(
        id="SCEN-Q-09",
        name="Backpressure Event Streaming Flow Control",
        protocol="TCP-Stream",
        target_port=7777,
        sla_p95_ms=6.0,
        description="Streams continuous telemetry events to connected clients. Detects TCP send buffer saturation (EAGAIN / EPOLLOUT) when client reading halts, pausing producer without blowing heap memory.",
        stack="Async Streaming TCP Server",
        driver_type="backpressure_client",
        driver_script="payloads/drivers/stream/backpressure_client.py",
        driver_args=["--target-ip", "172.30.0.10", "--port", "7777", "--duration", "300"],
        server_cmd=["python3", "-m", "scenarios.servers.backpressure_server", "--port", "7777"],
    ),
    "SCEN-Q-10": QueueingScenarioDefinition(
        id="SCEN-Q-10",
        name="Message Priority Re-ordering under Contention",
        protocol="AMQP-Pri",
        target_port=5673,
        sla_p95_ms=14.0,
        description="Priority queues (priority 1-10) with 100,000 backlog messages ensuring priority 10 emergency alerts are delivered ahead of low-priority traffic without priority inversion.",
        stack="RabbitMQ Priority Broker",
        driver_type="priority_queue_bench",
        driver_script="payloads/drivers/queue/priority_bench.py",
        driver_args=["--host", "172.30.0.10", "--port", "5673", "--duration", "300"],
        server_cmd=["python3", "-m", "scenarios.servers.priority_queue_server", "--port", "5673"],
    ),
}


def get_queueing_scenarios() -> Dict[str, Dict[str, Any]]:
    """Returns the reference dictionary of all 10 Queueing, Telemetry & Streaming scenarios."""
    return {
        s.id: {
            "id": s.id,
            "name": s.name,
            "category": s.category,
            "protocol": s.protocol,
            "target_port": s.target_port,
            "sla_p95_ms": s.sla_p95_ms,
        }
        for s in QUEUEING_SCENARIOS.values()
    }
