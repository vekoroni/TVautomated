"""Day story: where money is going, the measured reasons that fit, and the trade analysis for the day.

ACK, 14 Oct 2026: a tab that "lists the possible scenarios and the news and an explicit trade analysis
for the day ... using the data to come up with narratives and how it would impact tickers ... why the
flow of money is going into that sector or why it's coming out".

Three voices, each labelled:
- MEASURED: templates built only from the board's own numbers (relative strength, share volume, option
  footprints, measured macro sensitivities, cross-asset co-movement). A driver is a measured association
  that fits or contradicts today's flow, never a proven cause.
- PUBLISHED: items from the event payload (LLM-made, not verified by the board), matched by keyword.
- AI NARRATIVE: Claude writes the story from the measured facts only; numbers it uses that are not in
  the facts, and flow calls that contradict the measurement, are flagged.

Macro informs, never scores (CLAUDE.md rule 6): nothing here feeds a gate, score or rank in the
pipeline. Each day's flow calls go to a ledger and are scored against what money did next.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from macro_board import evidence as ev
from macro_board.decision_points import LEVEL_LABELS

MISSING = "MISSING"
FLOW_SIGN = {"INFLOW": 1, "TURNING_IN": 1, "OUTFLOW": -1, "TURNING_OUT": -1}
FLOW_TEXT = {
    "INFLOW": "Money is moving in",
    "TURNING_IN": "Money is turning in after a weak stretch",
    "OUTFLOW": "Money is moving out",
    "TURNING_OUT": "Money is leaving a recent leader",
    "NONE": "No clear money flow",
}
AI_LABEL = ("AI NARRATIVE: written by Claude from the measured facts on this tab only; hypotheses, not "
            "verified news")
PUBLISHED = "PUBLISHED"


def _num(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x) if math.isfinite(x) else None


def _pp(x, digits=2):
    return "n/a" if x is None else f"{x:+.{digits}f}"


# --- money flow ------------------------------------------------------------------------------------

def money_flow(relative_pp: Mapping[str, float | None], bands: Mapping[str, float], windows: Mapping[str, str]) -> dict:
    """Relative return against the benchmark over the short and long windows (pp). Missing is MISSING."""
    short_h, long_h, day_h = str(windows["short"]), str(windows["long"]), str(windows["day"])
    short, long_, day = (_num(relative_pp.get(h)) for h in (short_h, long_h, day_h))
    rel = {h: _num(relative_pp.get(h)) for h in (day_h, short_h, long_h)}
    if short is None or long_ is None:
        gone = [h for h in (short_h, long_h) if rel[h] is None]
        return {"label": MISSING, "relative_pp": rel,
                "text": f"Flow unknown: relative return over {', '.join(gone)} sessions is missing."}
    sb, lb = float(bands[short_h]), float(bands[long_h])
    if abs(short) < sb:
        label = "NONE"
    elif short > 0:
        label = "TURNING_IN" if long_ < -lb else "INFLOW"
    else:
        label = "TURNING_OUT" if long_ > lb else "OUTFLOW"
    text = (f"{FLOW_TEXT[label]}: {_pp(short)} pts vs the benchmark over {short_h} sessions, {_pp(long_)} over "
            f"{long_h}" + (f", {_pp(day)} on the last session." if day is not None else "."))
    return {"label": label, "relative_pp": rel, "text": text}


def relative_returns(metrics: Mapping, ticker: str, benchmark: str, horizons: Sequence[str]) -> dict:
    out = {}
    for h in horizons:
        a, b = (_num((metrics.get(t) or {}).get(f"ret_{h}d")) for t in (ticker, benchmark))
        ok = (metrics.get(ticker) or {}).get("status") not in (MISSING, None) and a is not None and b is not None
        out[str(h)] = round(a - b, 4) if ok else None
    return out


def volume_footprint(volume: pd.Series, window: int) -> dict:
    """Last session's share volume against its own average of the previous ``window`` sessions."""
    v = volume.dropna()
    if len(v) < window + 1 or float(v.iloc[-window - 1:-1].mean()) <= 0:
        return {"ratio": None, "session": str(v.index[-1].date()) if len(v) else None}
    return {"ratio": round(float(v.iloc[-1] / v.iloc[-window - 1:-1].mean()), 4), "session": str(v.index[-1].date())}


# --- option-flow footprints ------------------------------------------------------------------------

def load_flow_history(db_path: Path, tickers: Sequence[str], *, as_of: str, lookback_dates: int,
                      front_bucket: str) -> dict[str, pd.DataFrame]:
    """Per ticker and stored quote date: call/put volume and open interest (all expiries), contracts captured,
    front-bucket ATM IV (call/put mean, %) and 25-delta skew (pts). Read-only."""
    path = Path(db_path)
    if not path.exists() or not tickers:
        return {}
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        marks = ",".join("?" * len(tickers))
        frame = pd.read_sql_query(
            f"SELECT ticker, quote_date, dte_bucket, side, contract_count, atm_iv, skew_25d, total_open_interest, total_volume "
            f"FROM iv_surface_history WHERE ticker IN ({marks}) AND quote_date <= ?",
            con, params=[*tickers, as_of])
    finally:
        con.close()
    out = {}
    for ticker, g in frame.groupby("ticker"):
        dates = sorted(g["quote_date"].unique())[-int(lookback_dates):]
        g = g[g["quote_date"].isin(dates)]
        by_side = g.groupby(["quote_date", "side"])[["total_volume", "total_open_interest"]].sum().unstack("side")
        front = g[g["dte_bucket"] == front_bucket].groupby("quote_date")[["atm_iv", "skew_25d"]].mean()
        rows = pd.DataFrame({
            "call_volume": by_side.get(("total_volume", "call")), "put_volume": by_side.get(("total_volume", "put")),
            "call_oi": by_side.get(("total_open_interest", "call")), "put_oi": by_side.get(("total_open_interest", "put")),
        })
        rows["contracts"] = g.groupby("quote_date")["contract_count"].sum()
        rows["atm_iv_pct"] = front["atm_iv"] * 100.0
        rows["skew_pts"] = front["skew_25d"] * 100.0
        out[ticker] = rows.reset_index().rename(columns={"index": "quote_date"}).sort_values("quote_date")
    return out


def _pctile(history: np.ndarray, value: float) -> float | None:
    h = history[np.isfinite(history)]
    return None if h.size == 0 or value is None or not math.isfinite(value) else float(np.mean(h <= value))


