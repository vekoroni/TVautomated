"""BEH-001 compression context (rules COMPRESSION_IS_CONTEXTUAL, NO_FALSE_NR_LABELS).

Features are computed from completed bars only. Compression carries its
location and which side's swings are contracting; it never creates direction.
"""
from __future__ import annotations

import math
from typing import Mapping

import numpy as np

from .sequences import SequenceResult


def _location_label(*, near_support, near_resistance, limit: float):
    """Nearer boundary wins; an exact tie prefers neither side (mirror rule)."""
    s_ok = near_support is not None and near_support <= limit
    r_ok = near_resistance is not None and near_resistance <= limit
    if s_ok and r_ok:
        if math.isclose(near_support, near_resistance, rel_tol=1e-9, abs_tol=1e-12):
            return "AT_BOTH_BOUNDARIES"
        return "AT_SUPPORT" if near_support < near_resistance else "AT_RESISTANCE"
    if s_ok:
        return "AT_SUPPORT"
    if r_ok:
        return "AT_RESISTANCE"
    return None


def _bar_state(frame, rng, ltr, i: int, cfg: Mapping) -> tuple[dict, bool, float | None, bool]:
    """NR flags, inside bar, true-range ratio and the contracting verdict at bar i (completed bars only)."""
    nr = {}
    for n in cfg["nr_windows"]:
        n = int(n)
        nr[f"NR{n}"] = bool(i + 1 >= n and rng[i] < rng[i - n + 1:i].min())  # strict minimum
    inside = bool(i >= 1 and frame["high"].iloc[i] <= frame["high"].iloc[i - 1]
                  and frame["low"].iloc[i] >= frame["low"].iloc[i - 1])
    short, long_ = int(cfg["tr_ratio_short"]), int(cfg["tr_ratio_long"])
    ratio = None
    if i + 1 >= short + long_:
        ratio = float(ltr[i - short + 1:i + 1].mean() / ltr[i - short - long_ + 1:i - short + 1].mean())
    contracting = (ratio is not None and ratio < float(cfg["tr_ratio_max"])) or nr.get("NR7", False) or (
        inside and nr.get("NR4", False))
    return nr, inside, ratio, bool(contracting)


def _episode_start(frame, rng, ltr, end: int, cfg: Mapping) -> int:
    """First bar of the current contraction episode (P0-02, Phase 1, 8 Oct 2026).

    Walk back from the last bar while bars are contracting, tolerating at most `episode_max_gap_bars`
    consecutive non-contracting bars inside the episode (versioned config). The start never depends on the run
    clock, only on completed bars, so the same coil keeps the same start from run to run.
    """
    gap_max = int(cfg.get("episode_max_gap_bars", 1))
    start, gap, i = end, 0, end - 1
    while i >= 1:
        if _bar_state(frame, rng, ltr, i, cfg)[3]:
            start, gap = i, 0
        else:
            gap += 1
            if gap > gap_max:
                break
        i -= 1
    return start


def compression_context(seq: SequenceResult, policy: Mapping) -> dict:
    cfg = policy["compression"]
    frame = seq.frame
    end = seq.last_index
    rng = (frame["lh"] - frame["ll"]).to_numpy()
    ltr = frame["ltr"].to_numpy()
    nr, inside, ratio, contracting = _bar_state(frame, rng, ltr, end, cfg)
    short = int(cfg["tr_ratio_short"])
    # Box (P0-02): the extremes of the WHOLE episode, from its first contracting bar, so the boundaries are the
    # coil's recorded edges and only widen when a bar inside the episode exceeds them. The last-few-bars box is
    # kept as recent_box_* for reference. No contraction -> no episode.
    recent = frame.iloc[max(0, end - short + 1):end + 1]
    recent_high, recent_low = float(recent["high"].max()), float(recent["low"].min())
    episode_start = _episode_start(frame, rng, ltr, end, cfg) if contracting else None
    if episode_start is not None:
        box_bars = frame.iloc[episode_start:end + 1]
        box_high, box_low = float(box_bars["high"].max()), float(box_bars["low"].min())
    else:
        box_high, box_low = recent_high, recent_low
    atr = seq.atr(end)
    highs = [p for p in seq.minor_pivots if p.kind == "H"]
    lows = [p for p in seq.minor_pivots if p.kind == "L"]
    location = "OPEN"
    if len(highs) >= 2 and highs[-1].price < highs[-2].price and frame["close"].iloc[end] < highs[-1].price:
        location = "BELOW_FALLING_CEILING"
    elif len(lows) >= 2 and lows[-1].price > lows[-2].price and frame["close"].iloc[end] > lows[-1].price:
        location = "ABOVE_RISING_FLOOR"
    else:
        close = float(frame["close"].iloc[end])
        near_support = abs(math.log(close / lows[-1].price)) / atr if lows else None
        near_resistance = abs(math.log(close / highs[-1].price)) / atr if highs else None
        location = _location_label(near_support=near_support, near_resistance=near_resistance, limit=1.5) or location
    up = [w.distance_atr for w in seq.minor_waves if w.direction == "UP"][-2:]
    down = [w.distance_atr for w in seq.minor_waves if w.direction == "DOWN"][-2:]
    side = "UNMEASURED"
    if len(up) == 2 and len(down) == 2:
        up_c, down_c = up[1] < up[0], down[1] < down[0]
        side = "BOTH" if up_c and down_c else "UPSIDE" if up_c else "DOWNSIDE" if down_c else "NEITHER"
    return {"state": "CONTRACTING" if contracting else "NONE", **nr, "inside_bar": inside,
            "tr_ratio": None if ratio is None else round(ratio, 3), "location": location,
            "contracting_side": side, "box_high": box_high, "box_low": box_low,
            "recent_box_high": recent_high, "recent_box_low": recent_low,
            "episode_start_index": episode_start,
            "episode_start": seq.label(episode_start) if episode_start is not None else None,
            "episode_bars": (end - episode_start + 1) if episode_start is not None else 0}


def describe(compression: dict) -> str:
    flags = [k for k in ("NR2", "NR3", "NR4", "NR7") if compression.get(k)]
    if compression.get("inside_bar"):
        flags.append("INSIDE")
    return (f"{compression['state']}; flags={'/'.join(flags) or 'none'}; tr_ratio={compression['tr_ratio']}; "
            f"location={compression['location']}; contracting_side={compression['contracting_side']}; "
            f"box={compression['box_low']:.4g}-{compression['box_high']:.4g}")
