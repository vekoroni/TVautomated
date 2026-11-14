"""D1: ranges to sessions 5/10/20 are cumulative, not band increments.

The volatility fit is unchanged. Old saved incremental rows remain readable;
new cumulative percent aliases agree with the canonical fractional budgets.
"""
import math
import socket

import numpy as np
import pandas as pd
import pytest

import layer3_forward_variance as l3
from domain.volatility_budget import cumulative_expected_move_pct


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("D1 tests must not use the network")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


def prices(n=260):
    close = 100 * np.exp(np.cumsum(np.random.default_rng(41).normal(0, .02, n)))
    return pd.DataFrame({"close": close, "high": close * 1.01, "low": close * .99})


@pytest.mark.parametrize("vol", [.001, .05, .30, 1.5, 3.0, 4.0])
@pytest.mark.parametrize("method", ["HAR_RV", "GARCH"])
def test_cumulative_ranges_agree_with_session_budgets_and_preserve_fit(monkeypatch, vol, method):
    monkeypatch.setattr(l3, "_garch_forecast", lambda *_a, **_k: {
        "ann_vol": vol, "method_used": method, "alpha": .08, "beta": .9, "omega": .01,
    })
    result = l3.compute_forward_variance("TEST", prices(), implied_vol=.40)
    bounded = min(max(vol, l3.VOL_FLOOR), l3.VOL_CAP)
    assert result.forward_realised_vol == bounded
    assert result.forward_realised_vol_raw == vol
    assert result.method == method
    assert result.iv_tailwind_score == pytest.approx(.40 - bounded)
    moves = [result.expected_move_1_5d, result.expected_move_6_10d, result.expected_move_11_20d]
    assert moves == pytest.approx([bounded * math.sqrt(n / 252) * 100 for n in (5, 10, 20)])
    assert 0 < moves[0] <= moves[1] <= moves[2]
    row = result.to_dict()
    assert row["l3_expected_move_legacy_convention"] == "CUMULATIVE_1SIGMA"
    assert row["l3_expected_move_legacy_horizon_basis"] == "TRADING_SESSIONS"
    for horizon, n, alias in zip(("1_5D", "6_10D", "11_20D"), (5, 10, 20),
                                ("1_5d", "6_10d", "11_20d")):
        assert row[f"l3_expected_move_{alias}"] == pytest.approx(row[f"expected_move_{n}d_fraction"] * 100, abs=.0051)
        # Dropped canonical fields must not cause the new aliases to be summed twice.
        legacy_only = {k: v for k, v in row.items() if not k.startswith("expected_move_")}
        assert cumulative_expected_move_pct(legacy_only, horizon) == row[f"l3_expected_move_{alias}"]


@pytest.mark.parametrize("n,method", [(40, "EWMA_FALLBACK"), (15, "ATR_PROXY")])
def test_fallback_ranges_are_also_cumulative(n, method):
    result = l3.compute_forward_variance("SHORT", prices(n))
    assert result.method == method
    assert result.expected_move_6_10d == pytest.approx(result.expected_move_1_5d * math.sqrt(2))
    assert result.expected_move_11_20d == pytest.approx(result.expected_move_1_5d * 2)


def test_missing_history_stays_missing():
    row = l3.compute_forward_variance("MISSING", pd.DataFrame()).to_dict()
    assert all(row[f"l3_expected_move_{key}"] is None for key in ("1_5d", "6_10d", "11_20d"))
    assert cumulative_expected_move_pct(row, "6_10D") is None


@pytest.mark.parametrize("prefix", ["l3_", "garch_"])
def test_old_unmarked_saved_increments_remain_unchanged(prefix):
    row = {prefix + "expected_move_" + k: v for k, v in zip(("1_5d", "6_10d", "11_20d"), (3., 1., 2.))}
    assert cumulative_expected_move_pct(row, "6_10D") == 4.
    assert cumulative_expected_move_pct(row, "11_20D") == 6.


def test_unknown_alias_convention_is_not_guessed():
    assert cumulative_expected_move_pct({"l3_expected_move_6_10d": 4.,
        "l3_expected_move_legacy_convention": "UNKNOWN"}, "6_10D") is None
