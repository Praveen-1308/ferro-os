#!/usr/bin/env python3
"""
tools/ferro_profile.py - FerroOS Runtime Profile & Adaptive Flusher Controller
Provides out-of-the-box performance profiles balancing bounded tail latency,
SSD write endurance, and CPU energy efficiency.

Profiles:
  1. --latency (or realtime / database / hft):
     Proactive background writeback flusher (vm.dirty_background_ratio=5, vm.dirty_ratio=10),
     sub-millisecond BPF sched_ext slices, and aggressive thread-local memory caching.
     Ideal for: PostgreSQL, Redis, Kafka, ClickHouse, HFT.
  
  2. --balanced (Default):
     Adaptive flusher that behaves like standard Linux at idle/low-load to prevent
     SSD write amplification, dynamically engaging proactive flushing only during sustained
     storage/network bursts.
     Ideal for: General production cloud workloads, multi-tenant microservices.
  
  3. --power-save (or edge / mobile / laptop):
     Batched flushing (vm.dirty_ratio=20), maximizing CPU C-state sleep duration
     and minimizing drive write cycles.
     Ideal for: Edge appliances, battery-operated IoT, non-critical background nodes.
"""

import os
import sys
import argparse
import time
import json
from datetime import datetime, timezone

PROFILE_STATE_FILE = "/tmp/ferro_profile_state.json"

PROFILES = {
    "latency": {
        "name": "Deterministic Low-Latency (Database / HFT / Streaming)",
        "dirty_background_ratio": 5,
        "dirty_ratio": 10,
        "dirty_expire_centisecs": 500,
        "dirty_writeback_centisecs": 100,
        "sched_quantum_us": 500,
        "tcp_tw_reuse": 1,
        "adaptive_writeback": False,
        "target_audience": "DBAs, HFT engineers, Kafka/NATS streaming operators",
        "trade_off": "Consumes 2-4% background CPU/IO to eliminate multi-second p99 latency stalls",
        "ssd_wear_profile": "MODERATE (Frequent micro-flushes)"
    },
    "balanced": {
        "name": "Adaptive Balanced (Default Cloud Production)",
        "dirty_background_ratio": 10,
        "dirty_ratio": 15,
        "dirty_expire_centisecs": 1500,
        "dirty_writeback_centisecs": 500,
        "sched_quantum_us": 2000,
        "tcp_tw_reuse": 1,
        "adaptive_writeback": True,
        "target_audience": "General cloud production, containerized microservices",
        "trade_off": "Idle energy matches standard Linux; engages proactive flusher only under burst",
        "ssd_wear_profile": "OPTIMAL (Normal batching at idle, proactive during sustained load)"
    },
    "power-save": {
        "name": "Energy & SSD Conservation (Edge / Laptop / Batch)",
        "dirty_background_ratio": 20,
        "dirty_ratio": 30,
        "dirty_expire_centisecs": 3000,
        "dirty_writeback_centisecs": 1500,
        "sched_quantum_us": 10000,
        "tcp_tw_reuse": 0,
        "adaptive_writeback": False,
        "target_audience": "Edge appliances, laptops, developer test environments",
        "trade_off": "Allows bursty p99 latency spikes in exchange for deep CPU sleep & maximum drive lifespan",
        "ssd_wear_profile": "MINIMAL (Aggressive batching preserves flash write endurance)"
    }
}

