"""AVS options analytics framework — slice 2: the contract analytics block (ACK approved 30 Sep 2026).

Plan: Enhancements/decision_map/AVS_OPTIONS_ANALYTICS_FRAMEWORK_BUILD_PLAN_20260930.md. Display only.

Business rules (one owner: contracts/selected_contract_economics.contract_analytics):
- Prices a trader actually pays: breakeven and maximum loss at the ASK; extrinsic value shown at the mid and the ask.
- Intrinsic value at the current spot: call max(S − K, 0), put max(K − S, 0).
- Breakeven at expiry: call K + ask, put K − ask, and the signed stock move to it (rise +, fall −).
- Exposure per position: delta × multiplier × contracts shares; dollar delta = that × spot.
- Theta in USD per contract per calendar day; vega in USD per contract per IV point (provider units: per share).
- Spread as % of mid. Market-implied move = IV × √(days / 365): to expiry, and over the planned hold
  (sessions × 7/5 calendar days).
- Missing is never neutral: a missing input blanks only the figures that need it, names it, and marks the block
  PARTIAL; no direction or non-positive spot/strike marks it NOT_APPLICABLE.
"""
from __future__ import annotations

import sys
from math import sqrt
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.selected_contract_economics import contract_analytics  # noqa: E402

CALL = dict(direction="CALL", spot=105.0, strike=100.0, bid=6.8, ask=7.2, delta=0.62, theta=-0.05, vega=0.12,
            iv=0.30, dte_calendar=45, hold_sessions=20, iv_source="PROVIDER_EOD_CHAIN")
PUT = dict(CALL, direction="PUT", spot=95.0, delta=-0.60)


def test_a_call_block_from_a_worked_example():
    a = contract_analytics(**CALL)
    assert a["ca_state"] == "COMPLETE" and a["ca_missing_fields"] == ""
    assert a["ca_intrinsic_per_share"] == pytest.approx(5.0)
    assert a["ca_mid_per_share"] == pytest.approx(7.0)
    assert a["ca_extrinsic_at_mid_per_share"] == pytest.approx(2.0)
    assert a["ca_extrinsic_at_ask_per_share"] == pytest.approx(2.2)
    assert a["ca_extrinsic_share_of_ask_pct"] == pytest.approx(2.2 / 7.2 * 100, abs=1e-6)
    assert a["ca_breakeven_expiry_spot"] == pytest.approx(107.2)
    assert a["ca_breakeven_stock_move_pct"] == pytest.approx((107.2 / 105 - 1) * 100, abs=1e-6)
    assert a["ca_max_loss_per_position_usd"] == pytest.approx(720.0)
    assert a["ca_delta_share_equivalent"] == pytest.approx(62.0)
    assert a["ca_dollar_delta_usd"] == pytest.approx(62.0 * 105)
    assert a["ca_theta_usd_per_position_per_calendar_day"] == pytest.approx(-5.0)
    assert a["ca_vega_usd_per_position_per_iv_point"] == pytest.approx(12.0)
    assert a["ca_spread_pct_of_mid"] == pytest.approx(0.4 / 7.0 * 100, abs=1e-6)
    assert a["ca_implied_move_to_expiry_pct"] == pytest.approx(0.30 * sqrt(45 / 365) * 100, abs=1e-6)
    assert a["ca_implied_move_over_hold_pct"] == pytest.approx(0.30 * sqrt(28 / 365) * 100, abs=1e-6)
    assert a["ca_iv_source"] == "PROVIDER_EOD_CHAIN"


def test_a_put_is_mirrored():
    a = contract_analytics(**PUT)
    assert a["ca_intrinsic_per_share"] == pytest.approx(5.0)
    assert a["ca_breakeven_expiry_spot"] == pytest.approx(92.8)
    assert a["ca_breakeven_stock_move_pct"] == pytest.approx((92.8 / 95 - 1) * 100, abs=1e-6)   # a fall: negative
    assert a["ca_breakeven_stock_move_pct"] < 0
    assert a["ca_delta_share_equivalent"] == pytest.approx(-60.0)
    assert a["ca_dollar_delta_usd"] == pytest.approx(-60.0 * 95)