def footprint(hist: pd.DataFrame, *, session: str, sessions: pd.DatetimeIndex, cfg: Mapping) -> dict:
    """What option traders did on the last stored date, measured against the ticker's own stored history.
    A footprint says what was paid for, not which way the stock goes."""
    base = {"status": MISSING, "flags": [], "lean": "NONE", "quote_date": None, "prior_date": None}
    if hist is None or len(hist) == 0:
        return {**base, "text": "No stored option chain."}
    h = hist.sort_values("quote_date").reset_index(drop=True)
    last = h.iloc[-1]
    quote_date = str(last["quote_date"])
    index = pd.DatetimeIndex(sessions)
    pos_session = index.searchsorted(pd.Timestamp(session), side="right") - 1
    pos_quote = index.searchsorted(pd.Timestamp(quote_date), side="right") - 1
    age = int(pos_session - pos_quote)
    base.update({"quote_date": quote_date, "sessions_old": age})
    if age > int(cfg["max_age_sessions"]):
        return {**base, "text": f"Last stored chain {quote_date} is {age} sessions old: not today's flow."}
    prior = h.iloc[:-1]
    if len(prior) < int(cfg["min_history_dates"]):
        return {**base, "status": "THIN", "dates_in_history": int(len(prior)),
                "text": f"Only {len(prior)} earlier stored dates: too few to call anything unusual."}

    def val(row, key):
        return _num(row.get(key)) if hasattr(row, "get") else None

    cv, pv = val(last, "call_volume"), val(last, "put_volume")
    pr = h.iloc[-2]
    tol = float(cfg["coverage_tolerance_pct"]) / 100.0
    cov_now = val(last, "contracts")

    def comparable(rows):
        """Dates whose chain coverage (contracts captured) is within tolerance of today's."""
        if cov_now is None or "contracts" not in rows:
            return rows
        c = rows["contracts"].to_numpy(dtype=float)
        return rows[np.isfinite(c) & (np.abs(c / cov_now - 1.0) <= tol)]

    peers = comparable(prior)
    out = {**base, "status": "OK", "prior_date": str(pr["quote_date"]), "dates_in_history": int(len(prior)),
           "comparable_dates": int(len(peers)), "contracts": cov_now, "call_volume": cv, "put_volume": pv,
           "coverage_note": None}
    enough = len(peers) >= int(cfg["min_history_dates"])
    med_c, med_p = ((float(np.nanmedian(peers[k].to_numpy(dtype=float))) if enough else float("nan"))
                    for k in ("call_volume", "put_volume"))
    out["call_volume_vs_median"] = round(cv / med_c, 4) if cv is not None and med_c > 0 else None
    out["put_volume_vs_median"] = round(pv / med_p, 4) if pv is not None and med_p > 0 else None
    if not enough:
        out["coverage_note"] = (f"Only {len(peers)} earlier dates captured a comparable chain ({cov_now:.0f} contracts): "
                                f"volume not compared.")
    pc_hist = (peers["put_volume"] / peers["call_volume"].replace(0, np.nan)).to_numpy(dtype=float) if enough else np.array([])
    pc = pv / cv if cv and pv is not None else None
    out["put_call_ratio"] = None if pc is None else round(pc, 4)
    out["put_call_pctile"] = _pctile(pc_hist, pc) if pc is not None and enough else None

    cov_prev = val(pr, "contracts")
    same_cover = cov_now is None or cov_prev is None or (cov_prev > 0 and abs(cov_now / cov_prev - 1.0) <= tol)
    if not same_cover:
        out["coverage_note"] = (f"Chain coverage changed {cov_prev:.0f} to {cov_now:.0f} contracts since "
                                f"{out['prior_date']}: open interest not compared.")

    def change_pct(key):
        a, b = val(last, key), val(pr, key)
        return round((a / b - 1.0) * 100.0, 4) if a is not None and b and same_cover else None

    def stability(key, limit, relative=False):
        """A stored series is read only if its own day-to-day changes are plausible (IV relative to its level)."""
        series = h[key].to_numpy(dtype=float)[:-1]
        diffs = np.abs(np.diff(series))
        diffs = diffs[np.isfinite(diffs)]
        if diffs.size < int(cfg["min_history_dates"]) - 1:
            return "THIN", diffs
        noise = float(np.median(diffs)) / (float(np.nanmedian(np.abs(series))) or np.nan) if relative else float(np.median(diffs))
        return ("OK" if math.isfinite(noise) and noise <= float(limit) else "UNRELIABLE"), diffs

    def change_pts(key, status):
        a, b = val(last, key), val(pr, key)
        return round(a - b, 4) if status == "OK" and a is not None and b is not None else None

    iv_status, iv_diffs = stability("atm_iv_pct", cfg["iv_max_median_change_ratio"], relative=True)
    sk_status, sk_diffs = stability("skew_pts", cfg["skew_max_median_change_pts"])
    out.update({"call_oi_change_pct": change_pct("call_oi"), "put_oi_change_pct": change_pct("put_oi"),
                "iv_status": iv_status, "atm_iv_pct": val(last, "atm_iv_pct") if iv_status == "OK" else None,
                "atm_iv_change_pts": change_pts("atm_iv_pct", iv_status),
                "atm_iv_pctile": (_pctile(prior["atm_iv_pct"].to_numpy(dtype=float), val(last, "atm_iv_pct") or float("nan"))
                                  if iv_status == "OK" else None),
                "skew_status": sk_status, "skew_pts": val(last, "skew_pts") if sk_status == "OK" else None,
                "skew_change_pts": change_pts("skew_pts", sk_status)})
    unstable = [f"{name} (median day-to-day change {float(np.median(d)):.1f} pts)"
                for name, st, d in (("stored ATM IV", iv_status, iv_diffs), ("stored 25-delta skew", sk_status, sk_diffs))
                if st == "UNRELIABLE"]
    out["unstable_note"] = (" and ".join(unstable) + " too unstable to read.") if unstable else None

    def unusual_change(change, diffs):
        """Larger than the given share of this ticker's own day-to-day changes."""
        return change is not None and diffs.size > 0 and float(np.mean(diffs < abs(change))) >= float(cfg["unusual_pctile"])

    heavy, unusual = float(cfg["heavy_volume_ratio"]), float(cfg["unusual_pctile"])
    oi_bar, iv_bar, sk_bar = (float(cfg[k]) for k in ("oi_change_unusual_pct", "iv_change_unusual_pts",
                                                       "skew_change_unusual_pts"))
    since = f"since {out['prior_date']}"
    flags = []

    def flag(key, side, text):
        flags.append({"key": key, "side": side, "text": text})

    n_peers = len(peers)
    if (out["put_volume_vs_median"] or 0) >= heavy:
        flag("HEAVY_PUT_VOLUME", "PUT", f"Put volume {out['put_volume_vs_median']:.1f}x its median of {n_peers} comparable stored dates.")
    if (out["call_volume_vs_median"] or 0) >= heavy:
        flag("HEAVY_CALL_VOLUME", "CALL", f"Call volume {out['call_volume_vs_median']:.1f}x its median of {n_peers} comparable stored dates.")
    if out["put_call_pctile"] is not None and out["put_call_pctile"] >= unusual:
        flag("HIGH_PUT_CALL_RATIO", "PUT", f"Put/call volume {pc:.2f}, top {100 - out['put_call_pctile'] * 100:.0f}% of its history.")
    if out["put_call_pctile"] is not None and out["put_call_pctile"] <= 1 - unusual:
        flag("LOW_PUT_CALL_RATIO", "CALL", f"Put/call volume {pc:.2f}, bottom {out['put_call_pctile'] * 100:.0f}% of its history.")
    if (out["put_oi_change_pct"] or 0) >= oi_bar:
        flag("PUT_OI_BUILD", "PUT", f"Put open interest {out['put_oi_change_pct']:+.1f}% {since}: new put positions held.")
    if (out["call_oi_change_pct"] or 0) >= oi_bar:
        flag("CALL_OI_BUILD", "CALL", f"Call open interest {out['call_oi_change_pct']:+.1f}% {since}: new call positions held.")
    ivc = out["atm_iv_change_pts"]
    if ivc is not None and abs(ivc) >= iv_bar and unusual_change(ivc, iv_diffs):
        flag("IV_JUMP" if ivc > 0 else "IV_CRUSH", None,
             f"Front ATM IV {ivc:+.1f} pts {since} (now {out['atm_iv_pct']:.1f}%), larger than "
             f"{unusual * 100:.0f}% of its own daily changes.")
    skc = out["skew_change_pts"]
    if skc is not None and abs(skc) >= sk_bar and unusual_change(skc, sk_diffs):
        key, side = ("SKEW_BID", "PUT") if skc > 0 else ("SKEW_EASED", "CALL")
        flag(key, side, f"25-delta skew {skc:+.1f} pts {since}: downside protection "
                        f"{'bid' if side == 'PUT' else 'cheaper'}.")
    sides = [f["side"] for f in flags if f["side"]]
    puts, calls = sides.count("PUT"), sides.count("CALL")
    lean = "PUT_SIDE" if puts > calls else "CALL_SIDE" if calls > puts else "NONE"
    out.update({"flags": flags, "lean": lean,
                "text": " ".join([f["text"] for f in flags] + [n for n in (out["coverage_note"], out["unstable_note"]) if n])
                        if flags or out["coverage_note"] or out["unstable_note"]
                        else f"Option activity in line with its history ({quote_date})."})
    return out


