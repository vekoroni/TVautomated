"""Deterministic, cadence-aware TPO and volume profile calculations."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import math
from typing import Any
import numpy as np
import pandas as pd
from .params import MSParams, MS_PARAMS_V1


@dataclass(frozen=True, slots=True)
class MarketProfile:
    bins: pd.DataFrame
    bin_width: float
    poc: float | None
    value_area_low: float | None
    value_area_high: float | None
    data_quality: str
    total_tpo: int
    regular_volume: float
    interval_minutes: int | None = None
    cadence_source: str = "UNKNOWN"


def round_to_tick(value: float, tick: float) -> float:
    if tick <= 0 or value <= 0: raise ValueError("positive value and exchange tick required")
    return round(max(tick, round(value / tick) * tick), 10)


def profile_bin_width(*, exchange_tick: float, atr14: float, params: MSParams = MS_PARAMS_V1) -> float:
    if not math.isfinite(atr14) or atr14 <= 0: raise ValueError("positive finite ATR14 required")
    return round_to_tick(max(exchange_tick, atr14 / params.bin_divisor), exchange_tick)


def _value_area(counts: np.ndarray, poc_index: int, share: float) -> tuple[int, int]:
    target = counts.sum() * share; low = high = poc_index; accumulated = counts[poc_index]
    while accumulated < target and (low > 0 or high < len(counts) - 1):
        below = counts[low - 1] if low > 0 else -1; above = counts[high + 1] if high < len(counts)-1 else -1
        if above >= below: high += 1; accumulated += counts[high]
        else: low -= 1; accumulated += counts[low]
    return low, high


def _profile_cadence(frame: pd.DataFrame) -> tuple[int | None, str, str]:
    """Resolve cadence from the governed field, then timestamp deltas."""
    if "interval_minutes" in frame:
        values = pd.to_numeric(frame["interval_minutes"], errors="coerce").dropna().astype(int).unique()
        if len(values) == 1 and int(values[0]) > 0:
            interval = int(values[0]); source = "GOVERNED_FIELD"
        else:
            return None, "INVALID_MIXED_INTERVAL", "COARSE_DATA_LOW_CONFIDENCE"
    else:
        timestamps = pd.to_datetime(frame["timestamp_utc"], utc=True).sort_values().drop_duplicates()
        deltas = timestamps.diff().dropna().dt.total_seconds().div(60)
        if deltas.empty:
            return None, "INSUFFICIENT_TIMESTAMPS", "INSUFFICIENT_DATA"
        interval = max(1, int(round(float(deltas.median())))); source = "TIMESTAMP_DERIVED"
    quality = {
        1: "ONE_MINUTE_ESTIMATED",
        5: "FIVE_MINUTE_ESTIMATED",
        15: "COARSE_15_MINUTE",
        30: "COARSE_30_MINUTE",
    }.get(interval, "COARSE_DATA_LOW_CONFIDENCE")
    return interval, source, quality


def build_market_profile(bars: pd.DataFrame, *, exchange_tick: float, atr14: float, regular_open_utc: datetime, params: MSParams = MS_PARAMS_V1) -> MarketProfile:
    required = {"timestamp_utc", "high", "low", "close", "volume"}
    if bars.empty or not required <= set(bars.columns):
        return MarketProfile(pd.DataFrame(), 0.0, None, None, None, "INSUFFICIENT_DATA", 0, 0.0)
    frame = bars.copy(); frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    if "session_segment" in frame: frame = frame[frame["session_segment"].astype(str).str.upper().eq("REGULAR")]
    frame = frame.dropna(subset=list(required))
    if frame.empty: return MarketProfile(pd.DataFrame(), 0.0, None, None, None, "INSUFFICIENT_DATA", 0, 0.0)
    interval, cadence_source, cadence_quality = _profile_cadence(frame)
    # Governed frames must contain enough observations to represent a session.
    # Legacy test/research frames without an interval field retain their prior
    # small-sample behaviour until their callers migrate.
    if "interval_minutes" in frame and len(frame) < 13:
        return MarketProfile(pd.DataFrame(), 0.0, None, None, None, "INSUFFICIENT_DATA", 0, float(frame["volume"].sum()), interval, cadence_source)
    width = profile_bin_width(exchange_tick=exchange_tick, atr14=atr14, params=params)
    bottom = math.floor(float(frame["low"].min()) / width) * width; top = math.ceil(float(frame["high"].max()) / width) * width
    levels = np.arange(bottom, top + width * 0.5, width); periods: list[set[int]] = [set() for _ in levels]; volume = np.zeros(len(levels))
    open_ts = pd.Timestamp(regular_open_utc).tz_convert("UTC")
    for row in frame.itertuples(index=False):
        low_bin = math.floor(float(row.low)/width)*width; high_bin = math.floor(float(row.high)/width)*width
        indexes = np.flatnonzero((levels >= low_bin-1e-9) & (levels <= high_bin+1e-9))
        if not len(indexes): continue
        period = max(0, int((pd.Timestamp(row.timestamp_utc)-open_ts).total_seconds() // (params.tpo_period_minutes*60)))
        allocation = max(0.0, float(row.volume))/len(indexes)
        for index in indexes: periods[index].add(period); volume[index] += allocation
    counts = np.array([len(values) for values in periods])
    if not counts.any(): return MarketProfile(pd.DataFrame(), width, None, None, None, "INSUFFICIENT_DATA", 0, float(frame["volume"].sum()), interval, cadence_source)
    poc_index = int(np.flatnonzero(counts == counts.max())[-1]); va_low, va_high = _value_area(counts, poc_index, params.value_area_share)
    bins = pd.DataFrame({"price": levels, "tpo_count": counts, "volume_estimated": volume, "tpo_periods": [tuple(sorted(v)) for v in periods]})
    return MarketProfile(bins, width, float(levels[poc_index]), float(levels[va_low]), float(levels[va_high]), cadence_quality, int(counts.sum()), float(frame["volume"].sum()), interval, cadence_source)


def _threshold_period(periods: list[tuple[int,...]], indexes: range, target: float) -> int | None:
    all_periods = sorted({period for index in indexes for period in periods[index]}); final = sum(len(periods[index]) for index in indexes)
    for period in all_periods:
        if sum(sum(value <= period for value in periods[index]) for index in indexes) >= final*target: return period
    return None


def detect_double_distribution(profile: MarketProfile, *, atr14: float, params: MSParams = MS_PARAMS_V1) -> dict[str, Any]:
    bins = profile.bins
    if bins.empty or len(bins) < 7 or profile.total_tpo <= 0: return {"detected": False, "reason": "INSUFFICIENT_PROFILE"}
    counts = bins["tpo_count"].to_numpy(float); nonzero = counts[counts > 0]; threshold = float(np.quantile(nonzero, params.peak_percentile))
    peaks = [i for i in range(1,len(counts)-1) if counts[i] >= threshold and counts[i] >= counts[i-1] and counts[i] >= counts[i+1]]
    candidates = []
    for left in peaks:
        for right in peaks:
            if right <= left + params.valley_min_bins: continue
            weak = min(counts[left], counts[right]); low_indexes = [i for i in range(left+1,right) if counts[i] <= weak*params.valley_ratio]
            runs: list[list[int]] = []
            for index in low_indexes:
                if not runs or index != runs[-1][-1]+1: runs.append([index])
                else: runs[-1].append(index)
            runs = [run for run in runs if len(run) >= params.valley_min_bins]
            if not runs: continue
            valley = min(runs, key=lambda run:(max(counts[run]),-len(run),run[0])); split_low, split_high = valley[0], valley[-1]
            if float(bins.iloc[right].price-bins.iloc[left].price) < max(params.separation_min_bins*profile.bin_width, params.separation_atr*atr14): continue
            lower, upper = range(0,split_low), range(split_high+1,len(counts))
            if counts[list(lower)].sum() < profile.total_tpo*params.region_share or counts[list(upper)].sum() < profile.total_tpo*params.region_share: continue
            period_values = bins["tpo_periods"].tolist(); lower_time = _threshold_period(period_values,lower,params.chronology_share); upper_time = _threshold_period(period_values,upper,params.chronology_share)
            if lower_time is None or upper_time is None or abs(lower_time-upper_time)<1: continue
            lower_first = lower_time < upper_time
            first, second = (lower,upper) if lower_first else (upper,lower)
            candidates.append({"detected":True,"reason":"DOUBLE_DISTRIBUTION_DETECTED",
                "first_low":float(bins.iloc[first.start].price),"first_high":float(bins.iloc[first.stop-1].price),
                "second_low":float(bins.iloc[second.start].price),"second_high":float(bins.iloc[second.stop-1].price),
                "second_direction":"ABOVE" if lower_first else "BELOW","separation_low":float(bins.iloc[split_low].price),
                "separation_high":float(bins.iloc[split_high].price),"separation_indexes":tuple(valley),"weaker_peak":float(weak),
                "first_threshold_period":min(lower_time,upper_time),"second_threshold_period":max(lower_time,upper_time)})
    return max(candidates,key=lambda item:abs(item["second_low"]-item["first_low"])) if candidates else {"detected":False,"reason":"NO_QUALIFYING_DOUBLE_DISTRIBUTION"}
