"""N1 (Lab data validation, 3 Oct 2026; ACK "fix N1 next"): Morning GO requires a GO-eligible trigger.

Defect: GO was the Morning gate's fall-through. Any row not invalidated, with a quotable contract and
no flag, became GO; trigger state and the EOD candidate status were never checked. Run 20261001_211641:
192 of 347 Morning GO verdicts had no eligible trigger (139 REPAIR_AT_OPEN, 53 WATCH_ONLY), XLF among them.

Business rules:
- GO needs a GO-eligible trigger (trigger_go_eligible, owned upstream by the trigger layer).
- An EOD WATCH_ONLY candidate is never GO in the Morning; it stays visible as watch-only.
- A missing trigger eligibility is not eligibility (R1): stated, not GO.
- Rank, don't gate: such rows are FLAG with a stated reason and remain in the book.
- A contract-repair candidate with an eligible trigger and a passing repaired contract may still be GO.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_morning_gate_authority import _gate, _row  # existing harness (a GO row)


def test_row_with_an_eligible_trigger_is_go():
    out = _gate(_row(trigger_go_eligible=True, trigger_primary="VOL_COMPRESSION", candidate_status="TRIGGER_REQUIRED"))
    assert out["verdict"] == "GO"


def test_no_eligible_trigger_is_flagged_awaiting_trigger():
    out = _gate(_row(trigger_go_eligible=False, trigger_primary="NONE", candidate_status="REPAIR_AT_OPEN"))
    assert out["verdict"] == "FLAG"
    assert out["morning_execution_permission"] == "AWAITING_TRIGGER"
    assert out["morning_entry_action"] == "NO_TRADE"
    assert "NONE" in out["morning_unlock_condition"]


def test_missing_trigger_eligibility_is_not_eligibility():
    row = _row(candidate_status="TRIGGER_REQUIRED")
    row.pop("trigger_go_eligible", None)          # the shared fixture now carries an eligible trigger
    out = _gate(row)
    assert out["verdict"] == "FLAG"
    assert out["morning_execution_permission"] == "AWAITING_TRIGGER"
    assert "TRIGGER_ELIGIBILITY_NOT_RECORDED" in out["flag_reason"]


def test_watch_only_candidate_is_never_go():
    out = _gate(_row(trigger_go_eligible=True, trigger_primary="VOL_COMPRESSION", candidate_status="WATCH_ONLY"))
    assert out["verdict"] == "FLAG"
    assert out["morning_execution_permission"] == "WATCH_ONLY"


def test_repair_candidate_with_eligible_trigger_can_be_go():
    out = _gate(_row(trigger_go_eligible=True, trigger_primary="RANGE_BREAK_EARLY", candidate_status="REPAIR_AT_OPEN"))
    assert out["verdict"] == "GO"
