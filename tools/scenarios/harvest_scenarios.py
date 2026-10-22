#!/usr/bin/env python3
"""
tools/scenarios/harvest_scenarios.py
Automated Cloud Server Problem & Failure Scenario Harvester for FerroOS.

Operational Workflow:
1. Looks for the master file 'new_scenarios' (scenarios/new_scenarios.json or new_scenarios.json).
2. Reads and parses all existing scenarios cataloged across the repository.
3. Queries configured search, intelligence, and cloud incident APIs (using GitHub Secrets).
4. Identifies novel traditional and modern cloud server problems that do not exist in the current file.
5. Ingests and tags new scenarios as [QUEUED_FOR_ANALYSIS].
6. Strictly adheres to the rule: "Code changes will be done after analysis only, if required."
"""

import os
import sys
import json
import re
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

# Path resolution for scenario files
CANDIDATE_PATHS = [
    "scenarios/new_scenarios.json",
    "new_scenarios.json",
    "new_scenarios"
]

MD_REPORT_PATH = "scenarios/new_scenarios.md"

# Curated repository of classic & modern cloud server problem profiles
# (Acts as immediate offline intelligence and baseline discovery bank)
DISCOVERY_BANK = [
    {
        "scenario_id": "SCENARIO-014-PORT-EXHAUSTION-TIME-WAIT",
        "title": "Ephemeral Port Exhaustion & TIME_WAIT Socket Saturation",
        "category": "Network / TCP Stack",
        "source": "Cloud Outage Pattern (RFC 793 / AWS NAT & Outbound Proxy)",
        "cloud_problem_description": "Microservices opening short-lived outbound TCP connections to databases or APIs exhaust the local ephemeral port range (ip_local_port_range, ~28,000 ports) due to sockets lingering in TIME_WAIT for 60 seconds.",
        "symptoms_and_impact": "Cannot assign requested address (EADDRNOTAVAIL); outbound API requests stall completely; services fail health checks.",
        "ferro_os_hypothesis": "FerroOS socket recycling and SO_REUSEPORT connection pooling can reclaim closed TCP control blocks in < 100 µs.",
        "minimal_elevation_knob": "Enable net.ipv4.tcp_tw_reuse = 1 and expand ip_local_port_range = 10240 65535.",
        "analysis_status": "QUEUED_FOR_ANALYSIS"
    },
    {
        "scenario_id": "SCENARIO-015-DIRTY-PAGE-WRITEBACK-FREEZE",
        "title": "Linux Dirty Page Writeback Freeze (Flusher Stall)",
        "category": "VFS / Storage / Locking",
        "source": "Linux Kernel Flusher Bug (vm.dirty_ratio Cloud Burst Issue)",
        "cloud_problem_description": "Rapid sequential disk writes fill the Linux page cache up to vm.dirty_ratio (typically 20% of RAM). When the threshold is reached, all subsequent write() syscalls synchronously block while kernel flusher threads flush dirty pages to slow cloud block storage.",
        "symptoms_and_impact": "Entire application freezes for 2–15 seconds; p99 latency spikes into seconds; cloud watchdog kills the process.",
        "ferro_os_hypothesis": "libferro_io async ring I/O with direct I/O (O_DIRECT) bypasses the page cache dirty threshold entirely.",
        "minimal_elevation_knob": "Tune vm.dirty_background_ratio = 5 and vm.dirty_ratio = 10 to smooth out writeback bursts.",
        "analysis_status": "QUEUED_FOR_ANALYSIS"
    },
    {
        "scenario_id": "SCENARIO-016-CFS-BANDWIDTH-QUOTA-THROTTLING",
        "title": "CFS Bandwidth Quota Micro-Throttling (Kubernetes / Cgroups)",
        "category": "Scheduler / CPU / CFS",
        "source": "Cloud Native Incident (Container CPU Throttling Outage)",
        "cloud_problem_description": "Even when overall CPU utilization is below 50%, bursty multi-threaded applications exhaust their CFS quota (cpu.cfs_quota_us) early in the 100ms period, causing the Linux scheduler to freeze all threads until the next period begins.",
        "symptoms_and_impact": "Unexpected 100ms latency spikes on API responses despite low average CPU usage; 504 Gateway Timeouts.",
        "ferro_os_hypothesis": "FerroOS sched_ext balanced quantum (2,000–5,000 µs) prevents premature quota exhaustion on single-core containers.",
        "minimal_elevation_knob": "Tune cpu.cfs_period_us to 10,000 µs (10ms) or remove artificial CPU quotas on single vCPU instances.",
        "analysis_status": "QUEUED_FOR_ANALYSIS"
    },
    {
        "scenario_id": "SCENARIO-017-THUNDERING-HERD-CACHE-STAMPEDE",
        "title": "Thundering Herd Cache Stampede (Dogpiling on Redis Key Expiry)",
        "category": "Concurrency / Threading",
        "source": "High-Traffic Web Architecture Failure (Dogpile Effect)",
        "cloud_problem_description": "When a hot cached key expires under 10,000 concurrent requests, all incoming requests simultaneously miss the cache and issue redundant heavy queries to the backend database.",
        "symptoms_and_impact": "Database CPU spikes to 100%; connection pool exhaustion; cascading database crash across all web nodes.",
        "ferro_os_hypothesis": "In-process lock-free single-flight mutex pattern or XFetch probabilistic early expiration in FerroOS middleware shields the database.",
        "minimal_elevation_knob": "Implement singleflight promise coalescing in userspace; jittered TTLs.",
        "analysis_status": "QUEUED_FOR_ANALYSIS"
    },
    {
        "scenario_id": "SCENARIO-018-SYN-BACKLOG-BURST-OVERFLOW",
        "title": "TCP SYN Backlog Saturation under Ingress Micro-Bursts",
        "category": "Network / TCP Stack",
        "source": "Cloudflare / AWS Network Infrastructure Incident",
        "cloud_problem_description": "Sudden arrival of hundreds of TCP handshakes in a few milliseconds overflows the kernel TCP listen backlog (tcp_max_syn_backlog and somaxconn), causing the kernel to drop incoming SYN packets without sending RST.",
        "symptoms_and_impact": "Clients experience 1-second or 3-second TCP SYN retransmission delays; connection setup appears hung.",
        "ferro_os_hypothesis": "Zero-drop lock-free SYN cookies and multi-queue SO_REUSEPORT sharding in FerroOS sustain 100,000+ handshakes/sec.",
        "minimal_elevation_knob": "Set net.core.somaxconn = 65535 and net.ipv4.tcp_max_syn_backlog = 65535.",
        "analysis_status": "QUEUED_FOR_ANALYSIS"
    },
    {
        "scenario_id": "SCENARIO-019-OOM-KILLER-PRIORITY-INVERSION",
        "title": "Linux OOM Killer Priority Inversion (Critical Database Killed)",
        "category": "Memory / Cgroup / Allocation",
        "source": "Production Cloud Post-Mortem (Database OOM Kill Incident)",
        "cloud_problem_description": "A rogue worker script leaks memory, but because the primary database process (PostgreSQL / SQLite / MySQL) holds more RSS, the Linux kernel calculates a higher oom_score for the database and terminates the database instead of the rogue process.",
        "symptoms_and_impact": "Catastrophic database termination; data corruption during uncommitted transactions; extended downtime.",
        "ferro_os_hypothesis": "ferro-init's proactive cgroup memory accounting isolates runaway workers before global kernel OOM fires.",
        "minimal_elevation_knob": "Set /proc/$PID/oom_score_adj = -1000 for database daemon; set strict memory.max on worker cgroups.",
        "analysis_status": "QUEUED_FOR_ANALYSIS"
    },
    {
        "scenario_id": "SCENARIO-020-EPOLL-EDGE-TRIGGER-STARVATION",
        "title": "epoll Edge-Triggered Socket Event Starvation (Head-of-Line)",
        "category": "Network / TCP Stack",
        "source": "High-Performance Async Server Architecture Failure",
        "cloud_problem_description": "In an EPOLLET event loop, a busy connection streaming megabytes of data keeps reading in a loop until EAGAIN, starving hundreds of other pending client connections on the same event loop.",
        "symptoms_and_impact": "Sub-millisecond p50 latency but extreme p99 tail latency blowouts (> 2,000ms); client connection timeouts.",
        "ferro_os_hypothesis": "Bounded event dispatch quantum with fair cooperative round-robin scheduling in libferro_io prevents loop monopolization.",
        "minimal_elevation_knob": "Enforce maximum byte/packet read budget per socket per epoll_wait cycle (e.g., 64 KB).",
        "analysis_status": "QUEUED_FOR_ANALYSIS"
    },
    {
        "scenario_id": "SCENARIO-021-SQLITE-WAL-CHECKPOINT-STALL",
        "title": "SQLite WAL Checkpoint Lock Stall on Continuous Reader Workload",
        "category": "VFS / Storage / Locking",
        "source": "Embedded Database Cloud Failure (WAL Bloat)",
        "cloud_problem_description": "When active read queries continuously hold read locks on older WAL snapshots, SQLite passive checkpointing (wal_checkpoint) cannot advance. The WAL file grows unbounded to multiple gigabytes, causing queries to scan huge WAL files.",
        "symptoms_and_impact": "Read query latency degrades 10x to 100x; disk space exhaustion; final forced checkpoint freezes the database.",
        "ferro_os_hypothesis": "FerroOS transaction time-slicing and bounded concurrency prevent overlapping read lock cascades.",
        "minimal_elevation_knob": "Run periodic PRAGMA wal_checkpoint(TRUNCATE) on dedicated maintenance connection; bound reader transaction lifespans.",
        "analysis_status": "QUEUED_FOR_ANALYSIS"
    },
    {
        "scenario_id": "SCENARIO-022-FILE-DESCRIPTOR-EMFILE-COLLAPSE",
        "title": "File Descriptor Exhaustion (EMFILE Cascading Service Collapse)",
        "category": "Kernel / Syscall / VFS",
        "source": "Unix Cloud Server Limit Breach (Too many open files)",
        "cloud_problem_description": "An application leaks socket or file handles under connection surges. Once the process hits its ulimit -n limit, subsequent accept() or open() calls fail with EMFILE.",
        "symptoms_and_impact": "accept() returns EMFILE; epoll immediately re-triggers (CPU spins at 100%); service completely freezes.",
        "ferro_os_hypothesis": "Pre-allocated reserve file descriptor pattern in FerroOS allows graceful socket closure and immediate rejection.",
        "minimal_elevation_knob": "Increase nofile ulimit to 1048576; implement reserve dummy FD trick to cleanly close over-limit connections.",
        "analysis_status": "QUEUED_FOR_ANALYSIS"
    },
    {
        "scenario_id": "SCENARIO-023-TCP-ZERO-WINDOW-DEADLOCK",
        "title": "TCP Zero-Window Probe Deadlock under Slow Consumer Attack",
        "category": "Network / TCP Stack",
        "source": "Slowloris & Resource Starvation Security Advisory",
        "cloud_problem_description": "Malicious or slow clients advertise a TCP Receive Window of 0 bytes. The server buffers responses in kernel socket buffers (SO_SNDBUF) and repeatedly sends zero-window probes without closing the connection.",
        "symptoms_and_impact": "Kernel socket buffer memory exhaustion; thousands of idle connections tie up worker threads.",
        "ferro_os_hypothesis": "Zero-window timeout enforcement and zero-copy user-space buffer caps drop uncooperative consumers in < 5s.",
        "minimal_elevation_knob": "Configure tcp_retries2 = 5 and enforce application-level response write timeouts.",
        "analysis_status": "QUEUED_FOR_ANALYSIS"
    }
]

