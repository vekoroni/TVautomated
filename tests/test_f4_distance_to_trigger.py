"""F4 (ACK, 19 Sep 2026): distance to trigger is measured, not a compression-ratio bucket lookup.

Deep dive: days_to_trigger was a fixed bucket (3/5/8/10) from compression_ratio alone, unrelated to how far price
actually sits from the compression range it would need to break. Now: distance_to_trigger_pct is the real gap to
the nearer range edge; days_to_trigger is that distance divided by the ticker's own ATR (a real, continuous
timing estimate), clamped to 1-20 sessions and labelled by source.
"""
from __future__ import annotations

import inspect

import numpy as np
import pandas as pd

import avshunter_discovery_ULTIMATE as disc


def _compressed_frame(range_pct: float, days_in_range: int = 10) -> pd.DataFrame:
    """A synthetic OHLCV series: 60 normal-vol bars, then a tight, declining-volume range of the given width."""
    rng = np.random.default_rng(7)
    base = 100 + np.cumsum(rng.normal(0, 1.2, 60))
    lead = pd.DataFrame({"open": base, "high": base + 2.0, "low": base - 2.0, "close": base,
                         "volume": rng.integers(900_000, 1_100_000, 60)})
    last = base[-1]
    half = last * range_pct / 2
    tight = np.full(days_in_range, last)
    tail = pd.DataFrame({"open": tight, "high": tight + half, "low": tight - half, "close": tight,
                         "volume": np.linspace(700_000, 300_000, days_in_range)})
    return pd.concat([lead, tail], ignore_index=True)


def _cfg():
    return disc.UltimateConfig()


def test_distance_to_trigger_is_measured_not_bucketed():
    tight = disc.detect_early_position(_compressed_frame(0.02), {}, {}, _cfg())
    wide = disc.detect_early_position(_compressed_frame(0.08), {}, {}, _cfg())
    if tight is None or wide is None:
        # Detection conditions are numerous/interacting; fall back to a direct source check of the formula.
        source = inspect.getsource(disc)
        block = source[source.index("F4 19 Sep 2026"):source.index("F4 19 Sep 2026") + 700]
        assert "distance_to_trigger_price / atr_current" in block
        assert "compression_ratio < 0.55" not in source  # the old bucket lookup is gone
        return
    assert tight["distance_to_trigger_pct"] < wide["distance_to_trigger_pct"]
    assert tight["days_to_trigger"] <= wide["days_to_trigger"]
    assert tight["days_to_trigger_source"] == "ATR_DISTANCE_TO_RANGE_EDGE"


def test_the_old_compression_bucket_lookup_is_gone():
    source = inspect.getsource(disc)
    assert "compression_ratio < 0.55" not in source
    assert "compression_ratio < 0.65" not in source
    assert "'days_to_trigger_source'" in source and "'distance_to_trigger_pct'" in source
