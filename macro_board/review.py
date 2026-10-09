"""Daily review, section 1: the day's information and the market's reaction (ACK 9 Oct 2026). Display only.

Central question: did the market accept the new information, reject it, or absorb it without
meaningful displacement? Daily bars v1 (ACK), per instrument:
  gap      open vs previous close           the immediate response
  path     open -> close vs the gap          extended / faded / no opening reaction
  close    close vs previous close           the closing position
measured in the instrument's own daily move (20-session realised volatility of the sessions BEFORE
the day, so the day cannot inflate its own yardstick). With threshold k x daily move:
  ABSORBED  the close moved less than the threshold
  REJECTED  a gap beyond the threshold, then a close beyond it on the other side
  ACCEPTED  otherwise (the close moved, with the gap or without one)
Each label is scored on what followed past days with the same label (evidence.ticker_evidence:
next open -> close h sessions later, independent windows, held-out quarter).
What changed / was expected: the event payload (LLM-made, as published) and FRED prints; missing
consensus is stated. What disagreed: measured moves against SPY plus the payload's contradictions.
Thresholds in config["review"], PROVISIONAL.
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from . import evidence as ev

LABELS = ("ACCEPTED", "REJECTED", "ABSORBED", "UNKNOWN")


def _finite(*values) -> bool:
    return all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)


def classify(*, prev_close, open_, close, daily_move_pct, k: float) -> dict:
    """One instrument, one session."""
    out = {"label": "UNKNOWN", "direction": "NONE", "path": None, "gap_pct": None, "open_to_close_pct": None,
           "close_pct": None, "daily_move_pct": daily_move_pct, "threshold_pct": None}
    if not _finite(prev_close, open_, close) or prev_close <= 0 or open_ <= 0:
        return out
    gap = (open_ / prev_close - 1.0) * 100.0
    o2c = (close / open_ - 1.0) * 100.0
    move = (close / prev_close - 1.0) * 100.0
    out.update({"gap_pct": round(gap, 4), "open_to_close_pct": round(o2c, 4), "close_pct": round(move, 4)})
    if not _finite(daily_move_pct) or daily_move_pct <= 0:
        return out
    threshold = k * daily_move_pct
    out["threshold_pct"] = round(threshold, 4)
    gapped = abs(gap) >= threshold
    out["path"] = ("NO_OPENING_REACTION" if not gapped else
                   "EXTENDED" if np.sign(o2c) == np.sign(gap) else "FADED")
    if abs(move) < threshold:
        out.update({"label": "ABSORBED", "direction": ("UP" if gap > 0 else "DOWN") if gapped else "NONE"})
    elif gapped and np.sign(move) != np.sign(gap):
        out.update({"label": "REJECTED", "direction": "UP" if gap > 0 else "DOWN"})     # the gap that was rejected
    else:
        out.update({"label": "ACCEPTED", "direction": "UP" if move > 0 else "DOWN"})
    return out


def _key(label: str, direction: str) -> str:
    if label == "ACCEPTED":
        return f"ACCEPTED_{direction}"
    if label == "REJECTED":
        return f"REJECTED_GAP_{direction}"
    return label


def label_history(opens: pd.Series, closes: pd.Series, *, k: float, vol_sessions: int) -> pd.DataFrame:
    """The label for every session, each with the daily move of the sessions before it."""
    c, o = closes.astype(float), opens.reindex(closes.index).astype(float)
    daily = np.log(c).diff().rolling(vol_sessions).std(ddof=1).shift(1) * 100.0
    prev = c.shift(1)
    rows = [classify(prev_close=p, open_=op, close=cl, daily_move_pct=d, k=k)
            for p, op, cl, d in zip(prev.to_numpy(), o.to_numpy(), c.to_numpy(), daily.to_numpy())]
    frame = pd.DataFrame(rows, index=c.index)
    frame["daily_move_pct"] = daily
    frame["key"] = [_key(l, d) for l, d in zip(frame["label"], frame["direction"])]
    return frame


def label_evidence(opens: pd.DataFrame, closes: pd.DataFrame, ticker: str, *, k: float, vol_sessions: int,
                   horizons: Sequence[int], settings: Mapping) -> dict:
    """Today's label for ``ticker`` and what followed past sessions with the same label."""
    c = closes[ticker].dropna()
    o = opens[ticker].reindex(c.index)
    hist = label_history(o, c, k=k, vol_sessions=vol_sessions)
    today = hist.iloc[-1].to_dict()
    today["session"] = str(c.index[-1].date())
    mask = hist["key"] == today["key"]
    evidence = {}
    for h in horizons:
        fwd = ev.forward_returns(o.to_frame(ticker), c.to_frame(ticker), int(h))[ticker]
        evidence[str(h)] = ev.ticker_evidence(fwd, mask, int(h), settings)
    longest = ev.forward_returns(o.to_frame(ticker), c.to_frame(ticker), int(max(horizons)))[ticker]
    counts = hist["key"].value_counts().to_dict()
    pending = hist.loc[longest.isna(), "key"].value_counts().to_dict()
    clean = {k2: (None if isinstance(v, float) and not math.isfinite(v) else v) for k2, v in today.items()}
    return {"today": clean, "evidence": evidence, "label_counts": {str(k2): int(v) for k2, v in counts.items()},
            "label_counts_without_outcome": {str(k2): int(v) for k2, v in pending.items()}}


def _compact(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return "; ".join(f"{k}: {v}" for k, v in value.items() if v is not None)
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value)
    return str(value)


def _number(value) -> str:
    if not _finite(value):
        return str(value)
    return f"{value:,.0f}" if abs(value) >= 1000 else f"{value:,.2f}"


