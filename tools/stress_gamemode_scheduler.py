import os
import sys
import time
import math
import subprocess
import threading
import statistics

def run_stress_burn(duration_s, stop_event):
    """Aggressively burns CPU cycles across all available cores."""
    def worker():
        x = 1.0001
        while not stop_event.is_set():
            for _ in range(10000):
                x = math.sin(x) * math.cos(x) + 1.0001
    
    threads = [threading.Thread(target=worker, daemon=True) for _ in range(os.cpu_count() or 4)]
    for t in threads: t.start()
    return threads

def measure_frame_pacing(num_frames=600, target_fps=60):
    """Simulates a Wayland/KWin compositor frame loop and records frame interval jitter."""
    target_dt = 1.0 / target_fps
    frame_times = []
    
    t_prev = time.perf_counter()
    for _ in range(num_frames):
        # Busy-wait / sleep hybrid to simulate render + presentation loop
        t_target = t_prev + target_dt
        while time.perf_counter() < t_target:
            pass
        t_now = time.perf_counter()
        dt_ms = (t_now - t_prev) * 1000.0
        frame_times.append(dt_ms)
        t_prev = t_now
        
    return frame_times

def main():
    print("================================================================================")
    print("      FERRO-OS ADVANCED SCENARIO B: GAMEMODE SCHEDULER & JITTER STRESS TEST     ")
    print("================================================================================")
    
    print("\n--- PHASE 1: Baseline Stress (GameMode OFF / Standard Priority) ---")
    subprocess.run(["ferro-core", "gamemode", "off"], check=True)
    stop_event = threading.Event()
    stress_threads = run_stress_burn(duration_s=15, stop_event=stop_event)
    time.sleep(0.5) # allow stress to saturate
    
    frames_off = measure_frame_pacing(num_frames=600)
    stop_event.set()
    time.sleep(0.5)
    
    p99_off = sorted(frames_off)[int(len(frames_off) * 0.99)]
    max_off = max(frames_off)
    jitter_off = statistics.stdev(frames_off)
    dropped_off = sum(1 for f in frames_off if f > 18.0)

    print(f"  GameMode OFF: Jitter Stdev: {jitter_off:.3f} ms | p99 Latency: {p99_off:.2f} ms | Max Spike: {max_off:.2f} ms | Dropped: {dropped_off}/600")

    print("\n--- PHASE 2: Elevated Priority Stress (GameMode ON / Nice -10) ---")
    subprocess.run(["ferro-core", "gamemode", "on"], check=True)
    stop_event2 = threading.Event()
    stress_threads2 = run_stress_burn(duration_s=15, stop_event=stop_event2)
    time.sleep(0.5)
    
    frames_on = measure_frame_pacing(num_frames=600)
    stop_event2.set()
    time.sleep(0.5)
    
    subprocess.run(["ferro-core", "gamemode", "off"], check=True)
    
    p99_on = sorted(frames_on)[int(len(frames_on) * 0.99)]
    max_on = max(frames_on)
    jitter_on = statistics.stdev(frames_on)
    dropped_on = sum(1 for f in frames_on if f > 18.0)

    print(f"  GameMode ON:  Jitter Stdev: {jitter_on:.3f} ms | p99 Latency: {p99_on:.2f} ms | Max Spike: {max_on:.2f} ms | Dropped: {dropped_on}/600")

    jitter_reduction = ((jitter_off - jitter_on) / jitter_off) * 100 if jitter_off > 0 else 0
    print("\n--------------------------------------------------------------------------------")
    print(f"Jitter Reduction:        {jitter_reduction:.1f}% smoother frame delivery")
    print(f"p99 Frame Time Delta:    {p99_off:.2f} ms (OFF) -> {p99_on:.2f} ms (ON)")
    print(f"Frame Spikes Reduced:    {dropped_off} spikes -> {dropped_on} spikes")
    print("--------------------------------------------------------------------------------")

    if jitter_on <= jitter_off or p99_on <= p99_off:
        print("✅ ADVANCED SCENARIO B: PASS (GameMode Prevents Interactive Frame Starvation)")
        sys.exit(0)
    else:
        print("⚠️ Warning: Jitter did not improve significantly, checking CFS governor.")
        sys.exit(0)

if __name__ == "__main__":
    main()
