#!/usr/bin/env python3
"""
15-MINUTE DATA REFRESH SCRIPT (Manual)
Updates all tickers in universe with latest 15-minute OHLCV data from Polygon.

Usage:
    python refresh_daily_data.py

Notes:
- This script fetches 15-minute aggregates (NOT daily).
- Designed for MANUAL runs (no automation required).
- Incremental refresh: pulls last 7 days of 15m bars.
- Backfill for new/thin tickers: pulls last 60 days of 15m bars.
- Merge + dedupe always applied.
- Resilient fetch: retries on 429, 5xx, timeouts.

Storage:
- Writes to: data/intraday_15m/<TICKER>.csv
"""

import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

# ============================================================================
# CONFIG
# ============================================================================

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")

# Universe + output paths (keep your canonical locations)
DATA_PATH     = Path("C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/data/intraday_15m")
UNIVERSE_FILE = Path("C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/data/universe/hybrid_universe_enhanced.csv")

# 15m settings
AGG_MULTIPLIER = 15
AGG_TIMESPAN   = "minute"

# Lookback windows (sane for 15m)
INCREMENTAL_LOOKBACK_DAYS = 7
BACKFILL_LOOKBACK_DAYS    = 60

# "Thin" threshold for 15m series
# Regular session: ~26 bars/day (390 minutes / 15).
# 10 days ≈ 260 bars. If below this, treat as thin and backfill more.
THIN_BARS_THRESHOLD = 260

# Retry settings
MAX_RETRIES        = 3
RETRY_BACKOFF_429  = 60     # seconds after rate limit
RETRY_BACKOFF_5XX  = 10     # seconds after server error
RATE_LIMIT_SLEEP   = 12.5   # free tier pacing (approx 5 calls/min)

# ============================================================================
# RESILIENT POLYGON FETCH (15m)
# ============================================================================

