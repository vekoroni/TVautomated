"""
sec_activist_monitor.py
AVSHUNTER — SEC EDGAR 13D/13G filing monitor.

Polls the SEC EDGAR full-text search API for SC 13D and SC 13G filings.
Checks whether any filing target is in the AVSHUNTER universe.
Writes activist signal file consumed by Discovery phase as advisory context.

Run as:
  python sec_activist_monitor.py --once        # single poll, write signal file
  python sec_activist_monitor.py --daemon      # continuous polling every 30min
  python sec_activist_monitor.py --lookback 5  # override lookback window (days)
  python sec_activist_monitor.py --since 2026-06-01  # backfill from date

Output: dropbox/macro/sec_activist_signals.json

ADVISORY ONLY — never gates any trade verdict.
If signal file missing, pipeline continues unchanged.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SEC_MONITOR] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("sec_monitor")

ROOT               = Path(__file__).resolve().parent
SIGNAL_PATH        = ROOT / "dropbox" / "macro" / "sec_activist_signals.json"
UNIVERSE_CSV_PATH  = ROOT / "data" / "universe" / "polygon_liquid_universe.csv"
UNIVERSE_JSON_PATH = ROOT / "data" / "universe" / "avshunter_universe.json"
TICKER_CACHE_PATH  = ROOT / "data" / "cache" / "sec_company_tickers.json"
POLL_INTERVAL_SEC  = 1800  # 30 minutes

# EDGAR EFTS full-text search — keyword approach avoids form-type parameter issues
# Searches for documents containing "13D" or "13G", then filters by root_forms field.
SEC_SEARCH_URL = (
    "https://efts.sec.gov/LATEST/search-index"
    "?q=%2213D%22+%2213G%22"
    "&dateRange=custom&startdt={start}&enddt={end}"
    "&_source=file_date,display_names,entity_name,root_forms,file_type"
)

SEC_USER_AGENT = "AVSHUNTER research@makeo.co.uk"
_TARGET_ROOT_FORMS = {"SCHEDULE 13D", "SCHEDULE 13G"}

# Regex to extract ticker from EDGAR display_names entries.
# Format: "COMPANY NAME  (TICKER)  (CIK 0000123456)"
_TICKER_RE = re.compile(r"\(([A-Z]{1,5})\)")


def load_universe() -> Set[str]:
    """
    Load AVSHUNTER ticker universe from CSV (primary) or JSON (fallback).
    Returns set of uppercase ticker strings.
    """
    if UNIVERSE_CSV_PATH.exists():
        try:
            tickers: Set[str] = set()
            with open(UNIVERSE_CSV_PATH, encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    t = row.get("ticker") or row.get("Ticker") or row.get("TICKER")
                    if t:
                        tickers.add(str(t).upper().strip())
            log.info("Universe loaded from CSV: %d tickers", len(tickers))
            return tickers
        except Exception as exc:
            log.error("Universe CSV load failed: %s", exc)

    if UNIVERSE_JSON_PATH.exists():
        try:
            data = json.loads(UNIVERSE_JSON_PATH.read_text(encoding="utf-8-sig"))
            if isinstance(data, list):
                tickers = {str(t).upper() for t in data}
            else:
                raw = data.get("tickers", data.get("universe", []))
                tickers = {str(t).upper() for t in raw}
            log.info("Universe loaded from JSON: %d tickers", len(tickers))
            return tickers
        except Exception as exc:
            log.error("Universe JSON load failed: %s", exc)

    log.warning("No universe file found — all filings will be skipped")
    return set()


def _extract_ticker_from_display_names(display_names: Any) -> str:
    """
    Extract the first stock ticker from EDGAR display_names.
    EDGAR format: ["COMPANY NAME  (TICKER)  (CIK 0000123456)", "FILER NAME  (CIK ...)"]
    Returns uppercase ticker or "" if not found.
    Only the first entry (issuer/target company) is checked.
    """
    if isinstance(display_names, list) and display_names:
        first = str(display_names[0])
        matches = _TICKER_RE.findall(first)
        # Skip CIK-like matches (all digits after removing leading zeros)
        for m in matches:
            if not m.isdigit():
                return m.upper()
    return ""


def load_sec_company_ticker_map() -> Dict[str, str]:
    """
    Download and cache the SEC company tickers JSON (refreshed weekly).
    Maps company name (uppercase) → ticker uppercase.
    Used as fallback when ticker cannot be extracted from display_names.
    Cache: data/cache/sec_company_tickers.json
    """
    TICKER_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

    if TICKER_CACHE_PATH.exists():
        age_days = (
            datetime.now(timezone.utc).timestamp() - TICKER_CACHE_PATH.stat().st_mtime
        ) / 86400
        if age_days < 7:
            try:
                raw = json.loads(TICKER_CACHE_PATH.read_text(encoding="utf-8"))
                result = {
                    v["title"].upper(): v["ticker"].upper()
                    for v in raw.values()
                    if v.get("ticker") and v.get("title")
                }
                log.info(
                    "SEC ticker map loaded from cache: %d entries (age %.1fd)",
                    len(result), age_days,
                )
                return result
            except Exception as exc:
                log.warning("Cache load failed, re-fetching: %s", exc)

    try:
        url = "https://www.sec.gov/files/company_tickers.json"
        req = urllib.request.Request(url, headers={"User-Agent": SEC_USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = json.loads(resp.read().decode())
        TICKER_CACHE_PATH.write_text(json.dumps(raw), encoding="utf-8")
        result = {
            v["title"].upper(): v["ticker"].upper()
            for v in raw.values()
            if v.get("ticker") and v.get("title")
        }
        log.info("SEC company tickers refreshed: %d entries", len(result))
        return result
    except Exception as exc:
        log.error("SEC company tickers fetch failed: %s", exc)
        return {}


def fetch_recent_filings(start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """
    Fetch SC 13D/13G filings from EDGAR full-text search API.
    Filters server-side by keyword "13D" "13G", then client-side by root_forms.
    Returns list of filing dicts with extracted ticker.
    Graceful: returns [] on any network/parse failure.
    """
    url = SEC_SEARCH_URL.format(start=start_date, end=end_date)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": SEC_USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        hits = data.get("hits", {}).get("hits", [])
        log.info("EDGAR returned %d hits (%s → %s)", len(hits), start_date, end_date)

        filings: List[Dict[str, Any]] = []
        seen_accessions: Set[str] = set()

        for hit in hits:
            source = hit.get("_source", {})
            root_forms = source.get("root_forms", [])
            if isinstance(root_forms, str):
                root_forms = [root_forms]

            # Only keep genuine 13D/13G root forms
            matched_form = next(
                (rf for rf in root_forms if rf in _TARGET_ROOT_FORMS), None
            )
            if not matched_form:
                continue

            # Only keep primary documents (not exhibits like EX-99.1)
            file_type = source.get("file_type", "")
            if file_type and "SCHEDULE" not in file_type.upper() and "SC 13" not in file_type.upper():
                continue

            # Deduplicate by accession base (strip document filename suffix)
            full_id = hit.get("_id", "")
            accession_base = full_id.split(":")[0] if ":" in full_id else full_id
            if accession_base in seen_accessions:
                continue
            seen_accessions.add(accession_base)

            display_names = source.get("display_names", [])
            ticker = _extract_ticker_from_display_names(display_names)

            filings.append({
                "filing_type":      file_type or matched_form,
                "filing_date":      source.get("file_date", ""),
                "display_names":    display_names,
                "entity_name":      (
                    display_names[0].split("(")[0].strip()
                    if isinstance(display_names, list) and display_names
                    else ""
                ),
                "root_form":        matched_form,
                "accession_num":    accession_base,
                "extracted_ticker": ticker,
                "url": (
                    f"https://www.sec.gov/cgi-bin/browse-edgar"
                    f"?action=getcompany&filenum=&type=SC+13D&dateb=&owner=include"
                    f"&count=5&search_text=&accession={accession_base}"
                ),
            })

        log.info("Filtered to %d unique SCHEDULE 13D/13G filings", len(filings))
        return filings

    except Exception as exc:
        log.error("EDGAR fetch failed: %s", exc)
        return []


def resolve_tickers(
    filings: List[Dict[str, Any]],
    company_ticker_map: Dict[str, str],
) -> List[Dict[str, Any]]:
    """
    Resolve ticker for each filing.
    Primary: extract from display_names (works for ~95% of cases).
    Fallback: company name lookup via SEC company ticker map.
    """
    resolved = []
    for filing in filings:
        ticker = filing.get("extracted_ticker", "")

        # Fallback: company name lookup
        if not ticker:
            entity = filing.get("entity_name", "").upper().strip()
            ticker = company_ticker_map.get(entity, "")
            if not ticker:
                for suffix in (" INC", " CORP", " LTD", " LLC", " CO", " PLC", " NV", " SA"):
                    stripped = entity.removesuffix(suffix).strip()
                    ticker = company_ticker_map.get(stripped, "")
                    if ticker:
                        break

        resolved.append({**filing, "resolved_ticker": ticker})

    resolved_count = sum(1 for r in resolved if r.get("resolved_ticker"))
    log.info("Ticker resolution: %d/%d resolved", resolved_count, len(resolved))
    return resolved


def filter_universe_matches(
    resolved_filings: List[Dict[str, Any]],
    universe: Set[str],
) -> List[Dict[str, Any]]:
    """Return only filings where resolved_ticker is in the AVSHUNTER universe."""
    matches = [
        f for f in resolved_filings
        if f.get("resolved_ticker", "").upper() in universe
    ]
    log.info("Universe matches: %d", len(matches))
    return matches


def write_signal_file(matches: List[Dict[str, Any]], poll_time: str) -> None:
    """Write activist signal file consumed by Discovery phase."""
    payload = {
        "generated_at":         poll_time,
        "schema_version":       "1.0",
        "signal_count":         len(matches),
        "advisory_only":        True,
        "execution_permission": "NONE — research context only",
        "signals": [
            {
                "ticker":         m.get("resolved_ticker", ""),
                "filing_type":    m.get("filing_type", m.get("root_form", "")),
                "filing_date":    m.get("filing_date", ""),
                "entity_name":    m.get("entity_name", ""),
                "display_names":  m.get("display_names", []),
                "url":            m.get("url", ""),
                "signal_label": (
                    "ACTIVIST_13D"
                    if "13D" in m.get("root_form", m.get("filing_type", ""))
                    else "ACTIVIST_13G"
                ),
                "avshunter_note": (
                    "13D = controlling intent (>5% stake, change agenda). "
                    "13G = passive intent (>5% stake, no change agenda). "
                    "Both warrant DISCOVERY_ONLY re-route."
                ),
            }
            for m in matches
        ],
    }
    SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    SIGNAL_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info("Signal file written: %d matches → %s", len(matches), SIGNAL_PATH)


def run_poll(lookback_days: int = 3) -> int:
    """Run a single poll cycle. Returns number of universe matches found."""
    today = datetime.now(timezone.utc).date()
    start = (today - timedelta(days=lookback_days)).isoformat()
    end   = today.isoformat()

    log.info("Polling EDGAR SC 13D/13G filings: %s → %s", start, end)

    universe   = load_universe()
    ticker_map = load_sec_company_ticker_map()
    filings    = fetch_recent_filings(start, end)
    resolved   = resolve_tickers(filings, ticker_map)
    matches    = filter_universe_matches(resolved, universe)

    write_signal_file(matches, datetime.now(timezone.utc).isoformat())
    return len(matches)


def main() -> int:
    parser = argparse.ArgumentParser(description="AVSHUNTER SEC 13D/13G Monitor")
    parser.add_argument("--once",    action="store_true", help="Single poll then exit")
    parser.add_argument("--daemon",  action="store_true", help="Continuous polling every 30min")
    parser.add_argument("--lookback", type=int, default=3, help="Lookback days (default 3)")
    parser.add_argument("--since",   type=str, default="",
                        help="Override start date (YYYY-MM-DD). Overrides --lookback.")
    args = parser.parse_args()

    lookback = args.lookback
    if args.since:
        try:
            since_date = datetime.fromisoformat(args.since).date()
            today = datetime.now(timezone.utc).date()
            lookback = (today - since_date).days
            log.info("--since %s → lookback=%d days", args.since, lookback)
        except ValueError:
            log.error("Invalid --since date: %s (expected YYYY-MM-DD)", args.since)
            return 1

    if args.daemon:
        log.info("SEC monitor daemon starting — polling every %d min", POLL_INTERVAL_SEC // 60)
        while True:
            try:
                run_poll(lookback)
            except Exception as exc:
                log.error("Poll failed: %s", exc)
            time.sleep(POLL_INTERVAL_SEC)
    else:
        run_poll(lookback)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
