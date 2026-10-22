#!/usr/bin/env python3
"""
C100K Connection Avalanche Server
High-performance epoll / SO_REUSEPORT multi-port server designed to hold
100,000+ persistent idle TCP sockets and process an instantaneous broadcast avalanche.
Logs connection telemetry and socket memory to server_sockets.log.
"""

import sys
import os
import socket
import select
import time
import errno
import struct
import multiprocessing
import signal

PORTS = [9001, 9002, 9003, 9004]
CONTROL_PORT = 9000
LOG_FILE = os.environ.get("SERVER_SOCKETS_LOG", "server_sockets.log")

def get_sockstat():
    """Read socket statistics from /proc/net/sockstat if available."""
    stats = {"tcp_inuse": 0, "tcp_mem_kb": 0}
    try:
        with open("/proc/net/sockstat", "r") as f:
            for line in f:
                if line.startswith("TCP:"):
                    parts = line.strip().split()
                    for i, p in enumerate(parts):
                        if p == "inuse" and i + 1 < len(parts):
                            stats["tcp_inuse"] = int(parts[i + 1])
                        elif p == "mem" and i + 1 < len(parts):
                            # mem is in pages (4KB)
                            stats["tcp_mem_kb"] = int(parts[i + 1]) * 4
    except Exception:
        pass
    return stats

def get_cpu_psi():
    """Read CPU pressure stall information."""
    psi = 0.0
    try:
        with open("/proc/pressure/cpu", "r") as f:
            for line in f:
                if line.startswith("some"):
                    parts = line.strip().split()
                    for p in parts:
                        if p.startswith("avg10="):
                            psi = float(p.split("=")[1])
    except Exception:
        pass
    return psi

def run_worker(worker_id, shared_broadcast_event, ports, log_path):
    # Set high open file limit
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_NOFILE, (1048576, 1048576))
    except Exception as e:
        pass

    epoll = select.epoll()
    listening_socks = {}

    for port in ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.setblocking(False)
        s.bind(("0.0.0.0", port))
        s.listen(65535)
        epoll.register(s.fileno(), select.EPOLLIN)
        listening_socks[s.fileno()] = s

    clients = {} # fd -> sock
    last_log_time = time.time()
    broadcast_sent = False

    print(f"[Worker {worker_id}] Listening on ports {ports} with epoll...", flush=True)

    while True:
        try:
            # Check shared broadcast event
            if shared_broadcast_event.is_set() and not broadcast_sent:
                broadcast_sent = True
                bcast_start = time.perf_counter_ns()
                payload = f"AVALANCHE:{bcast_start}\n".encode()
                success_count = 0
                error_count = 0

                for fd, sock in list(clients.items()):
                    try:
                        sock.sendall(payload)
                        success_count += 1
                    except Exception:
                        error_count += 1
                bcast_elapsed_ms = (time.perf_counter_ns() - bcast_start) / 1e6
                print(f"[Worker {worker_id}] Avalanche broadcast complete! Sockets: {success_count}, Errors: {error_count}, Elapsed: {bcast_elapsed_ms:.2f}ms", flush=True)

            events = epoll.poll(0.05)
            now = time.time()

            # Periodic logging
            if worker_id == 0 and (now - last_log_time) >= 1.0:
                last_log_time = now
                stats = get_sockstat()
                psi = get_cpu_psi()
                total_local_clients = len(clients)
                with open(log_path, "a") as f:
                    f.write(f"{now:.3f},{worker_id},{stats.get('tcp_inuse', total_local_clients)},{stats.get('tcp_mem_kb', 0)},{psi:.2f}\n")
                    f.flush()

            for fd, event in events:
                if fd in listening_socks:
                    # Accept incoming connections in a batch
                    server_s = listening_socks[fd]
                    while True:
                        try:
                            client_s, addr = server_s.accept()
                            client_s.setblocking(False)
                            client_s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                            # Set small receive/send buffer
                            try:
                                client_s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
                                client_s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
                            except Exception:
                                pass
                            cfd = client_s.fileno()
                            epoll.register(cfd, select.EPOLLIN)
                            clients[cfd] = client_s
                        except BlockingIOError:
                            break
                        except Exception:
                            break
                elif event & select.EPOLLIN:
                    client_s = clients.get(fd)
                    if not client_s:
                        continue
                    try:
                        data = client_s.recv(1024)
                        if not data:
                            # Client closed connection
                            epoll.unregister(fd)
                            del clients[fd]
                            client_s.close()
                        else:
                            # Handle incoming commands
                            if data.startswith(b"TRIGGER_AVALANCHE"):
                                shared_broadcast_event.set()
                                client_s.sendall(b"OK_TRIGGERED\n")
                            elif data.startswith(b"PING"):
                                client_s.sendall(b"PONG\n")
                            elif data.startswith(b"COUNT"):
                                client_s.sendall(f"COUNT:{len(clients)}\n".encode())
                    except Exception:
                        epoll.unregister(fd)
                        if fd in clients:
                            del clients[fd]
                        try:
                            client_s.close()
                        except Exception:
                            pass
                elif event & (select.EPOLLHUP | select.EPOLLERR):
                    if fd in clients:
                        epoll.unregister(fd)
                        try:
                            clients[fd].close()
                        except Exception:
                            pass
                        del clients[fd]
        except (KeyboardInterrupt, SystemExit):
            break
        except Exception as e:
            # Continue running despite transient errors
            pass

