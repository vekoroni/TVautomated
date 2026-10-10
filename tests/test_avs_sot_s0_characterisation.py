"""S0 characterisation (source-of-truth programme, ACK 6 Oct 2026, "start S0 and S1").

These tests PIN TODAY'S BEHAVIOUR before anything changes (CLAUDE.md: legacy behaviour being changed is pinned by a
characterisation test first). Several pinned behaviours are known defects or are about to change by an approved ACK
decision. Each test names the S2 change that will flip it; that change must update the test in the same commit and
say why. Reference run: 20261006_060401 (frozen: Enhancements/assessment/AVS_LAB_SOURCE_OF_TRUTH_20261006/s0).

Pinned today:
- Morning gate: FLIPPED by E12 (6 Oct) - a NOT_COMPUTED or volatility-only option value is now an option-review FLAG;
  DOES_NOT_PAY_AT_ANTICIPATED_TIME keeps its own FLAG.                                     (E12 done)
- Lab rank score: moves with retired R:R (rr_options_reachable) and ignores the anticipated value.  -> flips with E11
- Execution-gate CSV: FIXED by H1 (6 Oct) - the header is the union of all rows; no column is dropped.
- EOD monetisability: FLIPPED (7 Oct) - valued at the anticipated level, never the legacy range extreme; a missing
  level is labelled DATA_MISSING, never valued at 0.0 (H6 contained).
- Lab book: target_price and structural_target resolve the same inputs in opposite order.          -> H4
"""
from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from test_morning_gate_authority import _gate, _row  # noqa: E402


def _go_row(**kw):
    return _row(trigger_go_eligible=True, trigger_primary="VOL_COMPRESSION", candidate_status="TRIGGER_REQUIRED",
                trade_lane="A", **kw)


# --- Morning gate: missing option value (E12) -------------------------------------------------------------------

@pytest.mark.parametrize("state", ["NOT_COMPUTED", "NOT_ASSESSED_VOLATILITY_ONLY"])
def test_e12_flipped_a_go_now_needs_a_computed_option_value(state):
    """Flipped by E12 (ACK 6 Oct 2026): these were GO; they are now an option-review FLAG
    (tests/test_avs_e12_option_review.py states the rule)."""
    assert _gate(_go_row(anticipated_pays_state=state))["verdict"] == "FLAG"


def test_today_only_does_not_pay_withholds_go():
    out = _gate(_go_row(anticipated_pays_state="DOES_NOT_PAY_AT_ANTICIPATED_TIME"))
    assert out["verdict"] == "FLAG"


# --- Lab rank score (RC3 / E11) ------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def lab():
    spec = importlib.util.spec_from_file_location("intelligence_lab_s0_characterisation",
                                                  ROOT / "intelligence-lab" / "intelligence_lab.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = {"options_verdict": "EXECUTE", "campaign_verdict": "READY_EXECUTE", "execution_verdict": "BUY_NOW",
        "eil_composite_score": 60, "options_score": 60, "wbs__wbs": 50}


def test_today_the_lab_rank_score_moves_with_retired_rr(lab):
    """E11 (approved approach, 6 Oct): the rank will stop using R:R; update this test in S4."""
    low = lab._compute_priority_score({**BASE, "rr_options": 0.5, "rr_options_reachable": 0.5})
    high = lab._compute_priority_score({**BASE, "rr_options": 3.0, "rr_options_reachable": 3.0})
    assert high > low


def test_today_the_lab_rank_score_ignores_the_anticipated_value(lab):
    poor = lab._compute_priority_score({**BASE, "anticipated_value_multiple_q50": 0.6,
                                        "anticipated_pays_state": "DOES_NOT_PAY_AT_ANTICIPATED_TIME"})
    rich = lab._compute_priority_score({**BASE, "anticipated_value_multiple_q50": 2.3,
                                        "anticipated_pays_state": "PAYS"})
    assert poor == rich


# --- H1: execution-gate CSV header from the first row ----------------------------------------------------------------

def test_h1_fixed_the_execution_gate_csv_keeps_every_column(tmp_path):
    """Flipped by H1 (6 Oct 2026): run 20261006_060401 lost 71 columns because the header came from the first row.
    The saved file now carries every column any row has, and each row's own values."""
    import execution_gate
    out = tmp_path / "gated.csv"
    execution_gate._write_csv(out, [{"ticker": "AAA", "final_action": "BUY_NOW"},
                                    {"ticker": "BBB", "final_action": "WAIT", "entry_premium": 1.72}])
    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == ["ticker", "final_action", "entry_premium"]
    assert rows[0]["entry_premium"] == "" and rows[1]["entry_premium"] == "1.72"


# --- EOD monetisability: legacy target, missing target labelled ------------------------------------------------------

def _hl_like(**kw):
    row = {"ticker": "HL", "contract_symbol": "HL261218P00017000", "contract_bid": 1.60, "contract_ask": 1.72,
           "contract_strike": 17.0, "contract_quote_timestamp_utc": "2026-10-05T20:00:00Z",
           "selected_quote_dataset_id": "S0-CHARACTERISATION"}
    row.update(kw)
    return row


def test_monetisability_flipped_to_the_anticipated_level():
    """Flipped by the monetisability change (ACK 6-7 Oct 2026): it was valued at the legacy target_spot (the range
    extreme, 16.34 for HL) and blind to the anticipated level; it now values at anticipated_level_q50
    (tests/test_avs_monetisability_anticipated_level.py states the rule)."""
    from eod_candidate_engine import _eod_selected_contract_monetisability as mon
    out = mon(_hl_like(target_spot=16.34), "PUT", 15.95)
    assert out.get("monetisability_target_spot") == pytest.approx(15.95)
    assert mon(_hl_like(target_spot=16.34), "PUT")["monetisability_state"] == "DATA_MISSING"


def test_a_missing_target_is_labelled_data_missing_never_valued_at_zero():
    from eod_candidate_engine import _eod_selected_contract_monetisability as mon
    out = mon(_hl_like(), "PUT")
    assert out["monetisability_state"] == "DATA_MISSING"
    assert out["monetisability_reason"] == "EOD_ASK_STRIKE_OR_ANTICIPATED_LEVEL_MISSING"


# --- H4: opposite target precedence in the Lab book ------------------------------------------------------------------

def test_today_the_lab_book_resolves_its_two_target_fields_in_opposite_order():
    """H4: with both a wall price and a structural target present, the two published fields disagree."""
    from contracts.lab_control import opportunity_book_row
    sig = {"ticker": "XYZ", "direction": "CALL", "lab_verdict": "GO", "wbs__wall_price": 50.0,
           "structural_target": 45.0}
    row = opportunity_book_row(sig, "20261006_060401", 1)
    assert row["target_price"] == pytest.approx(50.0)               # wall price first
    assert row["structural_target"] == pytest.approx(45.0)          # structural first