# --- why: drivers --------------------------------------------------------------------------------

def _fit(flow_label: str, signed: float | None) -> str:
    s = FLOW_SIGN.get(flow_label, 0)
    if not s or signed is None or signed == 0:
        return "NEUTRAL"
    return "CONSISTENT" if (signed > 0) == (s > 0) else "AGAINST"


def macro_drivers(sensitivity: Mapping, *, horizon: str, flow_label: str, min_abs_t: float, labels: Mapping[str, str],
                  changes: Sequence[Mapping], recent_sessions: Sequence[str]) -> list[dict]:
    """Conditions in today's state in which this ETF has measurably beaten or trailed its normal return."""
    recent = set(recent_sessions)
    out = []
    for cond, s in ((sensitivity or {}).get(str(horizon)) or {}).items():
        t, excess = _num(s.get("t")), _num(s.get("excess_pct"))
        if t is None or excess is None or abs(t) < float(min_abs_t):
            continue
        changed = next((c["session"] for c in changes if c.get("condition") == cond and c.get("to") == s.get("state")
                        and c.get("session") in recent), None)
        name = labels.get(cond, cond)
        word = "beat" if excess > 0 else "trailed"
        text = (f"{name} {str(s.get('state')).replace('_', ' ').lower()}"
                + (f" (changed {changed})" if changed else "")
                + f": in past sessions like this it {word} its normal {horizon}-session return by {_pp(excess)} pts "
                  f"(t {t:+.1f}, {s.get('n_eff_in')} independent windows).")
        out.append({"kind": "MACRO", "condition": cond, "state": s.get("state"), "excess_pct": excess, "t": t,
                    "n_eff": s.get("n_eff_in"), "recent_change": changed, "fit": _fit(flow_label, excess), "text": text})
    return sorted(out, key=lambda d: -abs(d["t"]))


