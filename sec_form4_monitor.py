"""
sec_form4_monitor.py
AVSHUNTER — SEC EDGAR Form 4 insider transaction monitor.

Polls SEC EDGAR for Form 4 filings (insider transactions) for the AVSHUNTER
universe. Detects cluster buying patterns that precede public moves.

Run as:
  python sec_form4_monitor.py --once              # single poll, write signal file
  python sec_form4_monitor.py --tickers NVDA,AAPL,MU --lookback 10
  python sec_form4_monitor.py --daemon            # continuous polling every 30min

Output: dropbox/macro/sec_form4_signals.json

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
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [FORM4_MONITOR] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("form4_monitor")

ROOT               = Path(__file__).resolve().parent
SIGNAL_PATH        = ROOT / "dropbox" / "macro" / "sec_form4_signals.json"
FORM4_CACHE_PATH   = ROOT / "data" / "cache" / "form4_cache.json"
UNIVERSE_CSV_PATH  = ROOT / "data" / "universe" / "polygon_liquid_universe.csv"
UNIVERSE_JSON_PATH = ROOT / "data" / "universe" / "avshunter_universe.json"
TICKER_CACHE_PATH  = ROOT / "data" / "cache" / "sec_company_tickers.json"
POLL_INTERVAL_SEC  = 1800  # 30 minutes

# EDGAR EFTS full-text search for Form 4 filings.
# Searching by ticker name via q= param — form type 4 is straightforward.
SEC_FORM4_SEARCH_URL = (
    "https://efts.sec.gov/LATEST/search-index"
    "?q=%22{ticker}%22&forms=4"
    "&dateRange=custom&startdt={start}&enddt={end}"
    "&_source=file_date,display_names,entity_name,root_forms,file_type,period_of_report"
    "&hits.hits._source=file_date,display_names,entity_name,root_forms,file_type"
)

# SEC XML base URL — used to fetch Form 4 XML for transaction code parsing
SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_clean}/{doc}"

SEC_USER_AGENT = "AVSHUNTER research@makeo.co.uk"

# Regex: extract ticker from EDGAR display_names entry (e.g. "APPLE INC (AAPL) (CIK 0000320193)")
_TICKER_RE = re.compile(r"\(([A-Z]{1,5})\)")
# Regex: extract CIK from EDGAR display_names entry
_CIK_RE    = re.compile(r"\(CIK\s+(\d+)\)", re.IGNORECASE)

# Transaction codes from Form 4 XML
_BUY_CODES  = {"P"}            # Purchase
_SELL_CODES = {"S", "D"}       # Sale, Disposition
_AWARD_CODES = {"A", "M", "G"} # Award/grant/other — excluded from buy/sell signal


def load_universe() -> Set[str]:
    """Load AVSHUNTER ticker universe. Returns set of uppercase tickers."""
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
            raw  = data if isinstance(data, list) else data.get("tickers", data.get("universe", []))
            tickers = {str(t).upper() for t in raw}
            log.info("Universe loaded from JSON: %d tickers", len(tickers))
            return tickers
        except Exception as exc:
            log.error("Universe JSON load failed: %s", exc)

    log.warning("No universe file found — will process tickers passed via --tickers only")
    return set()


def _edgar_get(url: str) -> Optional[dict]:
    """HTTP GET to EDGAR. Returns parsed JSON or None on failure."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": SEC_USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        log.debug("EDGAR GET failed [%s]: %s", url[:80], exc)
        return None


def _extract_ticker_from_entry(entry: str) -> str:
    """Extract first stock ticker from EDGAR display_names string."""
    matches = _TICKER_RE.findall(entry)
    for m in matches:
        if not m.isdigit():
            return m.upper()
    return ""


def _extract_cik_from_entry(entry: str) -> str:
    """Extract CIK from EDGAR display_names string."""
    m = _CIK_RE.search(entry)
    return m.group(1).lstrip("0") if m else ""


