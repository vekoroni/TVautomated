"""Daily review, section 3: where the opportunity is strongest (ACK 9 Oct 2026). Display only.

Top-down, from data the board already holds:
  market       QQQ vs SPY per horizon; broad or concentrated (RSP vs SPY, holdings participation)
  sectors      relative strength vs SPY kept apart from absolute direction (XLU can beat a falling
               SPY: defensive preference, not a call setup)
  constituents share of each ETF's weight that moved with it (issuer holdings)
  location     room to the nearest obstacle above and below, in % and in daily moves
Thresholds come from config["opportunity"] and are PROVISIONAL.
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

MISSING = "MISSING"


def _ret(metrics: Mapping, ticker: str, h: int):
    m = metrics.get(ticker) or {}
    if m.get("status") == MISSING:
        return None
    value = m.get(f"ret_{h}d")
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def leadership(metrics: Mapping, holdings: Mapping, horizons: Sequence[int], cfg: Mapping) -> dict:
    """QQQ vs SPY per horizon, and whether the market's move is broad or concentrated (20d)."""
    windows = {}
    for h in horizons:
        q, s = _ret(metrics, "QQQ", h), _ret(metrics, "SPY", h)
        diff = None if q is None or s is None else round(q - s, 4)
        band = float(cfg["leader_band_pp"][str(h)])
        leader = MISSING if diff is None else "NEITHER" if abs(diff) < band else ("QQQ" if diff > 0 else "SPY")
        windows[str(h)] = {"qqq_pct": q, "spy_pct": s, "qqq_minus_spy_pp": diff, "leader": leader}
    rsp, spy = _ret(metrics, "RSP", 20), _ret(metrics, "SPY", 20)
    rsp_gap = None if rsp is None or spy is None else round(rsp - spy, 4)
    participation = {t: ((holdings.get(t) or {}).get("windows") or {}).get("20", {}).get("participation_weight_pct")
                     for t in ("SPY", "QQQ")}
    spy_part = participation.get("SPY")
    concentrated = ((rsp_gap is not None and rsp_gap <= -float(cfg["rsp_concentration_band_pp"]))
                    or (spy_part is not None and spy_part < float(cfg["participation_broad_min_pct"])))
    state = ("CONCENTRATED" if concentrated else "BROAD" if rsp_gap is not None and spy_part is not None
             else "UNKNOWN")
    return {"windows": windows,
            "breadth": {"state": state, "rsp_minus_spy_20d_pp": rsp_gap, "participation_50d_pct": participation}}


def _relative_label(rel, absolute, band):
    if rel is None or absolute is None:
        return MISSING
    if abs(rel) < band:
        return "IN_LINE"
    side = "OUTPERFORMING" if rel > 0 else "UNDERPERFORMING"
    if absolute > 0:
        return f"{side}_AND_RISING" if rel > 0 else f"{side}_WHILE_RISING"
    if absolute < 0:
        return f"{side}_WHILE_FALLING" if rel > 0 else f"{side}_AND_FALLING"
    return f"{side}_FLAT"


def sector_rows(metrics: Mapping, tickers: Sequence[str], holdings: Mapping, horizons: Sequence[int],
                cfg: Mapping) -> list[dict]:
    """Relative strength vs SPY beside absolute direction, plus constituent confirmation."""
    rows = []
    for t in tickers:
        windows = {}
        for h in horizons:
            absolute, spy = _ret(metrics, t, h), _ret(metrics, "SPY", h)
            rel = None if absolute is None or spy is None else round(absolute - spy, 4)
            window = ((holdings.get(t) or {}).get("windows") or {}).get(str(h))
            if not window:
                constituents, confirming, top = "NO_HOLDINGS", None, []
            else:
                confirming = window.get("confirming_weight_pct")
                constituents = ("UNKNOWN" if confirming is None else "CONFIRMED"
                                if confirming >= float(cfg["confirmation_min_pct"]) else "NOT_CONFIRMED")
                top = [r.get("ticker") for r in (window.get("top_contributors") or [])[:3]]
            windows[str(h)] = {"absolute_pct": absolute, "relative_pp": rel,
                               "label": _relative_label(rel, absolute, float(cfg["relative_band_pp"][str(h)])),
                               "constituents": constituents, "confirming_weight_pct": confirming,
                               "top_contributors": top}
        rows.append({"ticker": t, "windows": windows})
    return rows


