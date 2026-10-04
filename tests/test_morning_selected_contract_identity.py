"""A Morning contract swap carries the new contract's identity as one unit (finding 28 Sep 2026).

Live evidence (runs 20260922_223221, 20260924_085940, 20260925_061649, 20260927_205123): when the
Morning's hydrated selected structure differs from the Evening contract, the selected-structure path
swapped the symbol, quote, Greeks and liquidity but left the Evening contract's strike, expiry and
days-to-expiry on the row (e.g. MTDR showed the 52.5 Dec-18 put beside the quote of
MTDR261120P00055000). 170-392 rows per Morning; the Lab displayed the mixed row. The hydrator
already publishes the new identity atomically (selected_contract_strike/expiry/dte).

Business rules:
- A row never combines one contract's symbol with another contract's strike, expiry or DTE.
- `dte` is calendar days to expiry (the hydrator's figure); `contract_dte` stays the governed
  trading-session count from the evidence session to the contract's own expiry (one owner:
  eod_candidate_engine._governed_contract_dte), so its declared basis stays true.
- When the Morning EV3 re-valuation does not produce a value, no Evening EV3 value - including the
  move-window value - survives on the row.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import morning_gate  # noqa: E402
from canonical_data.session_clock import xnys_sessions_between  # noqa: E402

OLD = "MTDR261218P00052500"
NEW = "MTDR261120P00055000"


def _evening_row(symbol: str = OLD) -> dict:
    return {
        "ticker": "MTDR", "direction": "PUT", "canonical_direction": "PUT", "instrument": "LONG_PUT",
        "run_id": "20260927_205123", "evidence_session_date": "2026-09-25",
        "contract_symbol": symbol, "recommended_contract": symbol,
        "strike": 52.5, "contract_strike": 52.5, "expiry": "2026-12-18", "contract_expiry": "2026-12-18",
        "dte": 84, "contract_dte": 58.0, "contract_dte_basis": "XNYS_TRADING_SESSIONS_TO_OCC_EXPIRY",
        "underlying_price": 56.0, "live_price": 56.0, "target_price": 50.0, "invalidation_price": 60.0,
        "planned_hold_sessions": 20, "horizon_bucket": "1_5d",
        "ev3_ev_conservative_return": 0.12, "ev3_move_window_ev_conservative_return": 0.08,
        "ev3_move_window_status": "EVALUATED", "ev_predicted": 0.12,
    }


def _hydrated(symbol: str = NEW, strike: float = 55.0, expiry: str = "2026-11-20", dte: int = 53) -> dict:
    leg = {"symbol": symbol, "strike": strike, "expiry": expiry, "dte": dte, "bid": 4.8, "ask": 6.0, "mid": 5.4,
           "delta": -0.58, "gamma": 0.04, "theta": -0.03, "vega": 0.08, "iv": 0.47, "oi": 117, "volume": 0,
           "contract_multiplier": 100.0, "quote_timestamp_utc": "2026-09-28T14:34:02Z"}
    return {
        "selected_structure_hydration_status": "COMPLETE", "selected_structure": "LONG_SINGLE",
        "selected_structure_id": "ECI1:fixture", "selected_contract_symbol": symbol,
        "selected_contract_symbols": f'["{symbol}"]', "selected_contract_strike": strike,
        "selected_contract_expiry": expiry, "selected_contract_dte": dte,
        "selected_quote_snapshot_id": "QUOTE1:fixture", "selected_quote_timestamp_utc": "2026-09-28T14:34:02Z",
        "selected_long_leg": leg, "selected_short_leg": None,
        "live_contract_symbol": symbol, "live_contract_bid": 4.8, "live_contract_ask": 6.0, "live_contract_mid": 5.4,
        "live_contract_iv": 0.47, "live_contract_delta": -0.58, "live_contract_gamma": 0.04,
        "live_contract_theta": -0.03, "live_contract_vega": 0.08, "live_contract_oi": 117,
        "live_contract_volume": 0, "live_contract_multiplier": 100.0, "live_options_source": "MARKETDATA",
        "live_contract_provider_updated": "2026-09-28T14:34:02Z",
    }


@pytest.fixture(autouse=True)
def _no_barrier_cache(monkeypatch):
    # The identity rule does not depend on EV3; keep the test off the live barrier cache file.
    monkeypatch.setattr(morning_gate, "_get_ev3_barrier_cache", lambda: (None, "TEST_NO_CACHE"))


def test_a_contract_swap_carries_the_new_contracts_strike_expiry_and_dte():
    row = _evening_row()
    morning_gate._recompute_selected_contract_economics(row, _hydrated())
    assert row["contract_symbol"] == NEW
    assert row["strike"] == 55.0 and row["contract_strike"] == 55.0
    assert row["expiry"] == "2026-11-20" and row["contract_expiry"] == "2026-11-20"
    assert row["dte"] == 53                                             # calendar days, hydrator's figure
    assert row["contract_dte"] == float(xnys_sessions_between(date(2026, 9, 25), date(2026, 11, 20)))
    assert row["contract_dte_basis"] == "XNYS_TRADING_SESSIONS_TO_OCC_EXPIRY"


def test_an_unchanged_contract_keeps_one_consistent_identity():
    row = _evening_row()
    morning_gate._recompute_selected_contract_economics(
        row, _hydrated(symbol=OLD, strike=52.5, expiry="2026-12-18", dte=81))
    assert row["contract_symbol"] == OLD
    assert row["strike"] == 52.5 and row["contract_strike"] == 52.5
    assert row["expiry"] == "2026-12-18" and row["contract_expiry"] == "2026-12-18"
    assert row["dte"] == 81
    assert row["contract_dte"] == float(xnys_sessions_between(date(2026, 9, 25), date(2026, 12, 18)))


def test_no_evening_ev3_value_survives_a_morning_revaluation_that_produced_none():
    row = _evening_row()
    morning_gate._recompute_selected_contract_economics(row, _hydrated())
    assert row["ev_predicted"] == ""
    assert row["ev3_ev_conservative_return"] in ("", None)
    assert row["ev3_move_window_ev_conservative_return"] in ("", None)
    assert row.get("ev3_move_window_status") in ("", None, "NOT_EVALUATED")
