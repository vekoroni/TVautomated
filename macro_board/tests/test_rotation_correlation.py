"""Live sector correlation (ACK 16 Oct 2026: "a breakdown of the sectors and their correlation, that is how we
start to understand the psychology of the markets"). Business rules, written before the engine. Display only."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from macro_board import rotation as rot

CFG = {"short_sessions": 60, "long_sessions": 250, "min_sessions": 40, "tail_quantile": 0.1,
       "crowding_low_pctile": 20, "crowding_high_pctile": 80, "crowding_change_sessions": 20,
       "shift_min_abs_change": 0.3, "max_shifts": 5, "history_points": 250,
       "cross_assets": {"USO": "Oil", "TLT": "Long Treasuries"}}


def _closes(returns: pd.DataFrame) -> pd.DataFrame:
    return 100 * (1 + returns).cumprod()


def _market(n=400, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n)
    spy = pd.Series(rng.normal(0, 0.01, n), index=idx)
    return idx, spy, rng


def test_the_matrix_is_symmetric_with_ones_on_the_diagonal_and_reads_together_and_opposite():
    idx, spy, rng = _market()
    a = pd.Series(rng.normal(0, 0.01, len(idx)), index=idx)
    rets = pd.DataFrame({"SPY": spy, "AAA": a, "BBB": a, "CCC": -a, "USO": rng.normal(0, .01, len(idx)),
                         "TLT": rng.normal(0, .01, len(idx))})
    out = rot.correlation_block(_closes(rets), ["AAA", "BBB", "CCC"], [], "SPY", CFG)
    m = out["matrix"]["long"]
    assert m["AAA"]["BBB"] == pytest.approx(1.0, abs=1e-3)
    assert m["AAA"]["CCC"] == pytest.approx(-1.0, abs=1e-3)
    assert m["BBB"]["AAA"] == m["AAA"]["BBB"] and m["AAA"]["AAA"] == 1.0


def test_the_relative_matrix_removes_the_market_so_only_rotation_is_left():
    idx, spy, rng = _market()
    rets = pd.DataFrame({"SPY": spy, **{t: spy + rng.normal(0, 0.003, len(idx)) for t in ("AAA", "BBB")},
                         "USO": rng.normal(0, .01, len(idx)), "TLT": rng.normal(0, .01, len(idx))})
    out = rot.correlation_block(_closes(rets), ["AAA", "BBB"], [], "SPY", CFG)
    assert out["matrix"]["long"]["AAA"]["BBB"] > 0.8               # both just follow the market
    assert abs(out["matrix"]["relative"]["AAA"]["BBB"]) < 0.2       # no shared rotation once SPY is removed


def test_beta_and_worst_and_best_day_capture_are_measured_against_spy():
    idx, spy, rng = _market()
    rets = pd.DataFrame({"SPY": spy, "UP2": 2 * spy, "HEDGE": -spy, "USO": rng.normal(0, .01, len(idx)),
                         "TLT": rng.normal(0, .01, len(idx))})
    out = rot.correlation_block(_closes(rets), ["UP2", "HEDGE"], [], "SPY", CFG)
    up2, hedge = out["to_benchmark"]["UP2"], out["to_benchmark"]["HEDGE"]
    assert up2["beta"] == pytest.approx(2.0, abs=0.02) and up2["down_capture"] == pytest.approx(2.0, abs=0.02)
    assert hedge["beta"] == pytest.approx(-1.0, abs=0.02) and hedge["down_capture"] < 0
    assert hedge["character"] == "HEDGE" and up2["character"] == "AMPLIFIER"


def test_the_strongest_outside_driver_of_a_sectors_relative_move_is_named():
    idx, spy, rng = _market()
    oil = pd.Series(rng.normal(0, 0.015, len(idx)), index=idx)
    rets = pd.DataFrame({"SPY": spy, "XLE": spy + oil, "USO": oil, "TLT": rng.normal(0, .01, len(idx))})
    out = rot.correlation_block(_closes(rets), ["XLE"], [], "SPY", CFG)
    d = out["to_benchmark"]["XLE"]["driver"]
    assert d["asset"] == "USO" and d["corr"] > 0.9


def test_crowding_is_low_when_sectors_stop_moving_together_and_its_percentile_is_against_its_own_history():
    idx, spy, rng = _market(n=500)
    common = pd.Series(rng.normal(0, 0.01, len(idx)), index=idx)
    quiet = idx >= idx[-60]                                          # the last 60 sessions decouple
    rets = {"SPY": spy, "USO": rng.normal(0, .01, len(idx)), "TLT": rng.normal(0, .01, len(idx))}
    for t in ("AAA", "BBB", "CCC", "DDD"):
        own = pd.Series(rng.normal(0, 0.01, len(idx)), index=idx)
        rets[t] = np.where(quiet, own, common + 0.3 * own)
    out = rot.correlation_block(_closes(pd.DataFrame(rets, index=idx)), ["AAA", "BBB", "CCC", "DDD"], [], "SPY", CFG)
    cr = out["crowding"]
    assert cr["state"] == "LOW" and cr["pctile"] <= 20
    assert cr["now"] < cr["median"]
    assert cr["change_vs_prior"] < 0                                 # falling over the last 20 sessions
    assert len(cr["history"]) <= CFG["history_points"]


def test_relationships_that_changed_recently_are_listed_as_shifts():
    idx, spy, rng = _market(n=400)
    a = pd.Series(rng.normal(0, 0.01, len(idx)), index=idx)
    b = a.copy()
    b[idx >= idx[-60]] = -a[idx >= idx[-60]]                         # flipped in the last 60 sessions
    rets = pd.DataFrame({"SPY": spy, "AAA": a, "BBB": b, "CCC": rng.normal(0, .01, len(idx)),
                         "USO": rng.normal(0, .01, len(idx)), "TLT": rng.normal(0, .01, len(idx))})
    out = rot.correlation_block(_closes(rets), ["AAA", "BBB", "CCC"], [], "SPY", CFG)
    top = out["shifts"][0]
    assert {top["a"], top["b"]} == {"AAA", "BBB"} and top["short"] < 0 < top["long"]


def test_a_ticker_without_enough_history_is_missing_not_zero():
    idx, spy, rng = _market()
    young = pd.Series(np.nan, index=idx)
    young.iloc[-20:] = rng.normal(0, 0.01, 20)
    rets = pd.DataFrame({"SPY": spy, "AAA": rng.normal(0, .01, len(idx)), "NEW": young,
                         "USO": rng.normal(0, .01, len(idx)), "TLT": rng.normal(0, .01, len(idx))})
    closes = 100 * (1 + rets.fillna(0)).cumprod()
    closes.loc[young.isna(), "NEW"] = np.nan
    out = rot.correlation_block(closes, ["AAA", "NEW"], [], "SPY", CFG)
    assert "NEW" in out["missing"] and "NEW" not in out["to_benchmark"]
    assert out["matrix"]["long"]["AAA"].get("NEW") is None
