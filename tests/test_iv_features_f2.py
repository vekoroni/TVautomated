"""F2: IV direction and IV percentile read the ticker's own IV history (ACK, 19 Sep 2026).

Run 20260918_112522:
- iv_direction was STABLE and iv_accel_detected False on every row: the history loader read
  runs/<run>/iv_history.json, which nothing writes (and an in-memory cache that already held today's IV).
- "IVP" placed today's ATM IV inside the range of 21-day REALISED volatility - an IV-vs-realised measure,
  not an IV percentile - yet it drove the options score (up to 22 points) and the cheap/expensive label.
The IV cache (iv_history_cache.db, restored 8-17 Sep and refreshed by every evening run) is the history source,
point-in-time (samples strictly before the evidence session). The realised-range measure is kept under its own
name; the source of the percentile is recorded; missing history is reported, never read as STABLE.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pandas as pd
import pytest

from scripts import avshunter_options_intelligence as oi

AS_OF = date(2026, 9, 18)


@pytest.fixture
def cache(tmp_path, monkeypatch):
    path = tmp_path / "iv_cache.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE iv_history (ticker TEXT, sample_date TEXT, atm_iv REAL, source TEXT, updated_at TEXT)")
    for i in range(1, 41):                                            # 40 daily samples: 0.20 ... 0.59
        con.execute("INSERT INTO iv_history VALUES ('AAA', ?, ?, 'x', 'x')",
                    ((AS_OF - timedelta(days=i)).isoformat(), 0.60 - i * 0.01))
    con.execute("INSERT INTO iv_history VALUES ('AAA', ?, 0.99, 'x', 'x')", (AS_OF.isoformat(),))   # same day: excluded
    con.execute("INSERT INTO iv_history VALUES ('BBB', ?, 0.30, 'x', 'x')", ((AS_OF - timedelta(days=1)).isoformat(),))
    con.commit()
    monkeypatch.setattr(oi, "IV_CACHE_DB", path)
    oi._iv_history_samples.cache_clear()
    return path


def test_history_is_point_in_time_and_ordered(cache):
    samples = oi._iv_history_samples("AAA", AS_OF.isoformat())
    assert len(samples) == 40 and samples[-1] == ((AS_OF - timedelta(days=1)).isoformat(), pytest.approx(0.59))
    assert all(d < AS_OF.isoformat() for d, _ in samples)


def test_the_true_iv_percentile_ranks_today_against_the_tickers_own_iv(cache):
    values = [v for _, v in oi._iv_history_samples("AAA", AS_OF.isoformat())]
    assert oi.iv_percentile_from_history(0.455, values) == pytest.approx(26 / 40)      # 0.20..0.45 below
    assert oi.iv_percentile_from_history(0.45, values[:5]) is None                     # too little history


def test_the_percentile_uses_iv_history_and_keeps_the_realised_range_measure(cache):
    result = {"iv_percentile": 0.90, "ivp_252d": 0.90, "ivp_30d": 0.70, "iv_rank": 90.0, "ivp_label": "EXPENSIVE"}
    oi._apply_true_iv_percentile(result, "AAA", 0.255, AS_OF)
    assert result["iv_percentile"] == pytest.approx(6 / 40, abs=1e-3) and result["ivp_252d"] == pytest.approx(6 / 40, abs=1e-3)
    assert result["iv_percentile_source"] == "IV_HISTORY_252D" and result["iv_history_samples"] == 40
    assert result["ivp_label"] == "CHEAP"
    assert result["iv_vs_rv_range_252d"] == 0.90 and result["iv_vs_rv_range_30d"] == 0.70   # kept, renamed


def test_insufficient_iv_history_keeps_the_proxy_and_says_so(cache):
    result = {"iv_percentile": 0.90, "ivp_252d": 0.90, "ivp_30d": 0.70, "iv_rank": 90.0, "ivp_label": "EXPENSIVE"}
    oi._apply_true_iv_percentile(result, "BBB", 0.25, AS_OF)
    assert result["iv_percentile"] == 0.90 and result["iv_percentile_source"] == "RV_RANGE_PROXY"
    assert result["iv_history_samples"] == 1


def test_iv_direction_reads_the_recent_history(cache):
    history = oi._load_iv_history("AAA", as_of=AS_OF)
    chain = pd.DataFrame({"dte": [15, 50], "implied_vol": [0.7, 0.7], "strike": [100, 100]})
    regime = oi.classify_iv_regime(0.59 * 1.25, chain, history, 100.0)
    assert regime["iv_direction"] == "RISING" and regime["iv_accel_detected"] is True


def test_no_iv_history_is_unavailable_not_stable():
    chain = pd.DataFrame({"dte": [15, 50], "implied_vol": [0.7, 0.7], "strike": [100, 100]})
    assert oi.classify_iv_regime(0.5, chain, [], 100.0)["iv_direction"] == "UNAVAILABLE"


def test_compute_iv_context_uses_the_store_and_the_true_percentile():
    import inspect
    source = inspect.getsource(oi.compute_iv_context)
    assert "_load_iv_history(ticker, as_of=" in source
    assert "_apply_true_iv_percentile(result, ticker, atm_iv," in source
