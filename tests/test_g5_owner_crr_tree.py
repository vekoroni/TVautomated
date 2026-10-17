"""G5/G9 (ACK approved 17 Oct 2026, D3): the pricing module owns its American tree; EV3's stays frozen.

Design: Enhancements/options_valuation_review/G5_G9_ONE_PRICER_ONE_BASIS_DESIGN_20261017.md section 4.1 ("the American
tree is copied into this module from vanguard/ev_engine_v3.py; EV3 itself is not edited").
Measured 17 Oct: EV3's tree takes about 40 ms per value at 300 steps because it rebuilds every level's prices;
Lane B's shortlist needs about 30,000 values a morning (689 s against 178 s before G5).

Business rules:
- The module's tree gives the same value as EV3's tree for every contract (same model, same steps).
- The card engine (option_value) uses the module's own tree.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from domain import option_valuation as ov  # noqa: E402
from vanguard.ev_engine_v3 import american_option_price  # noqa: E402

CASES = [(side, spot, strike, years, rate, q, vol)
         for side in ("CALL", "PUT")
         for spot in (8.0, 14.2, 100.0)
         for strike in (0.8, 1.0, 1.25)
         for years in (0.02, 0.25, 1.1)
         for rate, q in ((0.0428, 0.0), (0.0428, 0.03), (0.0, 0.0))
         for vol in (0.25, 0.9)]


@pytest.mark.parametrize("side,spot,k,years,rate,q,vol", CASES)
def test_the_module_tree_equals_ev3_s_tree(side, spot, k, years, rate, q, vol):
    strike = spot * k
    ev3 = american_option_price(spot, strike, years, rate, q, vol, side, steps=300)
    own = ov.american_crr_value(spot, strike, years, rate, q, vol, side, steps=300)
    assert own == pytest.approx(ev3, rel=1e-9, abs=1e-12)


def test_the_card_engine_uses_the_module_tree(monkeypatch):
    calls = []
    real = ov.american_crr_value
    monkeypatch.setattr(ov, "american_crr_value", lambda *a, **k: calls.append(1) or real(*a, **k))
    out = ov.option_value("PUT", 14.2, 15.0, 0.25, 0.6, rate=0.0428, dividend_yield=0.0, style="AMERICAN")
    assert calls and out["model"] == "AMERICAN_CRR"


def test_many_contracts_in_one_pass_equal_one_at_a_time():
    import numpy as np
    sides = np.array([c[0] == "CALL" for c in CASES])
    spot = np.array([c[1] for c in CASES]); strike = spot * np.array([c[2] for c in CASES])
    years = np.array([c[3] for c in CASES]); rate = np.array([c[4] for c in CASES])
    q = np.array([c[5] for c in CASES]); vol = np.array([c[6] for c in CASES])
    got = ov.american_crr_values(spot, strike, years, rate, q, vol, sides, steps=300)
    for i, case in enumerate(CASES):
        one = ov.american_crr_value(spot[i], strike[i], years[i], rate[i], q[i], vol[i], case[0], steps=300)
        assert got[i] == pytest.approx(one, rel=1e-9, abs=1e-12)


def test_many_contracts_in_one_pass_are_fast_enough_for_lane_b():
    import numpy as np
    n = 300
    start = time.perf_counter()
    ov.american_crr_values(np.full(n, 14.2), np.linspace(12, 17, n), np.full(n, 0.25), np.full(n, 0.0428),
                           np.full(n, 0.02), np.full(n, 0.6), np.zeros(n, bool), steps=300)
    # measured 17 Oct on ACK's PC: about 2.5 ms per value (EV3's tree: about 40 ms); 5 ms leaves room for load
    assert (time.perf_counter() - start) / n < 0.005
