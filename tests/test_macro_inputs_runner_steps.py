"""Run-MacroInputs.ps1 steps (ACK 19 Oct 2026: "how can we incorporate rapid_rotation_flag.py,
scripts\\build_local_gex.py and bond_macro_intelligence.py --verbose into the automation", then "build it all").

GEX and the bond state run by default before the producers; the rapid rotation flag runs after the macro packet
is rebuilt (it patches the packet) and before the board; its exit codes 1 and 2 are flag levels, not failures.
-Now runs a manual run straight away after a readiness report. Exercised with -PlanOnly and a simulated clock:
nothing is run or written."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "Run-MacroInputs.ps1"

pytestmark = pytest.mark.skipif(shutil.which("powershell.exe") is None or not (REPO / "venv" / "Scripts" / "python.exe").exists(),
                                reason="needs Windows PowerShell and the repo venv (trading calendar)")


def _plan(*extra: str, now_et: str = "2026-10-20 07:30") -> str:
    out = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RUNNER), "-PlanOnly",
                          "-NowET", now_et, *extra], capture_output=True, text=True, timeout=240, cwd=str(REPO))
    assert out.returncode == 0, out.stdout + out.stderr
    return out.stdout


def _order(text: str, names) -> list[int]:
    return [text.index(n) for n in names]


def test_gex_runs_first_and_bonds_run_after_the_producers_and_bonds_is_verbose():
    # 19 Oct 2026: bonds' Polygon calls seconds before the six producers coincided with HTTP 429s that wiped
    # out market intelligence; bonds now run once the producers have finished (only the board reads its state).
    text = _plan("-Session", "PreOpen")
    gex, vix, bonds, fred = _order(text, ["GEX (stored chains)", "VIX engine v4.1", "Bond macro + calendar",
                                          "FRED monitor v2.6"])
    assert gex < vix < bonds < fred
    assert "bond_macro_intelligence.py --verbose" in text


def test_the_rotation_flag_runs_after_the_packet_and_before_the_board_with_its_exit_codes_stated():
    text = _plan("-Session", "PreOpen")
    packet, flag, board = _order(text, ["Macro packet (build_macro_json)", "Rapid rotation flag", "ETF macro board"])
    assert packet < flag < board
    assert "exit 1/2 = flag level" in text


def test_each_new_step_can_be_skipped_and_the_old_switches_still_work():
    text = _plan("-Session", "PreOpen", "-SkipGex", "-SkipBonds", "-SkipRotationFlag")
    assert "GEX (stored chains)" not in text and "Bond macro" not in text and "Rapid rotation flag" not in text
    old = _plan("-Session", "PreOpen", "-WithGex", "-WithBonds")
    assert old.count("GEX (stored chains)") == 1 and old.count("Bond macro + calendar") == 1


def test_now_starts_a_manual_run_at_once_and_shows_the_readiness_report_first():
    text = _plan("-Now")
    assert "start window   : NOW (manual run)" in text
    assert "READINESS" in text