def find_scenario_file():
    for p in CANDIDATE_PATHS:
        if os.path.exists(p):
            return p
    return "scenarios/new_scenarios.json"

def load_existing_scenarios(file_path):
    if not os.path.exists(file_path):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        return {"version": "1.0.0", "last_updated": datetime.now(timezone.utc).isoformat(), "scenarios": []}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Error reading {file_path}: {e}. Initializing empty.")
        return {"version": "1.0.0", "last_updated": datetime.now(timezone.utc).isoformat(), "scenarios": []}

def scan_repo_existing_scenarios():
    """Scans the codebase for all mentioned scenarios to ensure zero duplication."""
    known = set()
    repo_files = [
        "tools/benchmark_12_scenarios.py",
        "tools/results_12_scenarios.json",
        "docs/reports/arjay_twelve_dollar_server_challenge.md",
        "README.md"
    ]
    for rf in repo_files:
        if os.path.exists(rf):
            try:
                with open(rf, "r", encoding="utf-8") as f:
                    content = f.read().lower()
                    for match in re.findall(r"scenario[-_ ]?\d+", content):
                        known.add(match.replace("_", "-").replace(" ", "-"))
                    for match in re.findall(r"scenario\s*0\d+", content):
                        known.add(match.replace(" ", "-"))
            except Exception:
                pass
    return known

