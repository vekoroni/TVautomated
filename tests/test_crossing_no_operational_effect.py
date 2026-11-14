"""The crossing scenario changes nothing operational (AVS-TRADE-001 design v4 sections 1, 7, 10, 12; ACK 14 Nov 2026).

Business rules:
- The selected contract, its score and the existing value choice (`contract_value_*`) are the same with the crossing
  shadow as without it.
- A caller of the anticipated move that passes no crossing anchors gets exactly what it got before; with anchors,
  every existing field keeps its value and only `crossing_` fields are added.
- No published crossing field is a name that Lane B's window flag, the rank owner or the value choice reads.
- Lane B's window flag is the same whether or not a row carries crossing fields.
- A failure inside the shadow comparison never takes a ticker down and never changes the selection.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

from domain import crossing_scenario as cs
from domain import crossing_shadow as sh
from domain.anticipated_move import ANTICIPATED_MOVE_FIELDS, anticipated_move_fields, thesis_active_state
from scripts import avshunter_options_intelligence as oi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data" / "scratch" / "workaround"))
import build_lab_handoff as blh  # noqa: E402

PUBLISHED = (*cs.CROSSING_FIELDS, *sh.CROSSING_SHADOW_FIELDS)


def _contract(symbol, dte, *, spread=0.08, delta=0.50, strike=100.0, mid=2.0, expiry="2026-10-23"):
    half = mid * spread / 2.0
    return {"symbol": symbol, "underlying": "TEST", "right": "C", "strike": strike, "expiration_date": expiry,
            "dte": dte, "mark": mid, "bid": mid - half, "ask": mid + half, "bid_size": 10, "ask_size": 10,
            "delta": delta, "gamma": 0.03, "theta": -0.03, "vega": 0.08, "implied_vol": 0.40, "open_interest": 100,
            "volume": 20, "spread_pct": spread, "quote_quality": "TWO_SIDED", "quality_flags": (),
            "quote_fields_complete": True, "mark_synthetic": False, "quote_timestamp_utc": "2026-09-24T20:00:00Z"}


CHAIN = [_contract("TEST261023C00100000", 29.0), _contract("TEST261023C00105000", 29.0, delta=0.30, strike=105.0),
         _contract("TEST261127C00100000", 64.0, mid=3.0, expiry="2026-11-27"),
         _contract("TEST261224C00100000", 92.0, mid=3.6, expiry="2026-12-24")]


def _ctx():
    row = pd.Series({"ticker": "TEST", "direction": "CALL", "horizon_bucket": "1_5d", "current_price": 100.0,
                     "target_price": 110.0, "invalidation_spot": 95.0, "invalidation_state": "AVAILABLE"})
    structural = oi.parse_structural_context(row)
    return {"ticker": "TEST", "direction": "CALL", "spot": 100.0, "horizon_bucket": "1_5d",
            "structural_target": 110.0, "invalidation_spot": 95.0, "hold_days": 5,
            "evidence_runway_sessions": 20, "evidence_move_sessions": 8, "strike_filter_level": 110.0,
            "dte_window": oi.governed_dte_window("1_5d"), "dte_config": oi.governed_dte_config("1_5d"),
            "_signal_row": {"ticker": "TEST", "final_direction": "CALL", "underlying_price": 100.0,
                            "structural_target": 110.0, "invalidation_spot": 95.0,
                            "evidence_session_date": "2026-09-24"},
            **{k: structural[k] for k in ("contract_runway_floor_days", "contract_min_holdable_dte",
                                          "contract_runway_basis", "contract_runway_hold_sessions")}}


@pytest.fixture(autouse=True)
def _shadow_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(oi, "_L3_RUNS_DIR", tmp_path, raising=False)
    monkeypatch.setitem(oi.CONTRACT_SELECTION, "value_selection_mode", "SHADOW")
    monkeypatch.setattr(oi, "_CDS_V2_SESSION", None, raising=False)


def test_the_selection_and_the_value_choice_are_identical_with_and_without_the_crossing_shadow(monkeypatch):
    with_shadow = oi.select_best_contract(pd.DataFrame(CHAIN), _ctx())
    monkeypatch.setattr(oi, "_crossing_shadow_for", lambda scores, selected, ctx: {})
    without = oi.select_best_contract(pd.DataFrame(CHAIN), _ctx())
    assert set(with_shadow) - set(without) == set(sh.CROSSING_SHADOW_FIELDS)
    for key, value in without.items():
        assert with_shadow[key] == value, key
    assert with_shadow["contract_value_selection_mode"] == "SHADOW"


def test_the_shadow_is_computed_from_the_selection_context_and_stays_a_shadow():
    out = oi.select_best_contract(pd.DataFrame(CHAIN), _ctx())
    assert out["crossing_selection_mode"] == "SHADOW" and out["crossing_shadow_set"] == "BEST_WITHIN_BOUNDED_SET_V1"
    assert out["crossing_pool_basis"] == "SCORED_CONTRACTS_AFTER_SELECTION_FILTERS"
    assert out["quote_tier"] in ("A", "B", "C") and out["quote_provenance"] == "ALIGNED"
    import json
    detail = json.loads(out["crossing_candidates_json"])
    assert detail["thesis_status_basis"] == "ACTIVE_AT_SELECTION_STAGE"
    counts = detail["pool_filter_counts"]
    assert counts["side_rows"] == 4 and counts["scored"] == detail["pool_scored"]
    removed = sum(v for k, v in counts.items() if k.startswith("removed_"))
    assert counts["side_rows"] - removed == counts["scored"]                 # the accounting reconciles
    assert out["crossing_shadow_reason"] is not None


def test_a_failure_in_the_shadow_never_takes_the_ticker_down_or_changes_the_selection(monkeypatch):
    baseline = oi.select_best_contract(pd.DataFrame(CHAIN), _ctx())

    def boom(*args, **kwargs):
        raise RuntimeError("shadow failed")
    monkeypatch.setattr(sh, "crossing_shadow_fields", boom)
    out = oi.select_best_contract(pd.DataFrame(CHAIN), _ctx())
    assert out["symbol"] == baseline["symbol"] and out["contract_score"] == baseline["contract_score"]
    assert out["crossing_shadow_reason"] == "NOT_ASSESSED_SHADOW_ERROR:RuntimeError" and out["crossing_shadow_symbol"] is None


AM = dict(direction="CALL", spot=100.0, outcome_level=110.0, outcome_definition="RANGE_HIGH", timeframe="1d",
          duration={"status": "IN_SAMPLE_REPLAY_NOT_VALIDATED", "n": 200, "q50_bars": 8, "q80_bars": 20},
          vol_annual=0.35, contract={"strike": 100.0, "ask": 5.0, "bid": 4.9, "iv": 0.30, "expiry": "2027-01-15",
                                     "as_of": "2026-11-11", "underlying": "TEST"},
          governed_window_sessions=20, rate=0.04, rate_basis="TEST", dividend_yield=0.0, dividend_basis="TEST")
ANCHORS = {"mode": "EVENING_AT_EVIDENCE", "thesis_id": "T:TEST", "contract_symbol": "TEST270115C00100000",
           "thesis_origin_date": "2026-11-11", "origin_spot": 100.0,
           "assessment_instant_utc": "2026-11-11T21:00:00+00:00", "quote_timestamp_utc": "2026-11-11T21:00:00Z",
           "thesis_active": True}


def test_a_caller_without_anchors_gets_exactly_what_it_got_before():
    out = anticipated_move_fields(**AM)
    assert not any(k.startswith("crossing_") for k in out)
    assert set(out) == set(ANTICIPATED_MOVE_FIELDS)


def test_with_anchors_every_existing_field_keeps_its_value_and_only_crossing_fields_are_added():
    before = anticipated_move_fields(**AM)
    after = anticipated_move_fields(**AM, crossing=ANCHORS)
    assert set(after) - set(before) == set(cs.CROSSING_FIELDS)
    for key, value in before.items():
        assert after[key] == value, key
    assert after["crossing_mode"] == "EVENING_AT_EVIDENCE" and after["crossing_frozen_target_level"] == before["anticipated_level_q50"]
    assert after["crossing_state"] in ("CROSSES_COVERING", "CROSSES_NOT_COVERING", "NO_CROSSING_BY_ARRIVAL")


def test_a_row_with_no_trade_side_event_or_unknown_thesis_status_is_stated_not_scored():
    no_event = anticipated_move_fields(**{**AM, "trade_side_event": False}, crossing=ANCHORS)
    assert no_event["crossing_state"] == "NOT_ASSESSED_NO_TRADE_SIDE_EVENT" and no_event["crossing_n_slow_pace_30"] is None
    unknown = anticipated_move_fields(**AM, crossing={**ANCHORS, "thesis_active": thesis_active_state("")})
    assert unknown["crossing_state"] == "NOT_ASSESSED_THESIS_STATUS_UNKNOWN"
    assert thesis_active_state("ACTIVE") is True and thesis_active_state("INVALIDATED") is False
    assert thesis_active_state(None) is None and thesis_active_state("nan") is None


def test_morning_uses_the_frozen_evening_target_and_arrival_not_the_live_recomputation():
    frozen = {**ANCHORS, "mode": "MORNING_FRESH_ENTRY", "assessment_instant_utc": "2026-11-13T14:40:00+00:00",
              "quote_timestamp_utc": "2026-11-13T14:39:00Z", "frozen_target_level": 110.0, "frozen_sessions_q50": 8,
              "frozen_sessions_q80": 20}
    out = anticipated_move_fields(**{**AM, "spot": 104.0, "contract": {**AM["contract"], "as_of": "2026-11-13"}},
                                  crossing=frozen)
    assert out["crossing_frozen_target_level"] == 110.0 and out["crossing_origin_spot"] == 100.0
    assert out["crossing_quote_spot"] == 104.0 and out["crossing_elapsed_sessions"] == 1
    assert out["crossing_thesis_origin_date"] == "2026-11-11"


def test_no_published_field_is_a_name_that_anything_operational_reads():
    assert not any(name.startswith(("monetisation_", "contract_value_", "scenario_", "anticipated_", "lb_")) for name in PUBLISHED)
    assert len(set(PUBLISHED)) == len(PUBLISHED)
    for rel in ("domain/opportunity_rank.py", "data/scratch/workaround/check_triage.py",
                "data/scratch/workaround/collect_decisions.py"):
        text = (ROOT / rel).read_text(encoding="utf-8-sig")
        assert "crossing_" not in text and "quote_tier" not in text and "quote_provenance" not in text, rel
    handoff = (ROOT / "data/scratch/workaround/build_lab_handoff.py").read_text(encoding="utf-8-sig")
    assert "crossing_" not in handoff and "quote_provenance" not in handoff
    # The existing book fields with the same prefix as nothing here: no collision with the saved card fields.
    from contracts.lab_control import FINAL_BOOK_FIELDS
    assert set(PUBLISHED) <= set(FINAL_BOOK_FIELDS)
    # Each new field appears in the book list exactly once. (Five older usmi_* names are listed twice there; that
    # is an existing defect, recorded separately, and not something this work adds to.)
    assert all(FINAL_BOOK_FIELDS.count(name) == 1 for name in PUBLISHED)


def test_lane_bs_window_flag_is_the_same_with_and_without_crossing_fields():
    settings = blh.DEFAULTS
    for sessions, setup in ((5, "1d|SPRING"), (40, "1d|SPRING"), (8, "1w|BREAKOUT"), (None, "1d|SPRING")):
        row = {"anticipated_sessions_q50": sessions, "trade_lane_setup": setup}
        with_fields = {**row, **{name: 3 for name in PUBLISHED}}
        assert blh.window_flag(with_fields, settings) == blh.window_flag(row, settings)
        assert blh.window_flag(with_fields, settings)[2] == "PROXY_Q50"


def test_the_card_and_book_lists_carry_the_new_fields_after_the_identity_fields():
    from canonical_data.instrument_identity import IDENTITY_FIELDS
    from contracts.lab_review_projection import CARD_FIELDS
    assert set(PUBLISHED) <= set(CARD_FIELDS) and set(IDENTITY_FIELDS) <= set(CARD_FIELDS)
    assert len(CARD_FIELDS) == len(set(CARD_FIELDS))
