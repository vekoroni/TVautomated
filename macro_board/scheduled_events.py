"""The scheduled part of the event payload, measured locally from FRED (ACK 10 Oct 2026).

The ChatGPT event payload mixes scheduled US releases with news. The scheduled part is measurable:

- the calendar: FRED release dates, past and scheduled;
- the print as known on the release day (FRED vintage, realtime = that day), the previous value and its
  revision since it was first published (vintage of the day before);
- a surprise measured against the series' own past changes - there is no free consensus source, so the
  sheet says so and never implies one;
- how markets reacted that session (the board's own reaction labels);
- how much more SPY and TLT have moved on that release's past days than on other days.

ChatGPT keeps only the unscheduled news. Display only. The release list (ids, headline series, ET
times) mirrors the overnight capture's (Enhancements/colab/avshunter_market_intelligence_v5_4_3.py,
OVERNIGHT_RELEASES) and lives in config["scheduled_events"]. FRED reads are cached under the board's
output and never print the key.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import json
import math
import os
from pathlib import Path
import re
from typing import Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

FRED = "https://api.stlouisfed.org/fred"
NY = ZoneInfo("America/New_York")
Transport = Callable[[str, Mapping], tuple]
_KEY = re.compile(r"((?:api_key)=)[^&\s'\"]+", re.IGNORECASE)


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


# -- FRED reads (cached; the key never leaves the transport) ---------------------------------------------------

def fred_key() -> str:
    """FRED_API_KEY from the environment, else the repo .env (as the runner's producers do)."""
    key = os.environ.get("FRED_API_KEY", "").strip()
    if key:
        return key
    env = Path(__file__).resolve().parents[1] / ".env"
    try:
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("FRED_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def _cached(cache_dir: Path, name: str, transport: Transport | None, url: str, params: Mapping):
    path = Path(cache_dir) / f"{name}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    if transport is None:
        return None
    try:
        status, payload = transport(url, params)
    except Exception:  # noqa: BLE001 - a failed read is reported, never invented
        return None
    if status != 200 or not isinstance(payload, dict):
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return payload


def _observations(payload) -> list:
    out = []
    for o in (payload or {}).get("observations") or []:
        v = _num(o.get("value"))
        if v is not None and o.get("date"):
            out.append({"date": o["date"], "value": v})
    return out


def fetch(releases: Sequence[Mapping], *, as_of: str, cache_dir: Path, transport: Transport | None = None,
          api_key: str | None = None, history_start: str = "2015-01-01") -> dict:
    """Release dates, headline series and, for releases dated on ``as_of``, the vintages known that day and
    the day before. Cached per session; offline builds use the cache."""
    key = (api_key if api_key is not None else fred_key()).strip()
    if transport is None and key:
        import requests

        def transport(url, params):
            r = requests.get(url, params={**params, "api_key": key, "file_type": "json"}, timeout=30)
            return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {})
    cache_dir = Path(cache_dir)
    out = {"status": "OK", "release_dates": {}, "series": {}, "vintages": {}, "errors": []}
    any_read = False
    for r in releases:
        rid, sid = int(r["release_id"]), r["series_id"]
        dates = _cached(cache_dir, f"release_dates_{rid}_{as_of}", transport, f"{FRED}/release/dates",
                        {"release_id": rid, "include_release_dates_with_no_data": "true", "sort_order": "asc", "limit": 10000})
        series = _cached(cache_dir, f"series_{sid}_{as_of}", transport, f"{FRED}/series/observations",
                         {"series_id": sid, "observation_start": history_start})
        if dates is None or series is None:
            out["errors"].append(f"{r['name']}: FRED read unavailable")
            continue
        any_read = True
        out["release_dates"][rid] = sorted({d["date"] for d in dates.get("release_dates") or [] if d.get("date")})
        out["series"][sid] = _observations(series)
        if as_of in out["release_dates"][rid]:
            before = (date.fromisoformat(as_of) - timedelta(days=1)).isoformat()
            start = (date.fromisoformat(as_of) - timedelta(days=500)).isoformat()
            on_day = _cached(cache_dir, f"vintage_{sid}_{as_of}", transport, f"{FRED}/series/observations",
                             {"series_id": sid, "observation_start": start, "realtime_start": as_of, "realtime_end": as_of})
            prior = _cached(cache_dir, f"vintage_{sid}_{before}", transport, f"{FRED}/series/observations",
                            {"series_id": sid, "observation_start": start, "realtime_start": before, "realtime_end": before})
            out["vintages"][rid] = {"on_day": _observations(on_day), "day_before": _observations(prior)}
    if not any_read:
        out["status"] = "NO_KEY" if not key and transport is None else "UNAVAILABLE"
    return out


# -- measurements ---------------------------------------------------------------------------------------------

def _changes(series: pd.Series, transform: str) -> pd.Series:
    if transform == "pct_change":
        return series.pct_change() * 100.0
    if transform == "diff":
        return series.diff()
    return series.astype(float)


def measured_surprise(series: pd.Series, transform: str, *, lookback: int, band_z: float) -> dict:
    """The latest change against the series' own past ``lookback`` changes. Not a consensus surprise."""
    basis = f"change vs its own past {lookback} changes; not a consensus surprise"
    ch = _changes(series.dropna().astype(float), transform)
    latest = _num(ch.iloc[-1]) if len(ch) else None
    past = ch.iloc[-1 - lookback:-1].dropna() if len(ch) > 1 else pd.Series(dtype=float)
    out = {"value": _num(series.iloc[-1]) if len(series) else None, "prior": _num(series.iloc[-2]) if len(series) > 1 else None,
           "change": None if latest is None else round(latest, 6), "z": None, "label": "INSUFFICIENT_HISTORY", "basis": basis}
    if latest is None or len(past) < max(6, lookback // 2):
        return out
    mean, std = float(past.mean()), float(past.std(ddof=1))
    if std < 1e-12:
        z = 0.0 if abs(latest - mean) < 1e-9 else math.copysign(math.inf, latest - mean)
    else:
        z = (latest - mean) / std
    out["z"] = round(z, 3) if math.isfinite(z) else None
    out["label"] = "ABOVE_OWN_TREND" if z >= band_z else "BELOW_OWN_TREND" if z <= -band_z else "IN_LINE_WITH_OWN_TREND"
    return out


def event_day_moves(closes: pd.DataFrame, release_days: Sequence[date], tickers: Sequence[str], *, as_of: date,
                    min_days: int) -> dict:
    """Mean |close-to-close move| on the release's past sessions vs the other sessions, per instrument."""
    out = {}
    days = {pd.Timestamp(d) for d in release_days}
    for t in tickers:
        if t not in closes.columns:
            out[t] = {"n": 0, "mean_abs_event_pct": None, "mean_abs_other_pct": None, "ratio": None}
            continue
        r = (closes[t].dropna().pct_change() * 100.0).dropna()
        r = r[r.index <= pd.Timestamp(as_of)]
        on = r.index.isin(list(days))
        ev, other = r[on].abs(), r[~on].abs()
        n = int(len(ev))
        e_mean = float(ev.mean()) if n else None
        o_mean = float(other.mean()) if len(other) else None
        ratio = (e_mean / o_mean) if (n >= int(min_days) and e_mean is not None and o_mean) else None
        out[t] = {"n": n, "mean_abs_event_pct": None if e_mean is None else round(e_mean, 4),
                  "mean_abs_other_pct": None if o_mean is None else round(o_mean, 4),
                  "ratio": None if ratio is None else round(ratio, 3)}
    return out


def build(data: Mapping, *, as_of_session: str, upcoming_sessions: Sequence[date], closes: pd.DataFrame,
          reactions: Mapping, cfg: Mapping) -> dict:
    as_of = date.fromisoformat(as_of_session)
    released, upcoming = [], []
    for r in cfg["releases"]:
        rid, sid = int(r["release_id"]), r["series_id"]
        dates = [date.fromisoformat(d) for d in (data.get("release_dates") or {}).get(rid, [])]
        obs = (data.get("series") or {}).get(sid) or []
        history = [d for d in dates if d < as_of]
        event_day = event_day_moves(closes, history, cfg["event_day_tickers"], as_of=as_of, min_days=int(cfg["min_event_days"]))
        if as_of in dates:
            vint = (data.get("vintages") or {}).get(rid) or {}
            on_day, before = vint.get("on_day") or [], vint.get("day_before") or []
            actual = on_day[-1] if on_day else None
            previous = on_day[-2] if len(on_day) > 1 else None
            first_known = next((o for o in before if previous and o["date"] == previous["date"]), None)
            series = pd.Series({pd.Timestamp(o["date"]): o["value"] for o in obs})
            if actual:
                series = series[series.index < pd.Timestamp(actual["date"])]
                if previous:
                    series[pd.Timestamp(previous["date"])] = previous["value"]
                series[pd.Timestamp(actual["date"])] = actual["value"]
                series = series.sort_index()
            surprise = measured_surprise(series, r["transform"], lookback=int(cfg["lookback_changes"]),
                                         band_z=float(cfg["surprise_band_z"])) if actual else None
            released.append({
                "release_id": rid, "name": r["name"], "series_id": sid, "date": as_of_session, "time_et": r["time_et"],
                "observation_date": actual["date"] if actual else None, "actual": actual["value"] if actual else None,
                "previous": previous["value"] if previous else None,
                "previous_as_first_known": first_known["value"] if first_known else None,
                "revision_of_previous": (round(previous["value"] - first_known["value"], 6)
                                         if previous and first_known else None),
                "unit": r.get("unit"), "transform": r["transform"],
                "change": surprise["change"] if surprise else None, "surprise": surprise,
                "forecast": None, "forecast_source": "NOT_AVAILABLE_LOCALLY",
                "reaction": {t: (reactions.get(t) or {"key": "UNKNOWN", "close_pct": None}) for t in cfg["reaction_tickers"]},
                "event_day": event_day, "why_it_matters": r.get("why_it_matters"),
                "status": "RELEASED" if actual else "RELEASED_NOT_READ"})
        for d in dates:
            if d <= as_of:
                continue
            ahead = next((i + 1 for i, s in enumerate(upcoming_sessions) if s >= d), None)
            if ahead is None or ahead > int(cfg["sessions_ahead"]):
                continue
            upcoming.append({"release_id": rid, "name": r["name"], "series_id": sid, "date": d.isoformat(),
                             "time_et": r["time_et"], "sessions_ahead": ahead,
                             "last_value": obs[-1]["value"] if obs else None, "last_observation": obs[-1]["date"] if obs else None,
                             "event_day": event_day, "why_it_matters": r.get("why_it_matters")})
    upcoming.sort(key=lambda e: (e["date"], e["time_et"] or "", e["name"]))
    return {"session": as_of_session, "status": data.get("status"), "released": released, "upcoming": upcoming,
            "errors": list(data.get("errors") or []),
            "source": "FRED release dates and vintage observations (measured; no consensus)"}


def _stamp(day: str, hhmm: str | None) -> tuple[str | None, str | None, str | None]:
    if not hhmm:
        return None, None, None
    local = datetime.combine(date.fromisoformat(day), time.fromisoformat(hhmm), tzinfo=NY)
    return (local.astimezone(ZoneInfo("UTC")).isoformat(), local.astimezone(ZoneInfo("Europe/London")).isoformat(),
            local.isoformat())


def as_event_payload(block: Mapping) -> dict:
    """The released events in the ChatGPT event payload's schema (route SCHEDULED_RELEASES_MEASURED)."""
    events = []
    for e in block.get("released") or []:
        utc, london, eastern = _stamp(e["date"], e.get("time_et"))
        s = e.get("surprise") or {}
        events.append({
            "event_id": f"{e['series_id']}_{e['date']}", "event_name": e["name"],
            "country_or_institution": f"United States / FRED release {e['release_id']}",
            "release_time_utc": utc, "release_time_london": london, "release_time_us_eastern": eastern,
            "status": e["status"], "actual": {e["series_id"]: e.get("actual"), "observation_date": e.get("observation_date"),
                                              "change": e.get("change"), "unit": e.get("unit")},
            "forecast": None, "forecast_source": "NOT_AVAILABLE_LOCALLY",
            "previous": {e["series_id"]: e.get("previous"), "as_first_published": e.get("previous_as_first_known"),
                         "revision": e.get("revision_of_previous")},
            "surprise_direction": s.get("label"), "surprise_score": s.get("z"), "surprise_basis": s.get("basis"),
            "evidence_quality": 100, "why_it_matters": e.get("why_it_matters"),
            "market_reaction": e.get("reaction"), "event_day_history": e.get("event_day")})
    return {"schema_version": "avshunter_us_economic_event_impact_v1_0",
            "generated_from_report_date": block.get("session"),
            "run_context": {"report_type": "AVSHUNTER scheduled US releases (measured)",
                            "coverage": "Scheduled FRED releases on the session; unscheduled news stays with the LLM payload",
                            "route": "SCHEDULED_RELEASES_MEASURED", "manual_review_required": True,
                            "automatic_execution_enabled": False},
            "events": events,
            "upcoming": block.get("upcoming") or [],
            "source": block.get("source")}


def redact(text: str) -> str:
    return _KEY.sub(r"\1REDACTED", str(text))