def cross_asset_drivers(relative_daily: pd.Series, assets_daily: pd.DataFrame, *, window: int, min_abs_corr: float,
                        short: int, flow_label: str, names: Mapping[str, str]) -> list[dict]:
    """Assets the ETF's relative return has measurably moved with, and what they did over the flow window."""
    out = []
    rel = relative_daily.dropna()
    for asset in assets_daily.columns:
        a = assets_daily[asset].reindex(rel.index)
        both = pd.concat([rel, a], axis=1).dropna().iloc[-int(window):]
        if len(both) < max(20, int(window) // 2):
            continue
        corr = float(both.iloc[:, 0].corr(both.iloc[:, 1]))
        if not math.isfinite(corr) or abs(corr) < float(min_abs_corr):
            continue
        recent = assets_daily[asset].dropna().iloc[-int(short):]
        if len(recent) < int(short):
            continue
        move = float(np.prod(1.0 + recent.to_numpy()) - 1.0) * 100.0
        fit = _fit(flow_label, math.copysign(1.0, corr) * move if move else None)
        text = (f"{names.get(asset, asset)} ({asset}) {_pp(move)}% over {short} sessions; this ETF's relative return "
                f"has moved {'with' if corr > 0 else 'against'} it (corr {corr:+.2f}, {len(both)} sessions).")
        out.append({"kind": "CROSS_ASSET", "asset": asset, "corr": round(corr, 4), "asset_move_pct": round(move, 4),
                    "fit": fit, "text": text})
    return sorted(out, key=lambda d: -abs(d["corr"]))


def match_news(items: Sequence[Mapping], keywords: Mapping[str, Sequence[str]]) -> dict[str, list]:
    """Published items whose text names a sector keyword. The board does not verify them."""
    out: dict[str, list] = {}
    for item in items or []:
        blob = " ".join(str(item.get(k) or "") for k in ("name", "institution", "what_changed", "surprise", "event_name"))
        for etf, words in keywords.items():
            if any(re.search(rf"\b{re.escape(w)}", blob, flags=re.IGNORECASE) for w in words):
                out.setdefault(etf, []).append({"label": PUBLISHED, "name": item.get("name") or item.get("event_name"),
                                                "institution": item.get("institution"),
                                                "what_changed": item.get("what_changed"),
                                                "surprise": item.get("surprise"), "time_utc": item.get("time_utc"),
                                                "source": item.get("source") or "event payload (LLM)"})
    return out


# --- ticker impact -------------------------------------------------------------------------------

def candidate_links(candidates: Sequence[Mapping], flows: Mapping[str, str], *, min_link_corr: float) -> dict[str, list]:
    out: dict[str, list] = {}
    for c in candidates or []:
        etf, corr, side = c.get("sector_etf"), _num(c.get("link_corr")), str(c.get("direction") or "").upper()
        flow = flows.get(etf) if etf else None
        if not etf:
            rel = "NO_SECTOR"
        elif corr is None or abs(corr) < float(min_link_corr):
            rel = "STOCK_SPECIFIC"
        elif flow not in FLOW_SIGN:
            rel = "NO_FLOW_READ"
        else:
            want = "CALL" if FLOW_SIGN[flow] > 0 else "PUT"
            rel = "WITH_FLOW" if side == want else "AGAINST_FLOW"
        out.setdefault(etf or "NONE", []).append({"ticker": c.get("ticker"), "direction": side, "verdict": c.get("verdict"),
                                                  "link_corr": corr, "rank": c.get("rank"), "relation": rel,
                                                  "sector_flow": flow})
    return out


# --- trade analysis ------------------------------------------------------------------------------

def _level_text(level: Mapping | None) -> str:
    if not level:
        return "missing"
    name = str(level.get("name"))
    return f"{LEVEL_LABELS.get(name, name.replace('_', ' '))} {level['level']:.2f}"


RECORD_TEXT = {
    "FOLLOWS": " History: this read has tended to follow through.",
    "REVERSES": " History: this read has more often reversed than followed through; the measured case is the fade.",
    "NO_CLEAR_RECORD": " History: no clear follow-through or reversal after this read.",
    "THIN": " History: too few past cases to judge.",
}


def trade_idea(ticker: str, *, flow: Mapping, room: Mapping, expression: Mapping, drivers: Sequence[Mapping],
               footprint: Mapping, persistence: str | None, live: Sequence[Mapping], record: str | None = None) -> dict:
    """Explicit read for the day: side from the measured flow, trigger and invalidation from price room,
    expression from option pricing, and the evidence for and against. A read for the human, not a gate."""
    label = flow.get("label")
    above, below = (room or {}).get("above"), (room or {}).get("below")
    fp_lean = footprint.get("lean")
    if label not in FLOW_SIGN:
        text = (f"{ticker}: {FLOW_TEXT.get(label, 'flow unknown')}. It becomes a call above {_level_text(above)} or a put "
                f"below {_level_text(below)} if money starts to move.")
        return {"ticker": ticker, "side": "STAND_ASIDE", "trigger": None, "invalidation": None,
                "expression": expression, "balance": {"with": 0, "against": 0}, "text": text, "live": list(live),
                "persistence": persistence, "record": record}
    side = "CALL" if FLOW_SIGN[label] > 0 else "PUT"
    trigger, invalidation = (above, below) if side == "CALL" else (below, above)
    with_ = sum(1 for d in drivers if d.get("fit") == "CONSISTENT")
    against = sum(1 for d in drivers if d.get("fit") == "AGAINST")
    if footprint.get("status") == "OK" and fp_lean in ("PUT_SIDE", "CALL_SIDE"):
        if (fp_lean == "PUT_SIDE") == (side == "PUT"):
            with_ += 1
        else:
            against += 1
    if record == "FOLLOWS":
        with_ += 1
    elif record == "REVERSES":
        against += 1
    if trigger is None:
        text = f"{ticker} {side.lower()}s with the flow, but the trigger level is missing: no price room measured."
    else:
        verb = "clears" if side == "CALL" else "loses"
        text = (f"{ticker} {side.lower()}s if it {verb} {_level_text(trigger)} ({_pp(trigger.get('distance_pct'))}%, "
                f"{trigger.get('distance_daily_moves')} daily moves); the idea is wrong back through "
                f"{_level_text(invalidation)}.")
    pricing = expression.get("pricing")
    if pricing in ("CHEAP", "RICH", "FAIR"):
        text += f" Options are {pricing.lower()} against history."
    text += RECORD_TEXT.get(record, "")
    text += f" Evidence: {with_} for, {against} against."
    return {"ticker": ticker, "side": side, "trigger": trigger, "invalidation": invalidation, "expression": expression,
            "balance": {"with": with_, "against": against}, "text": text, "live": list(live), "persistence": persistence,
            "record": record}


# --- measured against reality ----------------------------------------------------------------------

def _label_series(rel: Mapping[str, pd.Series], bands: Mapping[str, float], windows: Mapping[str, str]) -> pd.Series:
    short, long_ = rel[str(windows["short"])], rel[str(windows["long"])]
    sb, lb = float(bands[str(windows["short"])]), float(bands[str(windows["long"])])
    lab = np.full(len(short), None, dtype=object)
    s, l = short.to_numpy(dtype=float), long_.to_numpy(dtype=float)
    ok = np.isfinite(s) & np.isfinite(l)
    lab[ok & (np.abs(s) < sb)] = "NONE"
    up, down = ok & (s >= sb), ok & (s <= -sb)
    lab[up & (l < -lb)] = "TURNING_IN"
    lab[up & (l >= -lb)] = "INFLOW"
    lab[down & (l > lb)] = "TURNING_OUT"
    lab[down & (l <= lb)] = "OUTFLOW"
    return pd.Series(lab, index=short.index)


def flow_persistence(opens: pd.DataFrame, closes: pd.DataFrame, ticker: str, *, benchmark: str,
                     bands: Mapping[str, float], windows: Mapping[str, str], horizons: Sequence[int],
                     min_n_eff: int) -> dict:
    """After each flow label in history, did money keep going the same way? Forward relative return
    (next open to the close h sessions later, ETF minus benchmark) against all sessions."""
    if ticker not in closes.columns or benchmark not in closes.columns:
        return {}
    rel = {}
    for h in {str(windows["short"]), str(windows["long"])}:
        n = int(h)
        rel[h] = (closes[ticker] / closes[ticker].shift(n) - closes[benchmark] / closes[benchmark].shift(n)) * 100.0
    labels = _label_series(rel, bands, windows)
    out = {}
    for h in horizons:
        fwd = ev.forward_returns(opens[[ticker, benchmark]], closes[[ticker, benchmark]], int(h))
        frel = (fwd[ticker] - fwd[benchmark])
        valid = frel.notna() & labels.notna()
        positions = np.flatnonzero(valid.to_numpy())
        allv = frel[valid]
        base = ev.summarise(allv.to_numpy(), positions, int(h), full=False)
        per = {}
        for label in ("INFLOW", "TURNING_IN", "OUTFLOW", "TURNING_OUT", "NONE"):
            m = valid & (labels == label)
            pos = np.flatnonzero(m.to_numpy())
            if pos.size == 0:
                continue
            vals = frel.to_numpy()[pos]
            stats = ev.summarise(vals, pos, int(h), full=False)
            sign = FLOW_SIGN.get(label, 0)
            per[label] = {"n": stats["n"], "n_eff": stats["n_eff"], "mean_rel_pp": round(stats["mean_pct"], 4),
                          "t": None if stats["t"] is None else round(stats["t"], 3),
                          "excess_vs_all_pp": round(stats["mean_pct"] - base["mean_pct"], 4),
                          "flow_side_rate": round(float(np.mean(np.sign(vals) == sign)), 4) if sign else None,
                          "thin": stats["n_eff"] < int(min_n_eff)}
        out[str(h)] = {"all": {"n": base["n"], "mean_rel_pp": None if base["mean_pct"] is None else round(base["mean_pct"], 4)},
                       "labels": per, "history_from": str(closes.index[positions[0]].date()) if positions.size else None}
    return out


def persistence_verdict(label: str, rec: Mapping, horizon: str, *, min_abs_t: float) -> str | None:
    """FOLLOWS / REVERSES / NO_CLEAR_RECORD / THIN: what the relative return did after this label in history."""
    row = ((rec.get(str(horizon)) or {}).get("labels") or {}).get(label)
    if label not in FLOW_SIGN or not row:
        return None
    if row["thin"]:
        return "THIN"
    signed = FLOW_SIGN[label] * (row["t"] or 0.0)
    return "FOLLOWS" if signed >= min_abs_t else "REVERSES" if signed <= -min_abs_t else "NO_CLEAR_RECORD"


def persistence_text(ticker: str, label: str, rec: Mapping, horizon: str, *, min_abs_t: float = 2.0) -> str | None:
    block = (rec.get(str(horizon)) or {})
    row = (block.get("labels") or {}).get(label)
    if not row or label not in FLOW_SIGN:
        return None
    signed_t = FLOW_SIGN[label] * (row["t"] or 0.0)
    verdict = ("too few independent windows" if row["thin"] else
               f"it tended to follow through (t {row['t']:+.1f})" if signed_t >= min_abs_t else
               f"it tended to reverse (t {row['t']:+.1f})" if signed_t <= -min_abs_t else
               f"no clear follow-through (t {row['t']:+.1f})")
    return (f"After past {label.replace('_', ' ').lower()} reads on {ticker}, the next {horizon} sessions averaged "
            f"{_pp(row['mean_rel_pp'])} pts vs the benchmark ({_pp(row['excess_vs_all_pp'])} vs all sessions, "
            f"{row['n_eff']} independent windows, same side {row['flow_side_rate'] * 100:.0f}%): {verdict}.")


def _ledger_key(r: Mapping) -> tuple:
    return (r.get("session"), r.get("ticker"))


def record_stories(path: Path, rows: Sequence[Mapping]) -> int:
    """Append one flow call per session and ticker (the first build of a session wins)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = {_ledger_key(r) for r in read_ledger(path)}
    new = [r for r in rows if _ledger_key(r) not in seen]
    with path.open("a", encoding="utf-8") as fh:
        for r in new:
            fh.write(json.dumps(r) + "\n")
    return len(new)


def read_ledger(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def score_ledger(ledger: Sequence[Mapping], opens: pd.DataFrame, closes: pd.DataFrame, *, benchmark: str,
                 horizons: Sequence[int]) -> dict:
    """Live record of the board's own flow calls: forward relative return once the horizon has passed."""
    out = {}
    index = closes.index
    for h in horizons:
        fwd = ev.forward_returns(opens, closes, int(h))
        rows, pending = [], 0
        for r in ledger:
            t, flow = r.get("ticker"), r.get("flow")
            if flow not in FLOW_SIGN or t not in closes.columns or benchmark not in closes.columns:
                continue
            ts = pd.Timestamp(r.get("session"))
            if ts not in index:
                pending += 1
                continue
            v = fwd.at[ts, t] - fwd.at[ts, benchmark]
            if not math.isfinite(v):
                pending += 1
                continue
            rows.append(FLOW_SIGN[flow] * v * 100.0)
        arr = np.asarray(rows, dtype=float)
        out[str(h)] = {"scored": int(arr.size), "pending": pending,
                       "mean_flow_side_pp": round(float(arr.mean()), 4) if arr.size else None,
                       "flow_side_rate": round(float(np.mean(arr > 0)), 4) if arr.size else None}
    return out


# --- AI narrative --------------------------------------------------------------------------------

SYSTEM_PROMPT = """You write the daily market story for a trading desk's macro board.

You receive one JSON document of measured facts produced by the board: relative strength per sector and
industry ETF, share-volume and option-flow footprints, macro conditions with each ETF's measured response,
cross-asset co-movement, published news items (made by another LLM and not verified), live scenario
triggers, pipeline candidates and the price levels for the day.

Write the story of where money is moving and the reasons that fit the measurements.
- Use only the facts given. No outside knowledge, no news that is not in the facts.
- Every claim about a sector or ticker cites at least one number from the facts. Copy numbers exactly.
- A driver is a measured association. Write "fits", "is consistent with" or "goes against", never
  "because" or "caused".
- Name the evidence against each story as plainly as the evidence for it.
- Published items are claims by another source; say so when you use one.
- money_flow for each sector must be the label the facts give for that ticker.
- Describe triggers and invalidation levels from the facts. Do not size positions or tell the reader to trade.
- Plain English for a junior trader. Short sentences."""

AI_SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {"type": "string"},
        "sectors": {"type": "array", "items": {
            "type": "object",
            "properties": {"ticker": {"type": "string"},
                           "money_flow": {"type": "string",
                                          "enum": ["INFLOW", "TURNING_IN", "OUTFLOW", "TURNING_OUT", "NONE", "MISSING"]},
                           "story": {"type": "string"}},
            "required": ["ticker", "money_flow", "story"], "additionalProperties": False}},
        "tickers": {"type": "array", "items": {
            "type": "object", "properties": {"ticker": {"type": "string"}, "story": {"type": "string"}},
            "required": ["ticker", "story"], "additionalProperties": False}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "would_change_view": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["overview", "sectors", "tickers", "risks", "would_change_view"],
    "additionalProperties": False,
}

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}(?:T[\d:.]+Z?)?")
_NUMBER = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:\.\d+)?")


