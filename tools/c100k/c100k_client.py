#!/usr/bin/env python3
"""
C100K Connection Avalanche Client Harness
Spawns non-blocking persistent TCP connections across multiple ports,
monitors client harness health into client_cpu.csv,
triggers the 10ms avalanche broadcast, and measures tail latency & reconnection churn.
"""

import sys
import os
import socket
import select
import time
import errno
import multiprocessing
import json
import statistics

TARGET_HOST = os.environ.get("TARGET_HOST", "127.0.0.1")
PORTS = [9001, 9002, 9003, 9004]
CONTROL_PORT = 9000
CLIENT_CPU_CSV = os.environ.get("CLIENT_CPU_CSV", "client_cpu.csv")

def get_process_metrics():
    """Read CPU and RSS of client process."""
    cpu_pct = 0.0
    rss_mb = 0.0
    try:
        pid = os.getpid()
        with open(f"/proc/{pid}/statm", "r") as f:
            parts = f.read().split()
            rss_pages = int(parts[1])
            rss_mb = (rss_pages * 4096) / (1024 * 1024)
    except Exception:
        pass
    return cpu_pct, rss_mb

def worker_connect_and_hold(worker_id, target_conns, host, ports, ready_queue, result_queue, control_event, churn_event):
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_NOFILE, (1048576, 1048576))
    except Exception:
        pass

    epoll = select.epoll()
    socks = {} # fd -> sock
    connect_times = {}
    latencies = []
    errors = 0
    connected_count = 0

    port_idx = 0
    # Ramp up connections
    batch_size = 500
    for i in range(target_conns):
        target_port = ports[port_idx % len(ports)]
        port_idx += 1
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
            except Exception:
                pass
            s.setblocking(False)
            res = s.connect_ex((host, target_port))
            fd = s.fileno()
            epoll.register(fd, select.EPOLLOUT | select.EPOLLIN)
            socks[fd] = s
            connect_times[fd] = time.perf_counter()
        except Exception as e:
            errors += 1

        if (i + 1) % batch_size == 0 or (i + 1) == target_conns:
            # Poll for writable (connected)
            events = epoll.poll(0.02)
            for fd, event in events:
                if event & (select.EPOLLOUT | select.EPOLLIN):
                    if fd in socks:
                        connected_count += 1
                        # Change registration to EPOLLIN only
                        epoll.modify(fd, select.EPOLLIN)

    # Finish establishing remaining in-flight handshakes
    start_wait = time.time()
    while len(socks) > 0 and (time.time() - start_wait) < 5.0:
        events = epoll.poll(0.05)
        for fd, event in events:
            if event & select.EPOLLOUT:
                epoll.modify(fd, select.EPOLLIN)

    ready_queue.put((worker_id, len(socks), errors))
    print(f"[Client Worker {worker_id}] Holding {len(socks)} active sockets. Waiting for trigger...", flush=True)

    # Wait for Avalanche Broadcast Event
    control_event.wait()

    # Read incoming avalanche packets
    t_avalanche_start = time.perf_counter()
    received_msgs = 0
    deadline = t_avalanche_start + 15.0 # up to 15s wait

    while (time.perf_counter() < deadline) and (received_msgs < len(socks)):
        events = epoll.poll(0.02)
        now_ns = time.perf_counter_ns()
        for fd, event in events:
            if event & select.EPOLLIN:
                sock = socks.get(fd)
                if not sock:
                    continue
                try:
                    data = sock.recv(512)
                    if data and b"AVALANCHE:" in data:
                        received_msgs += 1
                        # Parse server timestamp
                        try:
                            ts_str = data.split(b"AVALANCHE:")[1].split(b"\n")[0]
                            server_ts_ns = int(ts_str)
                            # Latency in ms (server send to client recv)
                            lat_ms = (now_ns - server_ts_ns) / 1e6
                            latencies.append(lat_ms)
                        except Exception:
                            latencies.append((time.perf_counter() - t_avalanche_start) * 1000.0)
                except Exception:
                    errors += 1

    # Churn phase: simulate 10% connection drop and immediate reconnect
    dropped = 0
    reconnected = 0
    reconnect_latencies = []
    if churn_event.is_set():
        drop_target = max(1, len(socks) // 10)
        fds_to_drop = list(socks.keys())[:drop_target]
        for fd in fds_to_drop:
            epoll.unregister(fd)
            try:
                socks[fd].close()
            except Exception:
                pass
            del socks[fd]
            dropped += 1

        # Now reconnect
        t_recon_start = time.perf_counter()
        for i in range(dropped):
            target_port = ports[i % len(ports)]
            try:
                t0 = time.perf_counter()
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                s.connect((host, target_port))
                t1 = time.perf_counter()
                reconnect_latencies.append((t1 - t0) * 1000.0)
                reconnected += 1
                socks[s.fileno()] = s
            except Exception:
                errors += 1

    result_queue.put({
        "worker_id": worker_id,
        "holding_sockets": len(socks),
        "received_msgs": received_msgs,
        "latencies": latencies,
        "dropped": dropped,
        "reconnected": reconnected,
        "reconnect_latencies": reconnect_latencies,
        "errors": errors
    })

    # Cleanup
    for s in socks.values():
        try:
            s.close()
        except Exception:
            pass

def main():
    total_conns = 100000
    num_workers = 4
    if len(sys.argv) > 1:
        total_conns = int(sys.argv[1])
    if len(sys.argv) > 2:
        num_workers = int(sys.argv[2])

    conns_per_worker = total_conns // num_workers
    print(f"============================================================")
    print(f"  C100K AVALANCHE CLIENT HARNESS")
    print(f"  Target Host: {TARGET_HOST} | Total Sockets: {total_conns}")
    print(f"  Workers: {num_workers} ({conns_per_worker} per worker)")
    print(f"  Client Telemetry: {CLIENT_CPU_CSV}")
    print(f"============================================================")

    # Initialize client_cpu.csv
    with open(CLIENT_CPU_CSV, "w") as f:
        f.write("timestamp,client_cpu_pct,client_rss_mb,active_connections,messages_received,errors\n")
        f.flush()

    ready_queue = multiprocessing.Queue()
    result_queue = multiprocessing.Queue()
    control_event = multiprocessing.Event()
    churn_event = multiprocessing.Event()

    workers = []
    for w in range(num_workers):
        p = multiprocessing.Process(
            target=worker_connect_and_hold,
            args=(w, conns_per_worker, TARGET_HOST, PORTS, ready_queue, result_queue, control_event, churn_event)
        )
        p.start()
        workers.append(p)

    # Monitor ramp-up
    active_conns = 0
    t_start = time.time()
    for _ in range(num_workers):
        wid, c_cnt, errs = ready_queue.get(timeout=60.0)
        active_conns += c_cnt
        print(f"[Ramp] Worker {wid} reports {c_cnt} sockets ready ({active_conns}/{total_conns} total)")

    ramp_elapsed = time.time() - t_start
    print(f"\n[Ramp Complete] Connected {active_conns} persistent sockets in {ramp_elapsed:.2f}s!")

    # Record baseline client metric
    cpu_pct, rss_mb = get_process_metrics()
    with open(CLIENT_CPU_CSV, "a") as f:
        f.write(f"{time.time():.3f},{cpu_pct:.1f},{rss_mb:.1f},{active_conns},0,0\n")
        f.flush()

    time.sleep(2.0) # Settle connections

    # Step 2: Trigger Avalanche Broadcast via Control Port
    print(f"\n⚡ TRIGGERING C100K AVALANCHE BROADCAST VIA CONTROL PORT {CONTROL_PORT}...")
    control_event.set() # Unblock client workers to listen

    t_bcast_send = time.perf_counter()
    try:
        ctrl = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ctrl.connect((TARGET_HOST, CONTROL_PORT))
        ctrl.sendall(b"TRIGGER\n")
        resp = ctrl.recv(1024).decode()
        ctrl.close()
        print(f"[Control Response] {resp.strip()}")
    except Exception as e:
        print(f"[Control Error] Failed to send TRIGGER: {e}")

    # Set churn event for reconnection test
    churn_event.set()

    # Collect worker results
    all_latencies = []
    total_received = 0
    total_dropped = 0
    total_reconnected = 0
    all_reconnect_latencies = []
    total_errors = 0

    for _ in range(num_workers):
        res = result_queue.get(timeout=60.0)
        all_latencies.extend(res["latencies"])
        total_received += res["received_msgs"]
        total_dropped += res["dropped"]
        total_reconnected += res["reconnected"]
        all_reconnect_latencies.extend(res["reconnect_latencies"])
        total_errors += res["errors"]

    for p in workers:
        p.join()

    # Write final telemetry
    cpu_pct, rss_mb = get_process_metrics()
    with open(CLIENT_CPU_CSV, "a") as f:
        f.write(f"{time.time():.3f},{cpu_pct:.1f},{rss_mb:.1f},{active_conns},{total_received},{total_errors}\n")
        f.flush()

    # Calculate statistics
    if all_latencies:
        all_latencies.sort()
        p50 = statistics.median(all_latencies)
        p95 = all_latencies[int(len(all_latencies) * 0.95)]
        p99 = all_latencies[int(len(all_latencies) * 0.99)]
        p999 = all_latencies[int(len(all_latencies) * 0.999)] if len(all_latencies) >= 1000 else all_latencies[-1]
        max_lat = max(all_latencies)
        within_10ms = sum(1 for x in all_latencies if x <= 10.0)
        pct_within_10ms = (within_10ms / len(all_latencies)) * 100.0
    else:
        p50 = p95 = p99 = p999 = max_lat = pct_within_10ms = 0.0

    recon_p50 = statistics.median(all_reconnect_latencies) if all_reconnect_latencies else 0.0
    recon_p95 = all_reconnect_latencies[int(len(all_reconnect_latencies) * 0.95)] if all_reconnect_latencies else 0.0

    summary = {
        "target_conns": total_conns,
        "active_conns": active_conns,
        "received_msgs": total_received,
        "coverage_pct": (total_received / max(1, active_conns)) * 100.0,
        "within_10ms_pct": pct_within_10ms,
        "latency_p50_ms": round(p50, 3),
        "latency_p95_ms": round(p95, 3),
        "latency_p99_ms": round(p99, 3),
        "latency_p999_ms": round(p999, 3),
        "latency_max_ms": round(max_lat, 3),
        "dropped_conns": total_dropped,
        "reconnected_conns": total_reconnected,
        "reconnect_p50_ms": round(recon_p50, 3),
        "reconnect_p95_ms": round(recon_p95, 3),
        "errors": total_errors
    }

    print("\n" + "=" * 60)
    print("  C100K AVALANCHE BENCHMARK RESULTS")
    print("=" * 60)
    print(f"  Total Sockets Maintained:   {active_conns:,}")
    print(f"  Avalanche Messages Recv:    {total_received:,} ({summary['coverage_pct']:.2f}% coverage)")
    print(f"  Received within 10ms:       {summary['within_10ms_pct']:.2f}%")
    print(f"  Median Latency (p50):       {summary['latency_p50_ms']} ms")
    print(f"  Tail Latency (p95):         {summary['latency_p95_ms']} ms")
    print(f"  Worst Latency (p99):        {summary['latency_p99_ms']} ms")
    print(f"  Extreme Tail (p99.9):       {summary['latency_p999_ms']} ms")
    print(f"  Max Latency:                {summary['latency_max_ms']} ms")
    print(f"  10% Churn Dropped/Reconn:   {total_dropped:,} / {total_reconnected:,}")
    print(f"  Reconnect Latency (p50/p95):{summary['reconnect_p50_ms']} ms / {summary['reconnect_p95_ms']} ms")
    print(f"  Total Errors:               {total_errors}")
    print("=" * 60)

    summary_file = os.environ.get("C100K_SUMMARY_JSON", "c100k_summary.json")
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Summary JSON saved to {summary_file}")

if __name__ == "__main__":
    main()
