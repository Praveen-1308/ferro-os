"""
tools/benchmarks/sustained_realworld_matrix/scenarios/high_churn_io.py
Category 3: High-Churn I/O & Media (10 Scenarios: SCEN-IO-01 to SCEN-IO-10).
Authoritative, zero-synthetic disk writeback, zero-copy kernel transfers, and VFS churn benchmarks.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass(frozen=True)
class IOScenarioDefinition:
    id: str
    name: str
    category: str = "high_churn_io_media"
    protocol: str = "POSIX-IO"
    target_port: int = 0
    sla_p95_ms: float = 10.0
    description: str = ""
    io_mechanism: str = ""
    driver_type: str = ""
    driver_script: str = ""
    driver_args: List[str] = field(default_factory=list)
    server_cmd: List[str] = field(default_factory=list)
    verification_keys: List[str] = field(
        default_factory=lambda: ["zero_synthetic", "sla_p95", "rss_stability"]
    )


IO_SCENARIOS: Dict[str, IOScenarioDefinition] = {
    "SCEN-IO-01": IOScenarioDefinition(
        id="SCEN-IO-01",
        name="Multipart File Upload (1 MB - 25 MB chunks)",
        protocol="HTTP-Multipart",
        target_port=9000,
        sla_p95_ms=50.0,
        description="Receives chunked multipart uploads containing genuine binary JPEG and PNG images (1 MB to 25 MB), streams them to scratch storage, and validates SHA-256 checksums.",
        io_mechanism="epoll + chunked streaming write + fdatasync",
        driver_type="k6",
        driver_script="payloads/drivers/k6/multipart_upload.js",
        driver_args=["--vus", "100", "--duration", "300s"],
        server_cmd=["python3", "-m", "scenarios.servers.upload_server", "--port", "9000", "--scratch", "/scratch"],
    ),
    "SCEN-IO-02": IOScenarioDefinition(
        id="SCEN-IO-02",
        name="Linux sendfile(2) Zero-Copy Kernel Transfer",
        protocol="TCP-Raw",
        target_port=9001,
        sla_p95_ms=5.0,
        description="Zero-copy static media server streaming large video/binary buffers directly from VFS page cache into client TCP sockets via sendfile(2) without userspace copying.",
        io_mechanism="sendfile(2) + TCP_CORK",
        driver_type="wrk2",
        driver_script="payloads/drivers/wrk2/web_feed.lua",
        driver_args=["-t4", "-c100", "-d300s", "-R5000", "--latency"],
        server_cmd=["/bench/sendfile_server", "--port", "9001", "--media-dir", "/scratch/media"],
    ),
    "SCEN-IO-03": IOScenarioDefinition(
        id="SCEN-IO-03",
        name="MinIO S3 Compatible Object Storage Benchmark",
        protocol="S3-REST",
        target_port=9002,
        sla_p95_ms=35.0,
        description="MinIO / S3 object storage server executing AWS SigV4 PutObject, GetObject, and ListObjectsV2 with authentic MD5/SHA-256 ETag verification on scratch NVMe.",
        io_mechanism="S3 REST API v4 + pwritev + setxattr",
        driver_type="s3_bench",
        driver_script="payloads/drivers/s3/s3_bench.py",
        driver_args=["--endpoint", "http://172.30.0.10:9002", "--bucket", "matrix-bench", "--duration", "300"],
        server_cmd=["minio", "server", "/scratch/minio_data", "--address", ":9002"],
    ),
    "SCEN-IO-04": IOScenarioDefinition(
        id="SCEN-IO-04",
        name="Maildir 100,000 Small File Inode Churn",
        protocol="VFS",
        target_port=0,
        sla_p95_ms=10.0,
        description="Maildir message spool simulating MTA delivery: atomic file creation in tmp/, rename() to new/, reader processing to cur/, and concurrent unlink() across 100,000 inodes.",
        io_mechanism="openat(O_CREAT) + rename + unlink + getdents64",
        driver_type="maildir_bench",
        driver_script="payloads/drivers/vfs/maildir_bench.py",
        driver_args=["--spool", "/scratch/maildir", "--inodes", "100000", "--threads", "8"],
        server_cmd=["python3", "-m", "payloads.drivers.vfs.maildir_bench", "--spool", "/scratch/maildir", "--inodes", "100000"],
    ),
    "SCEN-IO-05": IOScenarioDefinition(
        id="SCEN-IO-05",
        name="fdatasync Saturation & Disk Write Barriers",
        protocol="POSIX-IO",
        target_port=0,
        sla_p95_ms=45.0,
        description="Multiple worker threads write 4 KB to 64 KB records to append-only journals in /scratch, flooding page cache to vm.dirty_ratio and issuing batched fdatasync() barriers.",
        io_mechanism="pwrite64 + fdatasync + barrier flush",
        driver_type="fdatasync_bench",
        driver_script="payloads/drivers/vfs/fdatasync_bench.py",
        driver_args=["--path", "/scratch/fsync_journal", "--threads", "8", "--duration", "300"],
        server_cmd=["python3", "-m", "payloads.drivers.vfs.fdatasync_bench", "--path", "/scratch/fsync_journal"],
    ),
    "SCEN-IO-06": IOScenarioDefinition(
        id="SCEN-IO-06",
        name="FIO Direct I/O (O_DIRECT) Kernel Bypass",
        protocol="FIO-Direct",
        target_port=0,
        sla_p95_ms=8.0,
        description="Flexible I/O Tester (FIO) with io_uring or libaio engine and direct=1. Bypasses page cache with 4 KB blocks, 70/30 randrw distribution, and iodepth=64 on scratch NVMe.",
        io_mechanism="O_DIRECT + io_uring / libaio",
        driver_type="fio",
        driver_script="payloads/drivers/fio/fio_direct.fio",
        driver_args=["--name=direct_io", "--direct=1", "--bs=4k", "--iodepth=64", "--runtime=300", "--time_based"],
        server_cmd=["fio", "payloads/drivers/fio/fio_direct.fio"],
    ),
    "SCEN-IO-07": IOScenarioDefinition(
        id="SCEN-IO-07",
        name="libvips SIMD Multithreaded Image Transcoding",
        protocol="CPU-SIMD",
        target_port=0,
        sla_p95_ms=60.0,
        description="Multithreaded image processing pipeline ingesting genuine JPEG photos, performing SIMD bilinear resize, sharpening convolution, and WebP compression.",
        io_mechanism="SIMD vector ops + mmap + WebP encode",
        driver_type="image_transcode_bench",
        driver_script="payloads/drivers/media/transcode_bench.py",
        driver_args=["--assets-dir", "payloads/assets", "--threads", "4", "--duration", "300"],
        server_cmd=["python3", "-m", "payloads.drivers.media.transcode_bench", "--assets-dir", "payloads/assets"],
    ),
    "SCEN-IO-08": IOScenarioDefinition(
        id="SCEN-IO-08",
        name="mmap Shared Memory Concurrent Updates",
        protocol="POSIX-mmap",
        target_port=0,
        sla_p95_ms=1.5,
        description="Memory-maps a 2 GB binary database file on /scratch via MAP_SHARED. 16 worker threads execute concurrent atomic random read-modify-writes via CAS followed by periodic msync().",
        io_mechanism="mmap(MAP_SHARED) + madvise(MADV_RANDOM) + msync",
        driver_type="mmap_bench",
        driver_script="payloads/drivers/vfs/mmap_bench.py",
        driver_args=["--file", "/scratch/mmap_db.bin", "--size-gb", "2", "--threads", "16", "--duration", "300"],
        server_cmd=["python3", "-m", "payloads.drivers.vfs.mmap_bench", "--file", "/scratch/mmap_db.bin"],
    ),
    "SCEN-IO-09": IOScenarioDefinition(
        id="SCEN-IO-09",
        name="Disk Queue Saturation & Block I/O Throttling",
        protocol="BlockIO",
        target_port=0,
        sla_p95_ms=40.0,
        description="Background generators write continuous 64 MB chunk files to saturate disk queue, while foreground reader threads issue 4 KB index lookups, evaluating I/O fairness under dirty page flush.",
        io_mechanism="open(O_DIRECT) + sync_file_range + pread64",
        driver_type="disk_queue_bench",
        driver_script="payloads/drivers/vfs/disk_queue_bench.py",
        driver_args=["--target", "/scratch/queue_test", "--duration", "300"],
        server_cmd=["python3", "-m", "payloads.drivers.vfs.disk_queue_bench", "--target", "/scratch/queue_test"],
    ),
    "SCEN-IO-10": IOScenarioDefinition(
        id="SCEN-IO-10",
        name="Temporary File Churn & Directory Re-indexing",
        protocol="POSIX-tmp",
        target_port=0,
        sla_p95_ms=12.0,
        description="Rapidly creates, scans, indexes, and deletes deep directory trees containing 50,000 temporary object files across 500 subdirectories, stressing dentry hash tables and directory block expansion.",
        io_mechanism="mkdirat + getdents64 + unlinkat + rmdir",
        driver_type="tmp_churn_bench",
        driver_script="payloads/drivers/vfs/tmp_churn_bench.py",
        driver_args=["--root", "/scratch/tmp_tree", "--files", "50000", "--duration", "300"],
        server_cmd=["python3", "-m", "payloads.drivers.vfs.tmp_churn_bench", "--root", "/scratch/tmp_tree"],
    ),
}


def get_io_scenarios() -> Dict[str, Dict[str, Any]]:
    """Returns the reference dictionary of all 10 High-Churn I/O & Media scenarios."""
    return {
        s.id: {
            "id": s.id,
            "name": s.name,
            "category": s.category,
            "protocol": s.protocol,
            "target_port": s.target_port,
            "sla_p95_ms": s.sla_p95_ms,
        }
        for s in IO_SCENARIOS.values()
    }