def _numbers_in(text: str) -> list[str]:
    return _NUMBER.findall(_DATE.sub(" ", text))


def _fact_numbers(facts) -> list[float]:
    out = []

    def walk(x):
        if isinstance(x, Mapping):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
        elif isinstance(x, bool):
            return
        elif isinstance(x, (int, float)) and math.isfinite(x):
            out.append(abs(float(x)))
        elif isinstance(x, str):
            out.extend(abs(float(n)) for n in _numbers_in(x))

    walk(facts)
    return out


def verify(output: Mapping, facts: Mapping, *, max_small_integer: int = 60) -> dict:
    """Numbers in the AI text that the facts do not contain (rounded to the AI's own precision), and flow
    calls that contradict the measured flow. Small integers are windows and counts and are not checked."""
    known = _fact_numbers(facts)
    texts = [output.get("overview") or ""] + [s.get("story") or "" for s in output.get("sectors") or []] + \
            [t.get("story") or "" for t in output.get("tickers") or []] + list(output.get("risks") or []) + \
            list(output.get("would_change_view") or [])
    unverified = []
    for text in texts:
        for raw in _numbers_in(text):
            v = abs(float(raw))
            digits = len(raw.split(".")[1]) if "." in raw else 0
            if digits == 0 and v <= max_small_integer:
                continue
            if not any(round(k, digits) == round(v, digits) for k in known):
                unverified.append(raw.lstrip("+-"))
    measured = {s.get("ticker"): s.get("flow") for s in facts.get("stories") or []}
    disagreements = [s.get("ticker") for s in output.get("sectors") or []
                     if s.get("ticker") in measured and s.get("money_flow") != measured[s.get("ticker")]]
    unknown = [s.get("ticker") for s in output.get("sectors") or [] if s.get("ticker") not in measured]
    return {"unverified_numbers": sorted(set(unverified)), "flow_disagreements": disagreements,
            "unknown_tickers": unknown}


