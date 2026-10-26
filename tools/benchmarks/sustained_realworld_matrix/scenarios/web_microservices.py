"""
tools/benchmarks/sustained_realworld_matrix/scenarios/web_microservices.py
Category 1: Web & Microservices (15 Scenarios: SCEN-WEB-01 to SCEN-WEB-15).
Authoritative, zero-synthetic cloud-native networking & serialization benchmarks.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass(frozen=True)
class WebScenarioDefinition:
    id: str
    name: str
    category: str = "web_microservices"
    protocol: str = "HTTP/1.1"
    target_port: int = 8000
    sla_p95_ms: float = 5.0
    description: str = ""
    server_stack: str = ""
    driver_type: str = "wrk2"
    driver_script: str = ""
    driver_args: List[str] = field(default_factory=list)
    server_cmd: List[str] = field(default_factory=list)
    verification_keys: List[str] = field(
        default_factory=lambda: ["zero_synthetic", "sla_p95", "rss_stability"]
    )


WEB_SCENARIOS: Dict[str, WebScenarioDefinition] = {
    "SCEN-WEB-01": WebScenarioDefinition(
        id="SCEN-WEB-01",
        name="FastAPI Async JSON Serialization",
        protocol="HTTP/1.1",
        target_port=8000,
        sla_p95_ms=5.0,
        description="Uvicorn ASGI event loop queries enterprise_seed.db for users & products, hydratively validates Pydantic schemas, serializes nested JSON responses.",
        server_stack="FastAPI / Uvicorn ASGI",
        driver_type="wrk2",
        driver_script="payloads/drivers/wrk2/web_feed.lua",
        driver_args=["-t4", "-c100", "-d300s", "-R5000", "--latency"],
        server_cmd=["python3", "-m", "uvicorn", "app:api", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"],
    ),
    "SCEN-WEB-02": WebScenarioDefinition(
        id="SCEN-WEB-02",
        name="Express.js High Churn REST Endpoints",
        protocol="HTTP/1.1",
        target_port=3000,
        sla_p95_ms=8.0,
        description="High churn REST endpoints serving dynamic order and catalog routes with Connection: close, forcing rapid socket churn and V8 GC pressure.",
        server_stack="Node.js Express / High-churn async handler",
        driver_type="wrk2",
        driver_script="payloads/drivers/wrk2/web_feed.lua",
        driver_args=["-t4", "-c200", "-d300s", "-R8000", "--latency", "-H", "Connection: close"],
        server_cmd=["node", "server.js", "--port", "3000"],
    ),
    "SCEN-WEB-03": WebScenarioDefinition(
        id="SCEN-WEB-03",
        name="Go Chi Lightweight HTTP Gateway",
        protocol="HTTP/1.1",
        target_port=8080,
        sla_p95_ms=2.0,
        description="Zero-allocation Go Chi routing gateway with middleware chain (RequestID, RealIP, Context timeout) and direct struct JSON serialization.",
        server_stack="Go Chi v5",
        driver_type="wrk2",
        driver_script="payloads/drivers/wrk2/web_feed.lua",
        driver_args=["-t4", "-c150", "-d300s", "-R20000", "--latency"],
        server_cmd=["/bench/go_gateway", "--port", "8080"],
    ),
    "SCEN-WEB-04": WebScenarioDefinition(
        id="SCEN-WEB-04",
        name="Rust Axum Multi-Core Microservice",
        protocol="HTTP/1.1",
        target_port=8081,
        sla_p95_ms=1.0,
        description="Rust Axum multi-threaded service on Tokio runtime with lock-free channel dispatch and SIMD-accelerated serde_json serialization.",
        server_stack="Rust Axum / Tokio",
        driver_type="wrk2",
        driver_script="payloads/drivers/wrk2/web_feed.lua",
        driver_args=["-t4", "-c250", "-d300s", "-R40000", "--latency"],
        server_cmd=["/bench/axum_server", "--port", "8081", "--workers", "2"],
    ),
    "SCEN-WEB-05": WebScenarioDefinition(
        id="SCEN-WEB-05",
        name="Nginx Reverse Proxy & Keep-Alive Pooling",
        protocol="HTTP/1.1",
        target_port=80,
        sla_p95_ms=3.0,
        description="Nginx epoll core maintaining upstream keep-alive connection pool (keepalive 64), proxying requests to local backends and buffering responses.",
        server_stack="Nginx 1.26",
        driver_type="wrk2",
        driver_script="payloads/drivers/wrk2/web_feed.lua",
        driver_args=["-t4", "-c500", "-d300s", "-R25000", "--latency"],
        server_cmd=["nginx", "-c", "/etc/nginx/nginx.conf"],
    ),
    "SCEN-WEB-06": WebScenarioDefinition(
        id="SCEN-WEB-06",
        name="Nginx TLS Handshake Session Resumption",
        protocol="HTTPS",
        target_port=443,
        sla_p95_ms=10.0,
        description="OpenSSL TLS 1.3 crypto engine testing new handshakes and session ticket resumption with genuine 2048-bit RSA/ECDSA certificates.",
        server_stack="Nginx / OpenSSL 3.0",
        driver_type="k6",
        driver_script="payloads/drivers/k6/tls_handshake.js",
        driver_args=["--vus", "100", "--duration", "300s"],
        server_cmd=["nginx", "-c", "/etc/nginx/nginx_tls.conf"],
    ),
    "SCEN-WEB-07": WebScenarioDefinition(
        id="SCEN-WEB-07",
        name="GraphQL Nested Entity Resolution",
        protocol="HTTP/1.1",
        target_port=4000,
        sla_p95_ms=15.0,
        description="GraphQL AST parsing and DataLoader batching across 4 relational levels (User -> Orders -> Items -> Product -> Reviews) over enterprise_seed.db.",
        server_stack="GraphQL / Apollo / Async Engine",
        driver_type="wrk2",
        driver_script="payloads/drivers/wrk2/graphql_query.lua",
        driver_args=["-t4", "-c100", "-d300s", "-R3000", "--latency"],
        server_cmd=["python3", "-m", "scenarios.servers.graphql_server", "--port", "4000"],
    ),
    "SCEN-WEB-08": WebScenarioDefinition(
        id="SCEN-WEB-08",
        name="Django WSGI Synchronous Worker Turnover",
        protocol="HTTP/1.1",
        target_port=8000,
        sla_p95_ms=20.0,
        description="Gunicorn WSGI managing sync workers with max-requests=500, forcing live process recycling and testing OS copy-on-write page cleanup.",
        server_stack="Django / Gunicorn WSGI",
        driver_type="wrk2",
        driver_script="payloads/drivers/wrk2/web_feed.lua",
        driver_args=["-t4", "-c50", "-d300s", "-R1500", "--latency"],
        server_cmd=["gunicorn", "wsgi_app:application", "-w", "4", "--max-requests", "500", "-b", "0.0.0.0:8000"],
    ),
    "SCEN-WEB-09": WebScenarioDefinition(
        id="SCEN-WEB-09",
        name="HTTP/2 Multiplexed Stream Saturation",
        protocol="HTTP/2",
        target_port=8443,
        sla_p95_ms=4.0,
        description="HTTP/2 multiplexing up to 100 concurrent streams per TCP socket connection using binary framing, HPACK header compression, and window flow control.",
        server_stack="HTTP/2 Server / nghttp2",
        driver_type="h2load",
        driver_script="payloads/drivers/h2load/run_h2load.sh",
        driver_args=["-n", "150000", "-c", "100", "-m", "50", "--duration=300s"],
        server_cmd=["python3", "-m", "scenarios.servers.http2_server", "--port", "8443"],
    ),
    "SCEN-WEB-10": WebScenarioDefinition(
        id="SCEN-WEB-10",
        name="gRPC Protobuf Bi-Directional Streaming",
        protocol="HTTP/2-gRPC",
        target_port=50051,
        sla_p95_ms=2.5,
        description="Bi-directional gRPC streaming RPCs serializing and deserializing compiled Protocol Buffer binary wire format without textual overhead.",
        server_stack="gRPC C-Core / Python gRPC",
        driver_type="ghz",
        driver_script="payloads/drivers/ghz/run_ghz.sh",
        driver_args=["--proto", "payloads/enterprise.proto", "--call", "enterprise.OrderService.StreamOrders", "-c", "50", "-z", "300s"],
        server_cmd=["python3", "-m", "scenarios.servers.grpc_server", "--port", "50051"],
    ),
    "SCEN-WEB-11": WebScenarioDefinition(
        id="SCEN-WEB-11",
        name="Server-Sent Events (SSE) Fan-Out (5,000 clients)",
        protocol="HTTP/1.1-SSE",
        target_port=8082,
        sla_p95_ms=5.0,
        description="Event broadcaster holding 5,000 persistent HTTP connection sockets broadcasting live ticker and order events across open socket descriptors.",
        server_stack="Asyncio SSE Broadcaster",
        driver_type="async_client",
        driver_script="payloads/drivers/sse/sse_client.py",
        driver_args=["--clients", "5000", "--duration", "300"],
        server_cmd=["python3", "-m", "scenarios.servers.sse_server", "--port", "8082"],
    ),
    "SCEN-WEB-12": WebScenarioDefinition(
        id="SCEN-WEB-12",
        name="WebSocket Full-Duplex Real-Time Churn",
        protocol="WS",
        target_port=8083,
        sla_p95_ms=3.0,
        description="RFC 6455 full-duplex WebSocket server exchanging masked binary and JSON frames with heartbeat ping/pong and high connection churn rate.",
        server_stack="WebSockets / Asyncio",
        driver_type="k6",
        driver_script="payloads/drivers/k6/websocket_churn.js",
        driver_args=["--vus", "250", "--duration", "300s"],
        server_cmd=["python3", "-m", "scenarios.servers.ws_server", "--port", "8083"],
    ),
    "SCEN-WEB-13": WebScenarioDefinition(
        id="SCEN-WEB-13",
        name="Resilience4j / Envoy Circuit Breaker Trips",
        protocol="HTTP/1.1",
        target_port=8084,
        sla_p95_ms=5.0,
        description="Circuit breaker state machine (Closed -> Open -> Half-Open) verifying fast-fail responses (503/429 < 0.5ms) under injected upstream failure.",
        server_stack="Envoy / Resilience Circuit Breaker",
        driver_type="wrk2",
        driver_script="payloads/drivers/wrk2/web_feed.lua",
        driver_args=["-t4", "-c100", "-d300s", "-R5000", "--latency"],
        server_cmd=["python3", "-m", "scenarios.servers.circuit_breaker_server", "--port", "8084"],
    ),
    "SCEN-WEB-14": WebScenarioDefinition(
        id="SCEN-WEB-14",
        name="OAuth2 JWT Cryptographic Token Validation",
        protocol="HTTP/1.1",
        target_port=8085,
        sla_p95_ms=2.0,
        description="Auth gateway verifying RFC 7519 HMAC-SHA256 JWT tokens, validating base64url decoding, cryptographic signatures, expiration, and scopes.",
        server_stack="Auth Gateway / Cryptography",
        driver_type="wrk2",
        driver_script="payloads/drivers/wrk2/jwt_auth.lua",
        driver_args=["-t4", "-c150", "-d300s", "-R15000", "--latency"],
        server_cmd=["python3", "-m", "scenarios.servers.jwt_server", "--port", "8085"],
    ),
    "SCEN-WEB-15": WebScenarioDefinition(
        id="SCEN-WEB-15",
        name="Rate Limiter Leaky Bucket Throttling",
        protocol="HTTP/1.1",
        target_port=8086,
        sla_p95_ms=1.5,
        description="High-performance token/leaky bucket rate limiter enforcing 5,000 req/sec limit per token with standard HTTP 429 backpressure headers.",
        server_stack="Token Bucket Rate Limiter",
        driver_type="wrk2",
        driver_script="payloads/drivers/wrk2/web_feed.lua",
        driver_args=["-t4", "-c200", "-d300s", "-R10000", "--latency"],
        server_cmd=["python3", "-m", "scenarios.servers.rate_limiter_server", "--port", "8086"],
    ),
}


def get_web_scenarios() -> Dict[str, Dict[str, Any]]:
    """Returns the reference dictionary of all 15 Web & Microservices scenarios."""
    return {
        s.id: {
            "id": s.id,
            "name": s.name,
            "category": s.category,
            "protocol": s.protocol,
            "target_port": s.target_port,
            "sla_p95_ms": s.sla_p95_ms,
        }
        for s in WEB_SCENARIOS.values()
    }
