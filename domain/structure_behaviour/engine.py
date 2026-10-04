"""BEH-001 engine: one timeframe -> reading + candidates; a ticker -> all timeframes.

Never raises for a ticker: any timeframe that cannot be evaluated is published
as NOT_EVALUATED with its reason and the remaining timeframes still run
(ACK amendment, 1 Oct 2026).
"""
from __future__ import annotations

from typing import Dict, List, Mapping, Optional

import pandas as pd

from pathlib import Path

from .compression import compression_context, describe
from .duration import attach_duration, load_duration_evidence
from .control import assess_control
from .events import detect_events, detect_local_events
from .phase import assess_phase, movement_maturity
from .sequences import build_sequences
from .signals import build_candidates

TIMEFRAME_ORDER = ("1mo", "1w", "1d", "60m", "15m", "5m")


def _not_evaluated(ticker: str, timeframe: str, role: str, status: str) -> dict:
    return {"Ticker": ticker, "Timeframe": timeframe, "Timeframe_Role": role, "Status": status,
            "As_Of": None, "Wyckoff_Phase": None, "Controller": "NOT_EVALUATED", "candidates": [], "events": []}


def analyse_timeframe(ticker: str, bars: Optional[pd.DataFrame], timeframe: str, policy: Mapping) -> dict:
    role = policy["timeframes"].get(timeframe, {}).get("role", "UNSPECIFIED")
    if bars is None or len(bars) == 0:
        return _not_evaluated(ticker, timeframe, role, "NOT_EVALUATED_NO_DATA")
    try:
        seq = build_sequences(bars, timeframe, policy)
        if seq.status != "EVALUATED":
            return _not_evaluated(ticker, timeframe, role, seq.status)
        control = assess_control(seq, policy)
        events = detect_events(seq, control, policy)
        phase = assess_phase(seq, control, events, policy)
        compression = compression_context(seq, policy)
        maturity = movement_maturity(control, policy)
        candidates = build_candidates(ticker=ticker, timeframe=timeframe, role=role, seq=seq, control=control,
                                      phase=phase, events=events, compression=compression,
                                      maturity=maturity, policy=policy)
        local = {"Local_Phase": phase["local_phase"], "Local_Controller": None, "Local_Maturity": None}
        if control.degree == "MAJOR":
            # NESTED_STRUCTURE: the minor-swing structure inside the campaign.
            local_control = assess_control(seq, policy, degree="MINOR")
            local_events = detect_local_events(seq, local_control, policy)
            local_phase = assess_phase(seq, local_control, local_events, policy, scope="LOCAL")
            local_maturity = movement_maturity(local_control, policy)
            local = {"Local_Phase": local_phase["phase"], "Local_Controller": local_control.controller,
                     "Local_Maturity": local_maturity, "Local_Context": local_phase["context"]}
            candidates += build_candidates(ticker=ticker, timeframe=timeframe, role=role, seq=seq,
                                           control=local_control, phase=local_phase, events=local_events,
                                           compression=compression, maturity=local_maturity, policy=policy,
                                           scope="LOCAL", include_context=False)
            events = events + [{**e, "scope": "LOCAL"} for e in local_events]
    except Exception as exc:  # recorded, never propagated to the run
        return _not_evaluated(ticker, timeframe, role, f"NOT_EVALUATED_ERROR:{type(exc).__name__}")
    return {**local,
        "Ticker": ticker, "Timeframe": timeframe, "Timeframe_Role": role, "Status": "EVALUATED",
        "As_Of": seq.label(seq.last_index), "Close": float(seq.frame["close"].iloc[-1]),
        "Wyckoff_Phase": phase["phase"], "Phase_Confidence": phase["confidence"],
        "Phase_Transition": phase["transition"],
        "Structural_Context": phase["context"], "Controller": control.controller,
        "Control_Quality": control.quality, "Control_Degree": control.degree,
        "Control_Transfer_Condition": control.transfer_condition, "Transfer_Level": control.transfer_level,
        "Movement_Maturity": maturity, "Thrusts": control.thrust_count,
        "Crabel_Compression": describe(compression), "events": events, "candidates": candidates,
    }


