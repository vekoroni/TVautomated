"""Opportunity-book integrity leftovers from E3-E7: defects L1, L2, L3.

Business rules (DQ-1 ... DQ-3; design rules R1 "missing is never neutral",
R2 "one owner per fact", R6 "labels say what was measured"):

* L1  Every contract-describing field written to the book describes the
      contract written in ``contract_symbol`` of the same row, or it is missing
      and the reason is recorded. After the Lab reselects a contract for the
      direction, or removes a wrong-side contract, nothing that describes the
      original contract (its morning selection, morning/current quotes, quote
      lineage, hydrated legs, exact-contract lifecycle, execution viability,
      DTE, premium economics) is published as if it described the row's
      contract; downstream readers that fall back to
      ``morning_selected_contract_symbol`` cannot restore it. A morning contract
      repair that cannot observe a field of the replacement contract leaves that
      field missing rather than keeping the previous contract's value.
* L2  An unobserved contract greek (delta, gamma, theta, vega, IV), open
      interest or volume is missing in the EOD candidate book, never 0.0.
      Consumers treat it as missing, not as zero.
* L3  ``CONTRACT_QUOTE_NOT_ESTABLISHED_FOR_RESELECTED_CONTRACT`` reflects the
      final state of the row: present while the reselected contract's own
      two-sided quote is not established, absent once enrichment establishes a
      quote that belongs to the reselected symbol.

Characterisation of the defective behaviour (6 tests, all passing on 8d1e04c
before the fix) is recorded in the commit message; these tests replace it.
"""
from __future__ import annotations

import csv
import json
import math

import pytest

import morning_gate
from contracts.lab_control import opportunity_book_row, write_final_opportunity_book
from tests.test_book_integrity_e3_e4_e5_e7 import CALL_OCC, PUT_OCC, _QUOTE, _manifest, _sig
from tests.test_eod_options_research_handoff import _row as _eod_row

QUOTE_NOT_ESTABLISHED = "CONTRACT_QUOTE_NOT_ESTABLISHED_FOR_RESELECTED_CONTRACT"
SIDE_CONFLICT_STATE = "OPTION_EXPRESSION_REMOVED_CONTRACT_SIDE_CONFLICT"


def _missing(value) -> bool:
    return value is None or value == "" or (isinstance(value, float) and math.isnan(value))


# ─── L1: realistic evidence of the ORIGINAL (morning-selected) contract ─────