def test_an_out_of_the_money_option_is_all_extrinsic():
    a = contract_analytics(**dict(CALL, spot=95.0))
    assert a["ca_intrinsic_per_share"] == 0.0
    assert a["ca_extrinsic_at_ask_per_share"] == pytest.approx(7.2)
    assert a["ca_extrinsic_share_of_ask_pct"] == pytest.approx(100.0)


def test_position_figures_scale_with_contracts():
    a = contract_analytics(**CALL, contracts=3)
    assert a["ca_max_loss_per_position_usd"] == pytest.approx(2160.0)
    assert a["ca_delta_share_equivalent"] == pytest.approx(186.0)
    assert a["ca_theta_usd_per_position_per_calendar_day"] == pytest.approx(-15.0)
    assert a["ca_contracts"] == 3


def test_a_missing_input_blanks_only_what_needs_it_and_is_named():
    a = contract_analytics(**dict(CALL, ask=None, vega=None, hold_sessions=None))
    assert a["ca_state"] == "PARTIAL"
    assert set(a["ca_missing_fields"].split("|")) == {"ask", "vega", "hold_sessions"}
    for field in ("ca_breakeven_expiry_spot", "ca_max_loss_per_position_usd", "ca_extrinsic_at_ask_per_share",
                  "ca_spread_pct_of_mid", "ca_mid_per_share", "ca_vega_usd_per_position_per_iv_point",
                  "ca_implied_move_over_hold_pct"):
        assert a[field] is None, field
    assert a["ca_intrinsic_per_share"] == pytest.approx(5.0)            # still computable
    assert a["ca_delta_share_equivalent"] == pytest.approx(62.0)
    assert a["ca_implied_move_to_expiry_pct"] is not None


def test_no_direction_or_invalid_prices_is_not_applicable():
    assert contract_analytics(**dict(CALL, direction="STRANGLE"))["ca_state"] == "NOT_APPLICABLE"
    assert contract_analytics(**dict(CALL, spot=0.0))["ca_state"] == "NOT_APPLICABLE"
    assert contract_analytics(**dict(CALL, strike=None))["ca_state"] == "NOT_APPLICABLE"


# --- wiring ---------------------------------------------------------------------------------------------------------

def test_the_evening_block_uses_the_selected_contracts_real_quote(monkeypatch):
    from scripts import avshunter_options_intelligence as oi
    monkeypatch.setattr(oi, "governed_thesis_window_sessions", lambda *a, **k: 20)
    contract = {"strike": 100.0, "bid": 6.8, "ask": 7.2, "delta": 0.62, "theta": -0.05, "vega": 0.12, "iv": 0.30,
                "dte": 45, "mark_synthetic": False}
    a = oi.evening_contract_analytics(contract, {"direction": "CALL", "spot": 105.0})
    assert a["ca_state"] == "COMPLETE"
    assert a["ca_breakeven_expiry_spot"] == pytest.approx(107.2)
    assert a["ca_iv_source"] == "PROVIDER_EOD_CHAIN"


def test_the_evening_block_never_prices_from_a_synthetic_quote(monkeypatch):
    from scripts import avshunter_options_intelligence as oi
    monkeypatch.setattr(oi, "governed_thesis_window_sessions", lambda *a, **k: 20)
    contract = {"strike": 100.0, "bid": 6.8, "ask": 7.2, "delta": 0.62, "theta": -0.05, "vega": 0.12, "iv": 0.30,
                "dte": 45, "mark_synthetic": True}
    a = oi.evening_contract_analytics(contract, {"direction": "CALL", "spot": 105.0})
    assert a["ca_breakeven_expiry_spot"] is None and a["ca_max_loss_per_position_usd"] is None
    assert {"bid", "ask"} <= set(a["ca_missing_fields"].split("|"))