def _prompt(facts: Mapping) -> str:
    return ("Measured facts for the session (JSON). Write the day's story as the schema asks.\n\n"
            + json.dumps(facts, sort_keys=True))


def ai_narrative(facts: Mapping, cfg: Mapping, *, cache_dir: Path, session: str, kind: str,
                 client_factory: Callable[[], object]) -> dict:
    """Claude's narrative from the measured facts. Cached per facts hash; a failure never breaks the build."""
    if not cfg.get("enabled"):
        return {"status": "DISABLED", "label": AI_LABEL}
    cache_dir = Path(cache_dir)
    prompt = _prompt(facts)
    digest = hashlib.sha256("\n".join([cfg["model"], str(cfg["prompt_version"]), SYSTEM_PROMPT, prompt])
                            .encode("utf-8")).hexdigest()
    target = cache_dir / f"{session}_{digest[:12]}.json"
    if target.exists():
        try:
            return {**json.loads(target.read_text(encoding="utf-8")), "cached": True}
        except ValueError:
            pass
    if kind not in cfg.get("call_on_build_kinds", []):
        earlier = sorted(cache_dir.glob(f"{session}_*.json"), key=lambda p: p.stat().st_mtime) if cache_dir.exists() else []
        if earlier:
            try:
                return {**json.loads(earlier[-1].read_text(encoding="utf-8")), "cached": True, "earlier_build": True}
            except ValueError:
                pass
        return {"status": "NOT_CALLED", "label": AI_LABEL,
                "reason": f"{kind} build: the narrative is written on {', '.join(cfg.get('call_on_build_kinds', []))} builds."}
    try:
        client = client_factory()
    except Exception as exc:  # credentials or workspace not configured
        return {"status": "UNAVAILABLE", "label": AI_LABEL, "reason": f"{type(exc).__name__}: {str(exc)[:200]}"}
    request = {"model": cfg["model"], "max_tokens": int(cfg["max_tokens"]), "system": SYSTEM_PROMPT,
               "messages": [{"role": "user", "content": prompt}],
               "output_config": {"effort": cfg["effort"], "format": {"type": "json_schema", "schema": AI_SCHEMA}},
               "timeout": float(cfg["timeout_seconds"])}
    if cfg.get("fallbacks"):
        request["betas"] = ["server-side-fallback-2026-07-01"]
        request["extra_body"] = {"fallbacks": cfg["fallbacks"]}
    try:
        response = client.beta.messages.create(**request)
    except Exception as exc:
        return {"status": "FAILED", "label": AI_LABEL, "reason": f"{type(exc).__name__}: {str(exc)[:200]}"}
    stop = getattr(response, "stop_reason", None)
    if stop == "refusal":
        return {"status": "REFUSED", "label": AI_LABEL, "reason": "The model declined the request."}
    text = next((b.text for b in response.content if getattr(b, "type", None) == "text"), "")
    try:
        output = json.loads(text)
    except ValueError:
        return {"status": "FAILED", "label": AI_LABEL, "reason": f"Unparseable output (stop_reason {stop})."}
    result = {"status": "OK", "label": AI_LABEL, "model": getattr(response, "model", cfg["model"]),
              "prompt_version": cfg["prompt_version"], "session": session, "build_kind": kind,
              "facts_sha256": digest, "output": output, "verification": verify(output, facts), "cached": False}
    cache_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


# --- orchestration ---------------------------------------------------------------------------------

def default_client_factory():
    """Workspace-scoped Anthropic client (same configuration as build_macro_json). Key from the environment."""
    import anthropic
    from anthropic_runtime_config import workspace_id
    return anthropic.Anthropic(default_headers={"anthropic-workspace-id": workspace_id()})