def _original_contract_evidence(symbol: str) -> dict:
    """What the morning stage wrote for the contract it selected."""
    return {
        "morning_selected_contract_symbol": symbol,
        "contract_source": "MARKETDATA_LIVE",
        "selected_quote_snapshot_id": "QUOTE1:aaaaaaaaaaaaaaaaaaaaaaaa",
        "selected_quote_timestamp_utc": "2026-09-17T13:45:00+00:00",
        "selected_quote_dataset_id": "MD:2026-09-17T13:45",
        "selected_structure_hydration_status": "COMPLETE",
        "selected_structure_hydration_reason": "",
        "selected_structure_hydration_schema_version": "selected_structure_v1",
        "selected_legs_json": json.dumps([{"symbol": symbol, "bid": 1.0, "ask": 1.1}]),
        "quote_as_of": "2026-09-17T13:45:00+00:00",
        "quote_freshness": "FRESH",
        "morning_contract_bid": 1.0, "morning_contract_ask": 1.1, "morning_contract_mid": 1.05,
        "morning_contract_spread_pct": 9.5, "morning_contract_bid_size": 25,
        "morning_contract_ask_size": 40, "morning_quote_dataset_id": "MD:2026-09-17T13:45",
        "morning_quote_timestamp_utc": "2026-09-17T13:45:00+00:00",
        "current_contract_bid": 1.1, "current_contract_ask": 1.2, "current_contract_mid": 1.15,
        "current_contract_spread_pct": 8.7, "current_contract_bid_size": 30,
        "current_contract_ask_size": 35, "current_quote_dataset_id": "MD:2026-09-17T14:30",
        "current_quote_timestamp_utc": "2026-09-17T14:30:00+00:00",
        "contract_bid_change": 0.1, "contract_bid_change_pct": 0.1, "contract_ask_change": 0.1,
        "contract_ask_change_pct": 0.09, "contract_mid_change": 0.1, "contract_mid_change_pct": 0.095,
        "contract_spread_change_pp": -0.8, "contract_bid_size_change": 5,
        "contract_ask_size_change": -5, "comparison_status": "SAME_CONTRACT",
        "change_status": "SAME_CONTRACT",
        "liquidity_state": "EXECUTABLE_NOW", "executable_now": True,
        "moneyness_state": "ATM", "delta_band": "NEAR_ATM_035_060", "atm_distance_sigma": 0.1,
        "dte_buffer_sessions": 3.0,
        "maturation_state_1d": "MATURE", "maturation_state_2d": "MATURE", "maturation_state_3d": "MATURE",
        "maturation_score_1d": 80, "maturation_score_2d": 82, "maturation_score_3d": 85,
        "liquidity_persistence_status": "PERSISTENT",
        "morning_liquidity_persistence_status": "PERSISTENT",
        "contract_dte": 7.0, "contract_dte_state": "AVAILABLE",
        "selected_contract_economics_ready": True,
        "execution_viability_contract_symbol": symbol,
        "execution_viability_state": "EXECUTABLE", "execution_viability_reason": "WITHIN_POLICY",
        "execution_viability_eligible": True, "execution_viability_reviewable": True,
        "execution_viability_bid": 1.0, "execution_viability_ask": 1.1,
        "execution_viability_spread_pct": 9.5,
        "contract_mark_synthetic": False, "theta_drag_pct": 12.0, "vega_risk_pct": 8.0,
        "theta_constrained": False,
        "ts_expiry_date": "2026-09-18", "ts_dte_remaining_at_stop": 2, "ts_dte_used": 7,
        "contract_selection_reason": "MORNING_EXACT_CONTRACT_REQUOTE",
    }


#: Book fields that describe the row's contract without naming their own symbol.
ORIGINAL_CONTRACT_FIELDS = (
    "morning_selected_contract_symbol", "contract_source",
    "selected_quote_timestamp_utc", "selected_quote_dataset_id",
    "selected_structure_hydration_status", "selected_structure_hydration_reason",
    "selected_structure_hydration_schema_version", "selected_legs_json",
    "quote_as_of", "quote_freshness",
    "morning_contract_bid", "morning_contract_ask", "morning_contract_mid",
    "morning_contract_spread_pct", "morning_contract_bid_size", "morning_contract_ask_size",
    "morning_quote_dataset_id", "morning_quote_timestamp_utc",
    "current_contract_bid", "current_contract_ask", "current_contract_mid",
    "current_contract_spread_pct", "current_contract_bid_size", "current_contract_ask_size",
    "current_quote_dataset_id", "current_quote_timestamp_utc",
    "contract_bid_change", "contract_bid_change_pct", "contract_ask_change",
    "contract_ask_change_pct", "contract_mid_change", "contract_mid_change_pct",
    "contract_spread_change_pp", "contract_bid_size_change", "contract_ask_size_change",
    "comparison_status", "change_status",
    "liquidity_state", "moneyness_state", "delta_band", "atm_distance_sigma",
    "dte_buffer_sessions", "maturation_state_1d", "maturation_state_2d", "maturation_state_3d",
    "maturation_score_1d", "maturation_score_2d", "maturation_score_3d",
    "liquidity_persistence_status", "morning_liquidity_persistence_status",
    "contract_dte", "selected_contract_economics_ready",
    "execution_viability_bid", "execution_viability_ask", "execution_viability_spread_pct",
    "contract_mark_synthetic", "theta_drag_pct", "vega_risk_pct", "theta_constrained",
    "ts_expiry_date", "ts_dte_remaining_at_stop", "ts_dte_used",
)


