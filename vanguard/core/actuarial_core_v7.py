"""Deterministic historical-equivalence contract for AVSHUNTER actuarial v7.

Only completed adjusted daily OHLCV is accepted.  Live auction, options,
macro, catalyst and clock-dependent inputs are deliberately excluded; those
remain post-query overlays in the live pipeline.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import pandas as pd


CALCULATION_VERSION = "actuarial_core_v7.0.0"
SCHEMA_VERSION = "actuarial_v7"
BUCKET_SCHEMA_VERSION = "2.0.0"
MIN_BARS_REQUIRED = 60
CORE_HASH_DIMENSIONS = (
    "vol_regime",
    "trend_direction",
    "trend_maturity",
    "structure_quality",
    "phase_v2",
    "momentum_bucket",
    "location_bucket",
    "wyckoff_phase_bucket",
    "crabel_state",
)


class ActuarialCoreContractError(ValueError):
    pass


def canonical_session_date(value: Any) -> str:
    return pd.to_datetime(value, errors="raise", utc=True).date().isoformat()


def normalise_daily_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ActuarialCoreContractError(f"daily OHLCV missing columns: {missing}")
    out = frame.loc[:, ["date", "open", "high", "low", "close", "volume"]].copy()
    out["date"] = out["date"].map(canonical_session_date)
    for col in ("open", "high", "low", "close", "volume"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    if out[["open", "high", "low", "close"]].isna().any().any():
        raise ActuarialCoreContractError("daily OHLC contains non-numeric/null values")
    if (out[["open", "high", "low", "close"]] <= 0).any().any():
        raise ActuarialCoreContractError("daily OHLC contains non-positive prices")
    if (out["volume"].fillna(0) < 0).any():
        raise ActuarialCoreContractError("daily volume contains negative values")
    out = out.sort_values("date", kind="stable").reset_index(drop=True)
    duplicates = out.duplicated("date", keep=False)
    if duplicates.any():
        dates = out.loc[duplicates, "date"].drop_duplicates().head(5).tolist()
        raise ActuarialCoreContractError(f"duplicate session dates: {dates}")
    return out


def compute_technicals(frame: pd.DataFrame) -> pd.DataFrame:
    df = normalise_daily_ohlcv(frame)
    close, high, low = df["close"], df["high"], df["low"]
    df["ema21"] = close.ewm(span=21, adjust=False).mean()
    df["ema50"] = close.ewm(span=50, adjust=False).mean()
    df["ema200"] = close.ewm(span=200, adjust=False).mean()
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1
    ).max(axis=1)
    df["atr14"] = tr.ewm(span=14, adjust=False).mean()
    df["atr_pct"] = 100 * df["atr14"] / close.replace(0, np.nan)
    dm_plus, dm_minus = high.diff().clip(lower=0), (-low.diff()).clip(lower=0)
    mask = dm_plus >= dm_minus
    dm_plus, dm_minus = dm_plus.where(mask, 0), dm_minus.where(~mask, 0)
    atr = tr.ewm(span=14, adjust=False).mean().replace(0, np.nan)
    di_plus = 100 * dm_plus.ewm(span=14, adjust=False).mean() / atr
    di_minus = 100 * dm_minus.ewm(span=14, adjust=False).mean() / atr
    dx = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan)
    df["adx"] = dx.ewm(span=14, adjust=False).mean().fillna(0.0)
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(span=14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(span=14, adjust=False).mean()
    df["rsi"] = (100 - 100 / (1 + gain / loss.replace(0, np.nan))).fillna(50.0)
    bb_mid, bb_std = close.rolling(20).mean(), close.rolling(20).std()
    df["bb_width"] = 400 * bb_std / bb_mid.replace(0, np.nan)
    df["high_252"] = high.rolling(252, min_periods=50).max()
    df["low_252"] = low.rolling(252, min_periods=50).min()
    df["dist_from_high"] = (df["high_252"] - close) / df["high_252"].replace(0, np.nan)
    df["dist_from_low"] = (close - df["low_252"]) / df["low_252"].replace(0, np.nan)
    def rolling_ranks(series: pd.Series) -> np.ndarray:
        values = series.to_numpy(dtype=float)
        result = np.empty(len(values), dtype=float)
        for idx, value in enumerate(values):
            sample = values[max(0, idx - 252) : idx + 1]
            valid = sample[~np.isnan(sample)]
            result[idx] = float(np.sum(valid < value) / len(valid) * 100) if len(valid) and not np.isnan(value) else 50.0
        return result
    df["atr_percentile_252"] = rolling_ranks(df["atr_pct"])
    df["bb_percentile_252"] = rolling_ranks(df["bb_width"])
    df["volume_mean_6"] = df["volume"].rolling(6, min_periods=1).mean()
    df["volume_mean_21"] = df["volume"].rolling(21, min_periods=1).mean()
    return df


def _rank(df: pd.DataFrame, column: str, idx: int) -> float:
    value = float(df[column].iloc[idx])
    sample = df[column].iloc[max(0, idx - 252) : idx + 1].dropna()
    return float((sample < value).sum() / len(sample) * 100) if len(sample) else 50.0


def _bucket(value: float, low: float, high: float, names: tuple[str, str, str]) -> str:
    return names[0] if value < low else names[2] if value > high else names[1]


def calculate_core_state(technicals: pd.DataFrame, idx: int) -> dict[str, Any] | None:
    if idx < MIN_BARS_REQUIRED:
        return None
    row = technicals.iloc[idx]
    close = float(row["close"])
    atr_rank = float(row["atr_percentile_252"]) if "atr_percentile_252" in technicals else _rank(technicals, "atr_pct", idx)
    bb_rank = float(row["bb_percentile_252"]) if "bb_percentile_252" in technicals else _rank(technicals, "bb_width", idx)
    vol = "COMPRESSION" if atr_rank < 30 and bb_rank < 30 else (
        "EXPANSION" if atr_rank > 70 or bb_rank > 70 else "NORMAL"
    )
    ema21, ema50, ema200 = float(row["ema21"]), float(row["ema50"]), float(row["ema200"])
    bullish = close > ema21 > ema50 > ema200
    bearish = close < ema21 < ema50 < ema200
    trend = "UP" if bullish else "DOWN" if bearish else "SIDEWAYS"
    dist_high = float(row["dist_from_high"]) if pd.notna(row["dist_from_high"]) else 0.5
    dist_low = float(row["dist_from_low"]) if pd.notna(row["dist_from_low"]) else 0.5
    distance = dist_high if trend == "UP" else dist_low
    maturity = "LATE" if distance < 0.05 else "MIDDLE" if distance < 0.15 else "EARLY"
    adx, rsi = float(row["adx"]), float(row["rsi"])
    recent = float(row["volume_mean_6"]) if "volume_mean_6" in technicals else technicals["volume"].iloc[max(0, idx - 5) : idx + 1].mean()
    average = float(row["volume_mean_21"]) if "volume_mean_21" in technicals else technicals["volume"].iloc[max(0, idx - 20) : idx + 1].mean()
    volume_ratio = float(recent / average) if average > 0 else 1.0
    if dist_high < 0.08 and rsi > 60 and (bullish or ema21 > ema50) and (volume_ratio < 0.85 or rsi > 75):
        wyckoff_phase, wyckoff_bucket = "DISTRIBUTION", "DISTRIBUTION"
    elif bullish and dist_high < 0.15 and adx > 25 and rsi > 55:
        wyckoff_phase, wyckoff_bucket = "E", "MARKUP"
    elif bullish and dist_high >= 0.15 and adx > 18 and rsi > 48:
        wyckoff_phase, wyckoff_bucket = "D", "MARKUP"
    elif dist_low < 0.10 and atr_rank < 35 and rsi > 38 and not bearish:
        wyckoff_phase, wyckoff_bucket = "C", "ACCUMULATION"
    elif dist_low < 0.15 and volume_ratio > 1.4 and atr_rank > 55:
        wyckoff_phase, wyckoff_bucket = "A", "ACCUMULATION"
    else:
        wyckoff_phase, wyckoff_bucket = "B", "ACCUMULATION"
    if trend == "SIDEWAYS":
        maturity = "SIDEWAYS_BUILDING" if vol == "COMPRESSION" or wyckoff_bucket == "ACCUMULATION" else "SIDEWAYS_RANGING"
    structure = "STRONG" if rsi > 55 else "WEAK" if rsi < 40 else "NEUTRAL"
    adx_bucket = _bucket(adx, 20, 35, ("WEAK", "MODERATE", "STRONG"))
    atr_bucket = _bucket(atr_rank, 33, 66, ("LOW", "MID", "HIGH"))
    phase = "EARLY_TRANSITION" if atr_rank < 45 and adx < 22 and bb_rank < 55 else (
        "CONTINUATION" if atr_rank >= 45 and adx >= 22 and rsi < 72 and bb_rank < 95 else "EXHAUSTION"
    )
    momentum_score = adx * atr_rank / 100
    momentum = "LOW" if momentum_score < 15 else "MID" if momentum_score < 30 else "HIGH" if momentum_score < 45 else "EXTREME"
    location = "NEAR_HIGH" if dist_high < 0.10 else "NEAR_LOW" if dist_low < 0.10 else (
        "MID_RANGE" if dist_high > 0.30 and dist_low > 0.30 else "TRANSITION_ZONE"
    )
    crabel = "CRABEL_READY" if vol == "COMPRESSION" and adx_bucket == "WEAK" else (
        "COILING" if atr_bucket == "LOW" and adx_bucket in {"WEAK", "MODERATE"} else "NONE"
    )
    state = {
        "vol_regime": vol, "trend_direction": trend, "trend_maturity": maturity,
        "structure_quality": structure, "phase_v2": phase, "momentum_bucket": momentum,
        "location_bucket": location, "wyckoff_phase_bucket": wyckoff_bucket,
        "crabel_state": crabel,
    }
    signature = "|".join(str(state[k]).upper() for k in CORE_HASH_DIMENSIONS)
    return {
        **state,
        "actuarial_core_hash": hashlib.sha256(signature.encode()).hexdigest()[:20],
        "state_hash": hashlib.md5("_".join(str(state[k]).upper() for k in CORE_HASH_DIMENSIONS).encode()).hexdigest()[:16],
        "actuarial_vol_regime": vol,
        "actuarial_structure_quality": structure,
        "realised_vol_regime": "LOW_IV" if vol == "COMPRESSION" else "HIGH_IV" if vol == "EXPANSION" else "ELEVATED_IV" if atr_rank >= 50 else "NORMAL_IV",
        "iv_regime": "LOW_IV" if vol == "COMPRESSION" else "HIGH_IV" if vol == "EXPANSION" else "ELEVATED_IV" if atr_rank >= 50 else "NORMAL_IV",
        "atr_pct_bucket": atr_bucket, "adx_bucket": adx_bucket,
        "atr_percentile": round(atr_rank, 2), "bb_percentile": round(bb_rank, 2),
        "adx": round(adx, 2), "rsi": round(rsi, 2),
        "dist_from_high": round(dist_high, 4), "dist_from_low": round(dist_low, 4),
        "wyckoff_phase": wyckoff_phase, "price": round(close, 4),
        "date": canonical_session_date(row["date"]),
        "calculation_version": CALCULATION_VERSION,
        "schema_version": SCHEMA_VERSION,
        "bucket_schema_version": BUCKET_SCHEMA_VERSION,
    }


def _calculate_core_state_fast(row: Any) -> dict[str, Any]:
    """Equivalent state calculation for a precomputed itertuples row."""
    close = float(row.close)
    atr_rank, bb_rank = float(row.atr_percentile_252), float(row.bb_percentile_252)
    vol = "COMPRESSION" if atr_rank < 30 and bb_rank < 30 else (
        "EXPANSION" if atr_rank > 70 or bb_rank > 70 else "NORMAL"
    )
    ema21, ema50, ema200 = float(row.ema21), float(row.ema50), float(row.ema200)
    bullish = close > ema21 > ema50 > ema200
    bearish = close < ema21 < ema50 < ema200
    trend = "UP" if bullish else "DOWN" if bearish else "SIDEWAYS"
    dist_high = float(row.dist_from_high) if pd.notna(row.dist_from_high) else 0.5
    dist_low = float(row.dist_from_low) if pd.notna(row.dist_from_low) else 0.5
    distance = dist_high if trend == "UP" else dist_low
    maturity = "LATE" if distance < 0.05 else "MIDDLE" if distance < 0.15 else "EARLY"
    adx, rsi = float(row.adx), float(row.rsi)
    volume_ratio = float(row.volume_mean_6 / row.volume_mean_21) if row.volume_mean_21 > 0 else 1.0
    if dist_high < 0.08 and rsi > 60 and (bullish or ema21 > ema50) and (volume_ratio < 0.85 or rsi > 75):
        wyckoff_phase, wyckoff_bucket = "DISTRIBUTION", "DISTRIBUTION"
    elif bullish and dist_high < 0.15 and adx > 25 and rsi > 55:
        wyckoff_phase, wyckoff_bucket = "E", "MARKUP"
    elif bullish and dist_high >= 0.15 and adx > 18 and rsi > 48:
        wyckoff_phase, wyckoff_bucket = "D", "MARKUP"
    elif dist_low < 0.10 and atr_rank < 35 and rsi > 38 and not bearish:
        wyckoff_phase, wyckoff_bucket = "C", "ACCUMULATION"
    elif dist_low < 0.15 and volume_ratio > 1.4 and atr_rank > 55:
        wyckoff_phase, wyckoff_bucket = "A", "ACCUMULATION"
    else:
        wyckoff_phase, wyckoff_bucket = "B", "ACCUMULATION"
    if trend == "SIDEWAYS":
        maturity = "SIDEWAYS_BUILDING" if vol == "COMPRESSION" or wyckoff_bucket == "ACCUMULATION" else "SIDEWAYS_RANGING"
    structure = "STRONG" if rsi > 55 else "WEAK" if rsi < 40 else "NEUTRAL"
    adx_bucket = _bucket(adx, 20, 35, ("WEAK", "MODERATE", "STRONG"))
    atr_bucket = _bucket(atr_rank, 33, 66, ("LOW", "MID", "HIGH"))
    phase = "EARLY_TRANSITION" if atr_rank < 45 and adx < 22 and bb_rank < 55 else (
        "CONTINUATION" if atr_rank >= 45 and adx >= 22 and rsi < 72 and bb_rank < 95 else "EXHAUSTION"
    )
    momentum_score = adx * atr_rank / 100
    momentum = "LOW" if momentum_score < 15 else "MID" if momentum_score < 30 else "HIGH" if momentum_score < 45 else "EXTREME"
    location = "NEAR_HIGH" if dist_high < 0.10 else "NEAR_LOW" if dist_low < 0.10 else (
        "MID_RANGE" if dist_high > 0.30 and dist_low > 0.30 else "TRANSITION_ZONE"
    )
    crabel = "CRABEL_READY" if vol == "COMPRESSION" and adx_bucket == "WEAK" else (
        "COILING" if atr_bucket == "LOW" and adx_bucket in {"WEAK", "MODERATE"} else "NONE"
    )
    state = {
        "vol_regime": vol, "trend_direction": trend, "trend_maturity": maturity,
        "structure_quality": structure, "phase_v2": phase, "momentum_bucket": momentum,
        "location_bucket": location, "wyckoff_phase_bucket": wyckoff_bucket,
        "crabel_state": crabel,
    }
    signature = "|".join(str(state[k]).upper() for k in CORE_HASH_DIMENSIONS)
    return {
        **state,
        "actuarial_core_hash": hashlib.sha256(signature.encode()).hexdigest()[:20],
        "state_hash": hashlib.md5("_".join(str(state[k]).upper() for k in CORE_HASH_DIMENSIONS).encode()).hexdigest()[:16],
        "actuarial_vol_regime": vol,
        "actuarial_structure_quality": structure,
        "realised_vol_regime": "LOW_IV" if vol == "COMPRESSION" else "HIGH_IV" if vol == "EXPANSION" else "ELEVATED_IV" if atr_rank >= 50 else "NORMAL_IV",
        "iv_regime": "LOW_IV" if vol == "COMPRESSION" else "HIGH_IV" if vol == "EXPANSION" else "ELEVATED_IV" if atr_rank >= 50 else "NORMAL_IV",
        "atr_pct_bucket": atr_bucket, "adx_bucket": adx_bucket,
        "atr_percentile": round(atr_rank, 2), "bb_percentile": round(bb_rank, 2),
        "adx": round(adx, 2), "rsi": round(rsi, 2),
        "dist_from_high": round(dist_high, 4), "dist_from_low": round(dist_low, 4),
        "wyckoff_phase": wyckoff_phase, "price": round(close, 4),
        "date": canonical_session_date(row.date),
        "calculation_version": CALCULATION_VERSION,
        "schema_version": SCHEMA_VERSION,
        "bucket_schema_version": BUCKET_SCHEMA_VERSION,
    }


def _forward_outcomes_arrays(
    close: np.ndarray, high: np.ndarray, low: np.ndarray, dates: np.ndarray, idx: int
) -> dict[str, Any] | None:
    entry = float(close[idx])
    if entry <= 0:
        return None

    def forward(horizon: int) -> tuple[float, float, float] | None:
        if len(close) - idx - 1 < horizon:
            return None
        end = idx + horizon + 1
        return (
            float((close[end - 1] - entry) / entry),
            float((np.max(high[idx + 1 : end]) - entry) / entry),
            float((np.min(low[idx + 1 : end]) - entry) / entry),
        )

    result: dict[str, Any] = {
        "outcome_5d_return": np.nan,
        "outcome_max_gain_5d": np.nan,
        "outcome_max_drawdown_5d": np.nan,
        "outcome_hit_5pct_up_5d": pd.NA,
        "outcome_10d_return": np.nan,
        "outcome_max_gain_10d": np.nan,
        "outcome_max_drawdown_10d": np.nan,
        "outcome_hit_7pct_up_10d": pd.NA,
        "outcome_20d_return": np.nan,
        "outcome_max_gain_20d": np.nan,
        "outcome_max_drawdown_20d": np.nan,
        "outcome_hit_10pct_up": pd.NA,
        "outcome_hit_5pct_down_before_10up": pd.NA,
        "outcome_days_to_10pct": np.nan,
        "outcome_days_to_5pct": np.nan,
        "outcome_category": pd.NA,
        "mature_5d": False,
        "mature_10d": False,
        "mature_20d": False,
        "label_asof_date": canonical_session_date(dates[-1]),
        "calculation_version": CALCULATION_VERSION,
    }
    five = forward(5)
    if five:
        ret, gain, drawdown = five
        result.update(
            outcome_5d_return=round(ret, 6),
            outcome_max_gain_5d=round(gain, 6),
            outcome_max_drawdown_5d=round(drawdown, 6),
            outcome_hit_5pct_up_5d=bool(gain >= 0.05),
            mature_5d=True,
        )
    ten = forward(10)
    if ten:
        ret, gain, drawdown = ten
        result.update(
            outcome_10d_return=round(ret, 6),
            outcome_max_gain_10d=round(gain, 6),
            outcome_max_drawdown_10d=round(drawdown, 6),
            outcome_hit_7pct_up_10d=bool(gain >= 0.07),
            mature_10d=True,
        )
    twenty = forward(20)
    if twenty:
        ret, gain, drawdown = twenty
        hit_10 = bool(gain >= 0.10)
        future_close = close[idx + 1 : idx + 21]
        future_high = high[idx + 1 : idx + 21]
        future_low = low[idx + 1 : idx + 21]
        first_close_10 = next(
            (i for i, value in enumerate((future_close - entry) / entry) if value >= 0.10),
            20,
        )
        hit_5_before_10 = hit_10 and bool(
            ((future_low[:first_close_10] - entry) / entry <= -0.05).any()
        )
        days_to_10 = next(
            (i + 1 for i, value in enumerate(future_high) if (value - entry) / entry >= 0.10),
            20,
        )
        days_to_5 = next(
            (i + 1 for i, value in enumerate(future_high) if (value - entry) / entry >= 0.05),
            20,
        )
        category = (
            "BIG_WIN" if ret >= 0.10 else "SMALL_WIN" if ret >= 0.02 else
            "BREAKEVEN" if ret >= -0.02 else "SMALL_LOSS" if ret >= -0.08 else "BIG_LOSS"
        )
        result.update(
            outcome_20d_return=round(ret, 6),
            outcome_max_gain_20d=round(gain, 6),
            outcome_max_drawdown_20d=round(drawdown, 6),
            outcome_hit_10pct_up=hit_10,
            outcome_hit_5pct_down_before_10up=hit_5_before_10,
            outcome_days_to_10pct=days_to_10,
            outcome_days_to_5pct=days_to_5,
            outcome_category=category,
            mature_20d=True,
        )
    return result


def compute_forward_outcomes(technicals: pd.DataFrame, idx: int) -> dict[str, Any] | None:
    """Return independently matured labels without treating pending data as failure."""
    return _forward_outcomes_arrays(
        technicals["close"].to_numpy(dtype=float),
        technicals["high"].to_numpy(dtype=float),
        technicals["low"].to_numpy(dtype=float),
        technicals["date"].to_numpy(),
        idx,
    )


def build_ticker_observations(ticker: str, daily_ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Build all eligible state rows, including immature recent horizons."""
    technicals = compute_technicals(daily_ohlcv)
    close = technicals["close"].to_numpy(dtype=float)
    high = technicals["high"].to_numpy(dtype=float)
    low = technicals["low"].to_numpy(dtype=float)
    dates = technicals["date"].to_numpy()
    technical_rows = list(technicals.itertuples(index=False))
    rows: list[dict[str, Any]] = []
    for idx in range(MIN_BARS_REQUIRED, len(technicals)):
        state = _calculate_core_state_fast(technical_rows[idx])
        outcomes = _forward_outcomes_arrays(close, high, low, dates, idx)
        if state is not None and outcomes is not None:
            rows.append({"ticker": ticker.upper().strip(), **state, **outcomes})
    result = pd.DataFrame(rows)
    if not result.empty and result.duplicated(["ticker", "date", "calculation_version"]).any():
        raise ActuarialCoreContractError("builder produced duplicate ticker/date/version keys")
    return result
