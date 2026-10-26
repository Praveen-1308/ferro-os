#!/usr/bin/env python3
"""
tools/benchmarks/sustained_realworld_matrix/infra/strict_runner.py

Milestone 1: Strict Execution Runner with universal pipefail enforcement and unmasked exit code preservation.
Guarantees:
  - set -eo pipefail universally declared in all bash executions.
  - Zero masking of non-zero exit codes (0, 1, 127, 137, 139, 143).
  - Clean capture of stdout, stderr, and trailing 50 lines of stderr.
  - Process group isolation (start_new_session=True) and clean cleanup.
  - Seamless integration with HostResourceWatchdog for sub-second emergency aborts.
"""

import os
import sys
import time
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple, Union


# Standard POSIX Signal to Name Mapping
SIGNAL_NAMES = {
    1: "SIGHUP",
    2: "SIGINT",
    3: "SIGQUIT",
    4: "SIGILL",
    6: "SIGABRT",
    8: "SIGFPE",
    9: "SIGKILL",
    11: "SIGSEGV",
    13: "SIGPIPE",
    14: "SIGALRM",
    15: "SIGTERM",
}


@dataclass
class CommandResult:
    """Structured result of strict process execution."""
    command: str
    raw_exit_code: int
    normalized_exit_code: int
    exit_classification: str
    stdout: str
    stderr: str
    stderr_tail: str
    duration_s: float
    timed_out: bool = False
    watchdog_aborted: bool = False
    pipefail_enforced: bool = True
    signal_name: Optional[str] = None

    @property
    def is_success(self) -> bool:
        """Returns True if command exited with code 0."""
        return self.normalized_exit_code == 0


def classify_exit_code(normalized_code: int, timed_out: bool = False, watchdog_aborted: bool = False) -> Tuple[str, Optional[str]]:
    """
    Classifies exit code into standard semantic categories.
    Returns (classification_string, signal_name_or_None).
    """
    if watchdog_aborted:
        sig_name = "SIGKILL" if normalized_code == 137 else "SIGTERM"
        return "WATCHDOG_TERMINATED", sig_name
    if timed_out:
        sig_name = "SIGKILL" if normalized_code == 137 else "SIGTERM"
        return "TIMEOUT_EXPIRED", sig_name
    if normalized_code == 0:
        return "CLEAN", None
    if normalized_code == 127:
        return "COMMAND_NOT_FOUND", None
    if normalized_code == 126:
        return "COMMAND_CANNOT_EXECUTE", None
    if normalized_code == 130:
        return "INTERRUPTED_SIGINT", "SIGINT"
    if normalized_code == 137:
        return "OOM_KILLED", "SIGKILL"
    if normalized_code == 139:
        return "CRASH_SEGFAULT", "SIGSEGV"
    if normalized_code == 143:
        return "SIGNAL_TERMINATED_SIGTERM", "SIGTERM"

    # Signals 128 + N
    if normalized_code > 128:
        sig_num = normalized_code - 128
        sig_name = SIGNAL_NAMES.get(sig_num, f"SIG_{sig_num}")
        return f"SIGNAL_TERMINATED_{sig_name}", sig_name

    # General error codes 1..125
    return "APPLICATION_ERROR", None


def extract_trailing_lines(text: str, line_count: int = 50) -> str:
    """Extracts the trailing N lines of text, preserving trailing error diagnostics."""
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) <= line_count:
        return text
    return "\n".join(lines[-line_count:])


