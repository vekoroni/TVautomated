"""AVS options analytics framework — slice 1, verified defects (ACK approved 30 Sep 2026).

Plan: Enhancements/decision_map/AVS_OPTIONS_ANALYTICS_FRAMEWORK_BUILD_PLAN_20260930.md. Display and measurement only.

1a. `vega_risk_pct` is documented as "loss if IV drops 10 points" as a percentage of the premium. Provider vega is per
    one IV point per share (e.g. MTDR 0.0774 on a 5.40 mid, 53 DTE). The loss per contract is vega x 10 x 100 against
    a premium of mark x 100, so the percentage is vega x 10 / mark x 100. The code divided a per-share loss by the
    per-contract premium: 100x too small.
1b. The convexity strike map's "too late" check must measure progress from the trade's OWN recorded stop. Operator
    precedence made every PUT use the call wall, ignoring its recorded stop and invalidation. Calls keep their order
    (stop_loss, structural_support, invalidation_price, put wall); puts use stop_loss, invalidation_price, call wall
    (structural support sits on the wrong side of a put).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import avshunter_options_intelligence as oi  # noqa: E402


@pytest.fixture(autouse=True)
def ticket_limit(monkeypatch):
    monkeypatch.setattr(oi, "ticket_spread_limit_fraction", lambda: 0.10)


# --- 1a -------------------------------------------------------------------------------------------------------------

def _econ(direction="PUT", mark=5.40, vega=0.0774):
    contract = {"mark": mark, "bid": 4.80, "ask": 6.00, "strike": 55.0, "theta": -0.0326, "vega": vega,
                "delta": -0.58 if direction == "PUT" else 0.58, "dte": 53}
    ctx = {"spot": 56.0, "entry": 56.0, "structural_target": 50.0 if direction == "PUT" else 62.0,
           "hold_days": 10, "direction": direction, "win_prob": 55.0}
    return oi.compute_trade_economics(contract, ctx, {"ivp_label": "FAIR"})


@pytest.mark.parametrize("direction", ["CALL", "PUT"])
def test_vega_risk_is_the_premium_lost_if_iv_drops_ten_points(direction):
    econ = _econ(direction)
    assert econ["vega_risk_pct"] == pytest.approx(0.0774 * 10 / 5.40 * 100, abs=0.01)   # 14.33 %


def test_vega_risk_scales_with_vega_not_with_the_contract_multiplier():
    assert _econ(vega=0.0387)["vega_risk_pct"] == pytest.approx(_econ(vega=0.0774)["vega_risk_pct"] / 2, abs=0.01)


# --- 1b -------------------------------------------------------------------------------------------------------------

def _csm(direction, spot, target, signal_row, walls):
    contract = {"mark_synthetic": False, "mark": 3.0, "delta": -0.45 if direction == "PUT" else 0.45, "dte": 20,
                "symbol": "TEST"}
    ctx = {"spot": spot, "direction": direction, "structural_target": target}
    return oi.build_convexity_strike_map(contract, ctx, {"iv_percentile": 0.30}, {"breakeven_pct": 3.0},
                                         walls, {}, signal_row)


def test_a_put_measures_progress_from_its_recorded_stop_not_the_call_wall():
    # stop 100 -> target 80: price 86 has covered 70 % of the way -> too late.
    # (The call wall at 91 would say 45 % -> not too late.)
    out = _csm("PUT", 86.0, 80.0, {"stop_loss": 100.0}, {"call_wall": 91.0, "put_wall": 70.0})
    assert out["csm_verdict"] == "TOO_LATE", out.get("csm_verdict_reason")


def test_a_put_without_a_recorded_stop_uses_its_invalidation_then_the_call_wall():
    out = _csm("PUT", 86.0, 80.0, {"invalidation_price": 100.0}, {"call_wall": 91.0})
    assert out["csm_verdict"] == "TOO_LATE"
    wall_only = _csm("PUT", 86.0, 80.0, {}, {"call_wall": 91.0, "put_wall": 70.0})
    assert wall_only["csm_verdict"] != "TOO_LATE"          # 45 % toward target from the call wall


def test_a_put_ignores_structural_support_which_sits_on_the_wrong_side():
    out = _csm("PUT", 86.0, 80.0, {"structural_support": 75.0, "stop_loss": 100.0}, {"call_wall": 91.0})
    assert out["csm_verdict"] == "TOO_LATE"


def test_calls_keep_their_existing_stop_order():
    # characterisation: stop_loss first, then structural_support, then invalidation, then the put wall
    assert _csm("CALL", 114.0, 120.0, {"stop_loss": 100.0}, {"put_wall": 109.0})["csm_verdict"] == "TOO_LATE"
    assert _csm("CALL", 114.0, 120.0, {"structural_support": 100.0}, {"put_wall": 109.0})["csm_verdict"] == "TOO_LATE"
    assert _csm("CALL", 114.0, 120.0, {}, {"put_wall": 109.0})["csm_verdict"] != "TOO_LATE"   # 45 % from the wall


# --- 1e -------------------------------------------------------------------------------------------------------------
# The Greeks shown for a contract must say where they came from. When the Heston model calibrates, Options Intelligence
# replaces the provider's Greeks with Heston/BSM Greeks at the at-the-money variance (ignoring the contract's own IV and
# skew); the Morning then writes the provider's live Greeks. The source travels with the Greeks.

@pytest.mark.parametrize("contract,expected", [
    ({"delta": 0.5, "heston_used": True}, "HESTON_ATM_VARIANCE_MODEL"),
    ({"delta": 0.5, "heston_used": False}, "PROVIDER_EOD_CHAIN"),
    ({"delta": 0.5}, "PROVIDER_EOD_CHAIN"),
    ({"delta": None}, "UNAVAILABLE"),
    ({}, "UNAVAILABLE"),
])
def test_the_greeks_source_is_named(contract, expected):
    assert oi.contract_greeks_source(contract) == expected


def test_the_morning_labels_the_live_provider_greeks_it_writes():
    import morning_gate
    from tests.test_morning_selected_contract_identity import _evening_row, _hydrated
    row = _evening_row()
    row["contract_greeks_source"] = "HESTON_ATM_VARIANCE_MODEL"
    original = morning_gate._get_ev3_barrier_cache
    morning_gate._get_ev3_barrier_cache = lambda: (None, "TEST_NO_CACHE")
    try:
        morning_gate._recompute_selected_contract_economics(row, _hydrated())
    finally:
        morning_gate._get_ev3_barrier_cache = original
    assert row["contract_delta"] == -0.58
    assert row["contract_greeks_source"] == "PROVIDER_MORNING_QUOTE"


def test_the_lab_book_carries_the_greeks_source_with_the_greeks():
    from contracts.lab_control import FINAL_BOOK_FIELDS
    assert "contract_greeks_source" in FINAL_BOOK_FIELDS
