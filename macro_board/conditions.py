"""Point-in-time macro condition states, one row per XNYS session.

Every state is what could have been known at that session's close: FRED prints are lagged
to their publication day, stale inputs become MISSING (never their last value, never a
neutral state), and trend/vol/breadth reuse the outcome scorer's definitions
(``avshunter.c12_outcome.conditions.market_condition``) so the board and the scorer agree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from avshunter.c12_outcome.conditions import ConditionSettings, market_condition

MISSING = "MISSING"


@dataclass(frozen=True)
class ConditionDef:
    key: str
    label: str
    measured: str          # what was measured, in words (R6)
    source: str
    states: tuple[str, ...]


CONDITION_DEFS: tuple[ConditionDef, ...] = (
    ConditionDef("market_trend", "SPY trend", "SPY close vs its 50- and 200-session means (outcome-scorer definition)",
                 "historical_prices.sqlite", ("ABOVE_BOTH", "ABOVE_LONG_ONLY", "ABOVE_SHORT_ONLY", "BELOW_BOTH")),
    ConditionDef("market_vol", "Realised volatility", "SPY 20-session realised vol percentile vs trailing 252 sessions",
                 "historical_prices.sqlite", ("LOW", "MID", "HIGH")),
    ConditionDef("market_breadth", "Breadth", "Share of database tickers above their 50-session mean",
                 "historical_prices.sqlite", ("LOW", "MID", "HIGH")),
    ConditionDef("liquidity", "Net liquidity proxy", "20-session change in Fed assets - TGA - ON RRP ($bn; research proxy, not spendable capital), z vs trailing year",
                 "FRED WALCL, WTREGEN, RRPONTSYD", ("EXPANDING", "FLAT", "CONTRACTING")),
    ConditionDef("curve_level", "Curve level", "10Y minus 2Y Treasury yield (pct points)",
                 "FRED SPREAD_2Y10Y", ("INVERTED", "FLAT", "STEEP")),
    ConditionDef("curve_move", "Curve move", "20-session change in 10Y-2Y spread, z vs trailing year",
                 "FRED SPREAD_2Y10Y", ("STEEPENING", "STABLE", "FLATTENING")),
    ConditionDef("yields", "10Y yield", "20-session change in 10Y Treasury yield, z vs trailing year",
                 "FRED DGS10", ("RISING", "STABLE", "FALLING")),
    ConditionDef("credit", "Credit appetite", "20-session HYG vs LQD relative log return, z vs trailing year",
                 "historical_prices.sqlite", ("TIGHTENING", "STABLE", "WIDENING")),
    ConditionDef("dollar", "US dollar", "20-session USD vs EUR log change (inverse of FRED DEXUSEU), z vs trailing year",
                 "FRED DEXUSEU", ("STRENGTHENING", "STABLE", "WEAKENING")),
    ConditionDef("oil", "Oil", "20-session USO log return, z vs trailing year",
                 "historical_prices.sqlite", ("RISING", "STABLE", "FALLING")),
)


# Inputs behind each condition, for observation dates: ("fred", series, frequency) or ("price", ticker).
CONDITION_INPUTS: dict[str, tuple[tuple[str, ...], ...]] = {
    "market_trend": (("price", "SPY"),),
    "market_vol": (("price", "SPY"),),
    "market_breadth": (("price", "SPY"),),
    "liquidity": (("fred", "WALCL", "weekly"), ("fred", "WTREGEN", "weekly"), ("fred", "RRPONTSYD", "daily")),
    "curve_level": (("fred", "SPREAD_2Y10Y", "daily"),),
    "curve_move": (("fred", "SPREAD_2Y10Y", "daily"),),
    "yields": (("fred", "DGS10", "daily"),),
    "credit": (("price", "HYG"), ("price", "LQD")),
    "dollar": (("fred", "DEXUSEU", "daily"),),
    "oil": (("price", "USO"),),
}


# --- primitives ------------------------------------------------------------------------

def align_point_in_time(series: pd.Series, sessions: pd.DatetimeIndex, lag_days: int,
                        max_age_days: int) -> pd.Series:
    """Value known at each session: the latest observation published by then (observation
    date + ``lag_days``), or NaN when none exists or the observation is older than
    ``max_age_days`` (stale is missing, never carried forward)."""
    observed = series.dropna().sort_index()
    out = np.full(len(sessions), np.nan)
    if observed.empty:
        return pd.Series(out, index=sessions)
    available = observed.index + pd.Timedelta(days=lag_days)
    position = available.searchsorted(sessions, side="right") - 1
    has = position >= 0
    picked = np.clip(position, 0, None)
    age_days = (sessions.values - observed.index.values[picked]) / np.timedelta64(1, "D")
    keep = has & (age_days <= max_age_days)
    out[keep] = observed.values[picked][keep]
    return pd.Series(out, index=sessions)


def observation_date_at(series: pd.Series, session: pd.Timestamp, lag_days: int,
                        max_age_days: int) -> pd.Timestamp | None:
    """Observation date of the value visible at ``session`` (None when nothing usable)."""
    observed = series.dropna().sort_index()
    if observed.empty:
        return None
    position = (observed.index + pd.Timedelta(days=lag_days)).searchsorted(session, side="right") - 1
    if position < 0:
        return None
    used = observed.index[position]
    return used if (session - used).days <= max_age_days else None


def current_observations(*, session: pd.Timestamp, sessions: pd.DatetimeIndex, closes: pd.DataFrame,
                         fred: pd.DataFrame, config: Mapping) -> dict:
    """Per condition: the observation dates actually used today and how many sessions old the
    oldest one is (information clock: observation date, not build date)."""
    lags, ages = config["fred_publication_lag_days"], config["fred_max_age_days"]
    out = {}
    for key, inputs in CONDITION_INPUTS.items():
        parts = []
        for spec in inputs:
            if spec[0] == "fred":
                _, name, frequency = spec
                used = None if name not in fred.columns else observation_date_at(
                    fred[name], session, int(lags[name]), int(ages[frequency]))
            else:
                name = spec[1]
                column = closes[name].dropna() if name in closes.columns else pd.Series(dtype=float)
                column = column[column.index <= session]
                used = column.index[-1] if not column.empty else None
            parts.append({"input": name, "observed": None if used is None else str(used.date())})
        dated = [pd.Timestamp(p["observed"]) for p in parts if p["observed"]]
        oldest = min(dated) if dated else None
        behind = None if oldest is None else int(((sessions > oldest) & (sessions <= session)).sum())
        out[key] = {"inputs": parts, "oldest": None if oldest is None else str(oldest.date()), "sessions_old": behind}
    return out


def rolling_z(change: pd.Series, window: int, min_periods: int) -> pd.Series:
    """Change divided by its trailing standard deviation (window ends at the session; no future)."""
    scale = change.rolling(window, min_periods=min_periods).std()
    return change / scale.replace(0.0, np.nan)


def trend_state(change: pd.Series, *, window: int, min_periods: int, band_z: float,
                up: str, flat: str, down: str) -> pd.Series:
    z = rolling_z(change, window, min_periods)
    state = np.where(z > band_z, up, np.where(z < -band_z, down, flat))
    return pd.Series(np.where(z.isna(), MISSING, state), index=change.index)


def level_state(value: pd.Series, edges: Sequence[float], labels: Sequence[str]) -> pd.Series:
    low, high = edges
    state = np.where(value < low, labels[0], np.where(value < high, labels[1], labels[2]))
    return pd.Series(np.where(value.isna(), MISSING, state), index=value.index)


def analog_mask(states: pd.DataFrame, current: Mapping[str, str],
                min_match_fraction: float) -> tuple[pd.Series, pd.Series]:
    """Sessions whose condition states resemble today's.

    Only conditions observed today take part; a historical MISSING never counts as a match.
    Returns (mask, similarity in [0, 1])."""
    keys = [k for k, v in current.items() if v != MISSING and k in states.columns]
    if not keys:
        empty = pd.Series(False, index=states.index)
        return empty, pd.Series(np.nan, index=states.index)
    matches = sum((states[k] == current[k]).astype(int) for k in keys)
    similarity = matches / len(keys)
    return similarity >= min_match_fraction - 1e-9, similarity


# --- building the frame -----------------------------------------------------------------

def _market_states(spy_close: pd.Series, panel: np.ndarray, settings: ConditionSettings) -> pd.DataFrame:
    """c12 market condition per session (trend, vol, breadth)."""
    closes = spy_close.to_numpy(dtype=float)
    rows = []
    for index in range(len(closes)):
        market = market_condition(closes[: index + 1], panel[: index + 1], settings)
        rows.append({
            "market_trend": MISSING if market.market_trend_state == "INSUFFICIENT_HISTORY" else market.market_trend_state,
            "market_vol": market.market_vol_state,
            "market_breadth": market.market_breadth_state,
            "market_vol_pct": market.market_vol_percentile,
            "market_breadth_share": market.market_breadth,
        })
    return pd.DataFrame(rows, index=spy_close.index)


def build_condition_frame(*, sessions: pd.DatetimeIndex, closes: pd.DataFrame, breadth_panel: np.ndarray,
                          fred: pd.DataFrame, c12: ConditionSettings, config: Mapping) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (states, values): one row per session, one column per condition key."""
    cc = config["conditions"]
    lags = config["fred_publication_lag_days"]
    ages = config["fred_max_age_days"]
    n = int(cc["change_sessions"])
    trend_kw = dict(window=int(cc["zscore_window_sessions"]), min_periods=int(cc["zscore_min_sessions"]),
                    band_z=float(cc["trend_band_z"]))

    def fred_series(name: str, frequency: str) -> pd.Series:
        if name not in fred.columns:
            return pd.Series(np.nan, index=sessions)
        return align_point_in_time(fred[name], sessions, int(lags[name]), int(ages[frequency]))

    def price(ticker: str) -> pd.Series:
        return closes[ticker] if ticker in closes.columns else pd.Series(np.nan, index=sessions)

    market = _market_states(price("SPY"), breadth_panel, c12)
    states = market[["market_trend", "market_vol", "market_breadth"]].copy()
    values = pd.DataFrame(index=sessions)
    values["market_trend"] = price("SPY")
    values["market_vol"] = market["market_vol_pct"]
    values["market_breadth"] = market["market_breadth_share"]

    net_liquidity = (fred_series("WALCL", "weekly") / 1000.0 - fred_series("WTREGEN", "weekly") / 1000.0
                     - fred_series("RRPONTSYD", "daily"))
    values["liquidity"] = net_liquidity
    states["liquidity"] = trend_state(net_liquidity.diff(n), up="EXPANDING", flat="FLAT", down="CONTRACTING", **trend_kw)

    spread = fred_series("SPREAD_2Y10Y", "daily")
    values["curve_level"] = spread
    states["curve_level"] = level_state(spread, cc["curve_level_bands_pct"], ("INVERTED", "FLAT", "STEEP"))
    values["curve_move"] = spread.diff(n)
    states["curve_move"] = trend_state(spread.diff(n), up="STEEPENING", flat="STABLE", down="FLATTENING", **trend_kw)

    ten_year = fred_series("DGS10", "daily")
    values["yields"] = ten_year
    states["yields"] = trend_state(ten_year.diff(n), up="RISING", flat="STABLE", down="FALLING", **trend_kw)

    credit = np.log(price("HYG") / price("LQD"))
    values["credit"] = credit.diff(n) * 100.0
    states["credit"] = trend_state(credit.diff(n), up="TIGHTENING", flat="STABLE", down="WIDENING", **trend_kw)

    usd = -np.log(fred_series("DEXUSEU", "daily"))
    values["dollar"] = usd.diff(n) * 100.0
    states["dollar"] = trend_state(usd.diff(n), up="STRENGTHENING", flat="STABLE", down="WEAKENING", **trend_kw)

    oil = np.log(price("USO"))
    values["oil"] = oil.diff(n) * 100.0
    states["oil"] = trend_state(oil.diff(n), up="RISING", flat="STABLE", down="FALLING", **trend_kw)

    order = [d.key for d in CONDITION_DEFS]
    return states[order], values[order]
