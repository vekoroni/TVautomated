"""Trigger events against a thesis's own recorded levels (Phase 3, design §7.2, principle P8 "events, not states").

Pure function over a SequenceResult (completed bars, any timeframe including 5m/15m/60m). It reports WHAT HAPPENED
AT WHICH BAR relative to levels it is given; it never chooses a side, never gates, and never reads another
module's state fields:
  BREAK_ATTEMPT_UP/DOWN   first close beyond the break level
  BREAK_ACCEPTED_UP/DOWN  the engine's acceptance rule met (behaviour.acceptance - the single acceptance owner)
  FAILED_BREAK_UP/DOWN    a close back inside before acceptance, or acceptance rejected - a trap for the other side
  RETEST_HELD_* / RETEST_FAILED_*  first return to an accepted level (within the acceptance margin)
  INVALIDATED             acceptance beyond the invalidation level
  OUTCOME_REACHED         a close at or beyond the target
  VWAP_RECLAIM / VWAP_LOSS  close crosses the VWAP anchored at the thesis origin, computed from these bars
Too few or invalid bars -> status NOT_MEASURED with no events (never "no event").
levels: {"up": float, "down": float, "invalidation": (float, "ABOVE"|"BELOW"), "target": (float, "ABOVE"|"BELOW")}
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional

import numpy as np

from .behaviour import acceptance


def _positive(value: Any) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 0 else None


def detect_events(seq, *, levels: Mapping[str, Any], from_index: int, policy: Mapping) -> Dict[str, Any]:
    if seq is None or getattr(seq, "frame", None) is None or getattr(seq, "status", "") != "EVALUATED":
        reason = getattr(seq, "status", "NO_BARS") if seq is not None else "NO_BARS"
        return {"status": f"NOT_MEASURED:{reason}", "events": [], "last_event": None}
    frame = seq.frame
    n = len(frame)
    start = min(max(1, int(from_index)), n - 1)
    lc = frame["lc"].to_numpy(float)
    atr = frame["atr"].to_numpy(float)
    close = frame["close"].to_numpy(float)
    high, low = frame["high"].to_numpy(float), frame["low"].to_numpy(float)
    margin = float(policy["acceptance"]["min_beyond_atr"])
    events: List[Dict[str, Any]] = []

    def add(name: str, i: int, level: Optional[float], **extra) -> None:
        events.append({"event": name, "index": int(i), "date": seq.label(int(i)), "level": level,
                       "close": float(close[i]), "interval": seq.timeframe, **extra})

    for key, side, tag in (("up", "ABOVE", "UP"), ("down", "BELOW", "DOWN")):
        level = _positive(levels.get(key))
        if level is None:
            continue
        sign, ln_level = (1.0 if side == "ABOVE" else -1.0), math.log(level)
        crossed = [i for i in range(start, n) if sign * (lc[i] - ln_level) > 0]
        if not crossed:
            continue
        add(f"BREAK_ATTEMPT_{tag}", crossed[0], level)
        acc = acceptance(seq, level=level, side=side, from_index=start, policy=policy)
        if acc["state"] in {"ACCEPTED", "ACCEPTED_PROVISIONAL"}:
            a = acc["index"]
            add(f"BREAK_ACCEPTED_{tag}", a, level, provisional=acc["state"] == "ACCEPTED_PROVISIONAL")
            for j in range(a + 1, n):
                extreme = math.log(low[j]) if side == "ABOVE" else math.log(high[j])
                a_j = atr[j] if np.isfinite(atr[j]) else 0.0
                if sign * (extreme - ln_level) <= margin * a_j:          # came back to the broken level
                    add(f"RETEST_HELD_{tag}" if sign * (lc[j] - ln_level) > 0 else f"RETEST_FAILED_{tag}", j, level)
                    break
        else:
            after = acc["index"] if acc["state"] == "REJECTED" else crossed[0]
            back = next((j for j in range(after + 1, n) if sign * (lc[j] - ln_level) < 0), None)
            if back is not None:
                add(f"FAILED_BREAK_{tag}", back, level)

    inval = levels.get("invalidation")
    if inval and _positive(inval[0]) is not None:
        acc = acceptance(seq, level=float(inval[0]), side=inval[1], from_index=start, policy=policy)
        if acc["state"] in {"ACCEPTED", "ACCEPTED_PROVISIONAL"}:
            add("INVALIDATED", acc["index"], float(inval[0]))

    target = levels.get("target")
    if target and _positive(target[0]) is not None:
        sign, ln_t = (1.0 if target[1] == "ABOVE" else -1.0), math.log(float(target[0]))
        hit = next((i for i in range(start, n) if sign * (lc[i] - ln_t) >= 0), None)
        if hit is not None:
            add("OUTCOME_REACHED", hit, float(target[0]))

    volume = frame["volume"].to_numpy(float)
    typical = (high + low + close) / 3.0
    w = volume[start:]
    if w.sum() > 0:
        vwap = np.cumsum(typical[start:] * w) / np.maximum(np.cumsum(w), 1e-12)
        diff = close[start:] - vwap
        for k in range(1, len(diff)):
            if diff[k - 1] < 0 < diff[k]:
                add("VWAP_RECLAIM", start + k, float(vwap[k]))
            elif diff[k - 1] > 0 > diff[k]:
                add("VWAP_LOSS", start + k, float(vwap[k]))

    events.sort(key=lambda e: e["index"])
    return {"status": "MEASURED", "events": events, "last_event": events[-1] if events else None}


# ------------------------------------------------------------------ Phase 3b: intraday build-up (Morning, advisory)
class _BarSequence:
    """Minimal sequence view of intraday bars for detect_events: log closes and a per-bar log-ATR taken from the
    DAILY ATR, so the engine's acceptance rule (closes >= margin x ATR beyond the level) asks for a decisive break."""

    status = "EVALUATED"

    def __init__(self, bars, timeframe: str, atr_daily: float):
        import pandas as pd
        frame = bars.copy()
        tcol = next((c for c in ("timestamp_utc", "date", "timestamp") if c in frame.columns), None)
        self._labels = (pd.to_datetime(frame[tcol], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ").tolist()
                        if tcol else [str(i) for i in range(len(frame))])
        frame = frame.reset_index(drop=True)
        frame["lc"] = np.log(frame["close"].astype(float))
        frame["atr"] = float(atr_daily) / frame["close"].astype(float)
        self.frame, self.timeframe = frame, timeframe

    def label(self, i: int) -> str:
        return self._labels[int(i)]


_ALIGNED = {"BULL": {"BREAK_ATTEMPT_UP", "BREAK_ACCEPTED_UP", "RETEST_HELD_UP", "VWAP_RECLAIM", "OUTCOME_REACHED"},
            "BEAR": {"BREAK_ATTEMPT_DOWN", "BREAK_ACCEPTED_DOWN", "RETEST_HELD_DOWN", "VWAP_LOSS", "OUTCOME_REACHED"}}
_OPPOSED = {"BULL": {"FAILED_BREAK_UP", "RETEST_FAILED_UP", "VWAP_LOSS", "INVALIDATED"},
            "BEAR": {"FAILED_BREAK_DOWN", "RETEST_FAILED_DOWN", "VWAP_RECLAIM", "INVALIDATED"}}


def intraday_buildup(bars, *, side: Optional[str], trigger: Any, invalidation: Any, target: Any, atr_daily: Any,
                     policy: Mapping, timeframe: str = "5m") -> Dict[str, Any]:
    """Build-up of the move today on the thesis's own levels (ACK 8 Oct 2026). Advisory display only.

    ALIGNED: the latest event moves the thesis's way; OPPOSED: it pushes against it; NONE: no event;
    NOT_MEASURED: no bars, no side or no daily ATR.
    """
    base = {"ib_interval": timeframe, "ib_authority": "ADVISORY_ONLY", "ib_events": "", "ib_last_event": None,
            "ib_last_event_time": None, "ib_last_event_level": None}
    atr = _positive(atr_daily)
    if bars is None or len(bars) == 0 or side not in {"BULL", "BEAR"} or atr is None:
        reason = "NO_BARS" if bars is None or len(bars) == 0 else "NO_SIDE" if side not in {"BULL", "BEAR"} else "NO_ATR"
        return {**base, "ib_state": "NOT_MEASURED", "ib_reason": reason}
    up = side == "BULL"
    levels = {("up" if up else "down"): trigger,
              "invalidation": (invalidation, "BELOW" if up else "ABOVE") if _positive(invalidation) else None,
              "target": (target, "ABOVE" if up else "BELOW") if _positive(target) else None}
    res = detect_events(_BarSequence(bars, timeframe, atr), levels=levels, from_index=1, policy=policy)
    events = res["events"]
    last = events[-1] if events else None
    if last is None:
        state = "NONE"
    elif last["event"] in _ALIGNED[side]:
        state = "ALIGNED"
    elif last["event"] in _OPPOSED[side]:
        state = "OPPOSED"
    else:
        state = "NONE"
    return {**base, "ib_state": state, "ib_reason": res["status"], "ib_events": ";".join(e["event"] for e in events),
            "ib_last_event": last["event"] if last else None, "ib_last_event_time": last["date"] if last else None,
            "ib_last_event_level": last["level"] if last else None}