def _day_scenarios(payload: Mapping, footprints: Mapping, focus: Sequence[str], cfg: Mapping) -> dict:
    plan = payload.get("session_plan") or {}
    instruments = []
    for t in focus:
        ins = (plan.get("instruments") or {}).get(t) or {}
        if not ins:
            continue
        branches = [{"branch": b, "text": (ins.get(b) or {}).get("text"), "expression": (ins.get(b) or {}).get("expression")}
                    for b in ("base", "up", "down") if (ins.get(b) or {}).get("text")]
        instruments.append({"ticker": t, "reference": ins.get("reference"), "basis": ins.get("basis"),
                            "daily_move_pct": ins.get("daily_move_pct"), "implied_move_pct": ins.get("implied_move_pct"),
                            "branches": branches, "history": [h.get("text") for h in ins.get("history") or []][:2],
                            "footprint": footprints.get(t)})
    ahead = int(cfg["events_sessions_ahead"])
    events = [{"name": e.get("name"), "date": e.get("date"), "time_et": e.get("time_et"), "kind": e.get("kind"),
               "detail": e.get("detail")}
              for e in (payload.get("decision_points") or {}).get("calendar") or []
              if isinstance(e.get("sessions_ahead"), int) and e["sessions_ahead"] <= ahead]
    call = plan.get("call") or {}
    published = ((payload.get("intel") or {}).get("events") or {})
    return {"next_session": plan.get("next_session"), "call": call.get("key"), "sentences": call.get("sentences") or [],
            "approach": call.get("approach"), "instruments": instruments, "events": events,
            "published_narrative": {"label": PUBLISHED, "source": "event payload (LLM)",
                                    "classification": published.get("classification"),
                                    "text": published.get("narrative")} if published.get("narrative") else None}


