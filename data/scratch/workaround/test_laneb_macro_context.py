"""AVS-MACRO-TRIAGE-001 T3 (ACK 20 Nov 2026): avs_day.ps1 points the triage at the board macro context.

today_context.json carries macro_context (the per-name file in the hand-off folder), macro_context_built (the board
build it came from), macro_context_note (MATCH / OLDER_BUILD / NEWER_BUILD against the session) and
macro_context_current (False when the board was rebuilt after it). The packs, evening and board steps run the join;
status says when it is missing or behind the board. The script runs from a copy in a temporary repo tree, so no live
file is read or written.

Run (PowerShell, repo root):
    venv\\Scripts\\python.exe -m pytest data\\scratch\\workaround\\test_laneb_macro_context.py -q -p no:cacheprovider --basetemp=%TEMP%\\avs_mc
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "avs_day.ps1"
SESSION, RUN = "2026-11-20", "20261120_000537"

pytestmark = pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="needs Windows PowerShell")


def _tree(tmp_path: Path, *, context_built: str | None, board_built: str = "2026-11-20T12:05:00+00:00") -> Path:
    w = tmp_path / "data" / "scratch" / "workaround"
    w.mkdir(parents=True)
    shutil.copy(SCRIPT, w / "avs_day.ps1")
    run = tmp_path / "data" / "output" / "runs" / RUN
    run.mkdir(parents=True)
    (run / "final_run_manifest.json").write_text("{}", encoding="utf-8")
    hand = w / "handoff" / f"lab_{SESSION}"
    hand.mkdir(parents=True)
    (hand / "handoff.csv").write_text("lb_order,lb_batch,lb_ledger_id,ticker\n1,1,L1,AAPL\n", encoding="utf-8")
    (hand / "receipt.json").write_text(json.dumps({"run_id": RUN, "session": SESSION, "lab_revision": "abc"}), encoding="utf-8")
    if context_built:
        (hand / f"triage_macro_context_{SESSION}.csv").write_text("ledger_id,money_tag\nL1,WITH\n", encoding="utf-8")
        (hand / f"triage_macro_context_{SESSION}.json").write_text(json.dumps(
            {"handoff": {"built_at_utc": "2026-11-20T10:43:00Z"},
             "board": {"build_kind": "MORNING", "built_at_utc": context_built},
             "board_session_note": "MATCH", "changed_money_tag": 3}), encoding="utf-8")
    board = tmp_path / "macro_board" / "output"
    board.mkdir(parents=True)
    (board / "etf_macro_board.html").write_text(f'<script>const BOARD={{"built_at_utc":"{board_built}"}}</script>',
                                                encoding="utf-8")
    return w


def _status(w: Path) -> tuple[dict, str]:
    out = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(w / "avs_day.ps1"),
                          "status"], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
    return json.loads((w / "today_context.json").read_text(encoding="utf-8-sig")), out.stdout


def test_today_context_points_at_the_macro_context_and_the_build_it_came_from(tmp_path):
    ctx, text = _status(_tree(tmp_path, context_built="2026-11-20T12:05:00+00:00"))
    assert ctx["macro_context"] == f"data\\scratch\\workaround\\handoff\\lab_{SESSION}\\triage_macro_context_{SESSION}.csv"
    assert ctx["macro_context_built"] == "2026-11-20T12:05:00+00:00" and ctx["macro_context_note"] == "MATCH"
    assert ctx["macro_context_current"] is True
    assert "No board macro context" not in text and "Board macro context is from" not in text


def test_status_says_when_the_board_was_rebuilt_after_the_macro_context(tmp_path):
    ctx, text = _status(_tree(tmp_path, context_built="2026-11-19T23:42:49+00:00"))
    assert ctx["macro_context_current"] is False
    assert "avs_day.ps1 board" in text and "2026-11-19T23:42:49+00:00" in text


def test_a_missing_macro_context_is_null_and_status_says_how_to_build_it(tmp_path):
    ctx, text = _status(_tree(tmp_path, context_built=None))
    assert ctx["macro_context"] is None and ctx["macro_context_built"] is None
    assert "No board macro context" in text and "avs_day.ps1 packs" in text


def _block(name: str) -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    m = re.search(rf"\n    '{name}' \{{\n(.*?)\n    \}}\n", text, flags=re.S)
    assert m, name
    return m.group(1)


def test_the_packs_evening_and_board_steps_run_the_join_before_rewriting_the_context():
    packs, board, evening = _block("packs"), _block("board"), _block("evening")
    assert packs.index("Invoke-MacroContext") < packs.rindex("Write-Context")
    assert board.index("Run-MacroBoard.ps1") < board.index("Invoke-MacroContext") < board.rindex("Write-Context")
    assert evening.index("build_lab_handoff.py") < evening.index("Invoke-MacroContext")
    assert "changed money_tag" in board                                   # the refreshed case reports the changes
    assert board.index("was not refreshed") < board.index("re-tag money for every triaged name")   # by hand only if it failed
    assert "-m macro_board.triage_context --handoff" in SCRIPT.read_text(encoding="utf-8")
