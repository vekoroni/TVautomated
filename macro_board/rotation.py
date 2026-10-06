"""Sector rotation: relative strength vs SPY, its momentum, rotation quadrants, and what each
of those has been worth on recorded history.

The coordinates are a transparent approximation of a relative-rotation graph, NOT the
proprietary JdK RS-Ratio/RS-Momentum:
  RS trend    = 100 x (sector / SPY) / its trailing ``trend_sessions`` mean
  RS momentum = 100 x RS trend / RS trend ``momentum_sessions`` ago
Above 100 on both axes = LEADING; trend above / momentum below = WEAKENING; both below =
LAGGING; trend below / momentum above = IMPROVING. Missing data is MISSING, never a quadrant.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from .evidence import effective_n

QUADRANTS = ("LEADING", "WEAKENING", "LAGGING", "IMPROVING")


def quadrant(trend: float, momentum: float) -> str:
    if trend is None or momentum is None or not np.isfinite(trend) or not np.isfinite(momentum):
        return "MISSING"
    if trend >= 100.0:
        return "LEADING" if momentum >= 100.0 else "WEAKENING"
    return "IMPROVING" if momentum >= 100.0 else "LAGGING"


def rotation_coordinates(closes: pd.DataFrame, tickers: Sequence[str], benchmark: str, *,
                         trend_sessions: int, momentum_sessions: int) -> dict[str, pd.DataFrame]:
    out = {}
    base = closes[benchmark]
    for ticker in tickers:
        if ticker not in closes.columns:
            continue
        rs = closes[ticker] / base
        trend = 100.0 * rs / rs.rolling(trend_sessions, min_periods=trend_sessions).mean()
        momentum = 100.0 * trend / trend.shift(momentum_sessions)
        frame = pd.DataFrame({"trend": trend, "momentum": momentum})
        frame["quadrant"] = [quadrant(t, m) for t, m in zip(frame["trend"], frame["momentum"])]
        out[ticker] = frame
    return out


def relative_forward_returns(opens: pd.DataFrame, closes: pd.DataFrame, tickers: Sequence[str], benchmark: str,
                             horizon: int) -> pd.DataFrame:
    """Next open -> close ``horizon`` sessions later, sector minus benchmark (same window)."""
    entry, exit_ = opens.shift(-1), closes.shift(-horizon)
    fwd = exit_ / entry - 1.0
    return pd.DataFrame({t: fwd[t] - fwd[benchmark] for t in tickers if t in fwd.columns}, index=closes.index)


def transition_counts(quadrants: Mapping[str, pd.Series], step: int) -> dict:
    """How often each quadrant moved to each other quadrant ``step`` sessions later."""
    counts: dict[str, dict[str, int]] = {q: {r: 0 for r in QUADRANTS} for q in QUADRANTS}
    for series in quadrants.values():
        values = list(series)
        for i in range(0, len(values) - step, step):
            a, b = values[i], values[i + step]
            if a in counts and b in counts[a]:
                counts[a][b] += 1
    return counts


def quadrant_forward_evidence(quadrants: Mapping[str, pd.Series], rel_fwd: pd.DataFrame, horizon: int) -> dict:
    """Pooled forward relative return by quadrant (positions thinned per sector)."""
    pooled: dict[str, list[float]] = defaultdict(list)
    windows: dict[str, int] = defaultdict(int)
    for ticker, series in quadrants.items():
        if ticker not in rel_fwd.columns:
            continue
        values = rel_fwd[ticker].to_numpy(dtype=float)
        states = series.reindex(rel_fwd.index).to_numpy()
        for q in QUADRANTS:
            positions = np.flatnonzero((states == q) & np.isfinite(values))
            pooled[q].extend((values[positions] * 100.0).tolist())
            windows[q] += effective_n(positions, horizon)
        observed = np.flatnonzero(np.isin(states, QUADRANTS) & np.isfinite(values))
        pooled["ALL"].extend((values[observed] * 100.0).tolist())
        windows["ALL"] += effective_n(observed, horizon)
    out = {}
    for q in (*QUADRANTS, "ALL"):
        data = np.array(pooled[q])
        if data.size == 0:
            out[q] = {"n": 0, "n_eff": 0, "mean_pct": None, "beat_rate": None, "ci_low_pct": None, "ci_high_pct": None}
            continue
        n_eff = windows[q]
        std = float(np.std(data, ddof=1)) if data.size > 1 else float("nan")
        half = 1.2816 * std / np.sqrt(n_eff) if n_eff >= 2 and std > 0 else None   # ~80% normal interval
        mean = float(np.mean(data))
        out[q] = {"n": int(data.size), "n_eff": int(n_eff), "mean_pct": round(mean, 4),
                  "beat_rate": round(float(np.mean(data > 0)), 4),
                  "ci_low_pct": None if half is None else round(mean - half, 4),
                  "ci_high_pct": None if half is None else round(mean + half, 4)}
    return out


def sector_name_to_etf(etf_to_sector: Mapping[str, str]) -> dict[str, str]:
    """GICS sector name (lower case) -> primary SPDR sector ETF, from the single sector owner
    (config/sector_etf_map_v1.json). Industry ETFs sharing a sector never displace an XL* fund."""
    out: dict[str, str] = {}
    for etf, sector in etf_to_sector.items():
        key = str(sector).strip().lower()
        if etf.startswith("XL") and key not in out:
            out[key] = etf
    return out


def etfs_for(names: Sequence[str] | None, mapping: Mapping[str, str]) -> list[str]:
    return [mapping[n.strip().lower()] for n in names or [] if isinstance(n, str) and n.strip().lower() in mapping]


def score_lead_lag(calls: Sequence[tuple[int, Sequence[str], Sequence[str]]], opens: pd.DataFrame, closes: pd.DataFrame,
                   benchmark: str, horizon: int) -> dict:
    """``calls``: (entry_index, lead ETFs, lag ETFs). Spread = mean lead return - mean lag return
    from the entry open to the close ``horizon - 1`` sessions later."""
    spreads, entries = [], []
    for entry, lead, lag in calls:
        exit_index = entry + horizon - 1
        if not lead or not lag or exit_index >= len(closes.index):
            continue

        def basket(tickers):
            rets = [closes[t].iloc[exit_index] / opens[t].iloc[entry] - 1.0 for t in tickers
                    if t in closes.columns and np.isfinite(opens[t].iloc[entry]) and np.isfinite(closes[t].iloc[exit_index])]
            return float(np.mean(rets)) if rets else None

        a, b = basket(lead), basket(lag)
        if a is None or b is None:
            continue
        spreads.append((a - b) * 100.0)
        entries.append(entry)
    if not spreads:
        return {"n": 0, "n_eff": 0, "mean_spread_pct": None, "hit_rate": None}
    return {"n": len(spreads), "n_eff": effective_n(entries, horizon),
            "mean_spread_pct": round(float(np.mean(spreads)), 4),
            "hit_rate": round(float(np.mean(np.array(spreads) > 0)), 4)}
