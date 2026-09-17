"""Interpreter, shell flags and concurrently running data writers."""

from __future__ import annotations

import os
import platform
import subprocess
import sys

from ..model import EnvironmentFacts

WRITER_MARKERS = (
    "intelligent_orchestrator.py",
    "run_phantom_backfill",
    "backfill_runbook.py",
    "morning_gate.py",
    "phantom_greek_rehydrate.py",
)


def running_data_writers(own_pid: int) -> tuple[str, ...]:
    command = (
        "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
        "ForEach-Object { \"$($_.ProcessId)|$($_.ParentProcessId)|$($_.CommandLine)\" }"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"process listing failed: {result.stderr.strip()[:300]}")
    found = []
    for line in result.stdout.splitlines():
        try:
            pid, parent, cmdline = line.split("|", 2)
        except ValueError:
            continue
        if pid.strip() in {str(own_pid)} or parent.strip() == str(own_pid):
            continue
        low = cmdline.lower()
        if "--plan-only" in low:
            continue
        for marker in WRITER_MARKERS:
            if marker in low:
                found.append(f"pid {pid.strip()}: {marker}")
                break
    return tuple(found)


def collect_environment_facts() -> EnvironmentFacts:
    return EnvironmentFacts(
        python_executable=sys.executable,
        python_version=platform.python_version(),
        host=platform.node(),
        shell_flags={k: v for k, v in sorted(os.environ.items()) if k.startswith("AVSHUNTER_")},
        running_data_writers=running_data_writers(os.getpid()),
    )