def price_room(closes: pd.Series, *, rv20_pct, extra_levels: Mapping[str, float], highs: pd.Series | None = None,
               lows: pd.Series | None = None, current: float | None = None, current_basis: str | None = None) -> dict:
    """Nearest obstacle above and below today's close among the 252-session high/low, the 50/200
    session averages and any supplied levels (GEX walls/flip, pipeline target/invalidation).
    The 252-session high/low are where price actually traded (intraday high/low) when bars carry
    them; the averages stay on closes. Distance in % and in daily moves (20-session realised
    volatility / sqrt(252))."""
    c = closes.dropna()
    if c.empty:
        return {"close": None, "levels": {}, "above": None, "below": None, "range_basis": None}
    close = float(c.iloc[-1])
    anchor = float(current) if isinstance(current, (int, float)) and math.isfinite(current) and current > 0 else close
    h = highs.reindex(c.index).dropna() if highs is not None else pd.Series(dtype=float)
    l = lows.reindex(c.index).dropna() if lows is not None else pd.Series(dtype=float)
    intraday = not h.empty and not l.empty
    levels = ({"high_252": float(h.iloc[-252:].max()), "low_252": float(l.iloc[-252:].min())} if intraday
              else {"high_252": float(c.iloc[-252:].max()), "low_252": float(c.iloc[-252:].min())})
    if len(c) >= 50:
        levels["sma50"] = float(c.iloc[-50:].mean())
    if len(c) >= 200:
        levels["sma200"] = float(c.iloc[-200:].mean())
    for name, value in (extra_levels or {}).items():
        if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
            levels[name] = float(value)
    daily = (float(rv20_pct) / math.sqrt(252.0)) if isinstance(rv20_pct, (int, float)) and rv20_pct > 0 else None

    def describe(name):
        pct = round((levels[name] / anchor - 1.0) * 100.0, 4)
        return {"name": name, "level": round(levels[name], 4), "distance_pct": pct,
                "distance_daily_moves": round(abs(pct) / daily, 2) if daily else None}

    above = [n for n, v in levels.items() if v > anchor]
    below = [n for n, v in levels.items() if v < anchor]
    return {"close": close, "current": anchor, "current_basis": current_basis if anchor != close else "CLOSE",
            "daily_move_pct": None if daily is None else round(daily, 4),
            "range_basis": "INTRADAY_HIGH_LOW" if intraday else "CLOSES",
            "levels": {k: round(v, 4) for k, v in levels.items()},
            "above": describe(min(above, key=lambda n: levels[n])) if above else None,
            "below": describe(max(below, key=lambda n: levels[n])) if below else None}


def _basis(row) -> str | None:
    """"PREMARKET 08:40 ET" for a quote that supersedes the close, else None."""
    if not row or not row.get("supersedes_close"):
        return None
    from zoneinfo import ZoneInfo
    when = pd.Timestamp(row["time_utc"]).tz_convert(ZoneInfo("America/New_York"))
    return f"{row.get('segment')} {when.strftime('%H:%M')} ET"


def gex_levels(gex_records: Sequence[Mapping]) -> dict:
    """{ticker: {call_wall, put_wall, gamma_flip}} from the GEX proxy rows (SPY, QQQ)."""
    out = {}
    for row in gex_records or []:
        ticker = row.get("Ticker")
        if ticker:
            out[ticker] = {k: row.get(src) for k, src in (("call_wall", "Call_Wall"), ("put_wall", "Put_Wall"),
                                                            ("gamma_flip", "Gamma_Flip"), ("as_of", "Date"))}
    return out


def build(*, metrics: Mapping, closes: pd.DataFrame, holdings: Mapping, horizons: Sequence[int], sectors: Sequence[str],
          gex_records: Sequence[Mapping], proposals: Mapping, room_tickers: Sequence[str], cfg: Mapping,
          highs: pd.DataFrame | None = None, lows: pd.DataFrame | None = None, latest: Mapping | None = None) -> dict:
    """The section 3 payload: market, sectors, constituents and price location."""
    gex = gex_levels(gex_records)
    room = {}
    for t in room_tickers:
        if t not in closes.columns:
            continue
        levels = dict(gex.get(t) or {})
        gex_as_of = levels.pop("as_of", None)
        prop = proposals.get(t) or {}
        levels["pipeline_target"] = prop.get("target_spot")
        levels["pipeline_invalidation"] = prop.get("invalidation_spot")
        room[t] = {**price_room(closes[t], rv20_pct=(metrics.get(t) or {}).get("rv20"), extra_levels=levels,
                                highs=highs[t] if highs is not None and t in highs.columns else None,
                                lows=lows[t] if lows is not None and t in lows.columns else None,
                                current=((latest or {}).get(t) or {}).get("current"),
                                current_basis=_basis((latest or {}).get(t))),
                   "gex_as_of": None if gex_as_of is None else str(gex_as_of)}
    return {"leadership": leadership(metrics, holdings, horizons, cfg),
            "sectors": sector_rows(metrics, sectors, holdings, horizons, cfg),
            "room": room, "settings": dict(cfg)}
