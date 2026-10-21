#!/usr/bin/env python3
import subprocess
import time
import sys
import socket

# 1. Start baseline HTTP server on 8088 in Ubuntu
srv_http = subprocess.Popen(['python3', '-m', 'http.server', '8088', '--bind', '127.0.0.1'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(0.5)

# 2. Start baseline UDP server on 5353 in Ubuntu
def run_udp():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(('127.0.0.1', 5353))
    resp = (
        b"\xaa\xbb\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00"
        b"\x09localhost\x00\x00\x01\x00\x01\xc0\x0c\x00\x01"
        b"\x00\x01\x00\x00\x00\x3c\x00\x04\x7f\x00\x00\x01"
    )
    while True:
        try:
            data, addr = s.recvfrom(4096)
            s.sendto(resp, addr)
        except Exception:
            break

import threading
udp_thread = threading.Thread(target=run_udp, daemon=True)
udp_thread.start()
time.sleep(0.5)

# 3. Run destruction benchmark
res = subprocess.run(['python3', 'tools/bench_breaking_point.py'])

srv_http.terminate()
sys.exit(res.returncode)
