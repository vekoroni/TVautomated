"""P0-02 (Phase 1): compression is one connected episode with recorded boundaries.

Business rules (design §6.2):
- A contraction has a start bar; its box is the high/low of the WHOLE episode, not of the last few bars.
- The episode keeps one identity from bar to bar while it lasts (same start), so its development can be followed.
- The box only widens when a later bar inside the episode exceeds it (a revision), never shrinks.
- No contraction -> no episode. Compression never sets a direction (unchanged rule).
"""
import copy

import numpy as np
import pandas as pd

from domain.structure_behaviour.compression import compression_context
from domain.structure_behaviour.engine import analyse_timeframe
from domain.structure_behaviour.policy import load_policy
from domain.structure_behaviour.sequences import build_sequences

POLICY = copy.deepcopy(dict(load_policy()))
POLICY["timeframes"]["1d"]["min_bars"] = 20


def _bars(wide=80, tight=12, seed=3, extra=None):
    rng = np.random.default_rng(seed)
    close = [100.0]
    ranges = []
    for i in range(wide):
        close.append(close[-1] * (1 + rng.normal(0, 0.02)))
        ranges.append(0.04)
    base = close[-1]
    for i in range(tight):
        close.append(base * (1 + 0.001 * np.sin(i)))
        ranges.append(0.006)
    for c, r in (extra or []):
        close.append(base * c)
        ranges.append(r)
    close = np.array(close[1:])
    ranges = np.array(ranges)
    high, low = close * (1 + ranges / 2), close * (1 - ranges / 2)
    dates = pd.bdate_range("2025-01-02", periods=len(close))
    return pd.DataFrame({"date": dates, "open": close, "high": high, "low": low, "close": close,
                         "volume": 1_000_000.0})


def _ctx(bars):
    return compression_context(build_sequences(bars, "1d", POLICY), POLICY)


def test_episode_box_covers_the_whole_contraction():
    bars = _bars()
    c = _ctx(bars)
    assert c["state"] == "CONTRACTING"
    start = pd.Timestamp(c["episode_start"])
    tight = bars[bars["date"] >= start]
    assert len(tight) >= 8                                   # the episode spans the tight bars, not 5
    assert c["box_high"] == tight["high"].max() and c["box_low"] == tight["low"].min()


def test_episode_identity_is_stable_while_it_lasts():
    bars = _bars()
    a, b = _ctx(bars.iloc[:-1]), _ctx(bars)
    assert a["state"] == b["state"] == "CONTRACTING"
    assert a["episode_start"] == b["episode_start"]


def test_box_widens_only_by_revision_inside_the_episode():
    base = _bars()
    later = _bars(extra=[(1.004, 0.006)])                   # still tight, closes a little above the old box
    a, b = _ctx(base), _ctx(later)
    assert b["episode_start"] == a["episode_start"]
    assert b["box_high"] >= a["box_high"] and b["box_low"] <= a["box_low"]


def test_no_contraction_means_no_episode():
    bars = _bars(tight=0)
    c = _ctx(bars)
    if c["state"] != "CONTRACTING":
        assert c["episode_start"] is None


def test_compression_candidate_id_uses_the_episode_start():
    bars = _bars()
    r1 = analyse_timeframe("TEST", bars.iloc[:-1], "1d", POLICY)
    r2 = analyse_timeframe("TEST", bars, "1d", POLICY)
    ids = lambda r: {c["Candidate_ID"] for c in r["candidates"] if c["Signal_Type"] == "Crabel Compression Breakout"}
    assert ids(r1) and ids(r1) == ids(r2)