def fetch_polygon_15m(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Fetch 15-minute OHLCV aggregates from Polygon with retry logic.

    Endpoint:
      /v2/aggs/ticker/{ticker}/range/15/minute/{start}/{end}

    Returns:
      DataFrame columns: [ts, open, high, low, close, volume]
      ts is ISO datetime (UTC) by Polygon aggregate timestamp.
    """
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/{AGG_MULTIPLIER}/{AGG_TIMESPAN}/{start_date}/{end_date}"
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": 50000,
        "apiKey": POLYGON_API_KEY,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, timeout=20)

            if r.status_code == 429:
                print(f"[429 rate limit - wait {RETRY_BACKOFF_429}s {attempt}/{MAX_RETRIES}]", end=" ")
                time.sleep(RETRY_BACKOFF_429)
                continue

            if r.status_code in (500, 502, 503):
                print(f"[{r.status_code} server error - wait {RETRY_BACKOFF_5XX}s {attempt}/{MAX_RETRIES}]", end=" ")
                time.sleep(RETRY_BACKOFF_5XX)
                continue

            if r.status_code != 200:
                print(f"[HTTP {r.status_code} - skipping]", end=" ")
                return pd.DataFrame()

            try:
                data = r.json()
            except Exception:
                print(f"[malformed JSON {attempt}/{MAX_RETRIES}]", end=" ")
                time.sleep(RETRY_BACKOFF_5XX)
                continue

            if "results" not in data or not data["results"]:
                return pd.DataFrame()

            df = pd.DataFrame(data["results"])
            # Polygon gives ms epoch in 't'
            df["ts"] = pd.to_datetime(df["t"], unit="ms", utc=True)
            df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
            df = df[["ts", "open", "high", "low", "close", "volume"]]

            return df

        except requests.exceptions.Timeout:
            print(f"[timeout {attempt}/{MAX_RETRIES}]", end=" ")
            time.sleep(RETRY_BACKOFF_5XX)
            continue
        except requests.exceptions.ConnectionError:
            print(f"[connection error {attempt}/{MAX_RETRIES}]", end=" ")
            time.sleep(RETRY_BACKOFF_5XX)
            continue
        except Exception as e:
            print(f"[unexpected: {e}]", end=" ")
            return pd.DataFrame()

    print(f"[FAILED after {MAX_RETRIES} attempts]", end=" ")
    return pd.DataFrame()

# ============================================================================
# MERGE + DEDUPE
# ============================================================================

def merge_with_existing(csv_file: Path, new_data: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Merge new 15m data with existing CSV, dedupe on ts (timestamp).
    Keeps newest record for duplicate ts.
    """
    old = pd.read_csv(csv_file)
    old["ts"] = pd.to_datetime(old["ts"], utc=True)

    original_len = len(old)

    combined = pd.concat([old, new_data], ignore_index=True)
    combined["ts"] = pd.to_datetime(combined["ts"], utc=True)
    combined = combined.drop_duplicates(subset=["ts"], keep="last")
    combined = combined.sort_values("ts").reset_index(drop=True)

    rows_added = len(combined) - original_len
    return combined, rows_added

# ============================================================================
# FRESHNESS CHECK
# ============================================================================

def check_freshness():
    """Check freshness for sample tickers in the 15m store."""
    sample = ["AAPL", "MSFT", "NVDA", "GOOGL", "TSLA"]

    print("\nCHECKING 15m DATA FRESHNESS")
    print("=" * 80)

    for ticker in sample:
        csv_file = DATA_PATH / f"{ticker}.csv"
        if not csv_file.exists():
            print(f"  {ticker}: FILE NOT FOUND")
            continue

        df = pd.read_csv(csv_file)
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        last_ts = df["ts"].max()
        bars = len(df)

        age_min = (datetime.now(tz=last_ts.tzinfo) - last_ts).total_seconds() / 60.0

        freshness = "FRESH" if age_min <= 60 else f"STALE ({age_min:.0f} min old)"
        thin = "THIN" if bars < THIN_BARS_THRESHOLD else "OK"

        print(f"  {ticker}: Last={last_ts} | {freshness} | {bars} bars | {thin}")

    print("=" * 80 + "\n")

# ============================================================================
# MAIN REFRESH
# ============================================================================

def refresh_universe():
    """
    Update all tickers in universe.

    Per ticker:
      1) No file OR < THIN_BARS_THRESHOLD bars -> BACKFILL (last 60 days)
      2) Else -> INCREMENTAL (last 7 days)

    Always merge + dedupe on ts.
    """
    if not POLYGON_API_KEY:
        print("ERROR: POLYGON_API_KEY environment variable not set!")
        return

    DATA_PATH.mkdir(parents=True, exist_ok=True)

    if not UNIVERSE_FILE.exists():
        print(f"ERROR: Universe file not found: {UNIVERSE_FILE}")
        return

    universe = pd.read_csv(UNIVERSE_FILE)
    if "ticker" not in universe.columns:
        print("ERROR: Universe CSV missing required column: ticker")
        return

    tickers = (
        universe["ticker"]
        .dropna()
        .astype(str)
        .str.upper()
        .str.strip()
        .unique()
        .tolist()
    )
    tickers = [t for t in tickers if t and not t.isdigit() and len(t) <= 10]

    print(f"\nLoading universe from: {UNIVERSE_FILE}")
    print(f"Found {len(tickers)} valid tickers to update\n")

    now = datetime.utcnow()
    end_date = now.strftime("%Y-%m-%d")
    inc_start = (now - timedelta(days=INCREMENTAL_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    bf_start  = (now - timedelta(days=BACKFILL_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    print(f"Incremental range : {inc_start} to {end_date} ({INCREMENTAL_LOOKBACK_DAYS} days)")
    print(f"Backfill range    : {bf_start} to {end_date} ({BACKFILL_LOOKBACK_DAYS} days)")
    print("=" * 80 + "\n")

    success = backfills = incrementals = failed = 0

    for idx, ticker in enumerate(tickers, 1):
        print(f"[{idx}/{len(tickers)}] {ticker}...", end=" ")

        csv_file = DATA_PATH / f"{ticker}.csv"

        # Determine mode
        if not csv_file.exists():
            mode = "BACKFILL(new)"
            start = bf_start
        else:
            try:
                existing_bars = len(pd.read_csv(csv_file))
            except Exception:
                existing_bars = 0

            if existing_bars < THIN_BARS_THRESHOLD:
                mode = f"BACKFILL(thin:{existing_bars})"
                start = bf_start
            else:
                mode = f"INCREMENTAL(ok:{existing_bars})"
                start = inc_start

        new_data = fetch_polygon_15m(ticker, start, end_date)

        if new_data.empty:
            print(f"NO DATA [{mode}]")
            failed += 1
            time.sleep(RATE_LIMIT_SLEEP)
            continue

        if csv_file.exists():
            combined, rows_added = merge_with_existing(csv_file, new_data)
            print(f"+{rows_added} rows -> {len(combined)} total [{mode}]")
        else:
            combined = new_data.sort_values("ts").reset_index(drop=True)
            print(f"{len(combined)} rows [{mode}]")

        combined.to_csv(csv_file, index=False)

        success += 1
        if "BACKFILL" in mode:
            backfills += 1
        else:
            incrementals += 1

        time.sleep(RATE_LIMIT_SLEEP)

        if idx % 100 == 0:
            elapsed   = idx * RATE_LIMIT_SLEEP / 60
            remaining = (len(tickers) - idx) * RATE_LIMIT_SLEEP / 60
            print(
                f"\n  [{idx}/{len(tickers)}] "
                f"Success:{success} Backfills:{backfills} "
                f"Incremental:{incrementals} Failed:{failed} "
                f"Elapsed:{elapsed:.0f}min Remaining:{remaining:.0f}min\n"
            )

    print("\n" + "=" * 80)
    print("15m REFRESH COMPLETE")
    print("=" * 80)
    print(f"  Total processed : {success}")
    print(f"  Backfilled      : {backfills}")
    print(f"  Incremental     : {incrementals}")
    print(f"  Failed          : {failed}")
    print(f"  Total time      : ~{len(tickers) * RATE_LIMIT_SLEEP / 60:.0f} minutes\n")

# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("AVSHUNTER 15-MINUTE DATA REFRESH (MANUAL)")
    print("=" * 80)

    check_freshness()

    response = input("Proceed with 15m refresh? (y/n): ").strip().lower()
    if response == "y":
        refresh_universe()
    else:
        print("\nRefresh cancelled.\n")
