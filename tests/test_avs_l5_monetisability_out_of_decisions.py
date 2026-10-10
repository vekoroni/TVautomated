"""L5 (ACK 7 Oct 2026, "1 = follow recommendation") and A7 ("7 = follow recommendation").

Monetisability (intrinsic value at expiry, no time value) is an AUDIT measure (approved field-role registry). It used to
decide three things: the EOD Lab GO -> CONTRACT_REPAIR economics lock, the pre-trade focus lane and the opportunity
tier - so a trade the anticipated move says PAYS (22 GOs on run 20261006 after the level fix) could be demoted by a
measure that ignores time value. The decision owner is the anticipated move's pays state, computed for the contract.
Business rules:
- Economics are comparable when the anticipated value was computed for the exact selected contract; otherwise the
  existing lock applies with a reason that says so. Monetisability no longer drives it.
- The focus lane and the tier read anticipated_pays_state: PAYS / DOES_NOT_PAY_AT_ANTICIPATED_TIME / not computed.
- A7: a quote from a different session than the evidence is an aged quote, not a conflict - only the exact-contract
  identity (symbol + quote dataset) is checked.
- The EOD engine and the Morning swap record which contract the anticipated value was computed for.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYMBOL = "TEST261120C00100000"


# --- Lab economics identity ------------------------------------------------------------------------------------------

def _sig(**kw):
    sig = {"ticker": "TEST", "direction": "CALL", "canonical_direction": "CALL", "selected_structure": "LONG_SINGLE",
           "anticipated_pays_state": "PAYS", "anticipated_contract_symbol": SYMBOL,
           "monetisability_status": "FAILED", "monetisability_contract_symbol": ""}
    sig.update(kw)
    return sig


def test_economics_are_comparable_when_the_anticipated_value_was_computed_for_the_selected_contract():
    from contracts.lab_control import _economics_identity
    out = _economics_identity(_sig(), selected_contract=SYMBOL)
    assert out["economics_comparable"] is True and out["economics_mismatch_reason"] == ""


def test_no_anticipated_value_or_a_different_contract_is_stated():
    from contracts.lab_control import _economics_identity
    missing = _economics_identity(_sig(anticipated_pays_state="NOT_COMPUTED"), selected_contract=SYMBOL)
    assert missing["economics_comparable"] is False
    assert missing["economics_mismatch_reason"] == "ANTICIPATED_VALUE_NOT_COMPUTED_FOR_SELECTED_CONTRACT"
    other = _economics_identity(_sig(anticipated_contract_symbol="TEST261120C00105000"), selected_contract=SYMBOL)
    assert other["economics_mismatch_reason"] == "ANTICIPATED_VALUE_CONTRACT_MISMATCH"


# --- pre-trade focus lane ----------------------------------------------------------------------------------------------

def _focus_row(**kw):
    row = {"ticker": "TEST", "direction": "CALL", "signal_price": 100, "invalidation_state": "AVAILABLE",
           "invalidation_spot": 95, "target_state": "AVAILABLE", "target_price": 110, "contract_symbol": SYMBOL,
           "contract_bid": 4.5, "contract_ask": 4.7, "contract_dte": 60,
           "selected_quote_timestamp_utc": "2026-09-18T20:00:00Z", "selected_quote_dataset_id": "q1",
           "monetisability_quote_snapshot_id": "q1", "monetisability_contract_symbol": SYMBOL,
           "evidence_session_date": "2026-09-18", "monetisability_state": "NOT_MONETISABLE",
           "anticipated_pays_state": "PAYS", "contract_repair_required": "FALSE", "contract_repair_status": "CONTRACT_OK",
           "trigger_go_eligible": "TRUE", "direction_conflict_status": "NO_CONFLICT"}
    row.update(kw)
    return row


def test_the_focus_lane_follows_the_pays_state_not_monetisability():
    from domain.pretrade_focus import FOCUS_PRIMARY, project_pretrade_focus
    assert project_pretrade_focus(_focus_row())["pretrade_focus_lane"] == FOCUS_PRIMARY
    no_pay = project_pretrade_focus(_focus_row(anticipated_pays_state="DOES_NOT_PAY_AT_ANTICIPATED_TIME"))
    assert no_pay["pretrade_focus_lane"] == "WATCH_MOVE_DOES_NOT_PAY"
    unknown = project_pretrade_focus(_focus_row(anticipated_pays_state="NOT_COMPUTED"))
    assert unknown["pretrade_focus_lane"] == "OPTION_VALUE_REVIEW"


def test_a7_a_prior_session_quote_is_not_an_evidence_conflict():
    from domain.pretrade_focus import project_pretrade_focus
    aged = project_pretrade_focus(_focus_row(selected_quote_timestamp_utc="2026-09-17T20:00:00Z"))
    assert aged["pretrade_contract_evidence_state"] == "COMPLETED_SESSION_QUOTE_OBSERVED"
    wrong = project_pretrade_focus(_focus_row(monetisability_contract_symbol="TEST261120C00105000"))
    assert wrong["pretrade_contract_evidence_state"] == "CONTRACT_EVIDENCE_CONFLICT_REVIEW"   # identity still checked


# --- opportunity tier ----------------------------------------------------------------------------------------------------

def test_the_tier_follows_the_pays_state_not_monetisability():
    from contracts.opportunity_tier import WATCH, derive_tier
    base = {"canonical_direction": "CALL", "governed_direction_record_sha256": "a" * 64,
            "invalidation_state": "AVAILABLE", "invalidation_price": 95.0, "structural_target": 115.0,
            "rr_underlying": 3.0, "monetisability_state": "NOT_MONETISABLE",
            "monetisability_state_timevalue": "NOT_MONETISABLE", "anticipated_pays_state": "PAYS",
            "spread_pct": 0.10, "spread_unit": "FRACTION_OF_MID", "time_horizon": "1_5d", "contract_dte": 14.0,
            "planned_hold_sessions": 5.0, "execution_viability_state": "EXECUTABLE_QUOTE",
            "trigger_state": "TRIGGER_READY", "contract_repair_status": "CONTRACT_OK", "final_action": "MANUAL_REVIEW"}
    assert derive_tier(base)[0] != WATCH
    tier, reason = derive_tier({**base, "anticipated_pays_state": "DOES_NOT_PAY_AT_ANTICIPATED_TIME"})
    assert tier == WATCH and reason == "EQUITY_VALID_OPTION_DOES_NOT_PAY_NO_PROMOTER"
    assert derive_tier({**base, "anticipated_pays_state": "NOT_COMPUTED"})[1] == "OPTION_VALUE_NOT_COMPUTED_AWAITING_RE_RESOLUTION"


# --- the valued contract is recorded --------------------------------------------------------------------------------------

def test_the_valued_contract_is_recorded():
    eod = (ROOT / "eod_candidate_engine.py").read_text(encoding="utf-8")
    mg = (ROOT / "morning_gate.py").read_text(encoding="utf-8")
    assert 'candidate["anticipated_contract_symbol"]' in eod
    assert 'out["anticipated_contract_symbol"] = symbol' in mg


def test_a_paying_row_stays_comparable_through_the_lab_book():
    """The book row - not only the signal - must carry the valued contract (found by the fixture update, 7 Oct)."""
    from contracts.lab_control import FINAL_BOOK_FIELDS, opportunity_book_row
    sig = {"ticker": "TEST", "direction": "CALL", "canonical_direction": "CALL", "lab_verdict": "GO",
           "contract_symbol": SYMBOL, "selected_structure": "LONG_SINGLE", "anticipated_pays_state": "PAYS",
           "anticipated_contract_symbol": SYMBOL, "monetisability_status": "FAILED"}
    row = opportunity_book_row(sig, "RUN", 1)
    assert "anticipated_contract_symbol" in FINAL_BOOK_FIELDS and row["anticipated_contract_symbol"] == SYMBOL
    assert row["economics_comparable"] is True and row["lab_verdict"] != "CONTRACT_REPAIR"