@pytest.mark.parametrize(
    "direction, original, reselected",
    [("PUT", CALL_OCC, PUT_OCC), ("CALL", "AAPL261016P00095000", "AAPL261016C00105000")],
)
def test_l1_reselected_row_publishes_nothing_that_describes_the_original_contract(
    direction, original, reselected
) -> None:
    sig = _sig(direction, recommended_contract=reselected, **_QUOTE, **_original_contract_evidence(original))
    row = opportunity_book_row(sig, "RUN-BI", 1)
    assert row["contract_symbol"] == reselected
    for field in ORIGINAL_CONTRACT_FIELDS:
        assert _missing(row[field]), f"{field} still describes {original}: {row[field]!r}"
    # A snapshot id is identity of an observed quote; none is established.
    assert row["selected_quote_snapshot_id"] != "QUOTE1:aaaaaaaaaaaaaaaaaaaaaaaa"
    assert _missing(row["selected_quote_snapshot_id"])
    # Exact-contract executability is not established for the reselected symbol.
    assert row["executable_now"] in (False, "False", "")
    assert row["execution_viability_contract_symbol"] == reselected
    assert row["execution_viability_state"] == "DATA_MISSING"
    assert row["execution_viability_reason"] == QUOTE_NOT_ESTABLISHED
    assert row["execution_viability_eligible"] in (False, "False")
    assert row["execution_viability_reviewable"] in (False, "False")
    # Reasons recorded; lineage kept in fields that name their own contract.
    assert row["contract_dte_state"] == "NOT_EVALUATED_CONTRACT_RESELECTED"
    assert QUOTE_NOT_ESTABLISHED in row["lab_coherence_flags"]
    assert row["previous_contract_symbol"] == original
    assert row["contract_selection_reason"].startswith(f"CONTRACT_RESELECTED_FOR_DIRECTION:{original}->{reselected}")


@pytest.mark.parametrize("direction, wrong_symbol", [("PUT", CALL_OCC), ("CALL", PUT_OCC)])
def test_l1_side_conflict_row_publishes_nothing_that_describes_the_removed_contract(
    direction, wrong_symbol
) -> None:
    sig = _sig(direction, **_QUOTE, **_original_contract_evidence(wrong_symbol))
    row = opportunity_book_row(sig, "RUN-BI", 1)
    assert _missing(row["contract_symbol"])
    assert row["contract_data_state"] == SIDE_CONFLICT_STATE
    for field in ORIGINAL_CONTRACT_FIELDS:
        assert _missing(row[field]), f"{field} still describes removed {wrong_symbol}: {row[field]!r}"
    assert _missing(row["selected_quote_snapshot_id"])
    assert _missing(row["execution_viability_contract_symbol"])
    assert row["execution_viability_state"] == "DATA_MISSING"
    assert row["execution_viability_reason"] == SIDE_CONFLICT_STATE
    assert row["contract_dte_state"] == "NOT_APPLICABLE_NO_SELECTED_CONTRACT"
    assert row["previous_contract_symbol"] == wrong_symbol


@pytest.mark.parametrize("direction, symbol", [("CALL", CALL_OCC), ("PUT", PUT_OCC)])
def test_l1_unchanged_contract_keeps_its_own_evidence(direction, symbol) -> None:
    sig = _sig(direction, contract_symbol=symbol, **_QUOTE, **_original_contract_evidence(symbol))
    row = opportunity_book_row(sig, "RUN-BI", 1)
    assert row["contract_symbol"] == symbol
    assert row["morning_selected_contract_symbol"] == symbol
    assert row["morning_contract_ask"] == 1.1
    assert row["current_contract_ask"] == 1.2
    assert row["quote_as_of"] == "2026-09-17T13:45:00+00:00"
    assert row["selected_quote_snapshot_id"] == "QUOTE1:aaaaaaaaaaaaaaaaaaaaaaaa"
    assert row["liquidity_state"] == "EXECUTABLE_NOW"
    assert row["contract_dte"] == 7.0
    assert row["execution_viability_state"] == "EXECUTABLE"
    assert row["theta_drag_pct"] == 12.0


def test_l1_non_directional_row_contract_evidence_is_not_withheld() -> None:
    sig = _sig("STRANGLE", **_original_contract_evidence(CALL_OCC))
    row = opportunity_book_row(sig, "RUN-BI", 1)
    assert row["contract_symbol"] == CALL_OCC
    assert row["morning_selected_contract_symbol"] == CALL_OCC
    assert row["liquidity_state"] == "EXECUTABLE_NOW"


