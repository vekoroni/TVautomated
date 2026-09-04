from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import avshunter_options_intelligence as oi


def _ctx(**overrides):
    base = {
        "ticker": "TST",
        "spot": 100.0,
        "entry": 100.0,
        "structural_target": 108.0,
        "atr": 2.0,
        "hold_days": 5,
        "direction": "CALL",
        "preferred_strategy": "LONG_CALL",
        "dte_window": (7, 14, 30),
        "delta_zone": (0.25, 0.55),
        "phase": "C",
        "win_prob": 64.0,
    }
    base.update(overrides)
    return base


def _contract(**overrides):
    base = {
        "symbol": "TST260515C00100000",
        "strike": 100.0,
        "expiry": "2026-05-15",
        "dte": 14,
        "bid": 2.00,
        "ask": 2.10,
        "mark": 2.05,
        "delta": 0.45,
        "gamma": 0.04,
        "theta": -0.04,
        "vega": 0.10,
        "implied_vol": 0.25,
        "oi": 1000,
        "volume": 250,
        "mark_synthetic": False,
    }
    base.update(overrides)
    return base


def _econ(**overrides):
    base = {
        "breakeven_price": 102.05,
        "rr_options": 3.2,
        "theta_drag_pct": 10.0,
    }
    base.update(overrides)
    return base


def _route(ctx=None, contract=None, econ=None, signal=None, walls=None, score=88.0):
    return oi.build_options_research_contract(
        ctx=ctx or _ctx(),
        signal_row=signal if signal is not None else pd.Series({"trigger_quality": "STRONG"}),
        contract=contract or _contract(),
        iv_ctx={"atm_iv": 0.25, "iv_percentile": 0.20},
        econ=econ or _econ(),
        ois_score=score,
        verdict="EXECUTE",
        stand_down_reason="",
        walls=walls or {"call_wall": 112.0, "put_wall": 90.0},
    )


def test_good_long_call_contract_goes_to_research_review_only():
    result = _route()

    assert result["execution_permission"] == oi.OPTIONS_RESEARCH_PERMISSION
    assert result["final_route"] == oi.OPTIONS_GO_ROUTE
    assert result["hard_vetoes"] == ""
    assert result["breakeven_feasibility"] >= 1.0


def test_negative_put_delta_is_valid_not_missing():
    result = _route(
        ctx=_ctx(direction="PUT", preferred_strategy="LONG_PUT", structural_target=92.0),
        contract=_contract(
            symbol="TST260515P00100000",
            delta=-0.38,
            bid=2.00,
            ask=2.10,
            mark=2.05,
        ),
        econ=_econ(breakeven_price=97.95, rr_options=3.2),
        walls={"call_wall": 112.0, "put_wall": 88.0},
    )

    assert "delta" not in result["missing_data"]
    assert result["final_route"] == oi.OPTIONS_GO_ROUTE


def test_missing_bid_ask_can_be_reconstructed_from_mid_and_spread():
    result = _route(
        contract=_contract(bid=None, ask=None, mark=2.00, spread_pct=0.05),
    )

    assert "bid" not in result["missing_data"]
    assert "ask" not in result["missing_data"]
    assert "MISSING_CRITICAL_OPTION_FIELDS" not in result["hard_vetoes"]


def test_selected_contract_preserves_quote_fields_for_research_contract():
    df = pd.DataFrame(
        [
            {
                "right": "P",
                "dte": 14,
                "mark_synthetic": False,
                "open_interest": 1000,
                "volume": 250,
                "spread_pct": 0.05,
                "mark": 2.0,
                "bid": 1.95,
                "ask": 2.05,
                "delta": -0.35,
                "strike": 100.0,
                "expiration_date": "2026-05-15",
                "gamma": 0.04,
                "theta": -0.04,
                "vega": 0.10,
                "implied_vol": 0.25,
                "symbol": "TST260515P00100000",
            }
        ]
    )
    contract = oi.select_best_contract(
        df,
        _ctx(direction="PUT", preferred_strategy="LONG_PUT", structural_target=92.0),
    )

    assert contract["bid"] == 1.95
    assert contract["ask"] == 2.05
    assert contract["delta"] == -0.35