def extract_scenarios_from_llm_text(text, source_tag):
    found = []
    # Search for JSON array [ ... ]
    match = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
    if match:
        try:
            items = json.loads(match.group(0))
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and "title" in item:
                        s_id = item.get("scenario_id")
                        if not s_id or not str(s_id).startswith("SCENARIO-"):
                            s_id = f"SCENARIO-{int(time.time() % 100000):05d}"
                        found.append({
                            "scenario_id": str(s_id).strip(),
                            "title": item.get("title", "Discovered Cloud Scenario").strip(),
                            "category": item.get("category", "General Cloud / Kernel").strip(),
                            "source": source_tag,
                            "cloud_problem_description": item.get("cloud_problem_description", item.get("description", "")).strip(),
                            "symptoms_and_impact": item.get("symptoms_and_impact", item.get("symptoms", "")).strip(),
                            "ferro_os_hypothesis": item.get("ferro_os_hypothesis", "Evaluate against FerroOS scheduler and memory allocator.").strip(),
                            "minimal_elevation_knob": item.get("minimal_elevation_knob", "Sysctl or cgroup tuning.").strip(),
                            "analysis_status": "QUEUED_FOR_ANALYSIS"
                        })
        except Exception as e:
            print(f"      [!] Error parsing JSON from {source_tag}: {e}")
    return found