def _fetch_transaction_codes(accession_id: str, display_names: list) -> List[str]:
    """
    Fetch Form 4 XML and extract transaction codes (P/S/A etc.).
    Returns list of codes, e.g. ["P", "P"] for two purchases.
    Best effort — returns [] on any failure (network, parse, plan restriction).
    """
    # Parse accession and document filename from EFTS _id
    # Format: "0001234567-24-000001:doc.xml" or "0001234567-24-000001"
    parts      = accession_id.split(":")
    accession  = parts[0]  # e.g. "0001234567-24-000001"
    doc_name   = parts[1] if len(parts) > 1 else ""
    accession_clean = accession.replace("-", "")

    # Get filer CIK from display_names[0] (the insider filer)
    cik = ""
    if isinstance(display_names, list) and display_names:
        cik = _extract_cik_from_entry(str(display_names[0]))

    if not cik or not accession_clean:
        return []

    # Try the document name from _id first; fallback to common Form 4 filenames
    candidates = [doc_name] if doc_name else []
    candidates += ["form4.xml", "wf-form4.xml", "primarydocument.xml", "doc4.xml"]

    for doc in candidates:
        if not doc or not doc.endswith(".xml"):
            continue
        url = SEC_ARCHIVES_URL.format(cik=cik, accession_clean=accession_clean, doc=doc)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": SEC_USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                xml_text = resp.read().decode("utf-8", errors="replace")
            # Extract all transactionCode elements via simple regex (no XML parser needed)
            codes = re.findall(r"<transactionCode[^>]*>([A-Z])</transactionCode>", xml_text)
            if codes:
                log.debug("  Form 4 XML: %s codes=%s", accession, codes)
                return codes
        except Exception:
            continue

    return []


def _classify_signal(
    buy_count: int,
    sell_count: int,
    buy_insiders: int,
    sell_insiders: int,
    net_shares: int,
    est_value: float,
) -> str:
    """Map filing counts/values to form4_signal label."""
    # Cluster buy: 2+ insiders bought
    if buy_insiders >= 2:
        return "CLUSTER_BUY"
    # Single buy with meaningful dollar value
    if buy_insiders == 1 and est_value >= 100_000:
        return "SINGLE_BUY"
    # Cluster sale: 2+ insiders sold (not just awards)
    if sell_insiders >= 2:
        return "CLUSTER_SALE"
    # Single sale or no meaningful activity
    if sell_insiders >= 1:
        return "SALE"
    # Activity exists but no clear buy/sell classification
    if buy_count > 0:
        return "SINGLE_BUY"
    return "NO_ACTIVITY"


