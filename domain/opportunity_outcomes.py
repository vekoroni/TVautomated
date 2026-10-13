"""R3 outcome views for one entry opportunity (B4.2 part 2, ACK 12 Oct 2026).

Measured from completed daily bars only - never stored guesses. The opportunity is the first close beyond the thesis
trigger; the feasible fill is the next session's open (the close is only known at the close). ATR(14, simple true range)
is frozen at the trigger close. Views: +1 / +3 / +5 / +10 session returns in ATR on the thesis side (+1 is the fill
session's close), MFE / MAE over the 10-session window, and the first +-1 ATR barrier from the fill with same-bar
ambiguity flagged. A view without enough sessions is None and the row is CENSORED; no session after the trigger close
is PENDING_FILL. Underlying only, gross of costs: context for mining, not a verdict on the pipeline.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

HORIZONS = (1, 3, 5, 10)
WINDOW = 10
ATR_SESSIONS = 14
VIEWS_VERSION = "OPPORTUNITY_VIEWS_V1"


def _atr(bars: pd.DataFrame, i: int) -> Optional[float]:
    if i < 1:
        return None
    hi, lo, cl = bars["high"].astype(float), bars["low"].astype(float), bars["close"].astype(float)
    tr = pd.concat([hi - lo, (hi - cl.shift()).abs(), (lo - cl.shift()).abs()], axis=1).max(axis=1)
    window = tr.iloc[max(1, i - ATR_SESSIONS + 1): i + 1]
    value = float(window.mean()) if len(window) else None
    return value if value and value > 0 else None


def opportunity_outcome_views(bars: pd.DataFrame, *, trigger_close_date: str, side: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"views_version": VIEWS_VERSION, "views_status": None, "atr_at_trigger": None,
                           "fill_date": None, "fill_price": None, "sessions_after_fill": 0,
                           **{f"ret_{h}_atr": None for h in HORIZONS}, "mfe_10_atr": None, "mae_10_atr": None,
                           "first_barrier": None, "basis": "UNDERLYING_GROSS_OF_COSTS"}
    sign = {"BULL": 1.0, "BEAR": -1.0}.get(str(side or "").upper())
    if sign is None or bars is None or bars.empty or not trigger_close_date:
        out["views_status"] = "NOT_EVALUATED"
        return out
    frame = bars.sort_values("date").reset_index(drop=True)
    dates = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d").tolist()
    key = str(trigger_close_date)[:10]
    if key not in dates:
        out["views_status"] = "TRIGGER_BAR_NOT_IN_STORE"
        return out
    t = dates.index(key)
    atr = _atr(frame, t)
    out["atr_at_trigger"] = atr
    if t + 1 >= len(frame):
        out["views_status"] = "PENDING_FILL"
        return out
    if atr is None:
        out["views_status"] = "NO_ATR"
        return out
    f = t + 1
    fill = float(frame["open"].iloc[f])
    out.update(fill_date=dates[f], fill_price=fill)
    window = frame.iloc[f: f + WINDOW]
    out["sessions_after_fill"] = len(window)
    for h in HORIZONS:
        if len(window) >= h:
            out[f"ret_{h}_atr"] = sign * (float(window["close"].iloc[h - 1]) - fill) / atr
    if len(window):
        hi, lo = window["high"].astype(float), window["low"].astype(float)
        fav = (hi.max() - fill) if sign > 0 else (fill - lo.min())
        adv = (fill - lo.min()) if sign > 0 else (hi.max() - fill)
        out["mfe_10_atr"], out["mae_10_atr"] = fav / atr, adv / atr
        up, down = fill + atr, fill - atr
        for h_, l_ in zip(hi, lo):
            hit_up, hit_down = h_ >= up, l_ <= down
            if hit_up and hit_down:
                out["first_barrier"] = "AMBIGUOUS_SAME_BAR"
                break
            if hit_up or hit_down:                         # side-relative: +1 ATR in the thesis direction first
                out["first_barrier"] = "FAVOURABLE" if (hit_up if sign > 0 else hit_down) else "ADVERSE"
                break
        else:
            out["first_barrier"] = "NONE_YET" if len(window) < WINDOW else "NONE_IN_WINDOW"
    out["views_status"] = "COMPLETE" if len(window) >= WINDOW else "CENSORED"
    return out


def opportunity_cohort(rows, bars_for) -> list:
    """R3 cohort: one row per (event, entry opportunity) from the append-only ledger rows (oldest first).

    first_seen_* is the first run that recorded the opportunity; recognition_lag_sessions counts completed sessions
    between the trigger close and the bar the pipeline first saw it on (how late the data reached mining). Outcome
    views come from the bars (bars_for(ticker) -> daily frame); a forming event has none (NO_CROSSING_YET).
    """
    groups: Dict[tuple, list] = {}
    for r in rows or []:
        groups.setdefault((r.get("event_id"), r.get("entry_opportunity_id") or None), []).append(r)
    cache: Dict[str, Any] = {}
    out = []
    for (event_id, opp), items in groups.items():
        first, last = items[0], items[-1]
        row = {"event_id": event_id, "entry_opportunity_id": opp, "ticker": first.get("ticker"),
               "timeframe": first.get("timeframe"), "candidate_id": first.get("candidate_id"),
               "thesis_side": first.get("thesis_side"), "trigger_close_date": last.get("trigger_close_date"),
               "first_seen_run": first.get("run_id"), "first_seen_as_of": first.get("as_of"),
               "first_seen_status": first.get("event_status"), "latest_status": last.get("event_status"),
               "latest_run": last.get("run_id"), "status_path": ">".join(i.get("event_status") or "" for i in items),
               "recognition_lag_sessions": None}
        tcd = row["trigger_close_date"]
        if opp is None or not tcd:
            row.update({"views_status": "NO_CROSSING_YET", "views_version": VIEWS_VERSION})
            out.append(row)
            continue
        ticker = str(row["ticker"] or "")
        if ticker not in cache:
            try:
                cache[ticker] = bars_for(ticker)
            except Exception:
                cache[ticker] = None
        bars = cache[ticker]
        if bars is not None and not bars.empty and row["first_seen_as_of"]:
            dates = pd.to_datetime(bars["date"]).dt.strftime("%Y-%m-%d")
            row["recognition_lag_sessions"] = int(((dates > str(tcd)[:10])
                                                   & (dates <= str(row["first_seen_as_of"])[:10])).sum())
        row.update(opportunity_outcome_views(bars, trigger_close_date=tcd, side=row["thesis_side"]))
        out.append(row)
    return out
