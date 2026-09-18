"""The horizon informs contract choice; it never decides which trades exist (ACK, 18 Sep 2026).

Business rules (ACK):
- Buy more runway than the anticipated move: a contract is never dropped for being longer-dated.
- Runway is a floor in correct units (sessions -> calendar days), a preference, never a ceiling.
- A contract short of the anticipated move is flagged for manual review, not sent to repair; only a
  contract that cannot be held past issue is unusable.
- One spread limit and one delta preference for every horizon. When nothing is inside the spread
  limit, the best contract is shown for manual review with the reason; the ticker never disappears.
- A missing horizon is reported, never defaulted to the shortest window.
- An end-of-day quote with a provider timestamp is labelled as awaiting the morning re-quote, not as
  "timestamp unavailable".

Evidence: 17 Sep evening run - 838 of 1,359 contract searches ended with no contract (482 on the
days-to-expiry window, 308 on the per-horizon spread band, 48 on delta); 667 of those tickers list only
monthly expiries (1, 29, 64, 92 days), which the 13-21 day window could never contain.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from domain.option_contract_liquidity import (
    calculate_dte_requirement,
    classify_current_executability,
)
from scripts import avshunter_options_intelligence as oi


def _contract(symbol: str, dte: float, *, right: str = "C", spread: float = 0.08, delta: float = 0.50,
              strike: float = 100.0) -> dict:
    mid = 2.0
    half = mid * spread / 2.0
    return {
        "symbol": symbol, "underlying": "TEST", "right": right, "strike": strike,
        "expiration_date": "2026-10-16", "dte": dte, "mark": mid, "bid": mid - half, "ask": mid + half,
        "bid_size": 10, "ask_size": 10, "delta": delta if right == "C" else -delta, "gamma": 0.03,
        "theta": -0.03, "vega": 0.08, "implied_vol": 0.40, "open_interest": 100, "volume": 20,
        "spread_pct": spread, "quote_quality": "TWO_SIDED", "quality_flags": (),
        "quote_fields_complete": True, "mark_synthetic": False,
        "quote_timestamp_utc": "2026-09-17T20:00:00Z",
    }


def _structural_context(horizon: str | None) -> dict:
    """The context the evening run builds from a signal row (runway fields are direction-independent)."""
    row = pd.Series({"ticker": "TEST", "direction": "CALL", "horizon_bucket": horizon,
                     "current_price": 100.0, "target_price": 110.0, "invalidation_spot": 95.0,
                     "invalidation_state": "AVAILABLE"})
    return oi.parse_structural_context(row)


def _ctx(horizon: str | None = "1_5d", direction: str = "CALL") -> dict:
    """Selection context as the existing selector tests build it, with the runway the run attaches."""
    return {"ticker": "TEST", "direction": direction, "spot": 100.0, "horizon_bucket": horizon,
            "structural_target": 110.0 if direction == "CALL" else 90.0, "hold_days": 5,
            "dte_window": oi.governed_dte_window(horizon), "dte_config": oi.governed_dte_config(horizon),
            **_runway(horizon)}


def _runway(horizon):
    ctx = _structural_context(horizon)
    return {k: ctx[k] for k in ("contract_runway_floor_days", "contract_min_holdable_dte",
                                "contract_runway_basis", "contract_runway_hold_sessions")}


def _select(rows: list[dict], ctx: dict) -> dict | None:
    return oi.select_best_contract(pd.DataFrame(rows), ctx)


# --- runway: a floor in correct units, never a ceiling ------------------------------------------------------------

def test_runway_requirement_converts_sessions_to_calendar_days():
    result = calculate_dte_requirement(10, monitor_sessions=2, exit_buffer_sessions=5)
    assert result["minimum_required_sessions"] == 17
    assert result["minimum_required_dte"] == math.ceil(17 * 7 / 5)          # 24 calendar days, not 17


def test_a_longer_dated_contract_is_never_dropped_for_being_longer():
    """The anticipated move is within 5 sessions, but the only contract has 64 days: it is the trade."""
    selected = _select([_contract("TEST261120C00100000", 64.0)], _ctx("1_5d"))
    assert selected is not None and selected["dte"] == 64.0


# ACK 18 Sep 2026 decision (a): the runway floor is the planned hold - the governed 20-session thesis window
# (+3 monitor, +5 exit buffer = 28 sessions = 40 calendar days) - whatever the anticipated move. The move is
# expected within the window; the contract must outlast the hold.

@pytest.mark.parametrize("horizon", ["1_5d", "6_10d", "11_20d"])
def test_monthly_chain_gets_the_nearest_expiry_covering_the_planned_hold(horizon):
    rows = [_contract("TEST260918C00100000", 1.0), _contract("TEST261016C00100000", 29.0),
            _contract("TEST261120C00100000", 64.0), _contract("TEST261218C00100000", 92.0)]
    selected = _select(rows, _ctx(horizon))
    assert selected["dte"] == 64.0          # 29 days cannot outlast a 20-session hold; 92 is more than needed


def test_the_runway_floor_is_the_planned_hold_not_the_anticipated_move():
    floors = {h: _structural_context(h)["contract_runway_floor_days"] for h in ("1_5d", "6_10d", "11_20d", None)}
    assert set(floors.values()) == {math.ceil((20 + 3 + 5) * 7 / 5)}
    assert _structural_context("1_5d")["contract_runway_hold_sessions"] == 20


def test_short_runway_is_selected_and_flagged_for_manual_review():
    selected = _select([_contract("TEST261002C00100000", 15.0)], _ctx("6_10d"))
    assert selected is not None
    assert selected["contract_runway_state"] == "RUNWAY_SHORT"
    assert selected["contract_runway_floor_days"] == math.ceil((20 + 3 + 5) * 7 / 5)


def test_a_contract_that_cannot_be_held_past_issue_is_never_chosen():
    assert _select([_contract("TEST260918C00100000", 1.0)], _ctx("1_5d")) is None


# --- one spread limit, one delta preference; manual review instead of disappearing --------------------------------

def test_spread_limit_is_the_same_for_every_horizon():
    for horizon in ("1_5d", "6_10d", "11_20d", None, "UNKNOWN"):
        assert oi.horizon_spread_limit(horizon) == oi.MAX_SPREAD_PCT


def test_a_contract_inside_the_single_spread_limit_is_selected_on_a_short_horizon():
    """20% spread: rejected by the former 15% band for 1_5d; inside the one reviewable limit (25%)."""
    selected = _select([_contract("TEST261016C00100000", 29.0, spread=0.20)], _ctx("1_5d"))
    assert selected is not None and selected["spread_above_limit"] is False


def test_when_nothing_is_inside_the_spread_limit_the_best_contract_goes_to_manual_review():
    rows = [_contract("TEST261016C00100000", 29.0, spread=0.60),
            _contract("TEST261016C00105000", 29.0, spread=0.35, strike=105.0)]
    selected = _select(rows, _ctx("6_10d"))
    assert selected is not None
    assert selected["spread_above_limit"] is True
    assert selected["selection_reason"] == "BEST_AVAILABLE_SPREAD_ABOVE_LIMIT_MANUAL_REVIEW"
    assert selected["spread_pct"] == 0.35   # the tighter of the two


def test_delta_preference_is_the_same_for_every_horizon():
    policies = [oi.governed_dte_config(h) for h in ("1_5d", "6_10d", "11_20d")]
    assert {(p["delta_min"], p["delta_max"]) for p in policies} == {
        (oi.CONTRACT_SELECTION["delta_preferred_abs"][0], oi.CONTRACT_SELECTION["delta_preferred_abs"][1])}


# --- missing horizon: reported, not defaulted ----------------------------------------------------------------------

@pytest.mark.parametrize("horizon", [None, "", "UNKNOWN"])
def test_missing_horizon_is_reported_and_uses_the_full_thesis_window_not_the_shortest(horizon):
    ctx = _structural_context(horizon)
    assert ctx["contract_runway_basis"] == "THESIS_WINDOW_D2|HORIZON_UNAVAILABLE"
    assert ctx["contract_runway_floor_days"] == math.ceil((20 + 3 + 5) * 7 / 5)


def test_known_horizon_is_the_runway_basis_and_stays_descriptive():
    ctx = _structural_context("6_10d")
    assert ctx["contract_runway_basis"] == "THESIS_WINDOW_D2|HORIZON:6_10d"
    assert ctx["dte_config"]["planned_hold_sessions"] == 10          # the horizon is still carried


# --- lifecycle: short runway is a manual-review flag, not a repair ------------------------------------------------

def test_lifecycle_short_runway_is_manual_review_not_contract_repair():
    result = classify_current_executability(
        bid=4.90, ask=5.00, quote_age_seconds=60, dte=15, minimum_required_dte=26,
        minimum_holdable_dte=5, moneyness_treatment="PREFERRED_EXECUTION")
    assert result["recovery_disposition"] == "MONITOR"
    assert result["liquidity_state"] == "RUNWAY_SHORT_REVIEW"
    assert "RUNWAY_BELOW_PLANNED_HOLD" in result["liquidity_reasons"]


def test_lifecycle_contract_not_holdable_past_issue_still_needs_repair():
    result = classify_current_executability(
        bid=4.90, ask=5.00, quote_age_seconds=60, dte=1, minimum_required_dte=26,
        minimum_holdable_dte=5, moneyness_treatment="PREFERRED_EXECUTION")
    assert result["liquidity_state"] == "DTE_UNSUITABLE"
    assert result["recovery_disposition"] == "CONTRACT_REPAIR"


# --- repair search follows the same rules ---------------------------------------------------------------------------

def test_repair_search_keeps_longer_dated_alternatives():
    chain = pd.DataFrame([_contract("TEST261120C00100000", 64.0), _contract("TEST260918C00100000", 1.0)])
    ctx = _ctx("1_5d")
    ctx["horizon_bucket"] = "1_5d"
    alternatives = oi.select_repair_alternative_contracts(chain, ctx)
    assert [a["symbol"] for a in alternatives] == ["TEST261120C00100000"]


# --- evening quote label ---------------------------------------------------------------------------------------------

def test_eod_quote_with_provider_timestamp_is_labelled_awaiting_morning_requote():
    from domain.option_contract_liquidity import label_eod_quote_state
    assert label_eod_quote_state("QUOTE_TIMESTAMP_UNAVAILABLE", "2026-09-17T20:00:00Z") == \
        "EOD_QUOTE_PENDING_MORNING_REQUOTE"
    assert label_eod_quote_state("QUOTE_TIMESTAMP_UNAVAILABLE", None) == "QUOTE_TIMESTAMP_UNAVAILABLE"
    assert label_eod_quote_state("REVIEWABLE_SPREAD", "2026-09-17T20:00:00Z") == "REVIEWABLE_SPREAD"


# --- Discovery/Vanguard join: one owner per shared fact (ACK 18 Sep 2026) ------------------------------------------
# Run 20260918_112522: both inputs carry 132 fields (Vanguard copies the Discovery row from its package). The plain
# merge suffixed them _x/_y, so the options stage read defaults - volume_ratio 1.0 and sector blank on all 1,499
# rows - and re-published those defaults to SuperBrain. 128 of the 132 were identical in both files.

def _join_inputs():
    disc = pd.DataFrame([{"ticker": "AAA", "volume_ratio": 2.4, "sector": "Technology", "iv_rank": None,
                          "adx_14": 22.0, "timestamp": "2026-09-17T20:00:00"},
                         {"ticker": "BBB", "volume_ratio": 0.6, "sector": "Energy", "iv_rank": 40.0,
                          "adx_14": None, "timestamp": "2026-09-17T20:01:00"}])
    vang = pd.DataFrame([{"ticker": "AAA", "volume_ratio": 2.4, "sector": "Technology", "iv_rank": 31.0,
                          "adx_14": 22.0, "timestamp": "2026-09-17T21:00:00+00:00", "verdict": "PASS"},
                         {"ticker": "BBB", "volume_ratio": 0.9, "sector": "Energy", "iv_rank": 40.0,
                          "adx_14": 18.5, "timestamp": "2026-09-17T21:01:00+00:00", "verdict": "PASS"}])
    return oi.merge_discovery_vanguard(disc, vang)


def test_every_shared_field_appears_once_under_its_own_name():
    merged = _join_inputs()
    assert not [c for c in merged.columns if c.endswith(("_x", "_y"))]
    assert list(merged["sector"]) == ["Technology", "Energy"] and "verdict" in merged.columns


def test_discovery_owns_the_fields_vanguard_copies_through():
    merged = _join_inputs().set_index("ticker")
    assert merged.loc["AAA", "volume_ratio"] == 2.4
    assert merged.loc["BBB", "volume_ratio"] == 0.6            # the owner's value, not the copy


def test_vanguard_owns_signal_time_and_the_resolved_trend_inputs():
    merged = _join_inputs().set_index("ticker")
    assert merged.loc["AAA", "timestamp"] == "2026-09-17T21:00:00+00:00"
    assert merged.loc["BBB", "adx_14"] == 18.5                 # Vanguard's OHLCV-resolved value


def test_a_missing_owner_value_is_filled_from_the_copy_and_every_difference_is_reported():
    merged = _join_inputs()
    assert merged.set_index("ticker").loc["AAA", "iv_rank"] == 31.0
    report = merged.attrs["merge_field_report"]
    assert report["volume_ratio"] == {"disagree": 1, "filled_from_copy": 0}
    assert report["iv_rank"] == {"disagree": 0, "filled_from_copy": 1}
    assert report["timestamp"]["disagree"] == 2


def test_structural_context_reads_the_real_volume_ratio():
    row = _join_inputs().iloc[0]
    assert oi.parse_structural_context(row)["vol_ratio"] == 2.4


# --- Macro: the latest packet always wins (ACK 18 Sep 2026) --------------------------------------------------------
# Several macro packets in one run are by design: a run near the open picks up the updated macro. The join must keep
# the newest by generation time, whichever file carries it, and record both packets when they differ.

def _macro_join(disc_generated: str, vang_generated: str):
    disc = pd.DataFrame([{"ticker": "AAA", "volume_ratio": 1.2, "macro_packet_id": "MACRO:D",
                          "macro_generated_at_utc": disc_generated, "macro_regime": "NEUTRAL"}])
    vang = pd.DataFrame([{"ticker": "AAA", "volume_ratio": 1.2, "macro_packet_id": "MACRO:V",
                          "macro_generated_at_utc": vang_generated, "macro_regime": "RISK_OFF"}])
    return oi.merge_discovery_vanguard(disc, vang)


def test_a_newer_macro_in_vanguard_replaces_the_older_discovery_stamp():
    merged = _macro_join("2026-09-18T11:00:00+00:00", "2026-09-18T13:45:00+00:00")
    row = merged.iloc[0]
    assert (row["macro_packet_id"], row["macro_regime"]) == ("MACRO:V", "RISK_OFF")
    assert row["volume_ratio"] == 1.2                               # non-macro fields keep their owner
    assert merged.attrs["macro_packet_resolution"] == {
        "discovery_packets": ["MACRO:D"], "vanguard_packets": ["MACRO:V"], "rows_using_vanguard_macro": 1}


def test_the_same_generation_time_keeps_the_discovery_stamp():
    row = _macro_join("2026-09-18T11:00:00+00:00", "2026-09-18T11:00:00+00:00").iloc[0]
    assert (row["macro_packet_id"], row["macro_regime"]) == ("MACRO:D", "NEUTRAL")


# --- Stand-down rows keep the upstream facts (ACK 18 Sep 2026) ------------------------------------------------------
# Run 20260918_112522: 147 rows stood down before a contract (137 without a long CALL/PUT direction) and their
# options record dropped 13 upstream facts that full rows carry; SuperBrain inherited the blanks.

_UPSTREAM_FACTS = {
    "win_probability": 60.3, "behaviour_state_key": "CONTINUATION|MID|TRANSITION_ZONE",
    "behaviour_state_hash": "ab12cd34", "sector_etf": "XLI", "catalyst_overlay": "NONE",
    "trade_type_classification": "STRUCTURAL_SINGLE_STOCK", "structure_first_required": True,
    "macro_alignment_state": "MACRO_NOT_APPLICABLE", "macro_direction_authority": "DISABLED",
    "macro_applicability": "NOT_APPLICABLE", "macro_direction_vote": "ABSTAIN",
    "macro_raw_direction_hint": "ABSTAIN", "macro_can_invert_direction": False,
}


def test_a_stand_down_record_carries_the_same_upstream_facts_as_a_full_row():
    row = pd.Series({"ticker": "BZ", "direction": "STRANGLE", "current_price": 20.0, **_UPSTREAM_FACTS})
    ctx = oi.parse_structural_context(row)
    ctx["_signal_row"] = row
    record = oi._stand_down(ctx, "No governed long CALL/PUT direction; chain request suppressed")
    assert {k: record.get(k) for k in _UPSTREAM_FACTS} == _UPSTREAM_FACTS
    assert record["dte"] is None and record["strike"] is None       # no contract: contract facts stay empty