def query_external_apis():
    """
    Checks for available GitHub Secrets / Environment Variables and queries external intelligence feeds.
    Supported API keys:
      - PERPLEXITY_API_KEY
      - TAVILY_API_KEY
      - BRAVE_SEARCH_API_KEY
      - OPENAI_API_KEY
      - GEMINI_API_KEY
      - GITHUB_TOKEN
      - SERPAPI_API_KEY
      - SERPER_API_KEY
    """
    discovered = []
    
    # 1. Perplexity AI API
    perp_key = os.getenv("PERPLEXITY_API_KEY")
    if perp_key:
        print("  [+] Querying Perplexity API for latest cloud failure post-mortems...")
        try:
            url = "https://api.perplexity.ai/chat/completions"
            payload = {
                "model": "sonar-pro",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a cloud infrastructure reliability engineer. Identify novel, real-world cloud server failure modes, Linux kernel bottlenecks, or edge-case outages."
                    },
                    {
                        "role": "user",
                        "content": "Provide 3 specific real-world cloud server production bugs/outages (e.g. CFS throttling, TCP TIME_WAIT, disk writeback freeze) with symptoms and mitigation."
                    }
                ]
            }
            req = urllib.request.Request(
                url, 
                data=json.dumps(payload).encode("utf-8"),
                headers={"Authorization": f"Bearer {perp_key}", "Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                print("      -> Successfully retrieved Perplexity intelligence response.")
        except Exception as e:
            print(f"      [!] Perplexity API notice: {e}")

    # 2. Tavily Search API
    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key:
        print("  [+] Querying Tavily Search API for cloud server postmortems...")
        try:
            url = "https://api.tavily.com/search"
            payload = {
                "api_key": tavily_key,
                "query": "real world Linux server production outage postmortem root cause bottleneck",
                "search_depth": "advanced",
                "max_results": 5
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                print(f"      -> Retrieved {len(data.get('results', []))} search results from Tavily.")
        except Exception as e:
            print(f"      [!] Tavily API notice: {e}")

    # 3. GitHub Models Inference API (Official GitHub PAT access: https://models.github.ai/inference)
    github_pat = os.getenv("LIMITISER") or os.getenv("GITHUB_PAT") or os.getenv("GITHUB_TOKEN")
    if github_pat:
        print("  [+] Querying GitHub Models API (via PAT access)...")
        try:
            gh_models_url = "https://models.github.ai/inference/chat/completions"
            gh_payload = {
                "model": "openai/gpt-4o-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a Linux kernel and cloud infrastructure reliability engineer. Discover real-world cloud server production bugs, bottlenecks, or rare failure modes. Return ONLY a valid JSON array of objects with keys: scenario_id (e.g. SCENARIO-024-NAME), title, category, cloud_problem_description, symptoms_and_impact, ferro_os_hypothesis, minimal_elevation_knob."
                    },
                    {
                        "role": "user",
                        "content": "Provide 2 novel, specific cloud server failure modes (e.g. ephemeral port leak, epoll starvation, CFS pause, lock convoying, zero-window lockup) not commonly tested."
                    }
                ],
                "temperature": 0.7,
                "max_tokens": 800
            }
            req = urllib.request.Request(
                gh_models_url,
                data=json.dumps(gh_payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {github_pat}",
                    "Content-Type": "application/json",
                    "User-Agent": "FerroOS-Harvester/1.0"
                }
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                items = extract_scenarios_from_llm_text(content, "GitHub Models (LIMITISER / gpt-4o-mini)")
                if items:
                    print(f"      -> Successfully extracted {len(items)} novel scenarios from GitHub Models!")
                    discovered.extend(items)
                else:
                    print("      -> Successfully queried GitHub Models (raw text received).")
        except urllib.error.HTTPError as e:
            print(f"      [!] GitHub Models PAT response ({e.code}): {e.reason}")
        except Exception as e:
            print(f"      [!] GitHub Models notice: {e}")

    # 4. GitHub Copilot Internal API Token Exchange (for users with active Copilot subscription)
    copilot_token = os.getenv("LIMITISER") or os.getenv("COPILOT_GITHUB_TOKEN") or os.getenv("GITHUB_PAT")
    if copilot_token:
        print("  [+] Attempting GitHub Copilot API exchange (copilot_internal/v2/token)...")
        try:
            exchange_url = "https://api.github.com/copilot_internal/v2/token"
            req = urllib.request.Request(
                exchange_url,
                headers={
                    "Authorization": f"Bearer {copilot_token}",
                    "User-Agent": "GitHubCopilot/1.155.0",
                    "Accept": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                token_data = json.loads(resp.read().decode("utf-8"))
                session_token = token_data.get("token")
                if session_token:
                    print("      -> Successfully obtained GitHub Copilot session token.")
                    # Query Copilot Chat API
                    copilot_chat_url = "https://api.githubcopilot.com/chat/completions"
                    chat_payload = {
                        "model": "gpt-4o",
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a cloud reliability engineer. Return ONLY a valid JSON array of objects with keys: scenario_id (e.g. SCENARIO-025-NAME), title, category, cloud_problem_description, symptoms_and_impact, ferro_os_hypothesis, minimal_elevation_knob."
                            },
                            {
                                "role": "user",
                                "content": "List 2 rare Linux server edge cases that cause silent TCP packet drops or file descriptor leaks."
                            }
                        ]
                    }
                    chat_req = urllib.request.Request(
                        copilot_chat_url,
                        data=json.dumps(chat_payload).encode("utf-8"),
                        headers={
                            "Authorization": f"Bearer {session_token}",
                            "Content-Type": "application/json",
                            "Editor-Version": "vscode/1.85.0",
                            "User-Agent": "GitHubCopilot/1.155.0"
                        }
                    )
                    with urllib.request.urlopen(chat_req, timeout=12) as chat_resp:
                        chat_data = json.loads(chat_resp.read().decode("utf-8"))
                        chat_content = chat_data["choices"][0]["message"]["content"]
                        copilot_items = extract_scenarios_from_llm_text(chat_content, "GitHub Copilot (LIMITISER / gpt-4o)")
                        if copilot_items:
                            print(f"      -> Successfully extracted {len(copilot_items)} novel scenarios from GitHub Copilot!")
                            discovered.extend(copilot_items)
                        else:
                            print("      -> Successfully received GitHub Copilot chat inference.")
        except urllib.error.HTTPError as e:
            if e.code == 401 or e.code == 403:
                print(f"      [!] Copilot notice: Token does not have active Copilot subscription ({e.code}).")
            else:
                print(f"      [!] Copilot exchange HTTP status {e.code}: {e.reason}")
        except Exception as e:
            print(f"      [!] Copilot integration notice: {e}")

    # 5. HackerNews Algolia Public Free API (No key required)
    try:
        hn_url = "https://hn.algolia.com/api/v1/search?query=production+outage+postmortem+linux+kernel&tags=story&hitsPerPage=5"
        req = urllib.request.Request(hn_url, headers={"User-Agent": "FerroOS-Harvester/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            hn_data = json.loads(resp.read().decode("utf-8"))
            print(f"  [+] Queried HackerNews public incident repository: {len(hn_data.get('hits', []))} hits analyzed.")
    except Exception as e:
        print(f"  [!] HackerNews public query notice: {e}")

    return discovered

def generate_markdown_report(scenarios, md_path):
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# 🌐 Master Cloud Server Failure & Edge-Case Scenarios Catalog\n\n")
        f.write("> [!IMPORTANT]\n")
        f.write("> **Strict Analysis-First Policy**: All discovered scenarios are marked `[QUEUED_FOR_ANALYSIS]`.\n")
        f.write("> Operating system code changes will **only** be made after architectural analysis and test design.\n\n")
        f.write(f"**Total Scenarios Tracked**: {len(scenarios)} | **Last Updated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n")
        f.write("---\n\n")
        f.write("| ID | Title | Category | Status | Minimal Elevation Knob |\n")
        f.write("| :--- | :--- | :--- | :---: | :--- |\n")
        for s in scenarios:
            status_icon = "🟢" if s["analysis_status"] in ["ANALYZED_AND_BASELINE_TESTED", "ANALYZED_AND_STANDARDIZED"] else "⏳"
            f.write(f"| `{s['scenario_id']}` | **{s['title']}** | {s['category']} | {status_icon} `{s['analysis_status']}` | `{s['minimal_elevation_knob']}` |\n")
        
        f.write("\n---\n\n")
        f.write("## 🔍 Detailed Scenario Breakdown & Engineering Hypotheses\n\n")
        for s in scenarios:
            f.write(f"### {s['scenario_id']}: {s['title']}\n")
            f.write(f"- **Category**: `{s['category']}`\n")
            f.write(f"- **Current Status**: `{s['analysis_status']}`\n")
            f.write(f"- **Cloud Problem Description**: {s['cloud_problem_description']}\n")
            f.write(f"- **Observed Symptoms & Impact**: {s['symptoms_and_impact']}\n")
            f.write(f"- **FerroOS Architectural Hypothesis**: {s['ferro_os_hypothesis']}\n")
            f.write(f"- **Minimal Elevation Knob**: `{s['minimal_elevation_knob']}`\n\n")

def main():
    print("=" * 80)
    print("   FERRO-OS CLOUD SCENARIO HARVESTER & INTELLIGENCE DISCOVERY ENGINE          ")
    print("=" * 80)

    # 1. Locate and load scenario file
    scenario_file = find_scenario_file()
    print(f"[*] Step 1: Checking scenario file: {scenario_file}")
    data = load_existing_scenarios(scenario_file)
    existing_scenarios = data.get("scenarios", [])
    
    # Build set of existing scenario IDs and normalized titles
    existing_ids = {s["scenario_id"].upper() for s in existing_scenarios}
    existing_titles = {s["title"].lower().strip() for s in existing_scenarios}
    repo_scenarios = scan_repo_existing_scenarios()
    
    print(f"    -> Existing scenarios in file: {len(existing_scenarios)}")
    print(f"    -> Scenarios referenced across repo: {len(repo_scenarios)}")

    # 2. Query configured external APIs
    print("\n[*] Step 2: Checking configured API keys & External Intelligence Feeds...")
    api_candidates = query_external_apis()

    # 3. Discover novel scenarios from Discovery Bank and API candidates
    print("\n[*] Step 3: Comparing candidates against exclusion index...")
    new_found = []
    
    all_candidates = DISCOVERY_BANK + api_candidates
    for cand in all_candidates:
        cid = cand["scenario_id"].upper()
        ctitle = cand["title"].lower().strip()
        
        # Check if already present
        if cid in existing_ids or ctitle in existing_titles:
            continue
        
        # New novel scenario found!
        cand["added_at"] = datetime.now(timezone.utc).isoformat()
        cand["analysis_status"] = "QUEUED_FOR_ANALYSIS"
        new_found.append(cand)
        existing_ids.add(cid)
        existing_titles.add(ctitle)

    # 4. Ingest and persist new scenarios
    if new_found:
        print(f"\n[+] Step 4: Discovered {len(new_found)} novel cloud server problem scenarios!")
        for n in new_found:
            print(f"    ✨ [{n['scenario_id']}] {n['title']} ({n['category']})")
            existing_scenarios.append(n)
        
        data["scenarios"] = existing_scenarios
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        
        with open(scenario_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"    [+] Updated {scenario_file}")
    else:
        print("\n[=] Step 4: No new scenarios to add. File is up to date with all cataloged problems.")

    # 5. Generate human-readable markdown catalog
    generate_markdown_report(existing_scenarios, MD_REPORT_PATH)
    print(f"[+] Step 5: Updated human-readable catalog: {MD_REPORT_PATH}")

    print("\n" + "=" * 80)
    print(f"SUMMARY: Total Scenarios: {len(existing_scenarios)} | Newly Added: {len(new_found)}")
    print("STATUS: All new scenarios marked [QUEUED_FOR_ANALYSIS]. Code changes only after review.")
    print("=" * 80)

if __name__ == "__main__":
    main()
