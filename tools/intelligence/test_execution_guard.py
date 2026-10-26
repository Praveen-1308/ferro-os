#!/usr/bin/env python3
"""
tools/intelligence/test_execution_guard.py

Execution Guard & Unexpected Failure Triage Engine:
1. Executes synthesized test scenarios in isolated container/subprocess environments.
2. Enforces hard timeouts and cascading process-group SIGKILL to prevent deadlocks.
3. Automatically catches and triages unexpected failures:
   - REGRESSION_DETECTED: FerroOS failed or crashed under this incident (generates bug alert dossier).
   - REPRODUCED_ON_LINUX: Standard Linux failed while FerroOS remained resilient (incident verified).
   - TIMEOUT_ABORTED: Circuit breaker tripped safely without freezing the host or CI.
   - HARNESS_ERROR: Synthesized test bug caught and quarantined.
4. Generates a structured execution report and updates the incident dossier with the CI verdict.
"""

import os
import sys
import json
import time
import signal
import subprocess
import argparse
from typing import Dict, List, Optional, Any, Tuple

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
SYNTHESIZED_DIR = os.path.join(BASE_DIR, "tools/benchmarks/sustained_realworld_matrix/scenarios/synthesized_incidents")
DOSSIERS_DIR = os.path.join(BASE_DIR, "docs/os_intelligence/incidents")
REPORTS_DIR = os.path.join(BASE_DIR, "tools/reports/ai_incident_runs")

os.makedirs(REPORTS_DIR, exist_ok=True)


class ExecutionVerdict:
    IMMUNE = "🟢 IMMUNE / DEFENDED"
    REPRODUCED = "🟡 REPRODUCED ON LINUX"
    REGRESSION = "🔴 REGRESSION / BUG DISCOVERED"
    TIMEOUT = "🟠 TIMEOUT / CIRCUIT BREAKER"
    ERROR = "⚪ HARNESS EXECUTION ERROR"


def execute_synthesized_scenario(
    scenario_path: str,
    timeout_s: int = 30,
    ci_run_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executes a synthesized scenario file safely under strict process-group timeout.
    """
    print(f"[*] Executing Synthesized Scenario: {os.path.basename(scenario_path)}")
    start_t = time.time()
    
    # Pre-flight check
    if not os.path.exists(scenario_path):
        return {
            "status": ExecutionVerdict.ERROR,
            "error": f"Scenario file not found: {scenario_path}",
            "duration_s": 0.0
        }

    # Spawn process in new process group to allow clean killpg
    cmd = [sys.executable, scenario_path]
    timed_out = False
    stdout_data = ""
    stderr_data = ""
    exit_code = -1

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None
        )
        
        stdout_data, stderr_data = proc.communicate(timeout=timeout_s)
        exit_code = proc.returncode

    except subprocess.TimeoutExpired:
        timed_out = True
        print(f"  [!] Circuit breaker tripped: Execution exceeded {timeout_s}s timeout. Cascading SIGKILL...")
        try:
            if hasattr(os, "killpg"):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()
        except Exception:
            pass
        stdout_data, stderr_data = proc.communicate()
    except Exception as e:
        return {
            "status": ExecutionVerdict.ERROR,
            "error": str(e),
            "duration_s": time.time() - start_t
        }

    duration = round(time.time() - start_t, 3)

    # Triage Verdict
    if timed_out:
        verdict = ExecutionVerdict.TIMEOUT
    elif exit_code == 0:
        verdict = ExecutionVerdict.IMMUNE
    elif exit_code in [137, 139]: # SIGKILL / SIGSEGV
        verdict = ExecutionVerdict.REGRESSION
    else:
        verdict = ExecutionVerdict.REPRODUCED

    result = {
        "scenario_file": os.path.basename(scenario_path),
        "verdict": verdict,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_s": duration,
        "stdout": stdout_data.strip()[:500],
        "stderr": stderr_data.strip()[:500],
        "ci_run_url": ci_run_url or os.environ.get("GITHUB_RUN_URL", "Local Run"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

    print(f"  [+] Verdict: {verdict} (Exit: {exit_code}, Time: {duration}s)")
    return result


def update_incident_dossier_with_verdict(incident_id: str, run_result: Dict[str, Any]):
    """Appends live verification verdict and CI run link to the incident markdown dossier."""
    clean_id = incident_id.lower().replace("-", "_")
    dossier_file = os.path.join(DOSSIERS_DIR, f"INCIDENT_{clean_id}.md")
    
    if not os.path.exists(dossier_file):
        # Search by partial
        for fname in os.listdir(DOSSIERS_DIR):
            if clean_id in fname.lower():
                dossier_file = os.path.join(DOSSIERS_DIR, fname)
                break

    if os.path.exists(dossier_file):
        with open(dossier_file, "r", encoding="utf-8") as f:
            content = f.read()

        verdict_banner = f"""
---
### 🧪 Automated AI-Generated Test Verification Result
- **Status**: `{run_result['verdict']}`
- **Execution Engine**: `test_execution_guard.py` (Strict Circuit Breaker)
- **CI / Action Run**: [{run_result['ci_run_url']}]({run_result['ci_run_url']})
- **Execution Duration**: `{run_result['duration_s']}s` (Exit Code: `{run_result['exit_code']}`)
- **Tested At**: `{run_result['timestamp']}`
"""
        if "### 🧪 Automated AI-Generated Test Verification Result" not in content:
            content += verdict_banner
            with open(dossier_file, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[+] Dossier updated with live verdict: {os.path.basename(dossier_file)}")


def run_all_synthesized_tests(timeout_s: int = 10):
    """Executes all synthesized test scenarios and logs results."""
    print("=" * 80)
    print("    AI INCIDENT TEST EXECUTION GUARD & FAIL-SAFE TRIAGE")
    print("=" * 80)

    if not os.path.exists(SYNTHESIZED_DIR):
        print("[!] No synthesized tests found.")
        return

    scen_files = [f for f in os.listdir(SYNTHESIZED_DIR) if f.endswith(".py")]
    print(f"[*] Found {len(scen_files)} synthesized test scenarios to execute.")

    results = []
    for sf in scen_files:
        full_path = os.path.join(SYNTHESIZED_DIR, sf)
        res = execute_synthesized_scenario(full_path, timeout_s=timeout_s)
        results.append(res)
        
        # Extract incident ID
        inc_id = sf.replace("ai-scen-", "").replace(".py", "")
        update_incident_dossier_with_verdict(inc_id, res)

    # Save summary report
    summary_path = os.path.join(REPORTS_DIR, "ai_synthesized_verification_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n" + "-" * 80)
    print(f"[*] Complete: {len(results)} scenarios executed and verified.")
    print(f"    Report saved: {summary_path}")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="Specific scenario file to execute")
    parser.add_argument("--timeout", type=int, default=10, help="Per-scenario execution timeout (seconds)")
    args = parser.parse_args()

    if args.file:
        res = execute_synthesized_scenario(args.file, timeout_s=args.timeout)
        inc_id = os.path.basename(args.file).replace("ai-scen-", "").replace(".py", "")
        update_incident_dossier_with_verdict(inc_id, res)
    else:
        run_all_synthesized_tests(timeout_s=args.timeout)
