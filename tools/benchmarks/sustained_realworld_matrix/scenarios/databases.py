"""
tools/benchmarks/sustained_realworld_matrix/scenarios/databases.py
Category 2: Databases & State Engines (12 Scenarios: SCEN-DB-01 to SCEN-DB-12).
Authoritative, zero-synthetic relational, embedded WAL, cache, and state engine benchmarks.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass(frozen=True)
class DatabaseScenarioDefinition:
    id: str
    name: str
    category: str = "databases_state_engines"
    protocol: str = "PGSQL"
    target_port: int = 5432
    sla_p95_ms: float = 12.0
    description: str = ""
    engine_type: str = ""
    storage_engine: str = ""
    driver_type: str = "pgbench"
    driver_script: str = ""
    driver_args: List[str] = field(default_factory=list)
    server_cmd: List[str] = field(default_factory=list)
    verification_keys: List[str] = field(
        default_factory=lambda: ["zero_synthetic", "sla_p95", "rss_stability"]
    )


DATABASE_SCENARIOS: Dict[str, DatabaseScenarioDefinition] = {
    "SCEN-DB-01": DatabaseScenarioDefinition(
        id="SCEN-DB-01",
        name="PostgreSQL TPC-B Transaction Ingestion",
        protocol="PGSQL",
        target_port=5432,
        sla_p95_ms=12.0,
        description="Standard TPC-B transaction workload (3 UPDATEs, 1 SELECT, 1 INSERT) testing disk WAL writeback (fdatasync), row locking, and shared buffer cache.",
        engine_type="PostgreSQL 16",
        storage_engine="Heap + WAL",
        driver_type="pgbench",
        driver_args=["-h", "172.30.0.10", "-p", "5432", "-U", "postgres", "-c", "50", "-j", "4", "-T", "300", "-b", "tpcb-like", "benchdb"],
        server_cmd=["postgres", "-D", "/var/lib/postgresql/data"],
    ),
    "SCEN-DB-02": DatabaseScenarioDefinition(
        id="SCEN-DB-02",
        name="SQLite WAL High-Concurrency Concurrent Read-Writes",
        protocol="Embedded-WAL",
        target_port=0,
        sla_p95_ms=4.0,
        description="SQLite 3 embedded database on scratch volume in WAL mode with 16 concurrent reader threads and 2 writer threads executing ACID order insertions.",
        engine_type="SQLite 3",
        storage_engine="B-Tree + WAL",
        driver_type="embedded_harness",
        driver_script="payloads/drivers/db/sqlite_wal_bench.py",
        driver_args=["--readers", "16", "--writers", "2", "--duration", "300"],
        server_cmd=["python3", "-m", "payloads.drivers.db.sqlite_wal_bench", "--scratch", "/scratch"],
    ),
    "SCEN-DB-03": DatabaseScenarioDefinition(
        id="SCEN-DB-03",
        name="Redis 7 Pipelined GET/SET Cache Operations",
        protocol="RESP",
        target_port=6379,
        sla_p95_ms=1.0,
        description="Redis 7 executing batch pipelined commands (16 commands per pipeline) testing socket buffer batching, amortized syscalls, and event loop throughput.",
        engine_type="Redis 7",
        storage_engine="In-Memory Dict",
        driver_type="redis-benchmark",
        driver_args=["-h", "172.30.0.10", "-p", "6379", "-c", "50", "-P", "16", "-n", "500000", "-t", "get,set", "-q"],
        server_cmd=["redis-server", "--protected-mode", "no", "--port", "6379"],
    ),
    "SCEN-DB-04": DatabaseScenarioDefinition(
        id="SCEN-DB-04",
        name="Redis BGSAVE Copy-on-Write Memory Pressure",
        protocol="RESP",
        target_port=6379,
        sla_p95_ms=15.0,
        description="Redis holding a 1.5 GB dataset under intensive writes. Periodic BGSAVE triggers fork() and copy-on-write page faults, testing memory ceilings.",
        engine_type="Redis 7",
        storage_engine="In-Memory RDB Snapshot",
        driver_type="redis_bgsave_bench",
        driver_script="payloads/drivers/db/redis_bgsave_bench.py",
        driver_args=["--host", "172.30.0.10", "--port", "6379", "--interval", "30"],
        server_cmd=["redis-server", "--save", "60", "1000", "--port", "6379"],
    ),
    "SCEN-DB-05": DatabaseScenarioDefinition(
        id="SCEN-DB-05",
        name="Valkey High-Throughput Cluster Sharding",
        protocol="RESP",
        target_port=6380,
        sla_p95_ms=1.2,
        description="Valkey high-throughput key-value engine with multi-threaded I/O and hash slot routing (CRC16 % 16384) over enterprise session and inventory data.",
        engine_type="Valkey 7.2",
        storage_engine="Multi-Threaded In-Memory",
        driver_type="valkey-benchmark",
        driver_args=["-h", "172.30.0.10", "-p", "6380", "-c", "100", "-P", "32", "-t", "set,get,mget"],
        server_cmd=["valkey-server", "--port", "6380", "--io-threads", "2"],
    ),
    "SCEN-DB-06": DatabaseScenarioDefinition(
        id="SCEN-DB-06",
        name="PgBouncer Connection Multiplexing (5,000 clients)",
        protocol="PGSQL",
        target_port=6432,
        sla_p95_ms=8.0,
        description="PgBouncer in transaction pooling mode multiplexing 5,000 client connection sockets into 25 backend PostgreSQL connections.",
        engine_type="PgBouncer + PostgreSQL",
        storage_engine="Connection Pool Gateway",
        driver_type="pgbench",
        driver_args=["-h", "172.30.0.10", "-p", "6432", "-U", "postgres", "-c", "5000", "-j", "8", "-T", "300", "-S", "benchdb"],
        server_cmd=["pgbouncer", "/etc/pgbouncer/pgbouncer.ini"],
    ),
    "SCEN-DB-07": DatabaseScenarioDefinition(
        id="SCEN-DB-07",
        name="SQLite FTS5 BM25 Full-Text Search Queries",
        protocol="Embedded-FTS5",
        target_port=0,
        sla_p95_ms=5.0,
        description="SQLite FTS5 virtual table indexing 40,000 genuine customer reviews, querying natural English keywords with BM25 statistical relevance ranking.",
        engine_type="SQLite 3 FTS5",
        storage_engine="Inverted Index BM25",
        driver_type="embedded_harness",
        driver_script="payloads/drivers/db/sqlite_fts5_bench.py",
        driver_args=["--queries", "10000", "--duration", "300"],
        server_cmd=["python3", "-m", "payloads.drivers.db.sqlite_fts5_bench", "--db", "/scratch/enterprise_seed.db"],
    ),
    "SCEN-DB-08": DatabaseScenarioDefinition(
        id="SCEN-DB-08",
        name="PostgreSQL Lock Contention & Deadlock Detection",
        protocol="PGSQL",
        target_port=5432,
        sla_p95_ms=25.0,
        description="Concurrent transactions competing for overlapping row-level locks on hot account records, exercising deadlock_timeout and lock manager queues.",
        engine_type="PostgreSQL 16",
        storage_engine="Row-Level Lock Manager",
        driver_type="pgbench",
        driver_script="payloads/drivers/db/deadlock_bench.sql",
        driver_args=["-h", "172.30.0.10", "-p", "5432", "-c", "100", "-j", "4", "-T", "300", "-f", "payloads/drivers/db/deadlock_bench.sql"],
        server_cmd=["postgres", "-D", "/var/lib/postgresql/data", "-c", "deadlock_timeout=100ms"],
    ),
    "SCEN-DB-09": DatabaseScenarioDefinition(
        id="SCEN-DB-09",
        name="PostgreSQL MVCC Table Bloat & Auto-VACUUM",
        protocol="PGSQL",
        target_port=5432,
        sla_p95_ms=30.0,
        description="High-churn UPDATE stream generating dead tuples in heap pages, triggering background autovacuum and measuring visibility map updates.",
        engine_type="PostgreSQL 16",
        storage_engine="MVCC Heap + Autovacuum",
        driver_type="pgbench",
        driver_args=["-h", "172.30.0.10", "-p", "5432", "-c", "50", "-j", "4", "-T", "300", "-f", "payloads/drivers/db/churn_updates.sql"],
        server_cmd=["postgres", "-D", "/var/lib/postgresql/data"],
    ),
    "SCEN-DB-10": DatabaseScenarioDefinition(
        id="SCEN-DB-10",
        name="Redis Sorted Sets (ZSET) Leaderboard Ingestion",
        protocol="RESP",
        target_port=6379,
        sla_p95_ms=2.0,
        description="Redis Sorted Sets tracking live user rankings with high-frequency ZADD, ZREVRANGEBYSCORE, and ZRANK operations testing SkipList rebalancing.",
        engine_type="Redis 7",
        storage_engine="In-Memory SkipList",
        driver_type="redis-benchmark",
        driver_args=["-h", "172.30.0.10", "-p", "6379", "-c", "100", "-n", "250000", "-t", "zadd,zrange", "-q"],
        server_cmd=["redis-server", "--port", "6379"],
    ),
    "SCEN-DB-11": DatabaseScenarioDefinition(
        id="SCEN-DB-11",
        name="Key-Value Range Scans under Continuous Writes",
        protocol="KV",
        target_port=7000,
        sla_p95_ms=6.0,
        description="Sorted Key-Value engine executing range scans concurrently with 10,000 writes/sec, evaluating snapshot read isolation and write amplification.",
        engine_type="Embedded KV Engine",
        storage_engine="LSM-Tree / B-Tree",
        driver_type="kv_bench",
        driver_script="payloads/drivers/db/kv_range_bench.py",
        driver_args=["--host", "172.30.0.10", "--port", "7000", "--duration", "300"],
        server_cmd=["python3", "-m", "scenarios.servers.kv_server", "--port", "7000"],
    ),
    "SCEN-DB-12": DatabaseScenarioDefinition(
        id="SCEN-DB-12",
        name="Connection Pool Exhaustion & Queue Backpressure",
        protocol="HTTP-DB",
        target_port=8090,
        sla_p95_ms=20.0,
        description="Application connection pool strictly bounded to 10 connections subjected to 1,000 concurrent client requests, testing queue backpressure and 503 rejection.",
        engine_type="Connection Pool Bounded Service",
        storage_engine="Bounded Pool Queue",
        driver_type="wrk2",
        driver_script="payloads/drivers/wrk2/web_feed.lua",
        driver_args=["-t4", "-c1000", "-d300s", "-R15000", "--latency"],
        server_cmd=["python3", "-m", "scenarios.servers.pool_exhaustion_server", "--port", "8090", "--pool-size", "10"],
    ),
}


def get_database_scenarios() -> Dict[str, Dict[str, Any]]:
    """Returns the reference dictionary of all 12 Databases & State Engines scenarios."""
    return {
        s.id: {
            "id": s.id,
            "name": s.name,
            "category": s.category,
            "protocol": s.protocol,
            "target_port": s.target_port,
            "sla_p95_ms": s.sla_p95_ms,
        }
        for s in DATABASE_SCENARIOS.values()
    }