def _write_source(tmp_path, fieldnames: list[str], values: dict) -> None:
    run = tmp_path / "RUN-BI"
    (run / "options").mkdir(parents=True, exist_ok=True)
    with (run / "options" / "options_intelligence_RUN-BI.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(values)


def _book(tmp_path, sig: dict) -> dict:
    return write_final_opportunity_book(
        "RUN-BI", [sig], {"pipeline_mode": "EOD", "fatal_flags": [], "stale_flags": []},
        tmp_path, sync_interpreter=False,
    )["rows"][0]


def test_l1_removed_contract_cannot_return_through_the_doi_projection_or_enrichment(tmp_path) -> None:
    _write_source(
        tmp_path, ["ticker", "contract_symbol", "theta_drag_pct", "contract_mark_synthetic", "ts_expiry_date"],
        {"ticker": "AAPL", "contract_symbol": CALL_OCC, "theta_drag_pct": 44.0,
         "contract_mark_synthetic": "False", "ts_expiry_date": "2026-09-18"},
    )
    row = _book(tmp_path, _sig("PUT", **_original_contract_evidence(CALL_OCC)))
    assert _missing(row["contract_symbol"])
    assert row["contract_data_state"] == SIDE_CONFLICT_STATE
    assert _missing(row["doi_governed_contract_symbol"])
    assert _missing(row["morning_selected_contract_symbol"])
    for field in ("theta_drag_pct", "contract_mark_synthetic", "ts_expiry_date"):
        assert _missing(row[field]), f"{field} of removed contract refilled: {row[field]!r}"


def test_l1_reselected_contract_economics_are_filled_only_from_its_own_symbol(tmp_path) -> None:
    _write_source(
        tmp_path, ["ticker", "contract_symbol", "theta_drag_pct", "vega_risk_pct"],
        {"ticker": "AAPL", "contract_symbol": CALL_OCC, "theta_drag_pct": 44.0, "vega_risk_pct": 9.0},
    )
    row = _book(tmp_path, _sig("PUT", contract_symbol=CALL_OCC, recommended_contract=PUT_OCC))
    assert row["contract_symbol"] == PUT_OCC
    assert _missing(row["theta_drag_pct"])
    assert _missing(row["vega_risk_pct"])


def test_l1_contract_economics_of_the_same_symbol_are_still_enriched(tmp_path) -> None:
    _write_source(
        tmp_path, ["ticker", "contract_symbol", "theta_drag_pct"],
        {"ticker": "AAPL", "contract_symbol": PUT_OCC, "theta_drag_pct": 44.0},
    )
    row = _book(tmp_path, _sig("PUT", contract_symbol=PUT_OCC))
    assert float(row["theta_drag_pct"]) == 44.0


# ─── L1: morning contract repair ────────────────────────────────────────────

_PREVIOUS = "AAA260116C00100000"
_REPLACEMENT = "AAA260116C00105000"


def _previous_contract_row() -> dict:
    return {
        "ticker": "AAA", "direction": "CALL", "contract_symbol": _PREVIOUS,
        "recommended_contract": _PREVIOUS, "signal_price": 100.0,
        "contract_bid": 2.0, "contract_ask": 2.1, "contract_mid": 2.05, "contract_spread_pct": 4.9,
        "contract_delta": 0.52, "contract_gamma": 0.03, "contract_theta": -0.05, "contract_vega": 0.12,
        "contract_iv": 0.31, "contract_oi": 900, "contract_volume": 150,
        "contract_quote_timestamp": "2026-09-16T20:00:00Z", "contract_source": "EOD_CHAIN",
        "contract_bid_size": 25, "contract_ask_size": 40, "contract_quote_quality": "TWO_SIDED",
        "premium_eod": 2.05, "premium": 2.05, "contract_premium": 2.05,
        "breakeven_price": 102.1, "breakeven_pct": 2.1,
    }


def test_l1_morning_repair_never_keeps_the_previous_contracts_unobserved_fields() -> None:
    live = {
        "live_price": 101.0,
        "morning_repair_contract_symbol": _REPLACEMENT,
        "live_contract_bid": 1.0, "live_contract_ask": 1.1, "live_contract_mid": 1.05,
        "live_contract_spread_pct": 9.5, "live_contract_delta": 0.41,
    }
    gated = morning_gate.run_gate(_previous_contract_row(), live, current_regime="BULLISH",
                                  spread_threshold=25.0, bond_state={}, macro_state={})
    assert gated["contract_symbol"] == _REPLACEMENT
    # Observed for the replacement: written.
    assert gated["contract_bid"] == 1.0
    assert gated["contract_ask"] == 1.1
    assert gated["contract_delta"] == 0.41
    # Not observed for the replacement: missing, never the previous contract's.
    for field in (
        "contract_gamma", "contract_theta", "contract_vega", "contract_iv", "contract_oi",
        "contract_volume", "contract_quote_timestamp", "contract_source", "contract_bid_size",
        "contract_ask_size", "contract_quote_quality", "premium_eod", "premium",
        "contract_premium", "breakeven_price", "breakeven_pct",
    ):
        assert _missing(gated.get(field)), f"{field} kept from {_PREVIOUS}: {gated.get(field)!r}"


def test_l1_morning_requote_of_the_same_contract_keeps_unrefreshed_fields() -> None:
    live = {
        "live_price": 101.0, "live_contract_bid": 2.0, "live_contract_ask": 2.1,
        "live_contract_mid": 2.05,
    }
    gated = morning_gate.run_gate(_previous_contract_row(), live, current_regime="BULLISH",
                                  spread_threshold=25.0, bond_state={}, macro_state={})
    assert gated["contract_symbol"] == _PREVIOUS
    assert gated["contract_gamma"] == 0.03
    assert gated["contract_oi"] == 900


def test_l1_hydrated_structure_change_never_keeps_the_previous_contracts_greeks() -> None:
    row = _previous_contract_row()
    live = {
        "selected_structure_hydration_status": "COMPLETE",
        "selected_contract_symbol": _REPLACEMENT, "selected_structure": "LONG_SINGLE",
        "live_contract_bid": 1.0, "live_contract_ask": 1.1, "live_contract_mid": 1.05,
    }
    morning_gate._recompute_selected_contract_economics(row, live)
    assert row["contract_symbol"] == _REPLACEMENT
    assert row["contract_ask"] == 1.1
    for field in ("contract_gamma", "contract_delta", "contract_iv", "contract_oi", "contract_source",
                  "contract_bid_size", "premium_eod", "breakeven_price"):
        assert _missing(row.get(field)), f"{field} kept from {_PREVIOUS}: {row.get(field)!r}"


def test_l1_hydrated_same_contract_keeps_unrefreshed_greeks() -> None:
    row = _previous_contract_row()
    live = {
        "selected_structure_hydration_status": "COMPLETE",
        "selected_contract_symbol": _PREVIOUS, "selected_structure": "LONG_SINGLE",
        "live_contract_bid": 2.0, "live_contract_ask": 2.1, "live_contract_mid": 2.05,
    }
    morning_gate._recompute_selected_contract_economics(row, live)
    assert row["contract_gamma"] == 0.03
    assert row["contract_oi"] == 900


# ─── L2: unobserved greeks / OI / volume stay missing in the candidate book ─

#: contract_vega is not a column of the EOD candidate book (absent, never 0.0);
#: it is still removed from the input so no future column could default it.
_L2_FIELDS = ("contract_delta", "contract_gamma", "contract_theta",
              "contract_iv", "contract_oi", "contract_volume")


@pytest.mark.parametrize("direction", ["CALL", "PUT"])
def test_l2_unobserved_greeks_and_open_interest_stay_missing(direction) -> None:
    row = _eod_row("AAA", route="OPTIONS_GO_REVIEW")
    row["direction"] = row["options_direction"] = direction
    for field in _L2_FIELDS + ("contract_vega",):
        row.pop(field, None)
    blank = _eod_row("BBB", route="OPTIONS_GO_REVIEW")
    blank["direction"] = blank["options_direction"] = direction
    blank.update({field: "" for field in _L2_FIELDS})
    records, written = _manifest([row, blank])
    by_ticker = {r["ticker"]: r for r in records}
    csv_rows = {r["ticker"]: r for r in written}
    for ticker in ("AAA", "BBB"):
        for field in _L2_FIELDS:
            value = by_ticker[ticker][field]
            assert value is None or (isinstance(value, float) and math.isnan(value)), (
                f"{ticker} {field} written as {value!r}"
            )
            assert csv_rows[ticker][field] == "", f"{ticker} {field} csv {csv_rows[ticker][field]!r}"


def test_l2_observed_greeks_including_a_real_zero_are_kept() -> None:
    row = _eod_row("AAA", route="OPTIONS_GO_REVIEW")
    row.update({"contract_delta": 0.42, "contract_gamma": 0.03, "contract_theta": -0.02,
                "contract_vega": 0.11, "contract_iv": 0.31, "contract_oi": 0, "contract_volume": 0})
    records, _ = _manifest([row])
    rec = {r["ticker"]: r for r in records}["AAA"]
    assert rec["contract_delta"] == 0.42
    assert rec["contract_gamma"] == 0.03
    assert rec["contract_theta"] == -0.02
    assert rec.get("contract_vega", float("nan")) != 0.0
    assert rec["contract_iv"] == 0.31
    # An observed zero open interest / volume is a measurement, not a default.
    assert rec["contract_oi"] == 0.0
    assert rec["contract_volume"] == 0.0


def test_l2_morning_gate_reads_a_missing_delta_as_unknown_not_zero() -> None:
    assert morning_gate._contract_side_from_row({"contract_delta": ""}) == ""
    assert morning_gate._contract_side_from_row({"contract_delta": float("nan")}) == ""


# ─── L3: the not-established flag reflects the final state ──────────────────

def test_l3_flag_removed_once_enrichment_establishes_the_reselected_contracts_quote(tmp_path) -> None:
    _write_source(
        tmp_path, ["ticker", "contract_symbol", "contract_bid", "contract_ask", "contract_mid"],
        {"ticker": "AAPL", "contract_symbol": PUT_OCC, "contract_bid": 1.0, "contract_ask": 1.1, "contract_mid": 1.05},
    )
    row = _book(tmp_path, _sig("PUT", contract_symbol=CALL_OCC, recommended_contract=PUT_OCC))
    assert row["contract_symbol"] == PUT_OCC
    assert float(row["contract_ask"]) == 1.1
    assert QUOTE_NOT_ESTABLISHED not in (row["lab_coherence_flags"] or "")
    # The reselection itself stays recorded.
    assert f"CONTRACT_RESELECTED_FOR_DIRECTION:{CALL_OCC}->{PUT_OCC}" in row["lab_coherence_flags"]


def test_l3_flag_stays_when_enrichment_only_has_the_original_contracts_quote(tmp_path) -> None:
    _write_source(
        tmp_path, ["ticker", "contract_symbol", "contract_bid", "contract_ask", "contract_mid"],
        {"ticker": "AAPL", "contract_symbol": CALL_OCC, "contract_bid": 1.0, "contract_ask": 1.1, "contract_mid": 1.05},
    )
    row = _book(tmp_path, _sig("PUT", contract_symbol=CALL_OCC, recommended_contract=PUT_OCC))
    assert row["contract_symbol"] == PUT_OCC
    assert _missing(row["contract_ask"])
    assert QUOTE_NOT_ESTABLISHED in row["lab_coherence_flags"]


@pytest.mark.parametrize("bid, ask", [("", 1.1), (1.0, ""), (1.0, 0.0), (0.0, 1.1)])
def test_l3_flag_stays_while_the_reselected_quote_is_not_two_sided(tmp_path, bid, ask) -> None:
    _write_source(
        tmp_path, ["ticker", "contract_symbol", "contract_bid", "contract_ask"],
        {"ticker": "AAPL", "contract_symbol": PUT_OCC, "contract_bid": bid, "contract_ask": ask},
    )
    row = _book(tmp_path, _sig("PUT", contract_symbol=CALL_OCC, recommended_contract=PUT_OCC))
    assert QUOTE_NOT_ESTABLISHED in row["lab_coherence_flags"]
