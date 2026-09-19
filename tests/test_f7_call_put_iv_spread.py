"""F7 / O2 (ACK, 19 Sep 2026): the call-put IV spread (25-delta risk reversal) reaches the
scanner fast-path output row instead of being hardcoded unavailable.

Deep dive: compute_iv_skew() genuinely computes put_25d_iv/call_25d_iv/risk_reversal/skew_label
from real chain data, and compute_iv_context() already folds those into its result (it calls
compute_iv_skew and does result.update(skew)). But in process_ticker()'s scanner fast-path
(_has_scanner branch), put_25d_iv and call_25d_iv were hardcoded to None, and the "best-effort
enhance from chain" loop right after it only copied ('term_structure','term_ratio','iv_direction',
'skew_label','risk_reversal','heston_params','vol_of_vol','iv_accel_detected') across - leaving
the two IV spread legs themselves stuck at None even when the chain-based enhancement succeeded.
"""
from __future__ import annotations

import inspect

import pandas as pd

import scripts.avshunter_options_intelligence as oi


def test_compute_iv_skew_is_real_not_hardcoded():
    spot = 100.0
    chain = pd.DataFrame([
        {"right": "P", "strike": 92.0, "dte": 20, "delta": -0.25, "implied_vol": 0.40},
        {"right": "C", "strike": 108.0, "dte": 20, "delta": 0.25, "implied_vol": 0.30},
    ])
    result = oi.compute_iv_skew(chain, spot)
    assert result["put_25d_iv"] is not None
    assert result["call_25d_iv"] is not None
    assert result["put_25d_iv"] != result["call_25d_iv"]
    assert result["skew_label"] != "UNKNOWN"


def test_compute_iv_context_carries_the_real_skew_legs_through():
    spot = 100.0
    chain = pd.DataFrame([
        {"right": "P", "strike": 92.0, "dte": 20, "delta": -0.25, "implied_vol": 0.40,
         "bid": 1.0, "ask": 1.1, "mark": 1.05, "open_interest": 500, "volume": 50, "underlying_price": spot},
        {"right": "C", "strike": 108.0, "dte": 20, "delta": 0.25, "implied_vol": 0.30,
         "bid": 1.0, "ask": 1.1, "mark": 1.05, "open_interest": 500, "volume": 50, "underlying_price": spot},
        {"right": "C", "strike": 100.0, "dte": 20, "delta": 0.50, "implied_vol": 0.35,
         "bid": 2.0, "ask": 2.1, "mark": 2.05, "open_interest": 500, "volume": 50, "underlying_price": spot},
    ])
    ctx = oi.compute_iv_context(chain, "TEST")
    assert ctx.get("put_25d_iv") is not None
    assert ctx.get("call_25d_iv") is not None


def test_scanner_fast_path_enhancement_forwards_both_skew_legs():
    source = inspect.getsource(oi)
    anchor = "Best-effort: try to enhance with chain IV data if available"
    block = source[source.index(anchor): source.index(anchor) + 800]
    assert "'put_25d_iv'" in block, "put_25d_iv is hardcoded None in the scanner path and never re-enhanced"
    assert "'call_25d_iv'" in block, "call_25d_iv is hardcoded None in the scanner path and never re-enhanced"