def test_incomplete_marketdata_chain_quote_triggers_contract_quote_fallback():
    class FakeResponse:
        ok = True
        status_code = 200

        def json(self):
            return {
                "s": "ok",
                "bid": [1.9],
                "ask": [2.1],
                "mid": [2.0],
                "delta": [0.42],
                "gamma": [0.03],
                "theta": [-0.04],
                "vega": [0.11],
                "iv": [0.26],
                "openInterest": [700],
                "volume": [120],
            }

    class FakeSession:
        called = False

        def get(self, *args, **kwargs):
            self.called = True
            return FakeResponse()

    old_available = oi._MD_AVAILABLE
    old_key = oi.MARKETDATA_API_KEY
    old_session = oi.MD_SESSION
    fake_session = FakeSession()
    try:
        oi._MD_AVAILABLE = True
        oi.MARKETDATA_API_KEY = "test-key"
        oi.MD_SESSION = fake_session
        enriched = oi.enrich_contract_with_real_quotes(
            {
                "underlying": "TST",
                "expiration_date": "2026-05-15",
                "right": "C",
                "strike": 100.0,
                "mark": 2.0,
                "mark_synthetic": False,
                "md_quote_source": "marketdata.app_incomplete",
            }
        )
    finally:
        oi._MD_AVAILABLE = old_available
        oi.MARKETDATA_API_KEY = old_key
        oi.MD_SESSION = old_session

    assert fake_session.called is True
    assert enriched["bid"] == 1.9
    assert enriched["ask"] == 2.1
    assert enriched["delta"] == 0.42
    assert enriched["mark_synthetic"] is False


def test_missing_critical_fields_are_visible_without_granting_execution():
    result = _route(contract=_contract(bid=None, ask=None))

    assert result["execution_permission"] == oi.OPTIONS_RESEARCH_PERMISSION
    assert result["final_route"] == oi.OPTIONS_GO_ROUTE
    assert result["contract_repair_required"] is True
    assert "CONTRACT_DATA_INCOMPLETE" in result["contract_review_flags"]
    assert "bid" in result["missing_data"]
    assert "ask" in result["missing_data"]


def test_wide_spread_is_advisory_repair_evidence_in_research_route():
    result = _route(contract=_contract(bid=1.60, ask=2.40, mark=2.00))

    assert result["final_route"] == oi.OPTIONS_GO_ROUTE
    assert result["contract_repair_required"] is True
    assert "SPREAD_GT_25PCT" in result["contract_review_flags"]


def test_breakeven_feasibility_is_advisory_in_research_route():
    result = _route(
        ctx=_ctx(structural_target=101.0, atr=0.2),
        econ=_econ(breakeven_price=105.0),
    )

    assert result["final_route"] == oi.OPTIONS_GO_ROUTE
    assert result["breakeven_info_flag"] == "BREAKEVEN_FEASIBILITY_LT_1"


def test_estimated_r_is_advisory_in_research_route():
    result = _route(econ=_econ(rr_options=0.5))

    assert result["final_route"] == oi.OPTIONS_GO_ROUTE
    assert "ESTIMATED_R_LT_1" in result["contract_review_flags"]


def test_no_trigger_is_visible_without_becoming_capital_authority():
    result = _route(ctx=_ctx(phase="B"), signal=pd.Series({}))

    assert result["final_route"] == oi.OPTIONS_GO_ROUTE
    assert result["trigger_state"] == "NO_TRIGGER"
    assert result["trigger_info_flag"] == "NO_TRIGGER"


def test_stand_down_record_is_research_only():
    result = oi._stand_down(_ctx(), "No options chain data available")

    assert result["execution_permission"] == oi.OPTIONS_RESEARCH_PERMISSION
    assert result["final_route"] == oi.OPTIONS_BLOCKED_ROUTE
