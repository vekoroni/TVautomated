"""
earnings_calendar_enricher.py
AVSHUNTER — Earnings catalyst calendar enrichment.
Adds earnings_days_to_event, earnings_timing, earnings_catalyst_flag
to candidates using the earningsAnnouncement field from Polygon snapshots.

DISPLAY FIELDS ONLY — never gates any phase verdict.
Can be called standalone (via fetch_earnings_calendar) or from morning_gate.py
by passing the already-fetched Polygon snapshot data via enrich_from_announcement_str.

3 Oct 2026 (ACK; design AVS_ANTICIPATED_MOVE_DESIGN_20261003 §9 step 1): the Polygon v2 snapshot carries no
earningsAnnouncement field (verified), so the Polygon path never produced a date. The governed source is
MarketData (canonical_data.marketdata_earnings); `earnings_disclosure` states the report against the trade's
hold and contract expiry. Catalysts are bonuses: this is position-risk disclosure, never a gate or a score.
The Polygon functions below are kept for old callers (repair, don't delete).
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

log = logging.getLogger("earnings_calendar_enricher")

POLYGON_API_KEY      = os.getenv("POLYGON_API_KEY", "").strip()
EARNINGS_WINDOW_DAYS = 5  # flag tickers within this many calendar days of earnings
EARNINGS_LOOKBACK_DAYS = 1  # also flag tickers that reported yesterday (post-earnings vol)


EARNINGS_DISCLOSURE_FIELDS = (
    "earnings_state", "earnings_date", "earnings_report_time", "earnings_fiscal_quarter",
    "earnings_sessions_to_event", "earnings_inside_hold", "earnings_inside_expiry",
    "earnings_unknown_reason", "earnings_source", "earnings_disclosure", "earnings_authority",
)


def _as_date(value: Any) -> Optional[date]:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def _sessions_between(start: date, end: date) -> int:
    """XNYS sessions after ``start`` up to and including ``end`` (0 when ``end`` <= ``start``)."""
    from avshunter.shared.xnys_calendar import is_xnys_session
    count, day = 0, start
    while day < end:
        day += timedelta(days=1)
        count += is_xnys_session(day)
    return count


def earnings_disclosure(
    earnings: Mapping[str, Any],
    *,
    as_of: Any,
    hold_sessions: Any,
    expiry: Any,
) -> Dict[str, Any]:
    """The next earnings report stated against the trade (disclosure only, never a gate or score).

    The price-impact session is the report day for BEFORE_OPEN / DURING_MARKET and the next session for
    AFTER_CLOSE (or an unknown time, conservatively the later one). ``earnings_inside_hold`` is None when the
    hold is UNESTIMATED; ``earnings_inside_expiry`` is None without an expiry. UNKNOWN is never "no catalyst".
    """
    as_of_day = _as_date(as_of) or datetime.now(timezone.utc).date()
    state = str((earnings or {}).get("state") or "UNKNOWN").upper()
    out: Dict[str, Any] = {field: None for field in EARNINGS_DISCLOSURE_FIELDS}
    out.update(earnings_state=state, earnings_source=(earnings or {}).get("source") or "MARKETDATA_EARNINGS",
               earnings_authority="DISCLOSURE_ONLY")
    if state == "NONE_IN_LOOKAHEAD":
        days = (earnings or {}).get("lookahead_days") or 120
        out["earnings_disclosure"] = f"No earnings report scheduled in the next {days} days."
        out["earnings_inside_hold"] = False
        out["earnings_inside_expiry"] = False
        return out
    report = _as_date((earnings or {}).get("date"))
    if state != "SCHEDULED" or report is None:
        out["earnings_state"] = "UNKNOWN"
        out["earnings_unknown_reason"] = str((earnings or {}).get("reason") or "DATE_NOT_PROVIDED")
        out["earnings_disclosure"] = (f"Earnings date unknown ({out['earnings_unknown_reason']}); "
                                      "check before entry.")
        return out
    report_time = str((earnings or {}).get("report_time") or "UNKNOWN").upper()
    sessions = _sessions_between(as_of_day, report) + (0 if report_time in {"BEFORE_OPEN", "DURING_MARKET"} else 1)
    hold = None
    try:
        hold = int(float(hold_sessions)) if hold_sessions not in (None, "") else None
    except (TypeError, ValueError):
        hold = None
    expiry_day = _as_date(expiry)
    inside_hold = None if hold is None else sessions <= hold
    inside_expiry = None if expiry_day is None else sessions <= _sessions_between(as_of_day, expiry_day)
    out.update(earnings_date=report.isoformat(), earnings_report_time=report_time,
               earnings_fiscal_quarter=(earnings or {}).get("fiscal_quarter") or "",
               earnings_sessions_to_event=sessions, earnings_inside_hold=inside_hold,
               earnings_inside_expiry=inside_expiry)
    when = report_time.replace("_", " ").lower()
    hold_text = ("hold not estimated" if inside_hold is None else
                 f"inside the {hold}-session hold" if inside_hold else f"after the {hold}-session hold")
    expiry_text = ("expiry not known" if inside_expiry is None else
                   f"before the {expiry_day.isoformat()} expiry" if inside_expiry
                   else f"after the {expiry_day.isoformat()} expiry")
    out["earnings_disclosure"] = (f"Earnings {report.isoformat()} ({when}): {sessions} sessions away, "
                                  f"{hold_text}, {expiry_text}. Gap and IV-crush risk; disclosure only.")
    return out


def enrich_from_announcement_str(
    earnings_str: str,
    as_of_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convert a Polygon earningsAnnouncement string to earnings display fields.
    Safe to call with empty string — returns UNKNOWN gracefully.

    Used by morning_gate.py to avoid a second Polygon API call per ticker.
    """
    today = datetime.now(timezone.utc).date()
    if as_of_date:
        try:
            today = datetime.fromisoformat(as_of_date).date()
        except Exception:
            pass

    if not earnings_str:
        return {
            "earnings_date":          "",
            "earnings_days_to_event": "",
            "earnings_timing":        "UNKNOWN",
            "earnings_catalyst_flag": "FALSE",
        }
    try:
        earnings_date = datetime.fromisoformat(earnings_str[:10]).date()
        days_to = (earnings_date - today).days
        if 0 <= days_to <= EARNINGS_WINDOW_DAYS:
            timing = "PRE_EARNINGS"
        elif -EARNINGS_LOOKBACK_DAYS <= days_to < 0:
            timing = "POST_EARNINGS"
        else:
            timing = "NO_CATALYST"
        return {
            "earnings_date":          str(earnings_date),
            "earnings_days_to_event": days_to,
            "earnings_timing":        timing,
            "earnings_catalyst_flag": "TRUE" if timing in ("PRE_EARNINGS", "POST_EARNINGS") else "FALSE",
        }
    except Exception as exc:
        return {
            "earnings_date":          "",
            "earnings_days_to_event": "",
            "earnings_timing":        "PARSE_ERROR",
            "earnings_catalyst_flag": "FALSE",
            "earnings_parse_error":   str(exc),
        }


