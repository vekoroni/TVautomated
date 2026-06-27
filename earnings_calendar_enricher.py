"""
earnings_calendar_enricher.py
AVSHUNTER — Earnings catalyst calendar enrichment.
Adds earnings_days_to_event, earnings_timing, earnings_catalyst_flag
to candidates using the earningsAnnouncement field from Polygon snapshots.

DISPLAY FIELDS ONLY — never gates any phase verdict.
Can be called standalone (via fetch_earnings_calendar) or from morning_gate.py
by passing the already-fetched Polygon snapshot data via enrich_from_announcement_str.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("earnings_calendar_enricher")

POLYGON_API_KEY      = os.getenv("POLYGON_API_KEY", "").strip()
EARNINGS_WINDOW_DAYS = 5  # flag tickers within this many calendar days of earnings
EARNINGS_LOOKBACK_DAYS = 1  # also flag tickers that reported yesterday (post-earnings vol)


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
