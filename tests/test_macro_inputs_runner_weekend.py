"""Run-MacroInputs.ps1 on weekends (ACK 10 Oct 2026: the trading-day rule does not apply at weekends).

There is no US session on a Saturday or Sunday, so the session windows, the regular-hours guard and the
trading-day skip do not apply: a weekend run starts straight away, measures from the last completed
session (Friday's close) and is labelled OffSession, so the board files it as an off-session build and
never overwrites Friday's scored evening record. Weekday XNYS holidays still skip (the Mon-Fri scheduled
tasks fire on them). Exercised with -PlanOnly and a simulated clock (-NowET): nothing is run or written.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "Run-MacroInputs.ps1"

pytestmark = pytest.mark.skipif(shutil.which("powershell.exe") is None or not (REPO / "venv" / "Scripts" / "python.exe").exists(),
                                reason="needs Windows PowerShell and the repo venv (trading calendar)")


def _plan(now_et: str, *extra: str) -> str:
    out = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RUNNER), "-PlanOnly",
                          "-NowET", now_et, *extra], capture_output=True, text=True, timeout=180, cwd=str(REPO))
    assert out.returncode == 0, out.stdout + out.stderr
    return out.stdout


def test_a_saturday_run_is_an_off_session_run_with_no_time_window_cut_at_fridays_close():
    text = _plan("2026-10-10 11:00")
    assert "session        : OffSession" in text
    assert "weekend: off-session run" in text and "would be skipped" not in text
    assert "start window   : none (weekend - starts immediately)" in text
    assert "session cut-off: 2026-10-09" in text
    assert "board build    : off-session (not the scored evening record)" in text


def test_an_explicit_postclose_at_the_weekend_is_still_off_session():
    text = _plan("2026-10-11 20:00", "-Session", "PostClose")
    assert "session        : OffSession" in text and "session cut-off: 2026-10-09" in text


def test_a_weekday_us_holiday_still_skips():
    text = _plan("2026-11-26 12:00")                                   # Thanksgiving, a Thursday
    assert "NO - the run would be skipped" in text and "OffSession" not in text


def test_a_trading_day_keeps_its_session_and_window():
    text = _plan("2026-10-09 17:00")
    assert "session        : PostClose" in text and "trading day    : yes" in text
    assert "start window   : 16:30 - 23:30 ET" in text
