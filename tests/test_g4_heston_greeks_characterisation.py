"""G4 characterisation (ACK approved 17 Oct 2026): pins the Heston Greek path as it behaves before the fix.

Design: Enhancements/options_valuation_review/G4_HESTON_GREEKS_ROOT_CAUSE_AND_DESIGN_20261017.md.
On a platform without signal.SIGALRM (Windows) the Nelder-Mead calibration can never run and the analytical proxy is
used. The proxy's at-the-money variance then drives Black-Scholes Greeks for every strike.
"""
from __future__ import annotations

import math
import signal
import sys
from pathlib import Path

import pandas as pd
import pytest
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import avshunter_options_intelligence as oi  # noqa: E402

SPOT = 100.0


def skewed_chain() -> pd.DataFrame:
    """A small-cap style chain: ATM IV 50%, downside puts far richer (skew), a back month at 45%."""
    rows = []
    for dte, atm in ((35, 0.50), (90, 0.45)):
        for strike in (70, 80, 90, 95, 100, 105, 110, 120):
            for right in ("C", "P"):
                iv = atm + max(0.0, (100 - strike) / 100.0) * 2.0      # steep put-side skew
                t = dte / 365.0
                d1 = (math.log(SPOT / strike) + 0.5 * iv * iv * t) / (iv * math.sqrt(t))
                delta = norm.cdf(d1) if right == "C" else norm.cdf(d1) - 1.0
                rows.append({"strike": float(strike), "dte": float(dte), "implied_vol": iv, "right": right,
                             "delta": delta, "open_interest": 5000.0})
    return pd.DataFrame(rows)


def provider_put() -> dict:
    """The provider's quote for an OTM put whose own IV (90%) sits far above the ATM IV."""
    return {"strike": 80.0, "dte": 35, "right": "P", "iv": 0.90, "implied_vol": 0.90,
            "delta": -0.2585, "gamma": 0.0215, "theta": -0.0712, "vega": 0.0861}


@pytest.fixture
def no_sigalrm(monkeypatch):
    monkeypatch.delattr(signal, "SIGALRM", raising=False)


def test_without_sigalrm_the_calibration_falls_to_the_analytical_proxy(no_sigalrm):
    params = oi.calibrate_heston(skewed_chain(), SPOT)
    assert params["method"] == "analytical_proxy"
    assert params["fit_error"] is None
    assert params["atm_iv"] == pytest.approx(0.50)


def test_the_atm_variance_model_greeks_are_kept_display_only_and_differ_from_the_provider(no_sigalrm):
    """Before G4 these values overwrote the provider's delta/gamma/theta/vega (source HESTON_ATM_VARIANCE_MODEL).
    The model calculation is unchanged; it is now published only as model_atm_* (repair, don't delete)."""
    params = oi.calibrate_heston(skewed_chain(), SPOT)
    enriched = oi.enrich_contract_with_heston_greeks(provider_put(), params, SPOT)
    t = 35 / 365.0
    sig = math.sqrt(params["v0"])
    d1, _ = oi._d1d2(SPOT, 80.0, t, sig, oi.RISK_FREE_RATE)
    assert enriched["model_atm_delta"] == pytest.approx(norm.cdf(d1) - 1.0)
    assert enriched["model_atm_delta"] != pytest.approx(provider_put()["delta"], abs=0.01)
    assert enriched["delta"] == provider_put()["delta"]
    assert enriched["heston_used"] is True
