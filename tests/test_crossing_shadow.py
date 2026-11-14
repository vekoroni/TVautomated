"""Shadow comparison by crossing scenario (AVS-TRADE-001 design v4 section 7; ACK 14 Nov 2026).

Business rules:
- The objective is the earliest slow-pace +30% crossing among contracts that cover it and can be traded. Tier is an
  eligibility test and a tie-break: a tier B contract that crosses at session 2 beats a tier A one at session 10.
- A lower-score strike in the same expiry is assessed, and chosen when it is better.
- When nothing qualifies the shadow is blank with a named reason. There is no implicit fallback.
- Provisional and tier C contracts are never the shadow; if they cover they are listed as research rows.
- The label says "best within the bounded set", and says when a search was cut short.
"""
import json

import pytest

from domain import crossing_scenario as cs
from domain import crossing_shadow as sh
from domain import option_valuation as ov

FEE_OPEN = float(ov.valuation_policy()["fee_usd_per_contract_open"]) / 100.0
FEE_CLOSE = float(ov.valuation_policy()["fee_usd_per_contract_close"]) / 100.0
ANCHORS = dict(side="CALL", thesis_id="T:AAA", thesis_origin_date="2026-11-11", origin_spot=100.0,
               frozen_target_level=110.0, arrival_sessions_median=10, arrival_sessions_slow=20,
               assessment_instant_utc="2026-11-11T21:00:00+00:00", quote_spot=100.0, thesis_active=True,
               evidence_session="2026-11-11", underlying="AAA", rate=0.04, rate_basis="TEST", dividend_yield=0.0,
               dividend_basis="TEST", thesis_status_basis="TEST")


def contract(symbol, expiry="2027-01-15", strike=100.0, bid=4.90, ask=5.00, oi=500, score=50.0,
             stamp="2026-11-11T21:00:00Z"):
    return {"symbol": symbol, "expiry": expiry, "strike": strike, "bid": bid, "ask": ask, "open_interest": oi,
            "iv": 0.30, "contract_score": score, "quote_timestamp_utc": stamp, "md_occ_symbol": symbol}


def crossing_at(monkeypatch, by_strike):
    """Each contract crosses +30% on the session given for its strike (None = never)."""
    def values(side, spots, strike, years, vol, **kw):
        n = by_strike.get(strike)
        return [1e6 if n is not None and j >= n else 0.0 for j in range(1, len(spots) + 1)]
    monkeypatch.setattr(cs, "_model_values", values)


def shadow(scores, selected, **over):
    out = sh.crossing_shadow_fields(scores, selected, anchors={**ANCHORS, **over.pop("anchors", {})}, **over)
    return out, json.loads(out["crossing_candidates_json"])


def test_a_lower_score_strike_in_the_same_expiry_is_assessed_and_chosen_when_it_crosses_earlier(monkeypatch):
    a, b = contract("A", strike=100.0, score=80.0), contract("B", strike=105.0, score=40.0)
    crossing_at(monkeypatch, {100.0: 9, 105.0: 3})
    out, detail = shadow([a, b], a)
    assert out["crossing_shadow_symbol"] == "B" and out["crossing_shadow_n_slow_pace_30"] == 3
    assert out["crossing_shadow_reason"] == "EARLIEST_COVERING_TRADEABLE_CROSSING"
    assert out["crossing_shadow_selected_n_slow_pace_30"] == 9
    assert detail["assessed"] == 2 and out["crossing_shadow_set"] == "BEST_WITHIN_BOUNDED_SET_V1"


def test_tier_is_eligibility_and_a_tie_break_not_the_first_key(monkeypatch):
    tier_a = contract("A", strike=100.0, bid=4.90, ask=5.00)             # 2% wide: tier A
    tier_b = contract("B", strike=105.0, bid=4.40, ask=5.00)             # 12.8% wide: tier B
    crossing_at(monkeypatch, {100.0: 10, 105.0: 2})
    out, _ = shadow([tier_a, tier_b], tier_a)
    assert (out["crossing_shadow_symbol"], out["crossing_shadow_tier"]) == ("B", "B")
    crossing_at(monkeypatch, {100.0: 4, 105.0: 4})                       # same session: the better tier wins
    assert shadow([tier_a, tier_b], tier_a)[0]["crossing_shadow_symbol"] == "A"


def test_when_the_selected_contract_is_already_the_best_the_reason_says_so(monkeypatch):
    a, b = contract("A", strike=100.0), contract("B", strike=105.0)
    crossing_at(monkeypatch, {100.0: 3, 105.0: 8})
    out, _ = shadow([a, b], a)
    assert (out["crossing_shadow_symbol"], out["crossing_shadow_reason"]) == ("A", "SAME_AS_SELECTED")


def test_no_crossing_no_cover_and_no_tradeable_cover_are_each_named(monkeypatch):
    a, b = contract("A", strike=100.0), contract("B", strike=105.0)
    crossing_at(monkeypatch, {})
    assert shadow([a, b], a)[0]["crossing_shadow_reason"] == "NO_CROSSING_IN_SET"
    short_a, short_b = contract("A", expiry="2026-12-04"), contract("B", strike=105.0, expiry="2026-12-04")
    crossing_at(monkeypatch, {100.0: 10, 105.0: 10})                     # U = 11: 10 + 3 > 11
    out, detail = shadow([short_a, short_b], short_a)
    assert out["crossing_shadow_reason"] == "NO_COVERING_CANDIDATE" and out["crossing_shadow_symbol"] is None
    wide_a = contract("A", bid=3.00, ask=5.00)                           # 50% wide: tier C
    stale_b = contract("B", strike=105.0, stamp="2026-11-10T21:00:00Z")  # yesterday's quote: provisional
    crossing_at(monkeypatch, {100.0: 3, 105.0: 3})
    out, detail = shadow([wide_a, stale_b], wide_a)
    assert out["crossing_shadow_reason"] == "NO_TRADEABLE_COVERING_CANDIDATE" and out["crossing_shadow_symbol"] is None
    roles = {c["symbol"]: c["role"] for c in detail["candidates"]}
    assert roles == {"A": "RESEARCH_ROW_COVERS_BUT_NOT_TRADEABLE", "B": "RESEARCH_ROW_COVERS_BUT_NOT_TRADEABLE"}