def fetch_recent_form4(tickers: List[str], lookback_days: int = 10) -> Dict[str, dict]:
    """
    Fetch Form 4 filings from SEC EDGAR for given tickers.
    Returns {ticker: signal_dict} for tickers with insider activity.

    EDGAR EFTS search: q="{ticker}"&forms=4 within lookback window.
    Transaction type: attempts XML parse (best effort, graceful fallback).
    """
    today = datetime.now(timezone.utc).date()
    start = (today - timedelta(days=lookback_days)).isoformat()
    end   = today.isoformat()

    results: Dict[str, dict] = {}

    for ticker in tickers:
        ticker_upper = str(ticker).upper().strip()
        if not ticker_upper:
            continue

        url = SEC_FORM4_SEARCH_URL.format(
            ticker=urllib.parse.quote(ticker_upper),
            start=start,
            end=end,
        )
        data = _edgar_get(url)
        if not data:
            continue

        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            results[ticker_upper] = {
                "ticker":             ticker_upper,
                "form4_signal":       "NO_ACTIVITY",
                "form4_insider_count": 0,
                "form4_net_shares":   0,
                "form4_est_value":    0.0,
                "form4_lookback_days": lookback_days,
                "form4_latest_date":  "",
            }
            continue

        # Deduplicate by accession base
        seen: Set[str] = set()
        filings: List[Dict[str, Any]] = []
        for hit in hits:
            source  = hit.get("_source", {})
            root_forms = source.get("root_forms", [])
            if isinstance(root_forms, str):
                root_forms = [root_forms]
            # Accept only genuine Form 4 (not 4/A amendments — those are already counted)
            if not any("4" == str(rf).strip() for rf in root_forms):
                # Fallback: check file_type
                if "4" not in str(source.get("file_type", "")):
                    continue

            full_id      = hit.get("_id", "")
            accession_b  = full_id.split(":")[0] if ":" in full_id else full_id
            if accession_b in seen:
                continue
            seen.add(accession_b)

            display_names = source.get("display_names", [])
            # For Form 4: display_names[0] = insider (filer), display_names[1] = issuer company
            issuer_ticker = ""
            if isinstance(display_names, list) and len(display_names) >= 2:
                issuer_ticker = _extract_ticker_from_entry(str(display_names[1]))
            elif isinstance(display_names, list) and display_names:
                issuer_ticker = _extract_ticker_from_entry(str(display_names[0]))

            # Only include if issuer matches our ticker
            if issuer_ticker and issuer_ticker != ticker_upper:
                continue

            filer_name = ""
            if isinstance(display_names, list) and display_names:
                filer_name = str(display_names[0]).split("(")[0].strip()

            filings.append({
                "accession_id":   full_id,
                "filing_date":    source.get("file_date", ""),
                "filer_name":     filer_name,
                "display_names":  display_names,
            })

        if not filings:
            results[ticker_upper] = {
                "ticker":             ticker_upper,
                "form4_signal":       "NO_ACTIVITY",
                "form4_insider_count": 0,
                "form4_net_shares":   0,
                "form4_est_value":    0.0,
                "form4_lookback_days": lookback_days,
                "form4_latest_date":  "",
            }
            continue

        # Attempt XML parse for transaction codes on first 3 filings (rate-limited)
        buy_count = sell_count = 0
        buy_insiders = sell_insiders = 0
        net_shares = 0
        est_value  = 0.0
        latest_date = max((f["filing_date"] for f in filings), default="")

        # Parse up to 3 filings for transaction type (avoid EDGAR hammering)
        xml_parsed = False
        for filing in filings[:3]:
            time.sleep(0.3)  # 300ms delay — be a polite EDGAR citizen
            codes = _fetch_transaction_codes(
                filing["accession_id"], filing["display_names"]
            )
            if codes:
                xml_parsed = True
                for code in codes:
                    if code in _BUY_CODES:
                        buy_count += 1
                    elif code in _SELL_CODES:
                        sell_count += 1
            # Count unique insider filers
            if any(c in _BUY_CODES for c in codes):
                buy_insiders += 1
            elif any(c in _SELL_CODES for c in codes):
                sell_insiders += 1

        # If XML parsing yielded nothing, use filing count as proxy
        if not xml_parsed:
            # Assume all Form 4 filings within 10 days for a single ticker = cluster activity
            buy_insiders  = len(filings)
            buy_count     = buy_insiders
            log.debug(
                "  %s: %d Form 4 filings — XML parse unavailable, assuming cluster",
                ticker_upper, len(filings),
            )

        signal = _classify_signal(
            buy_count, sell_count, buy_insiders, sell_insiders, net_shares, est_value,
        )

        results[ticker_upper] = {
            "ticker":              ticker_upper,
            "form4_signal":        signal,
            "form4_insider_count": max(buy_insiders, sell_insiders, len(filings)),
            "form4_net_shares":    net_shares,
            "form4_est_value":     round(est_value, 0),
            "form4_lookback_days": lookback_days,
            "form4_latest_date":   latest_date,
            "form4_filing_count":  len(filings),
            "form4_xml_parsed":    xml_parsed,
        }
        log.info(
            "  %s: %d Form 4 filings → signal=%s (buy_insiders=%d sell_insiders=%d xml=%s)",
            ticker_upper, len(filings), signal,
            buy_insiders, sell_insiders, xml_parsed,
        )
        time.sleep(0.2)  # polite EDGAR delay between tickers

    return results