def resample_intraday(bars_5m: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Regular-session bars aggregated from 5-minute bars, anchored at 09:30 ET."""
    ts = pd.to_datetime(bars_5m["timestamp_utc"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    frame = bars_5m.assign(timestamp=ts).sort_values("timestamp").reset_index(drop=True)
    if minutes == 5:
        return frame[["timestamp", "open", "high", "low", "close", "volume"]]
    session_open = frame["timestamp"].dt.normalize() + pd.Timedelta(hours=9, minutes=30)
    offset = ((frame["timestamp"] - session_open) // pd.Timedelta(minutes=minutes)).astype(int)
    frame["bucket"] = session_open + offset * pd.Timedelta(minutes=minutes)
    out = frame.groupby("bucket", sort=True).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                                                 close=("close", "last"), volume=("volume", "sum"))
    out = out.reset_index().rename(columns={"bucket": "timestamp"})
    return out[["timestamp", "open", "high", "low", "close", "volume"]]


def resample_daily(daily: pd.DataFrame, rule: str) -> Optional[pd.DataFrame]:
    """Weekly/monthly bars from completed daily bars; the last period may be
    in progress and is labelled by its last completed daily bar."""
    if daily is None or len(daily) == 0 or "date" not in daily.columns:
        return None
    frame = daily.assign(date=pd.to_datetime(daily["date"])).set_index("date").sort_index()
    out = frame.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last",
                                    "volume": "sum"}).dropna()
    last_day = frame.groupby(pd.Grouper(freq=rule)).apply(lambda g: g.index.max()).dropna()
    out.index = pd.DatetimeIndex(last_day.loc[out.index].values)
    return out.reset_index().rename(columns={"index": "date"})


_ROOT = Path(__file__).resolve().parents[2]
_EVIDENCE_CACHE: Dict[str, Optional[dict]] = {}


def _duration_evidence(policy: Mapping) -> Optional[dict]:
    """Duration evidence named by the policy, loaded once per path; None if unavailable."""
    try:
        path = Path(policy["duration"]["evidence_path"])
    except Exception:
        return None
    path = path if path.is_absolute() else _ROOT / path
    key = str(path)
    if key not in _EVIDENCE_CACHE:
        _EVIDENCE_CACHE[key] = load_duration_evidence(path)
    return _EVIDENCE_CACHE[key]


def analyse_ticker(ticker: str, daily: Optional[pd.DataFrame], intraday_5m: Optional[pd.DataFrame],
                   policy: Mapping, *, intraday_status: str = "") -> dict:
    """All timeframes; missing intraday never blocks the daily reading."""
    readings: Dict[str, dict] = {}
    for timeframe in ("1mo", "1w"):
        cfg = policy["timeframes"].get(timeframe)
        if cfg is None:
            continue
        try:
            readings[timeframe] = analyse_timeframe(ticker, resample_daily(daily, cfg["rule"]), timeframe, policy)
        except Exception as exc:
            readings[timeframe] = _not_evaluated(ticker, timeframe, cfg.get("role", ""),
                                                 f"NOT_EVALUATED_ERROR:{type(exc).__name__}")
    readings["1d"] = analyse_timeframe(ticker, daily, "1d", policy)
    for timeframe, minutes in (("60m", 60), ("15m", 15), ("5m", 5)):
        role = policy["timeframes"][timeframe]["role"]
        if intraday_5m is None or len(intraday_5m) == 0:
            readings[timeframe] = _not_evaluated(ticker, timeframe, role,
                                                 f"NOT_EVALUATED_{intraday_status or 'NO_INTRADAY_DATA'}")
            continue
        try:
            sessions = int(policy["timeframes"][timeframe]["sessions"])
            dates = sorted(pd.to_datetime(intraday_5m["timestamp_utc"], utc=True)
                           .dt.tz_convert("America/New_York").dt.date.unique())[-sessions:]
            subset = intraday_5m[pd.to_datetime(intraday_5m["timestamp_utc"], utc=True)
                                 .dt.tz_convert("America/New_York").dt.date.isin(dates)]
            readings[timeframe] = analyse_timeframe(ticker, resample_intraday(subset, minutes), timeframe, policy)
        except Exception as exc:
            readings[timeframe] = _not_evaluated(ticker, timeframe, role, f"NOT_EVALUATED_ERROR:{type(exc).__name__}")
    if intraday_status and intraday_status != "OK" and intraday_5m is not None and len(intraday_5m):
        # Usable but imperfect intraday data is flagged, never silently trusted.
        for tf in ("60m", "15m", "5m"):
            readings[tf]["Data_Status"] = intraday_status
            for c in readings[tf]["candidates"]:
                c["Warning"] = "; ".join(x for x in (c["Warning"], f"INTRADAY_DATA_{intraday_status}") if x)
    _cross_timeframe_warnings(readings)
    evidence = _duration_evidence(policy)
    for reading in readings.values():
        attach_duration(reading["candidates"], evidence)
        # Fresh or flagged (R12): the data state is a field, not only warning text.
        for c in reading["candidates"]:
            c["Data_Status"] = reading.get("Data_Status") or "OK"
    return {"ticker": ticker, "readings": readings, "intraday_status": intraday_status or "OK",
            "candidates": [c for tf in TIMEFRAME_ORDER if tf in readings for c in readings[tf]["candidates"]],
            "handoff": handoff_thesis(readings, policy)}


def _cross_timeframe_warnings(readings: Dict[str, dict]) -> None:
    daily = readings["1d"]
    intraday_ok = any(readings[tf]["Status"] == "EVALUATED" for tf in ("60m", "15m", "5m"))
    campaign_side = {"BUYERS": "BULL", "SELLERS": "BEAR"}.get(daily.get("Controller"))
    for tf, reading in readings.items():
        for c in reading["candidates"]:
            notes = [c["Warning"]] if c["Warning"] else []
            if tf == "1d" and not intraday_ok:
                notes.append("LOWER_TIMEFRAME_CONFIRMATION_UNAVAILABLE: daily performs setup and trigger roles")
            if tf != "1d" and campaign_side and c["Direction"] and c["Direction"] != campaign_side:
                notes.append(f"COUNTER_DAILY_CAMPAIGN: daily controller {daily['Controller']}")
            c["Warning"] = "; ".join(n for n in notes if n)


def _live(reading: Optional[dict]) -> List[dict]:
    if not reading or reading.get("Status") != "EVALUATED":
        return []
    return [c for c in reading["candidates"] if c["Direction"] in {"BULL", "BEAR"}
            and c["Signal_State"] in {"DETECTED", "ACTIVATED", "CONFIRMED"}]


def _primary(live: List[dict]) -> dict:
    priority = {"ACTIVATED": 0, "CONFIRMED": 0, "DETECTED": 1}
    return sorted(live, key=lambda c: (priority[c["Signal_State"]], c["Candidate_ID"]))[0]


def handoff_thesis(readings: Dict[str, dict], policy: Optional[Mapping] = None) -> dict:
    """Design §7: the daily reading sets the Thesis side. A two-sided daily reading takes
    the side of the highest timeframe above daily whose live candidates are one-sided
    (ACK 1 Oct 2026; evidence in config handoff.evidence); otherwise it stays UNASSIGNED."""
    daily = readings["1d"]
    if daily["Status"] != "EVALUATED":
        return {"thesis__side": "UNASSIGNED", "thesis__direction_status": "NOT_EVALUATED",
                "thesis__unassigned_reason": daily["Status"], "primary": None}
    live = _live(daily)
    sides = {c["Direction"] for c in live}
    if not live:
        return {"thesis__side": "UNASSIGNED", "thesis__direction_status": "NO_DIRECTIONAL_CANDIDATE",
                "thesis__unassigned_reason": "NO_DIRECTIONAL_CANDIDATE", "primary": None}
    if len(sides) == 1:
        primary = _primary(live)
        return {"thesis__side": primary["Direction"],
                "thesis__direction_status": f"{primary['Signal_State']}:{primary['Signal_Type']}",
                "thesis__unassigned_reason": "", "primary": primary}
    if policy is None:
        from .policy import load_policy
        policy = load_policy()
    rule = (policy.get("handoff") or {})
    if rule.get("conflict_resolution") == "HIGHER_TIMEFRAME_ONE_SIDED":
        for tf in rule.get("higher_timeframes", []):
            higher = _live(readings.get(tf))
            if not higher:
                continue
            higher_sides = {c["Direction"] for c in higher}
            if len(higher_sides) == 1:
                side = higher_sides.pop()
                primary = _primary([c for c in live if c["Direction"] == side])
                return {"thesis__side": side,
                        "thesis__direction_status": f"RESOLVED_BY_TIMEFRAME:{tf}:{primary['Signal_State']}:"
                                                    f"{primary['Signal_Type']}",
                        "thesis__unassigned_reason": "", "primary": primary}
            break  # the highest timeframe with live candidates is itself two-sided
    types = {c["Signal_Type"] for c in live}
    range_edges = "Spring Candidate" in types and bool(types & {"Upthrust Candidate", "UTAD Test"})
    reason = "RANGE_EDGES_TWO_SIDED" if range_edges else "CONFLICTING_DAILY_CANDIDATES"
    return {"thesis__side": "UNASSIGNED", "thesis__direction_status": "CONFLICT_REVIEW",
            "thesis__unassigned_reason": reason, "primary": None}
