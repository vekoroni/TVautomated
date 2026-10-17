"""X17-02 (ACK, 17 Oct 2026, Action C): the triage checker enforces the 16 Oct spread gate.

The 16 Oct triage task writes contract_spread_pct and must not name a contract over 25% of mid (W16-02); otherwise the
next strike or expiry that passes. check_triage.py did not look at it, so a triage that skipped the gate passed.

Business rules:
- A trade_contract over 25% of mid is a WARN the deep dive must answer.
- A triage without the contract_spread_pct column is a WARN (the gate was not applied).
- Within the gate, nothing is raised. Percent (25) and fraction (0.25) are both read.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "data" / "scratch" / "workaround" / "check_triage.py"
SESSION = "2026-10-19"


def _run(tmp_path: Path, spreads: dict[str, object] | None) -> str:
    folder = tmp_path / "split"
    folder.mkdir()
    pd.DataFrame([{"ticker": "AAA", "ledger_id": "L-AAA", "batch": "1", "best_contract": "AAA261218P00010000",
                   "best_contract_checked": "AAA261218P00010000"},
                  {"ticker": "BBB", "ledger_id": "L-BBB", "batch": "1", "best_contract": "BBB261218C00020000",
                   "best_contract_checked": "BBB261218C00020000"}]).to_csv(folder / "handoff.csv", index=False)
    rows = []
    for i, (t, c, side) in enumerate([("AAA", "AAA261218P00010000", "PUT"), ("BBB", "BBB261218C00020000", "CALL")], 1):
        r = {"deep_mine_rank": str(i), "ticker": t, "ledger_id": f"L-{t}", "side": side, "trigger": "x", "kill": "x",
             "trade_contract": c, "pays_at_half_target": "Y", "earnings_tastytrade": "", "cluster": "", "main_challenge": "x",
             "rank_reason": "x", "decision": "", "decision_reason": "", "contract_taken": "", "entry_type": "",
             "entry_premium": ""}
        if spreads is not None:
            r["contract_spread_pct"] = spreads[t]
        rows.append(r)
    pd.DataFrame(rows).to_csv(folder / f"batch1_triage_{SESSION}.csv", index=False)
    (folder / f"deep_dive_prompts_{SESSION}.md").write_text(
        "".join(f"## {i} {t}\nsession {SESSION} {folder}\n" for i, t in [(1, "AAA"), (2, "BBB")]), encoding="utf-8")
    subprocess.run([sys.executable, str(TOOL), "--folder", str(folder), "--session", SESSION], cwd=tmp_path,
                   capture_output=True, text=True)
    return (folder / f"check_triage_{SESSION}.md").read_text(encoding="utf-8")


def test_a_contract_over_25pct_of_mid_is_a_warning(tmp_path):
    report = _run(tmp_path, {"AAA": "31.5", "BBB": "12"})
    assert "AAA: trade_contract spread 31.5% of mid is over the 25% gate" in report
    assert "BBB: trade_contract spread" not in report


def test_a_fraction_is_read_the_same_way(tmp_path):
    report = _run(tmp_path, {"AAA": "0.30", "BBB": "0.10"})
    assert "AAA: trade_contract spread 30.0% of mid is over the 25% gate" in report


def test_a_triage_without_the_spread_column_is_a_warning(tmp_path):
    assert "contract_spread_pct column is missing" in _run(tmp_path, None)


def test_a_missing_value_on_a_row_is_a_warning(tmp_path):
    assert "BBB: contract_spread_pct is empty" in _run(tmp_path, {"AAA": "10", "BBB": ""})
