"""The board's own completed-session prices (ACK 9 Oct 2026). Read-only on the pipeline.

The pipeline's price store (historical_prices.sqlite) stays the primary source and is never
written. When it is behind the last completed US session, or a ticker has a gap (RSP and UUP
stopped on 20 Aug 2026), the board fills those completed sessions from Polygon's grouped daily
bars - one call per session for every US ticker - cached under macro_board/output/cache/grouped.
A fill never overwrites a value the store has. A session counts only after its close plus a settle
margin (late prints). An unavailable session is reported, never invented.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from typing import Callable, Mapping, Sequence

import pandas as pd

GROUPED_URL = "https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/{day}"
Transport = Callable[[str, Mapping], tuple]
_KEY = re.compile(r"((?:apiKey|api_key|token)=)[^&\s'\"]+", re.IGNORECASE)


def last_eligible_session(now: datetime, *, settle_minutes: float) -> date:
    """The latest XNYS session whose close (half days included) is at least ``settle_minutes`` ago."""
    from avshunter.shared.xnys_calendar import is_xnys_session, session_bounds
    from zoneinfo import ZoneInfo
    day = now.astimezone(ZoneInfo("America/New_York")).date()
    while True:
        if is_xnys_session(day):
            close = session_bounds(day)[1]
            if now >= close + timedelta(minutes=float(settle_minutes)):
                return day
        day -= timedelta(days=1)


def _sessions_between(after: date, through: date) -> list[date]:
    from avshunter.shared.xnys_calendar import is_xnys_session
    out, day = [], after + timedelta(days=1)
    while day <= through:
        if is_xnys_session(day):
            out.append(day)
        day += timedelta(days=1)
    return out


def plan_fill(closes: pd.DataFrame, tickers: Sequence[str], *, last_completed: date,
              max_gap_sessions: int) -> tuple[dict[date, list[str]], dict[str, dict]]:
    """({session: [tickers]}, {ticker: gap}) - completed sessions the store lacks, filled whole or
    not at all: a ticker whose trailing gap (last stored bar -> last completed session) is longer
    than ``max_gap_sessions`` is left as it is and reported, never part-filled (a hole would run
    through averages, the 252-session range and the evidence). Missing sessions inside the stored
    history are filled within the same window. A ticker never held in the store is not filled."""
    first = closes.index.min().date() if len(closes.index) else last_completed
    window = _sessions_between(first - timedelta(days=1), last_completed)[-int(max_gap_sessions):]
    plan: dict[date, list[str]] = {}
    too_long: dict[str, dict] = {}
    for t in tickers:
        if t not in closes.columns:
            continue
        held = closes[t].dropna()
        if held.empty:
            continue
        last = held.index.max().date()
        trailing = _sessions_between(last, last_completed)
        if len(trailing) > int(max_gap_sessions):
            too_long[t] = {"last_stored": last.isoformat(), "missing_sessions": len(trailing)}
            continue
        have = {d.date() for d in held.index}
        start = held.index.min().date()
        for d in window:
            if d > start and d not in have:
                plan.setdefault(d, []).append(t)
    return {d: sorted(v) for d, v in sorted(plan.items())}, too_long


def fetch_grouped_daily(day: date, *, cache_dir: Path, transport: Transport | None = None,
                        api_key: str | None = None) -> dict | None:
    """{ticker: {o,h,l,c,v}} for one completed session; cached once fetched, never on failure."""
    cache = Path(cache_dir) / f"grouped_{day.isoformat()}.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    if transport is None:
        key = (api_key or os.environ.get("POLYGON_API_KEY", "")).strip()
        if not key:
            return None
        import requests

        def transport(url, params):
            r = requests.get(url, params={**params, "apiKey": key}, timeout=60)
            return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {})
    try:
        status, payload = transport(GROUPED_URL.format(day=day.isoformat()), {"adjusted": "true"})
    except Exception:  # noqa: BLE001 - a failed session is reported by the caller, never invented
        return None
    results = (payload or {}).get("results") or []
    if status != 200 or not results:
        return None
    bars = {r["T"]: {k: r.get(k) for k in ("o", "h", "l", "c", "v")} for r in results if r.get("T")}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(bars, separators=(",", ":")), encoding="utf-8")
    return bars


def apply_fill(frames: Mapping[str, pd.DataFrame], grouped: Mapping[date, Mapping | None],
               plan: Mapping[date, Sequence[str]]) -> tuple[dict, dict]:
    """Fill planned (session, ticker) cells from the grouped bars where the store has no value."""
    fields = {"open": "o", "high": "h", "low": "l", "close": "c", "volume": "v"}
    out = {name: frame.copy() for name, frame in frames.items()}
    filled: dict[str, list[str]] = {}
    unavailable: dict[str, list[str]] = {}
    for day, tickers in sorted(plan.items()):
        stamp = pd.Timestamp(day)
        bars = grouped.get(day) or {}
        for t in tickers:
            bar = bars.get(t)
            if not bar or bar.get("c") is None:
                unavailable.setdefault(t, []).append(day.isoformat())
                continue
            wrote = False
            for name, key in fields.items():
                frame = out.get(name)
                if frame is None or bar.get(key) is None:
                    continue
                if stamp not in frame.index:
                    frame.loc[stamp] = float("nan")
                if t not in frame.columns:
                    frame[t] = float("nan")
                if pd.isna(frame.at[stamp, t]):
                    frame.at[stamp, t] = float(bar[key])
                    wrote = True
            if wrote:
                filled.setdefault(t, []).append(day.isoformat())
    for name in out:
        out[name] = out[name].sort_index()
    return out, {"filled": {t: sorted(v) for t, v in sorted(filled.items())},
                 "unavailable": {t: sorted(v) for t, v in sorted(unavailable.items())}}


def merge_breadth(panel: pd.DataFrame, grouped: Mapping[date, Mapping | None]) -> pd.DataFrame:
    """Add grouped closes for the panel's own tickers; the store's values are kept."""
    extra = {pd.Timestamp(d): {t: (bars.get(t) or {}).get("c") for t in panel.columns if t in (bars or {})}
             for d, bars in grouped.items() if bars}
    if not extra:
        return panel
    add = pd.DataFrame.from_dict(extra, orient="index").reindex(columns=panel.columns).astype(float)
    return panel.combine_first(add).sort_index()


def redact(text: str) -> str:
    return _KEY.sub(r"\1REDACTED", str(text))
