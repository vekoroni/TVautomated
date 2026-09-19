"""F8: physics runs on measured inputs, not neutral defaults (ACK, 19 Sep 2026).

Run 20260918_112522: physics_data_quality = DEGRADED_DEFAULTS on 1,580 of 1,580 Vanguard rows; seven inputs were
neutral defaults (avg_volume, beta, gap_pct, iv_rank, return_5d, return_10d, spread_pct_mid).
- gap_pct: Discovery has it on every row; the physics copy list omitted it.
- return_5d / return_10d / avg_volume / beta: computed nowhere. Now from the canonical price store at the row's
  evidence session (bar_data_asof), point-in-time. Returns are fractions (physics reads |x| <= 1 as a fraction).
- iv_rank and the option spread do not exist before the options stage: they stay flagged defaults, never invented.
"""

from __future__ import annotations

import inspect
import json
import sqlite3
from datetime import date, timedelta

import pytest

from vanguard import physics_state_engine as phys


def _store(path, series: dict, last: date):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS ohlcv_daily (ticker TEXT, trading_date TEXT, close REAL, volume REAL)")
    for symbol, bars in series.items():
        for i, (close, volume) in enumerate(reversed(bars)):
            con.execute("INSERT INTO ohlcv_daily VALUES (?, ?, ?, ?)",
                        (symbol, (last - timedelta(days=i)).isoformat(), close, volume))
    con.commit()
    con.close()


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "prices.sqlite"
    last = date(2026, 9, 17)
    spy, tkr = [100.0], [50.0]
    for i in range(1, 70):                               # ticker moves exactly twice SPY each day
        r = 0.01 if i % 2 else -0.005
        spy.append(spy[-1] * (1 + r))
        tkr.append(tkr[-1] * (1 + 2 * r))
    _store(path, {"SPY": [(c, 1e8) for c in spy], "ABC": [(c, 2_000_000.0) for c in tkr]}, last)
    _store(path, {"ABC": [(999.0, 1.0)]}, last + timedelta(days=1))   # after the evidence session: ignored
    monkeypatch.setattr(phys, "CANONICAL_PRICE_DB", path)
    return last, tkr


def test_price_inputs_are_measured_point_in_time(store):
    last, tkr = store
    inputs = phys.physics_price_inputs("ABC", last.isoformat())
    assert inputs["return_5d"] == pytest.approx(tkr[-1] / tkr[-6] - 1)          # a fraction
    assert inputs["return_10d"] == pytest.approx(tkr[-1] / tkr[-11] - 1)
    assert inputs["avg_volume"] == pytest.approx(2_000_000.0)
    assert inputs["beta"] == pytest.approx(2.0, abs=1e-6)
    assert inputs["physics_price_inputs_state"] == "CANONICAL_PRICE_STORE"


def test_missing_prices_leave_the_inputs_absent_and_say_why(store):
    inputs = phys.physics_price_inputs("NOPE", store[0].isoformat())
    assert "return_5d" not in inputs and "beta" not in inputs
    assert inputs["physics_price_inputs_state"] == "TICKER_PRICES_UNAVAILABLE"


def test_physics_counts_only_the_inputs_that_are_really_missing(store):
    last, _ = store
    row = {"ticker": "ABC", "gap_pct": 1.2, "atr_percentile_rank": 40, "adx_14": 22, "volume_ratio": 1.1,
           **phys.physics_price_inputs("ABC", last.isoformat())}
    defaulted = set(json.loads(phys.calculate_market_physics(row)["physics_defaulted_fields"]))
    assert not defaulted & {"avg_volume", "beta", "gap_pct", "return_5d", "return_10d"}
    assert {"iv_rank", "spread_pct_mid"} <= defaulted          # the two that cannot exist before options


def test_the_vanguard_runner_supplies_the_inputs_before_physics():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "scripts" / "run_vanguard_from_packages.py").read_text(
        encoding="utf-8")
    assert "physics_price_inputs(ticker, _disc_row.get(\"bar_data_asof\"))" in source
    copy_list = source[source.index("def signal_to_row("):source.index("calculate_market_physics(row, macro_context")]
    for field in ("gap_pct", "return_5d", "return_10d", "beta"):
        assert f'"{field}"' in copy_list, field