def test_the_morning_recomputes_the_block_for_the_contract_it_quotes(monkeypatch):
    import morning_gate
    from tests.test_morning_selected_contract_identity import _evening_row, _hydrated
    monkeypatch.setattr(morning_gate, "_get_ev3_barrier_cache", lambda: (None, "TEST_NO_CACHE"))
    row = _evening_row()
    row["ca_breakeven_expiry_spot"] = 47.0                       # the Evening contract's block
    morning_gate._recompute_selected_contract_economics(row, _hydrated())
    # MTDR261120P00055000: put, strike 55, ask 6.00 -> breakeven 49.00; live price 56
    assert row["ca_breakeven_expiry_spot"] == pytest.approx(49.0)
    assert row["ca_breakeven_stock_move_pct"] == pytest.approx((49.0 / 56.0 - 1) * 100, abs=1e-6)
    assert row["ca_iv_source"] == "PROVIDER_MORNING_QUOTE"
    assert row["ca_implied_move_over_hold_pct"] == pytest.approx(0.47 * sqrt(28 / 365) * 100, abs=1e-6)


def test_a_failed_morning_hydration_leaves_no_evening_block_behind(monkeypatch):
    import morning_gate
    from tests.test_morning_selected_contract_identity import _evening_row
    monkeypatch.setattr(morning_gate, "_get_ev3_barrier_cache", lambda: (None, "TEST_NO_CACHE"))
    row = _evening_row()
    row["ca_breakeven_expiry_spot"] = 47.0
    morning_gate._recompute_selected_contract_economics(row, {"selected_structure_hydration_status": "FAILED"})
    assert row["ca_breakeven_expiry_spot"] in ("", None)


def test_the_lab_book_carries_the_block():
    from contracts.lab_control import FINAL_BOOK_FIELDS, opportunity_book_row
    from contracts.selected_contract_economics import CONTRACT_ANALYTICS_FIELDS
    assert set(CONTRACT_ANALYTICS_FIELDS) <= set(FINAL_BOOK_FIELDS)
    sys.path.insert(0, str(ROOT / "tests"))
    from test_ila_release_coverage_gate import OCC, RUN_ID, _base_signal
    block = contract_analytics(**CALL)
    row = opportunity_book_row(_base_signal(contract_symbol=OCC, strike=100, expiry="2099-01-19", dte=30,
                                            premium_mid=7.0, contract_bid=6.8, contract_ask=7.2, **block), RUN_ID, 1)
    assert row["ca_breakeven_expiry_spot"] == pytest.approx(107.2)
    assert row["ca_state"] == "COMPLETE"


def test_the_evening_block_reaches_the_candidate_book_for_the_lab():
    import tempfile
    import pandas as pd
    sys.path.insert(0, str(ROOT / "tests"))
    from eod_candidate_engine import build_candidate_manifest
    from test_eod_options_research_handoff import _row
    block = contract_analytics(**CALL)
    row = {**_row("GOOD", route="OPTIONS_GO_REVIEW"), **block, "contract_greeks_source": "PROVIDER_EOD_CHAIN"}
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pd.DataFrame([row]).to_csv(root / "execution_v3_5_TEST.csv", index=False)
        out = build_candidate_manifest(eil_path=root / "execution_v3_5_TEST.csv",
                                       output_path=root / "morning_candidates_TEST.csv", run_id="TEST",
                                       max_candidates=10)
    got = out.to_dict("records")[0]
    assert got["ca_state"] == "COMPLETE"
    assert float(got["ca_breakeven_expiry_spot"]) == pytest.approx(107.2)
    assert got["contract_greeks_source"] == "PROVIDER_EOD_CHAIN"


def test_a_contract_voided_for_the_wrong_direction_takes_its_analytics_with_it():
    import eod_candidate_engine as eod
    row = {"recommended_contract": "AAA261218C00100000", **contract_analytics(**CALL),
           "contract_greeks_source": "PROVIDER_EOD_CHAIN"}
    out = eod._invalidate_direction_dependent_contract(row, {"direction_contract_reselection_required": "TRUE"})
    assert out["ca_breakeven_expiry_spot"] == "" and out["ca_state"] == ""
    assert out["contract_greeks_source"] == ""