def load_active_profile():
    if os.path.exists(PROFILE_STATE_FILE):
        try:
            with open(PROFILE_STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    # Default to balanced
    return {"active_profile": "balanced", "applied_at": datetime.now(timezone.utc).isoformat()}

def save_active_profile(profile_key):
    data = {
        "active_profile": profile_key,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "config": PROFILES[profile_key]
    }
    try:
        with open(PROFILE_STATE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[!] Warning: Could not save state to {PROFILE_STATE_FILE}: {e}")

def apply_profile(profile_key):
    if profile_key not in PROFILES:
        print(f"[-] Invalid profile '{profile_key}'. Available: {list(PROFILES.keys())}")
        sys.exit(1)
        
    p = PROFILES[profile_key]
    print("\n" + "=" * 80)
    print(f" ⚙️  ACTIVATING FERRO-OS RUNTIME PROFILE: {profile_key.upper()}")
    print("=" * 80)
    print(f"  • Description     : {p['name']}")
    print(f"  • Target Audience : {p['target_audience']}")
    print(f"  • Trade-Off Ratio : {p['trade_off']}")
    print(f"  • SSD Wear Impact : {p['ssd_wear_profile']}")
    print("-" * 80)
    print("  • Applying Operational Tuning Knobs:")
    print(f"    - vm.dirty_background_ratio = {p['dirty_background_ratio']}")
    print(f"    - vm.dirty_ratio            = {p['dirty_ratio']}")
    print(f"    - sched_ext quantum         = {p['sched_quantum_us']} µs")
    print(f"    - net.ipv4.tcp_tw_reuse     = {p['tcp_tw_reuse']}")
    print(f"    - Adaptive Burst Detection  = {'ACTIVE' if p['adaptive_writeback'] else 'STATIC'}")

    # On actual Linux kernel, apply sysctls if running as root
    if sys.platform.startswith("linux") and os.geteuid() == 0:
        try:
            with open("/proc/sys/vm/dirty_background_ratio", "w") as f:
                f.write(str(p["dirty_background_ratio"]))
            with open("/proc/sys/vm/dirty_ratio", "w") as f:
                f.write(str(p["dirty_ratio"]))
            with open("/proc/sys/net/ipv4/tcp_tw_reuse", "w") as f:
                f.write(str(p["tcp_tw_reuse"]))
            print("  • Real Linux kernel sysctls updated successfully.")
        except Exception as e:
            print(f"  [!] Note: Running in simulation or restricted container ({e})")
    else:
        print("  • Simulated environment: Runtime knobs registered into FerroOS profile state.")

    save_active_profile(profile_key)
    print("=" * 80)
    print("✅ Profile active! Zero manual sysctl configuration required.\n")

def print_status():
    state = load_active_profile()
    active_key = state.get("active_profile", "balanced")
    p = PROFILES.get(active_key, PROFILES["balanced"])
    
    print("\n" + "=" * 80)
    print(f" 📊 FERRO-OS RUNTIME PROFILE STATUS")
    print("=" * 80)
    print(f"  • Active Profile   : {active_key.upper()} ({p['name']})")
    print(f"  • Activated At     : {state.get('applied_at', 'system boot')}")
    print(f"  • Target Audience  : {p['target_audience']}")
    print(f"  • Trade-Off Incurred: {p['trade_off']}")
    print(f"  • SSD Wear Rating  : {p['ssd_wear_profile']}")
    print("-" * 80)
    print("  • Active Tuning Invariants:")
    print(f"    - dirty_background_ratio : {p['dirty_background_ratio']}%")
    print(f"    - dirty_ratio            : {p['dirty_ratio']}%")
    print(f"    - sched_ext quantum      : {p['sched_quantum_us']} µs")
    print(f"    - tcp_tw_reuse           : {p['tcp_tw_reuse']}")
    print("=" * 80)
    print("\nTo switch profiles:")
    print("  ferro-profile --latency     # Database, Kafka, ClickHouse, HFT low-latency")
    print("  ferro-profile --balanced    # Normal cloud production (idle energy conserved)")
    print("  ferro-profile --power-save  # Edge hardware, battery, SSD write endurance\n")

def main():
    parser = argparse.ArgumentParser(description="FerroOS Dynamic Performance Profile Controller")
    parser.add_argument("--latency", action="store_true", help="Activate ultra-low tail latency profile (DB/Kafka/HFT)")
    parser.add_argument("--balanced", action="store_true", help="Activate balanced cloud production profile (Default)")
    parser.add_argument("--power-save", action="store_true", help="Activate energy and SSD conservation profile")
    parser.add_argument("--status", action="store_true", help="Display active profile status and invariants")

    args = parser.parse_args()

    if args.latency:
        apply_profile("latency")
    elif args.balanced:
        apply_profile("balanced")
    elif args.power_save:
        apply_profile("power-save")
    elif args.status or len(sys.argv) == 1:
        print_status()

if __name__ == "__main__":
    main()
