"""Monetisability at the valued level (ACK 6-7 Oct 2026: "#3 ... no longer drives strikes or monetisability";
"carry on with monetisability").

Run 20261006_060401: monetisability valued every contract at the legacy target chain (target_spot / target_price /
structural_target = the prior 40-bar range extreme) while the anticipated move valued it at the governing setup's
anticipated level; 33 of 51 GOs showed NOT_MONETISABLE beside PAYS, and the field was labelled a "structural
target" when it was a range extreme (R6).
Business rules:
- Monetisability values the contract at anticipated_level_q50 - the level the decision values at - and records the
  basis. It is an expiry-intrinsic measure (role AUDIT in the field-role registry), not the pays verdict.
- No anticipated level: DATA_MISSING / ANTICIPATED_LEVEL_MISSING - never a fallback to the range extreme.
- The output names say what was measured: monetisability_target_spot + monetisability_target_basis.
- The EOD engine computes monetisability after the anticipated move, from the candidate's anticipated level.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from contracts.selected_contract_economics import evaluate_long_option_monetisability

ROOT = Path(__file__).resolve().parents[1]


def _hydrated(strike, ask, symbol="HPQ261120C00035000"):
    return {"selected_structure_hydration_status": "COMPLETE", "selected_structure": "LONG_SINGLE",
            "selected_structure_id": "ECI1:test", "selected_contract_symbol": symbol,
            "selected_quote_timestamp_utc": "2026-10-05T20:00:00Z", "selected_quote_snapshot_id": "S",
            "selected_long_leg": {"symbol": symbol, "bid": ask - 0.05, "ask": ask, "strike": strike}}


def test_the_contract_is_valued_at_the_anticipated_level_not_the_range_extreme():
    row = {"canonical_direction": "CALL", "anticipated_level_q50": 38.49, "target_spot": 36.23,
           "target_price": 36.23, "structural_target": 36.23}
    out = evaluate_long_option_monetisability(row, _hydrated(35.0, 1.0))
    assert out["monetisability_target_spot"] == pytest.approx(38.49)
    assert out["monetisability_target_basis"] == "ANTICIPATED_LEVEL_Q50"
    assert out["monetisability_target_profit_pct"] == pytest.approx((38.49 - 35.0 - 1.0) / 1.0 * 100, abs=1e-3)
    assert "monetisability_structural_target_spot" not in out


def test_no_anticipated_level_is_data_missing_never_the_range_extreme():
    row = {"canonical_direction": "CALL", "target_spot": 36.23, "structural_target": 36.23}
    out = evaluate_long_option_monetisability(row, _hydrated(35.0, 1.0))
    assert out["monetisability_state"] == "DATA_MISSING"
    assert out["monetisability_reason"] == "ANTICIPATED_LEVEL_MISSING"


def test_the_eod_engine_values_at_the_candidates_anticipated_level():
    from eod_candidate_engine import _eod_selected_contract_monetisability as mon
    row = {"ticker": "HPQ", "contract_symbol": "HPQ261120C00035000", "contract_bid": 0.95, "contract_ask": 1.0,
           "contract_strike": 35.0, "contract_quote_timestamp_utc": "2026-10-05T20:00:00Z",
           "selected_quote_dataset_id": "S", "target_spot": 36.23}
    out = mon(row, "CALL", 38.49)
    assert out["monetisability_target_spot"] == pytest.approx(38.49)
    assert mon(row, "CALL", None)["monetisability_reason"] == "EOD_ASK_STRIKE_OR_ANTICIPATED_LEVEL_MISSING"


def test_the_eod_engine_computes_monetisability_after_the_anticipated_move():
    src = (ROOT / "eod_candidate_engine.py").read_text(encoding="utf-8")
    assert src.index("candidate.update(anticipated_move_fields(") < src.index("eod_monetisability = _eod_selected_contract_monetisability(")
    assert "monetisability_structural_target_spot" not in src