def _load_cache() -> dict:
    """Load form4 cache (daily refresh guard)."""
    try:
        if FORM4_CACHE_PATH.exists():
            return json.loads(FORM4_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _write_cache(cache: dict) -> None:
    FORM4_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FORM4_CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _write_signal_file(signals: Dict[str, dict], poll_time: str) -> None:
    """Write form4 signal file consumed by scanner at startup."""
    signal_list = [s for s in signals.values() if s.get("form4_signal") not in (None, "NO_ACTIVITY")]
    payload = {
        "generated_at":         poll_time,
        "schema_version":       "1.0",
        "signal_count":         len(signal_list),
        "advisory_only":        True,
        "execution_permission": "NONE — research context only",
        "signals":              signal_list,
    }
    SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    SIGNAL_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info(
        "Form 4 signal file written: %d active signals → %s",
        len(signal_list), SIGNAL_PATH,
    )


def run_poll(tickers: Optional[List[str]] = None, lookback_days: int = 10) -> int:
    """
    Single poll cycle. If tickers not specified, uses universe CSV.
    Returns number of active signals found.
    """
    if tickers:
        universe = [t.strip().upper() for t in tickers if t.strip()]
    else:
        universe = list(load_universe())

    if not universe:
        log.warning("Empty universe — nothing to poll")
        return 0

    today_str  = datetime.now(timezone.utc).date().isoformat()
    cache      = _load_cache()
    poll_time  = datetime.now(timezone.utc).isoformat()

    # Refresh if no cache or cache is from a prior day
    cache_date = cache.get("_cache_date", "")
    if cache_date != today_str:
        log.info(
            "Form 4 poll: %d universe tickers | lookback=%dd | %s → %s",
            len(universe), lookback_days,
            (datetime.now(timezone.utc).date() - timedelta(days=lookback_days)).isoformat(),
            today_str,
        )
        signals = fetch_recent_form4(universe, lookback_days)
        cache = {**signals, "_cache_date": today_str}
        _write_cache(cache)
    else:
        log.info("Form 4 cache hit for %s — %d signals cached", today_str, len(cache) - 1)
        signals = {k: v for k, v in cache.items() if k != "_cache_date"}

    _write_signal_file(signals, poll_time)

    active = sum(
        1 for s in signals.values()
        if isinstance(s, dict) and s.get("form4_signal") not in (None, "NO_ACTIVITY")
    )
    return active


def main() -> int:
    parser = argparse.ArgumentParser(description="AVSHUNTER SEC Form 4 Insider Monitor")
    parser.add_argument("--once",     action="store_true", help="Single poll then exit")
    parser.add_argument("--daemon",   action="store_true", help="Continuous polling every 30min")
    parser.add_argument("--tickers",  type=str, default="",
                        help="Comma-separated tickers (overrides universe CSV)")
    parser.add_argument("--lookback", type=int, default=10,
                        help="Lookback window in days (default 10)")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()] if args.tickers else None

    if args.daemon:
        log.info(
            "Form 4 monitor daemon starting — polling every %d min",
            POLL_INTERVAL_SEC // 60,
        )
        while True:
            try:
                active = run_poll(tickers, args.lookback)
                log.info("Poll complete: %d active signals", active)
            except Exception as exc:
                log.error("Poll failed: %s", exc)
            time.sleep(POLL_INTERVAL_SEC)
    else:
        active = run_poll(tickers, args.lookback)
        log.info("Form 4 poll complete: %d active signals → %s", active, SIGNAL_PATH)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