def fetch_earnings_calendar(
    tickers: List[str],
    as_of_date: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Fetch earnings dates from Polygon v2 snapshot for a list of tickers.
    Returns dict: {ticker: {earnings_date, earnings_days_to_event, earnings_timing, ...}}
    Graceful: returns UNKNOWN for any ticker that fails.
    Intended for standalone / evening-pipeline use. morning_gate.py uses
    enrich_from_announcement_str() on its already-fetched snapshot data instead.
    """
    results: Dict[str, Dict[str, Any]] = {}
    if not POLYGON_API_KEY:
        log.warning("POLYGON_API_KEY not set — earnings calendar skipped")
        return {t: {"earnings_timing": "NO_KEY", "earnings_catalyst_flag": "FALSE"} for t in tickers}

    for ticker in tickers:
        try:
            url = (
                f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/"
                f"{ticker}?apiKey={POLYGON_API_KEY}"
            )
            with urllib.request.urlopen(url, timeout=8.0) as resp:
                data = json.loads(resp.read().decode())
            earnings_str = data.get("ticker", {}).get("earningsAnnouncement", "")
            results[ticker] = enrich_from_announcement_str(earnings_str, as_of_date)
            time.sleep(0.05)
        except Exception as exc:
            results[ticker] = {
                "earnings_date":          "",
                "earnings_days_to_event": "",
                "earnings_timing":        "FETCH_ERROR",
                "earnings_catalyst_flag": "FALSE",
                "earnings_fetch_error":   str(exc),
            }
    return results


def enrich_candidates_with_earnings(
    candidates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Add earnings calendar fields to a list of candidate dicts.
    Safe to call on any phase output that has a 'ticker' column.
    Used by evening pipeline (Phase 5) if called standalone.
    """
    tickers = [str(r.get("ticker", "")).upper() for r in candidates if r.get("ticker")]
    calendar = fetch_earnings_calendar(tickers)
    enriched = []
    for row in candidates:
        ticker = str(row.get("ticker", "")).upper()
        cal = calendar.get(ticker, {})
        enriched.append({**row, **cal})
    return enriched