def information(event_payload: Mapping | None, overnight: Mapping | None, *, session: str) -> dict:
    """What changed and what was expected: event payload records (as published) and FRED prints."""
    items = []
    for e in (event_payload or {}).get("events") or []:
        forecast = e.get("forecast")
        items.append({"name": e.get("event_name"), "institution": e.get("country_or_institution"),
                      "status": e.get("status"), "what_changed": _compact(e.get("actual")) or "MISSING",
                      "expected": _compact(forecast) or "MISSING", "previous": _compact(e.get("previous")),
                      "revised_previous": _compact(e.get("revised_previous")),
                      "surprise": e.get("surprise_direction"), "time_utc": e.get("release_time_utc"),
                      "source": "event payload (LLM)", "source_url": e.get("source_url")})
    for r in (overnight or {}).get("releases_today") or []:
        if r.get("state") != "RELEASED":
            continue
        items.append({"name": r.get("name"), "institution": "FRED", "status": "RELEASED",
                      "what_changed": f"{_number(r.get('value'))} (observation {r.get('observation_date')})",
                      "expected": "MISSING (no free consensus source)",
                      "previous": _number(r.get("prior")) if r.get("prior") is not None else None,
                      "revised_previous": None, "surprise": None, "time_utc": None, "time_et": r.get("time_et"),
                      "source": "FRED", "source_url": None})
    payload_session = (event_payload or {}).get("generated_from_report_date")
    return {"items": items, "payload_session": payload_session,
            "payload_matches_session": payload_session == session if payload_session else None}


def disagreements(rows: Mapping[str, Mapping], *, confirming_weight_1d, contradictions: Sequence[str],
                  cfg: Mapping, reference: str = "SPY") -> dict:
    """Measured contrary moves: instruments that moved beyond their own threshold against the
    reference (or moved while the reference absorbed), the reference's constituents, and the
    payload's published contradictions."""
    ref = rows.get(reference) or {}
    ref_moved = ref.get("label") in ("ACCEPTED", "REJECTED") and _finite(ref.get("close_pct"))
    measured = []
    for t, r in rows.items():
        if t == reference or not _finite(r.get("close_pct"), r.get("threshold_pct")):
            continue
        if abs(r["close_pct"]) < r["threshold_pct"]:
            continue
        if ref_moved and np.sign(r["close_pct"]) == np.sign(ref["close_pct"]):
            continue
        measured.append({"ticker": t, "close_pct": r["close_pct"], "label": r.get("label"),
                         "versus": f"{reference} {ref.get('close_pct'):+.2f}%" if ref_moved else f"{reference} absorbed"})
    measured.sort(key=lambda d: -abs(d["close_pct"]))
    constituents = ("UNKNOWN" if confirming_weight_1d is None else
                    "CONFIRMED" if confirming_weight_1d >= float(cfg["confirmation_min_pct"]) else "NOT_CONFIRMED")
    return {"measured": measured, "constituents": constituents, "confirming_weight_1d_pct": confirming_weight_1d,
            "published": list(contradictions or [])}


def headline(rows: Mapping[str, Mapping], tickers: Sequence[str]) -> str:
    parts = []
    for t in tickers:
        r = rows.get(t) or {}
        label, direction = r.get("label", "UNKNOWN"), r.get("direction", "NONE")
        if label == "ACCEPTED":
            parts.append(f"{t} accepted ({direction.lower()})")
        elif label == "REJECTED":
            parts.append(f"{t} rejected (gap {direction.lower()})")
        else:
            parts.append(f"{t} {label.lower()}")
    return " · ".join(parts)


def build(*, opens: pd.DataFrame, closes: pd.DataFrame, instruments: Sequence[str], sectors: Sequence[str],
          focus: Sequence[str], horizons: Sequence[int], evidence_settings: Mapping, holdings: Mapping,
          event_payload: Mapping | None, overnight: Mapping | None, cfg: Mapping) -> dict:
    k, vol = float(cfg["threshold_daily_moves"]), int(cfg["vol_sessions"])
    session = str(closes.index[-1].date())
    rows = {}
    for t in list(dict.fromkeys(list(instruments) + list(sectors))):
        if t not in closes.columns or closes[t].dropna().empty:
            continue
        c = closes[t].dropna()
        if c.index[-1] != closes.index[-1]:
            rows[t] = {"label": "UNKNOWN", "direction": "NONE", "note": f"no bar for {session}"}
            continue
        hist = label_history(opens[t].reindex(c.index), c, k=k, vol_sessions=vol)
        today = hist.iloc[-1].to_dict()
        rows[t] = {key: (None if isinstance(v, float) and not math.isfinite(v) else v) for key, v in today.items()}
    scored = {t: label_evidence(opens, closes, t, k=k, vol_sessions=vol, horizons=horizons, settings=evidence_settings)
              for t in focus if t in closes.columns}
    spy_window = ((holdings.get("SPY") or {}).get("windows") or {}).get("1") or {}
    return {"session": session, "headline": headline(rows, list(focus)),
            "instruments": {t: rows[t] for t in instruments if t in rows},
            "sectors": {t: rows[t] for t in sectors if t in rows},
            "scored": scored,
            "information": information(event_payload, overnight, session=session),
            "disagreements": disagreements(rows, confirming_weight_1d=spy_window.get("confirming_weight_pct"),
                                           contradictions=(event_payload or {}).get("cross_asset_contradictions") or [],
                                           cfg=cfg),
            "unresolved": {"counter_case": ((event_payload or {}).get("counter_case") or {}).get("summary"),
                           "verdict": ((event_payload or {}).get("final_verdict") or {}).get("verdict")},
            "settings": dict(cfg)}
