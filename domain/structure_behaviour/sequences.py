"""BEH-001 L1-L2: completed bars -> dated swings, waves, current leg, range.

All distances are log units divided by the log-ATR at the measuring bar, so
the same rule applies to every ticker and a log-reflected chart gives the
mirrored structure. Pivots carry their confirmation bar (as-of rule).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class Pivot:
    index: int
    kind: str              # "H" or "L"
    price: float
    confirmed_index: int
    label: str             # date/timestamp text of the pivot bar


@dataclass(frozen=True)
class Wave:
    start: Pivot
    end: Pivot
    direction: str         # "UP" / "DOWN"
    distance_atr: float
    bars: int
    volume_ratio: float    # mean volume over the wave / mean volume before it
    extension_atr: Optional[float]  # beyond the previous same-kind extreme (+ = new extreme)


@dataclass(frozen=True)
class CurrentLeg:
    start: Pivot
    direction: str
    extreme_index: int
    extreme_price: float
    end_index: int
    distance_atr: float
    confirmed: bool = False


@dataclass(frozen=True)
class TradingRange:
    support: float
    resistance: float
    start_index: int
    end_index: int
    width_atr: float
    price_inside: bool


@dataclass(frozen=True)
class SequenceResult:
    status: str
    timeframe: str
    frame: Optional[pd.DataFrame]
    minor_pivots: Tuple[Pivot, ...] = ()
    major_pivots: Tuple[Pivot, ...] = ()
    minor_waves: Tuple[Wave, ...] = ()
    major_waves: Tuple[Wave, ...] = ()
    current_leg: Optional[CurrentLeg] = None
    major_leg: Optional[CurrentLeg] = None
    trading_range: Optional[TradingRange] = None
    local_range: Optional[TradingRange] = None

    @property
    def last_index(self) -> int:
        return len(self.frame) - 1 if self.frame is not None else -1

    def atr(self, index: int) -> float:
        return float(self.frame["atr"].iloc[index])

    def label(self, index: int) -> str:
        return str(self.frame["label"].iloc[index])


def reflect_bars(bars: pd.DataFrame, reference: Optional[float] = None) -> pd.DataFrame:
    """Log reflection about K (default last close); volume unchanged."""
    k = float(bars["close"].iloc[-1]) if reference is None else float(reference)
    out = bars.copy()
    out["open"] = k * k / bars["open"]
    out["close"] = k * k / bars["close"]
    out["high"] = k * k / bars["low"]
    out["low"] = k * k / bars["high"]
    return out


def normalise_bars(bars: pd.DataFrame, atr_bars: int) -> Optional[pd.DataFrame]:
    """Validated log frame with log true range and log-ATR, or None."""
    if bars is None or len(bars) == 0 or not set(REQUIRED_COLUMNS).issubset(bars.columns):
        return None
    values = bars.loc[:, list(REQUIRED_COLUMNS)].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    if not np.isfinite(values).all() or (values[:, :4] <= 0).any() or (values[:, 4] < 0).any():
        return None
    o, h, l, c, v = (values[:, i] for i in range(5))
    if (l > np.minimum(o, c) * (1 + 1e-12)).any() or (h < np.maximum(o, c) * (1 - 1e-12)).any():
        return None
    frame = pd.DataFrame({"lo": np.log(o), "lh": np.log(h), "ll": np.log(l), "lc": np.log(c),
                          "open": o, "high": h, "low": l, "close": c, "volume": v})
    prev = frame["lc"].shift(1)
    frame["ltr"] = pd.concat([frame["lh"] - frame["ll"], (frame["lh"] - prev).abs(),
                              (frame["ll"] - prev).abs()], axis=1).max(axis=1)
    frame["atr"] = frame["ltr"].rolling(atr_bars, min_periods=atr_bars).mean()
    label_source = None
    for column in ("timestamp", "date", "timestamp_utc"):
        if column in bars.columns:
            label_source = pd.to_datetime(bars[column]).astype(str).str.slice(0, 19).to_numpy()
            break
    frame["label"] = label_source if label_source is not None else [str(i) for i in range(len(frame))]
    return frame


def _zigzag(frame: pd.DataFrame, reversal_atr: float) -> Tuple[Tuple[Pivot, ...], Optional[Tuple[str, int]]]:
    """Symmetric ATR zig-zag. Returns confirmed pivots and the open extreme."""
    lh, ll, atr = frame["lh"].to_numpy(), frame["ll"].to_numpy(), frame["atr"].to_numpy()
    pivots = []
    seeking = None        # None until the first reversal; then "H" (in up-leg) or "L"
    hi_i = lo_i = None
    for i in range(len(frame)):
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        if hi_i is None:
            hi_i = lo_i = i
            continue
        if seeking is None:
            if lh[i] > lh[hi_i]:
                hi_i = i
            if ll[i] < ll[lo_i]:
                lo_i = i
            up_rev = lh[i] - ll[lo_i] >= reversal_atr * a and lo_i < i
            down_rev = lh[hi_i] - ll[i] >= reversal_atr * a and hi_i < i
            if up_rev and not down_rev:
                pivots.append(Pivot(lo_i, "L", float(frame["low"].iloc[lo_i]), i, frame["label"].iloc[lo_i]))
                seeking, hi_i = "H", i
            elif down_rev and not up_rev:
                pivots.append(Pivot(hi_i, "H", float(frame["high"].iloc[hi_i]), i, frame["label"].iloc[hi_i]))
                seeking, lo_i = "L", i
            continue
        if seeking == "H":
            if lh[i] >= lh[hi_i]:
                hi_i = i
            elif lh[hi_i] - ll[i] >= reversal_atr * a:
                pivots.append(Pivot(hi_i, "H", float(frame["high"].iloc[hi_i]), i, frame["label"].iloc[hi_i]))
                seeking, lo_i = "L", i
        else:
            if ll[i] <= ll[lo_i]:
                lo_i = i
            elif lh[i] - ll[lo_i] >= reversal_atr * a:
                pivots.append(Pivot(lo_i, "L", float(frame["low"].iloc[lo_i]), i, frame["label"].iloc[lo_i]))
                seeking, hi_i = "H", i
    open_extreme = None
    if seeking == "H":
        open_extreme = ("H", hi_i)
    elif seeking == "L":
        open_extreme = ("L", lo_i)
    return tuple(pivots), open_extreme


def _waves(frame: pd.DataFrame, pivots: Sequence[Pivot]) -> Tuple[Wave, ...]:
    out = []
    lh, ll, volume, atr = frame["lh"].to_numpy(), frame["ll"].to_numpy(), frame["volume"].to_numpy(), frame["atr"].to_numpy()
    for position, (a, b) in enumerate(zip(pivots, pivots[1:])):
        start_log = lh[a.index] if a.kind == "H" else ll[a.index]
        end_log = lh[b.index] if b.kind == "H" else ll[b.index]
        scale = atr[b.index] if np.isfinite(atr[b.index]) and atr[b.index] > 0 else np.nan
        wave_vol = volume[a.index + 1:b.index + 1].mean() if b.index > a.index else np.nan
        before = volume[max(0, a.index - 20):a.index + 1].mean()
        previous_same = [p for p in pivots[:position + 1] if p.kind == b.kind]
        extension = None
        if previous_same:
            ref = previous_same[-1]
            ref_log = lh[ref.index] if ref.kind == "H" else ll[ref.index]
            extension = ((end_log - ref_log) if b.kind == "H" else (ref_log - end_log)) / scale
        out.append(Wave(a, b, "UP" if b.kind == "H" else "DOWN", abs(end_log - start_log) / scale,
                        b.index - a.index, float(wave_vol / before) if before > 0 else float("nan"),
                        None if extension is None else float(extension)))
    return tuple(out)


def _current_leg(frame: pd.DataFrame, pivots: Sequence[Pivot], open_extreme) -> Optional[CurrentLeg]:
    if not pivots:
        return None
    last = pivots[-1]
    direction = "DOWN" if last.kind == "H" else "UP"
    if open_extreme is not None:
        extreme_index = open_extreme[1]
    else:
        extreme_index = last.index
    lh, ll, atr = frame["lh"].to_numpy(), frame["ll"].to_numpy(), frame["atr"].to_numpy()
    start_log = lh[last.index] if last.kind == "H" else ll[last.index]
    extreme_log = ll[extreme_index] if direction == "DOWN" else lh[extreme_index]
    extreme_price = float(frame["low" if direction == "DOWN" else "high"].iloc[extreme_index])
    end = len(frame) - 1
    return CurrentLeg(last, direction, extreme_index, extreme_price, end,
                      abs(extreme_log - start_log) / atr[end])


def _trading_range(frame: pd.DataFrame, pivots: Sequence[Pivot], policy: Mapping) -> Optional[TradingRange]:
    """Range from the latest pivots. A boundary test that price has since
    reclaimed (spring / upthrust) does not end the established range."""
    found = _range_from_window(frame, pivots, policy)
    minimum = int(policy["range"]["min_pivots"])
    if found is not None or len(pivots) <= minimum:
        return found
    for drop in (1, 2):
        if len(pivots) - drop < minimum:
            break
        prior = _range_from_window(frame, pivots[:-drop], policy)
        if prior is not None:
            return prior if prior.price_inside else None
    return None


def _range_from_window(frame: pd.DataFrame, pivots: Sequence[Pivot], policy: Mapping) -> Optional[TradingRange]:
    cfg = policy["range"]
    window = list(pivots[-int(cfg["min_pivots"]):])
    if len(window) < int(cfg["min_pivots"]):
        return None
    highs = [p for p in window if p.kind == "H"]
    lows = [p for p in window if p.kind == "L"]
    if len(highs) < 2 or len(lows) < 2:
        return None
    end = len(frame) - 1
    atr = float(frame["atr"].iloc[end])
    tol = float(cfg["boundary_tolerance_atr"]) * atr
    log_h = [math.log(p.price) for p in highs]
    log_l = [math.log(p.price) for p in lows]
    stepping_down = all(b < a - tol for a, b in zip(log_h, log_h[1:])) and all(b < a - tol for a, b in zip(log_l, log_l[1:]))
    stepping_up = all(b > a + tol for a, b in zip(log_h, log_h[1:])) and all(b > a + tol for a, b in zip(log_l, log_l[1:]))
    if stepping_down or stepping_up:
        return None
    resistance, support = max(p.price for p in highs), min(p.price for p in lows)
    width = (math.log(resistance) - math.log(support)) / atr
    if width > float(cfg["max_width_atr"]):
        return None
    close = float(frame["lc"].iloc[end])
    inside = math.log(support) - tol <= close <= math.log(resistance) + tol
    return TradingRange(support, resistance, window[0].index, window[-1].index, width, inside)


def build_sequences(bars: pd.DataFrame, timeframe: str, policy: Mapping) -> SequenceResult:
    frame = normalise_bars(bars, int(policy["atr_bars"]))
    if frame is None:
        return SequenceResult("NOT_EVALUATED_INVALID_BARS", timeframe, None)
    minimum = int(policy["timeframes"].get(timeframe, {}).get("min_bars", policy["atr_bars"] + 2))
    if len(frame) < minimum and timeframe in policy["timeframes"]:
        return SequenceResult("NOT_EVALUATED_INSUFFICIENT_BARS", timeframe, frame)
    minor, minor_open = _zigzag(frame, float(policy["swing_reversal_atr"]["minor"]))
    major, major_open = _zigzag(frame, float(policy["swing_reversal_atr"]["major"]))
    if not minor:
        return SequenceResult("NOT_EVALUATED_NO_SWINGS", timeframe, frame)
    return SequenceResult(
        "EVALUATED", timeframe, frame, minor, major, _waves(frame, minor), _waves(frame, major),
        _current_leg(frame, minor, minor_open), _current_leg(frame, major, major_open),
        _trading_range(frame, major if len(major) >= int(policy["range"]["min_pivots"]) else minor, policy),
        _trading_range(frame, minor, policy),
    )