def test_a_not_assessed_thesis_reports_its_state_not_a_comparison(monkeypatch):
    monkeypatch.setattr(cs, "_model_values", lambda *a, **k: pytest.fail("must not price"))
    out, _ = shadow([contract("A")], contract("A"), anchors={"arrival_sessions_slow": None, "arrival_sessions_median": None})
    assert out["crossing_shadow_reason"] == "NOT_ASSESSED_NO_ARRIVAL_TIME" and out["crossing_shadow_symbol"] is None


def test_the_set_is_bounded_deterministic_and_deduplicated(monkeypatch):
    crossing_at(monkeypatch, {})
    scores = [contract(f"E{e}S{k}", expiry=f"2027-0{e}-15", strike=100.0 + k, score=float(k))
              for e in range(1, 7) for k in range(6)]
    selected = scores[-1]                                                 # in the sixth expiry: outside the nearest four
    out, detail = shadow(scores, selected)
    symbols = [c["symbol"] for c in detail["candidates"]]
    # Four expiries x (top three by score + that expiry's best-liquidity contract) + the selected = the design maximum.
    assert len(symbols) == len(set(symbols)) == 4 * (3 + 1) + 1
    assert symbols[:4] == ["E1S5", "E1S4", "E1S3", "E1S0"] and symbols[-1] == selected["symbol"]
    assert detail["pool_scored"] == 36 and detail["not_in_set"] == 36 - 17
    again = shadow(list(reversed(scores)), selected)[1]
    assert [c["symbol"] for c in again["candidates"]] == symbols          # order of input does not matter
    few, d2 = shadow(scores[:2], scores[0])                               # fewer than M in an expiry
    assert d2["assessed"] == 2


def test_the_best_liquidity_contract_of_an_expiry_joins_the_set_even_with_a_low_score(monkeypatch):
    crossing_at(monkeypatch, {130.0: 2})
    scores = [contract(f"S{k}", strike=100.0 + k, score=90.0 - k, bid=4.0, ask=5.0) for k in range(4)]   # 22% wide
    liquid = contract("LIQ", strike=130.0, score=1.0, bid=4.95, ask=5.00)
    out, detail = shadow(scores + [liquid], scores[0])
    reasons = {c["symbol"]: c["set_reason"] for c in detail["candidates"]}
    assert reasons["LIQ"] == "BEST_LIQUIDITY_IN_EXPIRY" and "S3" not in reasons
    assert out["crossing_shadow_symbol"] == "LIQ"


def test_a_search_cut_by_the_cap_marks_the_set_incomplete_and_is_not_a_failure(monkeypatch):
    crossing_at(monkeypatch, {105.0: 3})
    cfg = {**cs.crossing_config(), "search_cap_sessions": 20}
    a, b = contract("A", expiry="2027-06-18"), contract("B", strike=105.0, expiry="2027-06-18")
    out, detail = shadow([a, b], a, anchors={"arrival_sessions_slow": 40}, config=cfg)
    states = {c["symbol"]: c["state"] for c in detail["candidates"]}
    assert states["A"] == "SEARCH_TRUNCATED_AT_CONFIG_CAP"
    assert out["crossing_shadow_set_complete"] == "NO" and detail["truncated_by_cap"] == 1
    assert out["crossing_shadow_symbol"] == "B" and detail["search_cap"] == 20


def test_the_selected_contracts_own_quote_is_graded_and_its_provenance_stated(monkeypatch):
    crossing_at(monkeypatch, {})
    out, _ = shadow([contract("A", bid=5.20, ask=5.00)], contract("A", bid=5.20, ask=5.00))
    assert (out["quote_tier_validity"], out["quote_tier"], out["quote_tier_reason"]) == ("INVALID_CROSSED_QUOTE", None, "CROSSED_QUOTE")
    out, _ = shadow([contract("A")], contract("A"))
    assert (out["quote_tier"], out["quote_provenance"]) == ("A", "ALIGNED")
    assert out["quote_tier_spread_share"] == pytest.approx(0.10 / 4.95, abs=1e-6)


def test_nothing_published_uses_a_name_lane_b_or_the_value_choice_acts_on(monkeypatch):
    crossing_at(monkeypatch, {100.0: 3})
    out, _ = shadow([contract("A")], contract("A"))
    assert set(out) == set(sh.CROSSING_SHADOW_FIELDS)
    assert not any(k.startswith(("monetisation_", "contract_value_", "scenario_")) for k in out)
    assert out["crossing_selection_mode"] == "SHADOW" and out["crossing_pool_basis"] == "SCORED_CONTRACTS_AFTER_SELECTION_FILTERS"


def test_the_pool_filter_counts_travel_with_the_result(monkeypatch):
    crossing_at(monkeypatch, {})
    counts = {"chain_rows_side": 40, "removed_below_holdable_dte": 4, "removed_outside_delta_mandate": 10}
    _, detail = shadow([contract("A")], contract("A"), pool_counts=counts)
    assert detail["pool_filter_counts"] == counts
