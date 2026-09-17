"""Business rules for the Layer 3 volatility fallback (ACK 17 Sep 2026).

Defect (investigation 17 Sep 2026): `_garch_forecast` receives numpy returns (`_log_returns` returns an
ndarray), so arch returns `conditional_volatility` as an ndarray; the code called `.iloc[-1]`, raised
AttributeError, and `except Exception: pass` hid it. The arch fallback could never return a forecast.

Model comparison (Enhancements/expression_forensics/garch_comparison_study.json): HAR-RV best (QLIKE 0.511),
GARCH(1,1) 0.593 with 6.6% non-stationary fits, EGARCH as coded unsafe (QLIKE 319; forecasts down to 0.1% of
delivered). ACK decision 17 Sep 2026: fallback order HAR-RV -> GARCH(1,1) -> EWMA; EGARCH removed.

Rules:
  F1 when HAR-RV is unavailable, GARCH(1,1) is fitted from numpy returns and returns a forecast;
  F2 EGARCH is never fitted;
  F3 a fit that arch rescaled is converted back to the caller's percent units;
  F4 a failed or non-stationary GARCH(1,1) fit is logged with its reason (never silent) and returns None;
  F5 when HAR-RV and GARCH(1,1) are both unavailable, compute_forward_variance uses EWMA;
  F6 with the real arch package (test environment), a GARCH-like numpy series yields a finite GARCH forecast.

The production venv does not include `arch`; F1–F5 use a stand-in module so they run everywhere.
"""

from __future__ import annotations

import logging
import math
import sys
import types

import numpy as np
import pandas as pd
import pytest

import layer3_forward_variance as l3


class _Result:
    def __init__(self, cond_vol, params, scale=1.0):
        self.conditional_volatility = np.asarray(cond_vol, dtype=float)   # ndarray, as arch returns for ndarray input
        self.params = pd.Series(params)
        self.scale = scale
        self.convergence_flag = 0


def _install_fake_arch(monkeypatch, behaviours):
    """behaviours: vol name -> _Result or Exception raised from fit(). Records every model requested."""
    calls = []

    def arch_model(y, vol, p, q, dist, rescale):
        calls.append(vol)
        outcome = behaviours.get(vol, AssertionError(f"{vol} must not be fitted"))

        class _Model:
            def fit(self, **_kwargs):
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
        return _Model()

    module = types.ModuleType("arch")
    module.arch_model = arch_model
    monkeypatch.setitem(sys.modules, "arch", module)
    monkeypatch.setattr(l3, "_har_rv_forecast", lambda *_a, **_k: None)
    return calls


def _returns(n=252, daily=0.02, seed=3):
    return np.random.default_rng(seed).normal(0.0, daily, n)


def _expected(last_pct, persist, lr_var_pct, horizon=20):
    avg = max(sum(lr_var_pct + persist ** h * (last_pct ** 2 - lr_var_pct) for h in range(1, horizon + 1)) / horizon, 1e-8)
    return l3._annualise(math.sqrt(avg) / 100.0)


def test_f1_garch11_forecast_from_numpy_returns(monkeypatch):
    r = _returns()
    garch = _Result(np.full(len(r), 1.8), {"omega": 0.05, "alpha[1]": 0.08, "beta[1]": 0.9})
    _install_fake_arch(monkeypatch, {"Garch": garch})
    result = l3._garch_forecast(r, horizon=20)
    assert result is not None and result["method_used"] == "GARCH"
    assert result["ann_vol"] == pytest.approx(_expected(1.8, 0.98, 0.05 / (1 - 0.98)))


def test_f2_egarch_is_never_fitted(monkeypatch):
    r = _returns()
    garch = _Result(np.full(len(r), 1.8), {"omega": 0.05, "alpha[1]": 0.08, "beta[1]": 0.9})
    calls = _install_fake_arch(monkeypatch, {"Garch": garch})
    l3._garch_forecast(r, horizon=20)
    assert calls == ["Garch"]


def test_f3_rescaled_fit_returns_percent_units(monkeypatch):
    r = _returns()
    _install_fake_arch(monkeypatch, {"Garch": _Result(np.full(len(r), 1.8), {"omega": 0.05, "alpha[1]": 0.08, "beta[1]": 0.9})})
    base = l3._garch_forecast(r, horizon=20)["ann_vol"]
    _install_fake_arch(monkeypatch, {"Garch": _Result(np.full(len(r), 18.0), {"omega": 5.0, "alpha[1]": 0.08, "beta[1]": 0.9}, scale=10.0)})
    assert l3._garch_forecast(r, horizon=20)["ann_vol"] == pytest.approx(base)


def test_f4_failed_and_non_stationary_fits_are_logged(monkeypatch, caplog):
    r = _returns()
    _install_fake_arch(monkeypatch, {"Garch": RuntimeError("garch boom")})
    with caplog.at_level(logging.WARNING, logger="layer3_forward_variance"):
        assert l3._garch_forecast(r, horizon=20) is None
    assert "GARCH(1,1)" in caplog.text and "garch boom" in caplog.text
    caplog.clear()
    _install_fake_arch(monkeypatch, {"Garch": _Result(np.full(len(r), 1.8), {"omega": 0.05, "alpha[1]": 0.3, "beta[1]": 0.8})})
    with caplog.at_level(logging.WARNING, logger="layer3_forward_variance"):
        assert l3._garch_forecast(r, horizon=20) is None
    assert "not stationary" in caplog.text


def test_f5_ewma_when_har_rv_and_garch_unavailable(monkeypatch):
    _install_fake_arch(monkeypatch, {"Garch": RuntimeError("garch boom")})
    prices = pd.Series(100 * np.exp(np.cumsum(_returns(260))))
    result = l3.compute_forward_variance("TEST", pd.DataFrame({"close": prices}), implied_vol=0.0, regime="")
    assert result.method == "EWMA_FALLBACK"


def test_f6_real_arch_garch_forecast_from_numpy_series():
    pytest.importorskip("arch")
    rng = np.random.default_rng(11)
    omega, alpha, beta, n = 0.02, 0.08, 0.9, 600
    var, r = omega / (1 - alpha - beta), []
    for _ in range(n):
        shock = rng.normal() * math.sqrt(var)
        r.append(shock)
        var = omega + alpha * shock ** 2 + beta * var
    returns = np.array(r[-252:]) / 100.0          # percent-scale process expressed as log returns
    original = l3._har_rv_forecast
    l3._har_rv_forecast = lambda *_a, **_k: None
    try:
        result = l3._garch_forecast(returns, horizon=20)
    finally:
        l3._har_rv_forecast = original
    assert result is not None and result["method_used"] == "GARCH"
    realised = float(np.std(returns)) * math.sqrt(252)
    assert 0.5 * realised < result["ann_vol"] < 2.0 * realised