def build(payload: Mapping, config: Mapping, *, opens: pd.DataFrame, closes: pd.DataFrame, volumes: pd.DataFrame,
          sessions: pd.DatetimeIndex, rooms: Mapping, kind: str, record: bool, ai_enabled: bool = True,
          client_factory: Callable[[], object] = default_client_factory,
          resolve: Callable[[str], Path] = Path) -> dict:
    """The Day story payload."""
    from macro_board import session_plan as splan  # one owner for option pricing (cheap / rich)

    cfg = config["day_story"]
    rot_cfg = config["rotation"]
    bench = rot_cfg["benchmark"]
    windows = {k: str(v) for k, v in cfg["flow_windows"].items()}
    bands = config["opportunity"]["relative_band_pp"]
    horizons = sorted({windows["day"], windows["short"], windows["long"]}, key=int)
    focus = [t for t in config["session_plan"]["focus"] if t in closes.columns]
    tickers = [t for t in list(rot_cfg["sectors"]) + list(rot_cfg["industries"]) if t in closes.columns]
    etfs = payload.get("etfs") or {}
    metrics = {t: (etfs.get(t) or {}).get("metrics") or {} for t in set(tickers) | set(focus) | {bench}}
    session = str(payload["as_of_session"])

    flow_cfg = cfg["options_flow"]
    hist = load_flow_history(resolve(flow_cfg["db"]), tickers + focus, as_of=session,
                             lookback_dates=int(flow_cfg["lookback_dates"]), front_bucket=flow_cfg["front_bucket"])
    footprints = {t: footprint(hist.get(t), session=session, sessions=sessions, cfg=flow_cfg) for t in tickers + focus}

    labels = {m["key"]: m["label"] for m in (payload.get("conditions") or {}).get("meta") or []}
    changes = (payload.get("conditions") or {}).get("changes") or []
    recent = [str(d.date()) for d in sessions[-int(cfg["recent_change_sessions"]):]]
    daily = closes.pct_change(fill_method=None)
    assets = [a for a in cfg["cross_assets"] if a in daily.columns]
    news = match_news(((payload.get("review") or {}).get("information") or {}).get("items") or [], cfg["news_keywords"])
    rotation_rows = {r["ticker"]: r for r in (payload.get("rotation") or {}).get("rows") or []}
    live = [x for x in (payload.get("scenario_watch") or {}).get("live") or [] if x.get("state") in ("TRIGGERED", "WATCHING")]
    plan_cfg = config["session_plan"]

    flows, stories = {}, []
    for t in tickers:
        rel = relative_returns(metrics, t, bench, horizons)
        flow = money_flow(rel, bands, windows)
        flows[t] = flow["label"]
        vol = volume_footprint(volumes[t], int(cfg["volume_window_sessions"])) if t in volumes.columns else {"ratio": None}
        row = rotation_rows.get(t) or {}
        drivers = macro_drivers((etfs.get(t) or {}).get("sensitivity") or {}, horizon=str(cfg["driver_horizon"]),
                                flow_label=flow["label"], min_abs_t=float(cfg["driver_min_abs_t"]), labels=labels,
                                changes=changes, recent_sessions=recent)
        drivers += cross_asset_drivers(daily[t] - daily[bench], daily[[a for a in assets if a != t]],
                                       window=int(cfg["cross_asset_window_sessions"]),
                                       min_abs_corr=float(cfg["cross_asset_min_abs_corr"]), short=int(windows["short"]),
                                       flow_label=flow["label"], names=cfg["cross_assets"])
        drivers = sorted(drivers, key=lambda d: (d["fit"] == "NEUTRAL",
                                                 -(abs(d.get("t") or 0) / 2.0 + abs(d.get("corr") or 0))))
        drivers = drivers[: int(cfg["driver_max"])]
        persistence = flow_persistence(opens, closes, t, benchmark=bench, bands=bands, windows=windows,
                                       horizons=[int(h) for h in cfg["persistence_horizons"]],
                                       min_n_eff=int(cfg["persistence_min_n_eff"]))
        pers_text = persistence_text(t, flow["label"], persistence, str(cfg["driver_horizon"]),
                                     min_abs_t=float(cfg["persistence_min_abs_t"]))
        record = persistence_verdict(flow["label"], persistence, str(cfg["driver_horizon"]),
                                     min_abs_t=float(cfg["persistence_min_abs_t"]))
        expression = splan.expression(etfs.get(t) or {}, plan_cfg)
        ticker_live = [x for x in live if x.get("ticker") == t]
        idea = trade_idea(t, flow=flow, room=rooms.get(t) or {}, expression=expression, drivers=drivers,
                          footprint=footprints[t], persistence=pers_text, live=ticker_live, record=record)
        evidence = [flow["text"]]
        if vol.get("ratio") is not None:
            day_ret = _num(metrics.get(t, {}).get("ret_1d"))
            evidence.append(f"Share volume {vol['ratio']:.2f}x its {cfg['volume_window_sessions']}-session average on a "
                            f"{_pp(day_ret)}% day ({vol['session']}).")
        if row.get("quadrant"):
            evidence.append(f"Rotation: {row['quadrant'].lower()} for {row.get('sessions_in_quadrant')} sessions "
                            f"(5 sessions ago {str(row.get('quadrant_5_ago') or 'unknown').lower()}).")
        window20 = ((((etfs.get(t) or {}).get("holdings") or {}).get("windows") or {}).get(windows["long"]) or {})
        contributors = [f"{c.get('ticker')} {_pp(_num(c.get('contribution_pp')))}"
                        for c in (window20.get("top_contributors") or [])[:3] if isinstance(c, Mapping)]
        if contributors:
            evidence.append("Holdings carrying the 20-session move: " + ", ".join(contributors) + " pts.")
        stories.append({
            "ticker": t, "name": row.get("sector_name"), "kind": "sector" if t in rot_cfg["sectors"] else "industry",
            "flow": flow, "volume": vol, "quadrant": row.get("quadrant"), "quadrant_5_ago": row.get("quadrant_5_ago"),
            "footprint": footprints[t], "drivers": drivers, "published": news.get(t, []),
            "packet_bias": {"label": PUBLISHED, "value": row.get("packet_bias")} if row.get("packet_bias") else None,
            "persistence": persistence, "persistence_text": pers_text, "evidence": evidence, "trade": idea,
            "live": ticker_live, "candidates": [],
        })

    links = candidate_links((payload.get("session_plan") or {}).get("candidates") or [], flows,
                            min_link_corr=float(plan_cfg["min_link_corr"]))
    for s in stories:
        s["candidates"] = links.get(s["ticker"], [])[: int(cfg["max_candidates_per_story"])]
    short = windows["short"]
    stories.sort(key=lambda s: (s["flow"]["label"] in ("NONE", MISSING), -abs(s["flow"]["relative_pp"].get(short) or 0)))

    def names(label_set):
        return [s["ticker"] for s in stories if s["flow"]["label"] in label_set]

    overview = []
    for label_set, words in ((("INFLOW", "TURNING_IN"), "Money moving in"), (("OUTFLOW", "TURNING_OUT"), "Money moving out")):
        group = [s for s in stories if s["flow"]["label"] in label_set][:6]
        if group:
            overview.append(f"{words} (vs {bench}, {short} sessions): " + ", ".join(
                f"{s['ticker']} {_pp(s['flow']['relative_pp'].get(short))}" for s in group) + ".")
    missing = names((MISSING,))
    if missing:
        overview.append("Flow unknown (missing prices): " + ", ".join(missing) + ".")

    ideas = [s["trade"] for s in stories if s["trade"]["side"] != "STAND_ASIDE"][: int(cfg["max_trade_ideas"])]
    day = _day_scenarios(payload, footprints, focus, cfg)
    impact = [c for s in stories for c in s["candidates"]]
    impact_counts = {k: sum(1 for c in impact if c["relation"] == k)
                     for k in ("WITH_FLOW", "AGAINST_FLOW", "STOCK_SPECIFIC", "NO_FLOW_READ")}

    ledger_path = resolve(cfg["ledger"])
    if record:
        record_stories(ledger_path, [{"session": session, "ticker": s["ticker"], "flow": s["flow"]["label"],
                                      "relative_pp": s["flow"]["relative_pp"], "trade_side": s["trade"]["side"],
                                      "build_kind": kind, "built_at_utc": payload.get("built_at_utc")} for s in stories])
    ledger = read_ledger(ledger_path)
    live_record = score_ledger(ledger, opens, closes, benchmark=bench, horizons=[int(h) for h in cfg["persistence_horizons"]])

    facts = {
        "session": session, "next_session": day["next_session"], "benchmark": bench,
        "market": {"call": day["call"], "sentences": day["sentences"], "approach": day["approach"]},
        "index_branches": [{"ticker": i["ticker"], "branches": [b["text"] for b in i["branches"]],
                            "options_footprint": (i["footprint"] or {}).get("text")} for i in day["instruments"]],
        "events_ahead": day["events"],
        "stories": [{"ticker": s["ticker"], "name": s["name"], "flow": s["flow"]["label"],
                     "rel_1d_pp": s["flow"]["relative_pp"].get(windows["day"]),
                     "rel_5d_pp": s["flow"]["relative_pp"].get(short),
                     "rel_20d_pp": s["flow"]["relative_pp"].get(windows["long"]),
                     "evidence": s["evidence"], "options_footprint": s["footprint"].get("text"),
                     "drivers": [{"fit": d["fit"], "text": d["text"]} for d in s["drivers"]],
                     "published_news": [{"name": n["name"], "what_changed": (n.get("what_changed") or "")[:300]}
                                        for n in s["published"]],
                     "flow_record": s["persistence_text"], "trade": s["trade"]["text"],
                     "candidates": [{"ticker": c["ticker"], "direction": c["direction"], "relation": c["relation"]}
                                    for c in s["candidates"]],
                     "live_scenarios": [{"scenario": x["scenario"], "side": x["side"], "state": x["state"],
                                         "verdict": (x.get("record") or {}).get("verdict")} for x in s["live"]]}
                    for s in stories],
    }
    ai_cfg = dict(cfg["ai_narrative"])
    if not ai_enabled:  # as-of or AVSH_BOARD_AI=0 builds: no call, the session's latest narrative is shown labelled
        ai_cfg["call_on_build_kinds"] = []
    ai = ai_narrative(facts, ai_cfg, cache_dir=resolve(ai_cfg["cache_dir"]), session=session, kind=kind,
                      client_factory=client_factory)
    print(f"[board] day story: {len(stories)} ETFs, in {names(('INFLOW', 'TURNING_IN'))}, "
          f"out {names(('OUTFLOW', 'TURNING_OUT'))}; AI narrative {ai['status']}"
          + (f" ({ai.get('reason')})" if ai.get("reason") else ""))
    return {"session": session, "overview": overview, "day": day, "stories": stories, "trade_ideas": ideas,
            "impact_counts": impact_counts, "ai": ai, "live_record": live_record, "ledger_rows": len(ledger),
            "settings": {k: v for k, v in cfg.items() if k not in ("rationale", "news_keywords")},
            "authority": "DISPLAY_ONLY: a narrative for the human; never a gate, score or rank."}
