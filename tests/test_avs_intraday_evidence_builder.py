"""Step 4 builder (ACK 5 Oct 2026): intraday BEH-001 evidence, built and tested like the daily panels.

Rules fixed before results are read (see the builder's docstring):
- Panels split by a stable hash of the ticker (a ticker is never in both).
- Forward bars after the cut are the stored 5-minute bars resampled with the engine's own resample_intraday to the
  setup's timeframe, over a fixed own-timeframe window (60m 33, 15m 52, 5m 78 bars).
- Outcomes use C12's classify + evaluate_passage: the level touched first is EVENT, the invalidation first is
  INVALIDATION, neither inside the window is CENSORED (never success or failure).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Enhancements" / "direction_evidence"))

import beh001_intraday_evidence as ie


def _bars(session, closes):
    start = pd.Timestamp(f"{session} 13:30", tz="UTC")
    t = pd.date_range(start, periods=len(closes), freq="5min")
    return pd.DataFrame({"timestamp_utc": t, "open": closes, "high": [c + 0.05 for c in closes],
                         "low": [c - 0.05 for c in closes], "close": closes, "volume": 1000})


def test_panel_split_is_stable_and_disjoint():
    names = [f"T{i:03d}" for i in range(200)]
    first = {t: ie.panel_of(t) for t in names}
    assert first == {t: ie.panel_of(t) for t in names}
    assert set(first.values()) == {"original", "holdout"}
    assert 60 < sum(v == "original" for v in first.values()) < 140


def test_forward_bars_are_resampled_to_the_setup_timeframe():
    bars = pd.concat([_bars("2026-06-02", [10.0] * 78), _bars("2026-06-03", [10.0] * 78)], ignore_index=True)
    fwd = ie.forward_bars(bars, after_session="2026-06-01", timeframe="15m")
    assert len(fwd) == 52                                       # 2 sessions x 26 fifteen-minute bars
    assert len(ie.forward_bars(bars, after_session="2026-06-01", timeframe="5m")) == 78


def test_level_first_is_event_and_invalidation_first_is_invalidation():
    rising = _bars("2026-06-02", [10.0 + 0.1 * i for i in range(78)])
    falling = _bars("2026-06-02", [10.0 - 0.1 * i for i in range(78)])
    up = ie.score(direction="BULL", close=10.0, invalidation=9.0, target=11.0,
                  fwd=ie.forward_bars(rising, after_session="2026-06-01", timeframe="5m"), window=78)
    down = ie.score(direction="BULL", close=10.0, invalidation=9.0, target=11.0,
                    fwd=ie.forward_bars(falling, after_session="2026-06-01", timeframe="5m"), window=78)
    flat = ie.score(direction="BULL", close=10.0, invalidation=9.0, target=11.0,
                    fwd=ie.forward_bars(_bars("2026-06-02", [10.0] * 78), after_session="2026-06-01",
                                        timeframe="5m"), window=78)
    assert up[0] == "EVENT" and down[0] == "INVALIDATION" and flat[0] == "CENSORED"
    assert 0 < up[1] <= 78


def test_packager_uses_the_original_panel_and_states_pooled_scope():
    import beh001_intraday_duration_pack as pack
    recs = ([{"panel": "original", "timeframe": "60m", "signal_type": "S", "direction": "BULL", "test": "OUTCOME",
              "cause": "EVENT", "time_bars": 5, "age_bars": 1}] * 40
            + [{"panel": "holdout", "timeframe": "60m", "signal_type": "S", "direction": "BULL", "test": "OUTCOME",
                "cause": "INVALIDATION", "time_bars": 2, "age_bars": 1}] * 40)
    groups = pack.build(recs, [0, 3, 6, 11, 21], min_n=30)["groups"]
    allg = [g for g in groups if g["age_bucket"] == "ALL"]
    assert {g["scope"] for g in allg} == {"LOCAL", "CAMPAIGN"}
    assert all(g["scope_basis"] == "POOLED_OVER_SCOPE" for g in groups)
    assert allg[0]["n"] == 40 and allg[0]["p_event_at_limit"] == 1.0          # holdout rows never enter the evidence
    assert pack.build(recs[:10], [0, 3, 6, 11, 21], min_n=30)["groups"][0]["status"] == "INSUFFICIENT_SAMPLE"