def run_control_listener(shared_event, log_path):
    """Control server on Port 9000 to trigger avalanche or report status."""
    ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ctrl_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ctrl_sock.bind(("0.0.0.0", CONTROL_PORT))
    ctrl_sock.listen(128)
    print(f"[Control Server] Listening on port {CONTROL_PORT}...", flush=True)

    with open(log_path, "w") as f:
        f.write("timestamp,worker_id,tcp_inuse,tcp_mem_kb,cpu_psi_pct\n")
        f.flush()

    while True:
        try:
            conn, addr = ctrl_sock.accept()
            req = conn.recv(1024).decode().strip()
            if req == "TRIGGER":
                print("[Control] Received TRIGGER command. Arming avalanche!", flush=True)
                shared_event.set()
                conn.sendall(b"OK:AVALANCHE_TRIGGERED\n")
            elif req == "RESET":
                shared_event.clear()
                conn.sendall(b"OK:RESET\n")
            elif req == "STATUS":
                stats = get_sockstat()
                psi = get_cpu_psi()
                conn.sendall(f"TCP_INUSE:{stats.get('tcp_inuse', 0)},MEM_KB:{stats.get('tcp_mem_kb', 0)},PSI:{psi:.2f}\n".encode())
            else:
                conn.sendall(b"UNKNOWN_COMMAND\n")
            conn.close()
        except Exception:
            break

def main():
    num_workers = min(multiprocessing.cpu_count(), 4)
    if len(sys.argv) > 1:
        num_workers = int(sys.argv[1])

    print(f"============================================================")
    print(f"  C100K AVALANCHE SERVER STARTING")
    print(f"  Workers: {num_workers} | Ports: {PORTS}")
    print(f"  Socket Log: {LOG_FILE}")
    print(f"============================================================")

    shared_event = multiprocessing.Event()
    processes = []

    # Start control listener process
    p_ctrl = multiprocessing.Process(target=run_control_listener, args=(shared_event, LOG_FILE))
    p_ctrl.daemon = True
    p_ctrl.start()
    processes.append(p_ctrl)

    # Start worker processes
    for w in range(num_workers):
        p = multiprocessing.Process(target=run_worker, args=(w, shared_event, PORTS, LOG_FILE))
        p.daemon = True
        p.start()
        processes.append(p)

    def sig_handler(sig, frame):
        print("\nShutting down C100K server...")
        for p in processes:
            p.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    for p in processes:
        p.join()

if __name__ == "__main__":
    main()
