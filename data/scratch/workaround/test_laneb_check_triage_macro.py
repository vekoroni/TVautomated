"""AVS-MACRO-TRIAGE-001 T5 (ACK 20 Nov 2026): check_triage.py `macro` check, WARN only, never FAIL.

For each triage row whose ledger_id is in the board macro context (triage_macro_context_<session>.csv): the first word
of money_tag equals the file's money_tag; macro_sector_agreement starts with the file's agreement word; macro_kill_switch
carries the file's kill level. A hand-typed or stale value is a WARN with the file's value beside it. A missing file is
one WARN saying the board context was not available; a context behind the latest board build is a WARN.

Run (PowerShell, repo root):
    venv\\Scripts\\python.exe -m pytest data\\scratch\\workaround\\test_laneb_check_triage_macro.py -q -p no:cacheprovider --basetemp=%TEMP%\\avs_ctm
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_triage  # noqa: E402
from test_laneb_check_triage import LEGACY_COLS, SESSION, lab_handoff, legacy_row, write  # noqa: E402

MACRO_COLS = ["money_tag", "macro_sector_agreement", "macro_scenario_ids", "macro_kill_switch", "sector_check"]
BUILT = "2026-11-12T12:05:00+00:00"
CONTEXT = [
    {"ledger_id": f"{SESSION}_AAA_CALL", "ticker": "AAA", "money_tag": "WITH",
     "macro_sector_agreement": "AGREE: measured LEAN_IN (MEASURED), packet LEAN_IN (LLM macro packet)",
     "macro_kill_switch": f"measured LEAN IN on XLK void below 205.30 (sma50; MORNING build {BUILT})",
     "board_built_at_utc": BUILT},
    {"ledger_id": f"{SESSION}_CPNG_PUT", "ticker": "CPNG", "money_tag": "MIXED",
     "macro_sector_agreement": "PARTIAL: measured NEUTRAL (MEASURED), packet AVOID (LLM macro packet)",
     "macro_kill_switch": f"no measured kill level on XLY: no clear relative-performance read (MORNING build {BUILT})",
     "board_built_at_utc": BUILT},
]


def _context(folder: Path, rows=CONTEXT, built=BUILT) -> None:
    write(folder / f"triage_macro_context_{SESSION}.csv", list(rows[0]), rows)
    (folder / f"triage_macro_context_{SESSION}.json").write_text(json.dumps({"board": {"built_at_utc": built}}), encoding="utf-8")


def _intel(tmp_path: Path, built=BUILT) -> Path:
    p = tmp_path / "etf_intelligence_latest.json"
    p.write_text(json.dumps({"meta": {"built_at_utc": built}}), encoding="utf-8")
    return p


def _row(ticker, side, contract, quote, half, level, **macro):
    r = legacy_row(1 if ticker == "AAA" else 2, ticker, side, contract, quote, half, level)
    r.update(macro)
    return r


AAA_OK = dict(money_tag="WITH (board: XLK outperforming, packet agrees)", macro_sector_agreement="AGREE (measured and packet)",
              macro_kill_switch="XLK void below 205.30")
CPNG_OK = dict(money_tag="MIXED: stock-specific", macro_sector_agreement="PARTIAL", macro_kill_switch="no measured kill level")


def _run(tmp_path, capsys, rows, *, context=True, intel_built=BUILT):
    folder = lab_handoff(tmp_path)
    if context:
        _context(folder)
    tri = tmp_path / "triage"
    write(tri / f"batch1_triage_{SESSION}.csv", LEGACY_COLS + MACRO_COLS, rows)
    code = check_triage.main(["--folder", str(folder), "--triage-folder", str(tri), "--session", SESSION,
                              "--context", str(tmp_path / "none.json"), "--macro-intelligence", str(_intel(tmp_path, intel_built))])
    out = capsys.readouterr().out
    return code, out, out.split("## Notes")[0]


def test_macro_columns_taken_from_the_board_context_raise_no_line(tmp_path, capsys):
    _, out, head = _run(tmp_path, capsys, [_row("AAA", "CALL", "AAA270115C00090000", "3.80/4.00 OI 817", "103.674", "107.9199", **AAA_OK),
                                           _row("CPNG", "PUT", "CPNG270219P00017000", "1.86/2.23 OI 161", "10.9258", "10.9258", **CPNG_OK)])
    assert " macro:" not in head and "board macro context" not in head
    assert "macro: 2 of 2 rows match the board macro context" in out


def test_a_hand_typed_money_tag_is_a_warn_with_the_boards_value_never_a_fail(tmp_path, capsys):
    code, out, head = _run(tmp_path, capsys, [_row("AAA", "CALL", "AAA270115C00090000", "3.80/4.00 OI 817", "103.674", "107.9199",
                                                    **dict(AAA_OK, money_tag="MIXED (XLF +0.4% pre-market; macro RISK_OFF)"))])
    warn = head.split("## WARN")[1]
    assert "AAA macro: money_tag MIXED vs board WITH" in warn
    assert "money_tag" not in head.split("## WARN")[0], "the macro check never FAILs"


def test_agreement_and_kill_switch_that_do_not_carry_the_boards_values_are_warns(tmp_path, capsys):
    _, out, head = _run(tmp_path, capsys, [_row("AAA", "CALL", "AAA270115C00090000", "3.80/4.00 OI 817", "103.674", "107.9199",
                                                money_tag="WITH", macro_sector_agreement="MIXED",
                                                macro_kill_switch="VIX 25.46 backwardated; HY OAS 3.43")])
    assert "macro_sector_agreement MIXED vs board AGREE" in head and "macro_kill_switch lacks the board level 205.30" in head


def test_a_missing_context_file_is_one_warn_saying_the_board_context_was_not_available(tmp_path, capsys):
    code, out, head = _run(tmp_path, capsys, [_row("AAA", "CALL", "AAA270115C00090000", "3.80/4.00 OI 817", "103.674", "107.9199", **AAA_OK)],
                           context=False)
    assert head.count("board macro context was not available") == 1
    assert "board macro context was not available" in head.split("## WARN")[1]      # a WARN, not a FAIL
    assert "macro_kill_switch" not in head


def test_a_context_behind_the_latest_board_build_is_a_warn(tmp_path, capsys):
    _, out, head = _run(tmp_path, capsys, [_row("AAA", "CALL", "AAA270115C00090000", "3.80/4.00 OI 817", "103.674", "107.9199", **AAA_OK)],
                        intel_built="2026-11-12T14:00:00+00:00")
    assert "board macro context is from the build of 2026-11-12T12:05:00+00:00" in head and "avs_day.ps1 board" in head


def test_a_triage_row_whose_ledger_id_is_not_in_the_context_is_named(tmp_path, capsys):
    _, out, head = _run(tmp_path, capsys, [_row("CCC", "CALL", "CCC270115C00045000", "3.80/4.00 OI 817", "48", "50", **AAA_OK)])
    assert "not in the board macro context: CCC" in head