class StrictExecutionRunner:
    """
    Strict execution engine enforcing:
      1. /bin/bash subshell with 'set -eo pipefail'.
      2. Unmasked exit code and signal preservation.
      3. Process group isolation and cascading kill on termination.
      4. Live watchdog monitoring during execution.
    """

    def __init__(self, bash_path: str = "/bin/bash"):
        self.bash_path = bash_path
        if not os.path.exists(self.bash_path):
            self.bash_path = "/usr/bin/bash" if os.path.exists("/usr/bin/bash") else "bash"

    def run(
        self,
        command: Union[str, List[str]],
        timeout_s: float = 360.0,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        watchdog: Optional[Any] = None,
        poll_interval_s: float = 0.05,
    ) -> CommandResult:
        """
        Executes command with strict pipefail and unmasked exit code preservation.

        Args:
          command: String shell pipeline or list of binary arguments.
          timeout_s: Maximum allowed execution duration.
          cwd: Optional working directory.
          env: Optional environment variables.
          watchdog: Optional HostResourceWatchdog instance. If watchdog triggers emergency_abort,
                    the command is immediately aborted.
          poll_interval_s: Watchdog poll interval while process is active.
        """
        start_time = time.time()
        is_shell = isinstance(command, str)

        if is_shell:
            cmd_str = command.strip()
            # Enforce set -eo pipefail
            full_command = f"set -eo pipefail; {cmd_str}"
            popen_args = [self.bash_path, "-c", full_command]
            display_cmd = cmd_str
        else:
            popen_args = command
            display_cmd = " ".join(command)

        # Merge environment if provided
        proc_env = os.environ.copy()
        if env:
            proc_env.update(env)

        # Launch in new process group to allow clean cascading termination
        proc = subprocess.Popen(
            popen_args,
            cwd=cwd,
            env=proc_env,
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        pgid = proc.pid

        stdout_chunks: List[str] = []
        stderr_chunks: List[str] = []

        def _drain_stream(stream, chunks_list):
            try:
                while True:
                    chunk = stream.read(4096)
                    if not chunk:
                        break
                    chunks_list.append(chunk)
            except Exception:
                pass
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        t_out = threading.Thread(target=_drain_stream, args=(proc.stdout, stdout_chunks), daemon=True)
        t_err = threading.Thread(target=_drain_stream, args=(proc.stderr, stderr_chunks), daemon=True)
        t_out.start()
        t_err.start()

        timed_out = False
        watchdog_aborted = False

        # Monitoring loop
        while True:
            # Check watchdog emergency abort
            if watchdog is not None:
                is_aborted = getattr(watchdog, "emergency_abort", False)
                if callable(getattr(watchdog, "is_aborted", None)):
                    is_aborted = watchdog.is_aborted()
                if is_aborted:
                    watchdog_aborted = True
                    break

            # Check timeout
            elapsed = time.time() - start_time
            if elapsed >= timeout_s:
                timed_out = True
                break

            # Check if process has finished
            ret = proc.poll()
            if ret is not None:
                break

            time.sleep(poll_interval_s)

        # Terminate process tree if aborted or timed out
        if watchdog_aborted or timed_out:
            try:
                os.killpg(pgid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            time.sleep(0.15)
            # Unconditionally send SIGKILL to the entire process group
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass

        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(pgid, signal.SIGKILL)
                proc.wait(timeout=1.0)
            except Exception:
                pass

        # Bounded join on stream reading threads to prevent hangs on orphan child processes holding pipes
        remaining_time = max(0.0, timeout_s - (time.time() - start_time))
        join_budget = min(0.3, remaining_time) if not (timed_out or watchdog_aborted) else 0.5
        t_out.join(timeout=join_budget)
        t_err.join(timeout=join_budget)

        if t_out.is_alive() or t_err.is_alive():
            # Background orphan still holding pipes; force process group kill and close parent stream ends
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            try:
                if proc.stdout and not proc.stdout.closed:
                    proc.stdout.close()
            except Exception:
                pass
            try:
                if proc.stderr and not proc.stderr.closed:
                    proc.stderr.close()
            except Exception:
                pass
            t_out.join(timeout=0.3)
            t_err.join(timeout=0.3)

        stdout = "".join(stdout_chunks)
        stderr = "".join(stderr_chunks)

        duration_s = round(time.time() - start_time, 4)
        raw_code = proc.returncode if proc.returncode is not None else -1

        # Normalize negative signal exit codes to standard POSIX (128 + N)
        if raw_code < 0:
            normalized_code = 128 + abs(raw_code)
        else:
            normalized_code = raw_code

        # If aborted by watchdog or timed out, ensure normalized code is 143 (SIGTERM) or 137 (SIGKILL)
        if watchdog_aborted and normalized_code == 0:
            normalized_code = 143
        elif timed_out and normalized_code == 0:
            normalized_code = 143

        classification, sig_name = classify_exit_code(
            normalized_code,
            timed_out=timed_out,
            watchdog_aborted=watchdog_aborted,
        )
        stderr_tail = extract_trailing_lines(stderr, line_count=50)

        return CommandResult(
            command=display_cmd,
            raw_exit_code=raw_code,
            normalized_exit_code=normalized_code,
            exit_classification=classification,
            stdout=stdout,
            stderr=stderr,
            stderr_tail=stderr_tail,
            duration_s=duration_s,
            timed_out=timed_out,
            watchdog_aborted=watchdog_aborted,
            pipefail_enforced=True,
            signal_name=sig_name,
        )


# Module-level convenience functions matching Survey 3 & PROJECT.md contracts:

_GLOBAL_RUNNER = StrictExecutionRunner()

def run_strict_pipe(cmd_str: str, timeout: int = 360) -> Tuple[int, str, str]:
    """
    Universal pipefail execution contract matching Survey 3 specification.
    Returns (normalized_returncode, stdout, stderr).
    """
    res = _GLOBAL_RUNNER.run(cmd_str, timeout_s=float(timeout))
    return res.normalized_exit_code, res.stdout, res.stderr

def execute_with_pipefail(command: str) -> Tuple[int, str, str]:
    """
    Direct alias matching test_harness.py contract.
    Returns (exit_code, stdout, stderr).
    """
    return run_strict_pipe(command)

def run_strict_command(
    command: Union[str, List[str]],
    timeout_s: float = 360.0,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    watchdog: Optional[Any] = None,
) -> CommandResult:
    """Full-featured strict command execution returning CommandResult."""
    return _GLOBAL_RUNNER.run(command, timeout_s=timeout_s, cwd=cwd, env=env, watchdog=watchdog)
