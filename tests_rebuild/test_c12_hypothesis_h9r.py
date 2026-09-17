"""H9R forward test (ACK 17 Sep 2026; SIGNAL_RESEARCH_PLAN_A.md Addendum 2) — measurement only, no authority.

Rules:
  R1 an event is a session with |open - prior close| >= gap_atr_multiple x ATR (ending the prior session),
     volume >= volume_multiple x median volume of the prior lookback, prior liquidity >= the dollar threshold, and a
     clean prior history (no one-bar move >= break ratio, no sub-cent close) — on or after the forward start only;
  R2 at most one event per ticker within the spacing (sessions); direction UP/DOWN; HELD when the session closed
     beyond its open in the gap direction, else FADED;
  R3 an outcome at horizon h is log(close[t+h] / close[t]) net of the median of the liquid, clean universe over the
     same window; it is not scored before close[t+h] exists; a break inside (t, t+h] is DATA_BREAK;
  R4 evaluation is gated: INSUFFICIENT_EVIDENCE until the minimum event dates and events exist; PASS only when the
     clustered t <= the pass threshold and |mean| exceeds the median share spread; otherwise NOT_PASSED;
  R5 the service is idempotent and appends outcomes as later sessions arrive; the report shows the forward test.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math
import sqlite3

import numpy as np
import pytest

from avshunter.c12_outcome import hypotheses as hyp
from avshunter.c12_outcome import service
from avshunter.c12_outcome.adapters import storage
from avshunter.config import ConfigRegistry
from avshunter.config.adapters import load_documents, load_lock
from avshunter.shared.xnys_calendar import is_xnys_session

NOW = datetime(2026, 11, 20, 22, 0, tzinfo=timezone.utc)


def settings(**overrides):
    base = dict(hypothesis_id="H9R_GAP_UP_REVERSAL", forward_start=date(2026, 9, 17), gap_atr_multiple=2.0,
                volume_multiple=2.0, atr_sessions=14, volume_lookback_sessions=20, liquidity_lookback_sessions=20,
                liquidity_min_dollar_volume=5_000_000.0, integrity_lookback_sessions=60, break_ratio=10.0,
                sub_cent_price=0.01, spacing_sessions=20, horizons=(5, 10, 20), primary_horizon=10,
                primary_direction="UP", min_event_dates=3, min_events=4, pass_t=-2.0)
    base.update(overrides)
    return hyp.GapHypothesisSettings(**base)


def sessions(start: date, count: int) -> list[date]:
    out, day = [], start
    while len(out) < count:
        if is_xnys_session(day):
            out.append(day)
        day += timedelta(days=1)
    return out


def panel(n_sessions=120, tickers=("GAP", "CALM", "THIN"), start=date(2026, 6, 1)):
    days = sessions(start, n_sessions)
    k = len(tickers)
    rng = np.random.default_rng(3)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, (n_sessions, k)), axis=0))
    open_ = close * (1 + rng.normal(0, 0.002, (n_sessions, k)))
    high = np.maximum(open_, close) * 1.005
    low = np.minimum(open_, close) * 0.995
    volume = np.full((n_sessions, k), 1_000_000.0)
    volume[:, tickers.index("THIN")] = 1_000.0          # illiquid: 100 x 1,000 = $100k
    return hyp.PricePanel(tuple(days), tuple(tickers), open_, high, low, close, volume)


def inject_gap(p: hyp.PricePanel, ticker: str, session: date, gap_fraction: float, volume_multiple: float, held=True):
    j, i = p.tickers.index(ticker), p.sessions.index(session)
    prev = p.close[i - 1, j]
    p.open[i, j] = prev * (1 + gap_fraction)
    p.close[i, j] = p.open[i, j] * (1 + (0.01 if (gap_fraction > 0) == held else -0.01))
    p.high[i, j] = max(p.open[i, j], p.close[i, j]) * 1.002
    p.low[i, j] = min(p.open[i, j], p.close[i, j]) * 0.998
    p.volume[i, j] = p.volume[i - 1, j] * volume_multiple
    return i


def test_r1_gap_up_with_volume_and_liquidity_is_an_event():
    p = panel()
    day = next(d for d in p.sessions if d >= date(2026, 9, 17))
    inject_gap(p, "GAP", day, 0.10, 3.0)
    events = hyp.detect_events(p, p.sessions.index(day), settings(), last_event_session={})
    assert [(e.ticker, e.direction, e.held) for e in events] == [("GAP", "UP", "HELD")]
    assert events[0].gap_atr >= 2.0 and events[0].entry_close == pytest.approx(p.close[p.sessions.index(day), 0])


@pytest.mark.parametrize("gap, vol, ticker", [(0.10, 1.2, "GAP"), (0.004, 3.0, "GAP"), (0.10, 3.0, "THIN")])
def test_r1_no_event_without_volume_size_or_liquidity(gap, vol, ticker):
    p = panel()
    day = next(d for d in p.sessions if d >= date(2026, 9, 17))
    inject_gap(p, ticker, day, gap, vol)
    assert hyp.detect_events(p, p.sessions.index(day), settings(), last_event_session={}) == []


def test_r1_before_forward_start_and_broken_history_are_excluded():
    p = panel()
    early = next(d for d in p.sessions if d < date(2026, 9, 17) and p.sessions.index(d) > 70)
    inject_gap(p, "GAP", early, 0.10, 3.0)
    assert hyp.detect_events(p, p.sessions.index(early), settings(), last_event_session={}) == []
    day = next(d for d in p.sessions if d >= date(2026, 9, 17))
    i = inject_gap(p, "GAP", day, 0.10, 3.0)
    p.close[i - 30, 0] = p.close[i - 31, 0] * 20                        # 20x one-bar move inside the lookback
    assert hyp.detect_events(p, i, settings(), last_event_session={}) == []


def test_r2_spacing_direction_and_faded():
    p = panel()
    day = next(d for d in p.sessions if d >= date(2026, 9, 17))
    i = inject_gap(p, "GAP", day, -0.10, 3.0, held=False)
    events = hyp.detect_events(p, i, settings(), last_event_session={"GAP": p.sessions[i - 5]})
    assert events == []
    events = hyp.detect_events(p, i, settings(), last_event_session={"GAP": p.sessions[i - 25]})
    assert [(e.direction, e.held) for e in events] == [("DOWN", "FADED")]


def test_r3_outcome_net_of_universe_median_and_data_break():
    p = panel()
    day = next(d for d in p.sessions if d >= date(2026, 9, 17))
    i = inject_gap(p, "GAP", day, 0.10, 3.0)
    event = hyp.detect_events(p, i, settings(), last_event_session={})[0]
    out = hyp.score_outcome(p, event, 5, settings())
    raw = math.log(p.close[i + 5, 0] / p.close[i, 0])
    calm = math.log(p.close[i + 5, 1] / p.close[i, 1])
    assert out.state == "SCORED" and out.raw_return == pytest.approx(raw)
    assert out.net_return == pytest.approx(raw - np.median([raw, calm]))       # THIN is not liquid
    p.close[i + 3, 0] = p.close[i + 2, 0] * 15
    assert hyp.score_outcome(p, event, 5, settings()).state == "DATA_BREAK"
    short = hyp.PricePanel(p.sessions[:i + 3], p.tickers, p.open[:i + 3], p.high[:i + 3], p.low[:i + 3],
                           p.close[:i + 3], p.volume[:i + 3])
    assert hyp.score_outcome(short, event, 5, settings()) is None


def test_r4_gate_and_verdict():
    s = settings(min_event_dates=3, min_events=6, pass_t=-2.0)
    few = [("d1", -0.02, 0.001)] * 3
    assert hyp.evaluate(few, s)["verdict"] == "INSUFFICIENT_EVIDENCE"
    strong = [(f"d{k}", -0.02 - 0.001 * k, 0.001) for k in range(12)]
    assert hyp.evaluate(strong, s)["verdict"] == "PASS"
    weak = [(f"d{k}", (-1) ** k * 0.02, 0.001) for k in range(12)]
    assert hyp.evaluate(weak, s)["verdict"] == "NOT_PASSED"
    costly = [(f"d{k}", -0.002 - 0.0001 * k, 0.05) for k in range(12)]
    assert hyp.evaluate(costly, s)["verdict"] == "NOT_PASSED"


def test_r5_service_idempotent_and_appends_outcomes(tmp_path):
    p = panel(n_sessions=160)
    day = next(d for d in p.sessions if d >= date(2026, 9, 17))
    i = inject_gap(p, "GAP", day, 0.10, 3.0)
    db = tmp_path / "prices.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE ohlcv_daily (ticker TEXT, trading_date TEXT, open REAL, high REAL, low REAL, close REAL, "
                "volume REAL, bar_status TEXT)")
    rows = [(t, d.isoformat(), p.open[a, b], p.high[a, b], p.low[a, b], p.close[a, b], p.volume[a, b], "COMPLETE")
            for a, d in enumerate(p.sessions) for b, t in enumerate(p.tickers)]
    con.executemany("INSERT INTO ohlcv_daily VALUES (?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    store = storage.connect(tmp_path / "scoring.sqlite")
    documents = load_documents()
    snap = ConfigRegistry.from_documents(documents, load_lock()).resolve(date(2026, 9, 17))
    first = service.track_hypotheses(store, p.sessions[i + 6], snap, NOW, db, settings_override=settings())
    assert first["new_events"] == 1 and first["new_outcomes"] == 1           # only h=5 available
    again = service.track_hypotheses(store, p.sessions[i + 6], snap, NOW, db, settings_override=settings())
    assert again["new_events"] == 0 and again["new_outcomes"] == 0
    later = service.track_hypotheses(store, p.sessions[i + 25], snap, NOW, db, settings_override=settings())
    assert later["new_outcomes"] == 2                                          # h=10 and h=20 appended
    path = service.build_report(store, p.sessions[i + 25], snap, tmp_path / "report")
    assert "Forward hypothesis tests" in path.read_text(encoding="utf-8")


def test_registered_settings_load_from_configuration():
    documents = load_documents()
    snap = ConfigRegistry.from_documents(documents, load_lock()).resolve(date(2026, 9, 17))
    s = hyp.settings_from_snapshot(snap)
    assert s.hypothesis_id == "H9R_GAP_UP_REVERSAL" and s.forward_start == date(2026, 9, 17)
    assert s.primary_horizon == 10 and s.primary_direction == "UP" and s.pass_t < 0
