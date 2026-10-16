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


# --- live sector correlation (ACK 16 Oct 2026: "a breakdown of the sectors and their correlation, that is how we
# start to understand the psychology of the markets"). Display only. ------------------------------------------

def _character(beta: float) -> str:
    if beta < 0:
        return "HEDGE"
    if beta < 0.35:
        return "DEFENSIVE"
    if beta < 0.8:
        return "PARTIAL"
    if beta < 1.2:
        return "MARKET_LIKE"
    return "AMPLIFIER"


def _matrix(frame: pd.DataFrame, names: Sequence[str], min_periods: int) -> dict:
    m = frame[list(names)].corr(min_periods=min_periods)
    return {a: {b: (1.0 if a == b else (None if not np.isfinite(m.loc[a, b]) else round(float(m.loc[a, b]), 3)))
                for b in names} for a in names}


def correlation_block(closes: pd.DataFrame, sectors: Sequence[str], industries: Sequence[str], benchmark: str,
                      cfg: Mapping) -> dict:
    """How sectors move with the market and with each other.

    - matrix: daily-return correlation between sectors over the long and short windows, and of their returns
      relative to the benchmark (the rotation "seesaw": the market's own move removed);
    - to_benchmark: correlation (long/short), beta, return on the benchmark's worst/best days as a multiple of
      its move, a character label from beta, and the outside asset most linked to the relative move;
    - crowding: average pairwise sector correlation over the short window, against its own history;
    - shifts: pairs whose short-window correlation differs most from the long-window one.
    A ticker without enough history is listed as missing, never shown as zero."""
    short_n, long_n, min_n = int(cfg["short_sessions"]), int(cfg["long_sessions"]), int(cfg["min_sessions"])
    returns = closes.pct_change(fill_method=None)
    long_r, short_r = returns.iloc[-long_n:], returns.iloc[-short_n:]
    assets = [a for a in cfg["cross_assets"] if a in returns.columns]

    def enough(t):
        return (t in returns.columns and int(long_r[t].notna().sum()) >= min_n
                and int(short_r[t].notna().sum()) >= min(min_n, short_n // 2))

    wanted = list(dict.fromkeys(list(sectors) + list(industries)))
    ok = [t for t in wanted if enough(t)]
    missing = [t for t in wanted if t not in ok]
    sec = [t for t in sectors if t in ok]
    bench = long_r[benchmark]
    lo, hi = bench.quantile(float(cfg["tail_quantile"])), bench.quantile(1 - float(cfg["tail_quantile"]))

    to_bench = {}
    for t in ok:
        both = pd.concat([long_r[t], bench], axis=1, keys=["x", "s"]).dropna()
        x, s = both["x"], both["s"]
        beta = float(np.cov(x, s)[0, 1] / s.var())
        rel = x - s
        drivers = {a: float(rel.corr(long_r[a].reindex(rel.index))) for a in assets if a != t}
        drivers = {a: v for a, v in drivers.items() if np.isfinite(v)}
        top = max(drivers, key=lambda a: abs(drivers[a])) if drivers else None
        short_both = pd.concat([short_r[t], short_r[benchmark]], axis=1).dropna()
        to_bench[t] = {
            "corr_long": round(float(x.corr(s)), 3),
            "corr_short": round(float(short_both.iloc[:, 0].corr(short_both.iloc[:, 1])), 3),
            "beta": round(beta, 3), "character": _character(beta),
            "vol_pct": round(float(x.std() * np.sqrt(252) * 100), 2),
            "down_capture": round(float(x[s <= lo].mean() / s[s <= lo].mean()), 3),
            "up_capture": round(float(x[s >= hi].mean() / s[s >= hi].mean()), 3),
            "driver": None if top is None else {"asset": top, "name": cfg["cross_assets"][top],
                                                "corr": round(drivers[top], 3)},
            "drivers": {a: round(v, 3) for a, v in drivers.items()},
        }

    matrix = {"long": _matrix(long_r, sec, min_n), "short": _matrix(short_r, sec, min(min_n, short_n // 2)),
              "relative": _matrix(long_r[sec].sub(bench, axis=0), sec, min_n)} if sec else {}

    crowding = None
    if len(sec) >= 2:
        upper = np.triu_indices(len(sec), 1)
        values, dates = [], []
        frame = returns[sec]
        for end in range(short_n, len(frame) + 1):
            window = frame.iloc[end - short_n:end]
            if window.notna().sum().min() < short_n // 2:
                continue
            values.append(float(np.nanmean(window.corr().values[upper])))
            dates.append(str(frame.index[end - 1].date()))
        if values:
            hist = np.asarray(values)
            now = hist[-1]
            pct = float(np.mean(hist < now) * 100)
            k = int(cfg["crowding_change_sessions"])
            state = ("LOW" if pct <= float(cfg["crowding_low_pctile"]) else
                     "HIGH" if pct >= float(cfg["crowding_high_pctile"]) else "NORMAL")
            n_hist = int(cfg["history_points"])
            crowding = {"now": round(now, 3), "pctile": round(pct, 1), "state": state,
                        "median": round(float(np.median(hist)), 3), "min": round(float(hist.min()), 3),
                        "max": round(float(hist.max()), 3), "since": dates[0], "as_of": dates[-1],
                        "change_vs_prior": round(float(now - hist[-1 - k]), 3) if len(hist) > k else None,
                        "long_window": round(float(np.nanmean(long_r[sec].corr().values[upper])), 3),
                        "history": {"sessions": dates[-n_hist:], "values": [round(v, 3) for v in hist[-n_hist:]]}}

    shifts = []
    for i, a in enumerate(sec):
        for b in sec[i + 1:]:
            lv, sv = matrix["long"][a][b], matrix["short"][a][b]
            if lv is None or sv is None or abs(sv - lv) < float(cfg["shift_min_abs_change"]):
                continue
            shifts.append({"a": a, "b": b, "long": lv, "short": sv, "change": round(sv - lv, 3)})
    shifts.sort(key=lambda d: -abs(d["change"]))

    return {"sectors": sec, "tickers": ok, "missing": missing, "benchmark": benchmark,
            "windows": {"short": short_n, "long": long_n}, "as_of": str(returns.index[-1].date()),
            "matrix": matrix, "to_benchmark": to_bench, "crowding": crowding,
            "shifts": shifts[: int(cfg["max_shifts"])]}
