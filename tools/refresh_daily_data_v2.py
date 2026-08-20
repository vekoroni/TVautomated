# -*- coding: utf-8 -*-
r"""
AVSHUNTER — Daily Data Refresh v2 (Universe-aligned, non-interactive, audited)

What it does
- Reads the *same* universe your pipeline uses (default: dropbox/universe/universe_latest.csv)
- Refreshes per-ticker OHLCV CSVs in data/daily/<TICKER>.csv using Polygon aggregates
- Uses last-saved bar date to decide incremental start (not a fixed "last 7 days")
- Backfills ~900 trading days when history is thin / missing
- Emits a full-universe freshness report you can fail-close on

Usage (recommended)
  .\venv\Scripts\python.exe tools\refresh_daily_data_v2.py --yes

If you want explicit universe path
  .\venv\Scripts\python.exe tools\refresh_daily_data_v2.py --universe dropbox\universe\universe_latest.csv --yes

Fail-close if too much of the universe is stale
  .\venv\Scripts\python.exe tools\refresh_daily_data_v2.py --yes --max_stale_days 2 --block_if_stale_pct 5
  (blocks if >5% of tickers have last bar older than 2 days)

Auth
- Requires POLYGON_API_KEY in environment, or a .env in repo root.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import requests

# -----------------------------
# Defaults
# -----------------------------
MIN_BARS_OK = 260
BACKFILL_DAYS = 900
INCR_BUFFER_DAYS = 5          # fetch a little overlap to avoid gaps
RATE_SLEEP = 0.25             # politeness between requests
RETRY_MAX = 5
RETRY_BACKOFF_BASE = 1.8

AGGS_URL = "https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}"

# -----------------------------
# Helpers
# -----------------------------
def repo_root() -> Path:
    # tools/refresh_daily_data_v2.py -> repo root is parent of tools
    return Path(__file__).resolve().parents[1]

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def load_env() -> None:
    # optional .env support without forcing dependency
    env_path = repo_root() / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)

def polygon_key() -> str:
    key = os.environ.get("POLYGON_API_KEY", "").strip()
    if not key:
        raise RuntimeError("POLYGON_API_KEY missing. Set it in environment or repo-root .env")
    return key

def read_universe_tickers(universe_csv: Path) -> List[str]:
    if not universe_csv.exists():
        raise RuntimeError(f"Universe file not found: {universe_csv}")

    with universe_csv.open("r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        if not rdr.fieldnames or "ticker" not in [h.strip() for h in rdr.fieldnames]:
            raise RuntimeError("Universe CSV must include a 'ticker' column")
        tickers = []
        seen = set()
        for row in rdr:
            t = (row.get("ticker") or "").strip().upper()
            if not t:
                continue
            if t in seen:
                continue
            seen.add(t)
            tickers.append(t)
        return tickers

def safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def parse_yyyy_mm_dd(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)

def date_to_yyyy_mm_dd(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")

def load_existing_csv(path: Path) -> Optional[List[Dict[str, Any]]]:
    if not path.exists():
        return None
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        if not rdr.fieldnames:
            return None
        for r in rdr:
            rows.append(r)
    return rows or None

def last_date_in_rows(rows: List[Dict[str, Any]]) -> Optional[datetime]:
    # expects a 'date' column in YYYY-MM-DD
    dates = []
    for r in rows:
        d = (r.get("date") or "").strip()
        if not d:
            continue
        try:
            dates.append(parse_yyyy_mm_dd(d))
        except Exception:
            continue
    return max(dates) if dates else None

def rows_to_index(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    # keyed by date
    out = {}
    for r in rows:
        d = (r.get("date") or "").strip()
        if not d:
            continue
        out[d] = r
    return out

def fetch_aggs(ticker: str, start: datetime, end: datetime, api_key: str) -> List[Dict[str, Any]]:
    url = AGGS_URL.format(
        ticker=ticker,
        start=date_to_yyyy_mm_dd(start),
        end=date_to_yyyy_mm_dd(end),
    )
    params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key}

    for attempt in range(1, RETRY_MAX + 1):
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 200:
                data = r.json()
                results = data.get("results") or []
                out = []
                for bar in results:
                    # bar timestamp is ms
                    ts = int(bar.get("t"))
                    dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
                    out.append({
                        "date": dt.strftime("%Y-%m-%d"),
                        "open": bar.get("o"),
                        "high": bar.get("h"),
                        "low": bar.get("l"),
                        "close": bar.get("c"),
                        "volume": bar.get("v"),
                        "vwap": bar.get("vw", ""),
                        "transactions": bar.get("n", ""),
                    })
                return out

            if r.status_code in (429, 500, 502, 503, 504):
                sleep_s = (RETRY_BACKOFF_BASE ** (attempt - 1))
                time.sleep(sleep_s)
                continue

            # hard failure (404 etc.)
            raise RuntimeError(f"HTTP_{r.status_code}")

        except requests.RequestException:
            sleep_s = (RETRY_BACKOFF_BASE ** (attempt - 1))
            time.sleep(sleep_s)
            continue

    raise RuntimeError("RETRY_EXHAUSTED")

def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    # stable output schema
    fields = ["date", "open", "high", "low", "close", "volume", "vwap", "transactions"]
    safe_mkdir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in sorted(rows, key=lambda x: x.get("date", "")):
            w.writerow({k: r.get(k, "") for k in fields})

def classify_history_state(bar_count: int) -> str:
    if bar_count <= 0:
        return "MISSING"
    if bar_count < 100:
        return "THIN"
    if bar_count < MIN_BARS_OK:
        return "WARMING_UP"
    return "OK"

def days_stale(last_bar: Optional[datetime], now_utc: datetime) -> Optional[int]:
    if not last_bar:
        return None
    return int((now_utc.date() - last_bar.date()).days)

# -----------------------------
# Reporting
# -----------------------------
@dataclass
class RefreshRow:
    ticker: str
    status: str               # OK / UPDATED / BACKFILLED / NO_DATA / FAIL
    bar_count: int
    last_bar_date: str
    stale_days: str
    history_state: str        # MISSING / THIN / WARMING_UP / OK
    error: str

# -----------------------------
# Main
# -----------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default=str(repo_root() / "dropbox" / "universe" / "universe_latest.csv"),
                    help="Universe CSV (must include 'ticker')")
    ap.add_argument("--outdir", default=str(repo_root() / "data" / "daily"),
                    help="Per-ticker OHLCV output directory")
    ap.add_argument("--yes", action="store_true", help="Run non-interactively (recommended for automation)")
    ap.add_argument("--max_stale_days", type=int, default=2, help="Last bar older than this => stale")
    ap.add_argument("--block_if_stale_pct", type=float, default=None,
                    help="Fail-close if stale_pct > this number (e.g. 5 for 5%%).")
    ap.add_argument("--rate_sleep", type=float, default=RATE_SLEEP)
    ap.add_argument("--min_bars", type=int, default=MIN_BARS_OK)
    ap.add_argument("--backfill_days", type=int, default=BACKFILL_DAYS)
    ap.add_argument("--incr_buffer_days", type=int, default=INCR_BUFFER_DAYS)
    args = ap.parse_args()

    if not args.yes:
        raise SystemExit("BLOCKED: Add --yes to run (non-interactive). This prevents accidental partial refresh runs.")

    load_env()
    key = polygon_key()

    universe_csv = Path(args.universe)
    outdir = Path(args.outdir)
    safe_mkdir(outdir)

    tickers = read_universe_tickers(universe_csv)
    now = utc_now()

    print("=== DAILY DATA REFRESH v2 ===")
    print(f"Universe: {universe_csv} ({len(tickers)} tickers)")
    print(f"Outdir:   {outdir}")
    print(f"as_of:    {iso_z(now)}")
    print(f"Policy:   max_stale_days={args.max_stale_days} | min_bars={args.min_bars} | backfill_days={args.backfill_days}")

    rows: List[RefreshRow] = []

    ok = updated = backfilled = no_data = fail = 0
    stale = 0

    for i, t in enumerate(tickers, 1):
        csv_path = outdir / f"{t}.csv"
        err = ""
        status = "OK"

        existing = load_existing_csv(csv_path)
        last_dt = last_date_in_rows(existing) if existing else None
        bar_count = len(existing) if existing else 0

        try:
            # Choose fetch window
            if bar_count < args.min_bars:
                # backfill
                start = (now - timedelta(days=args.backfill_days))
                end = now
                new_rows = fetch_aggs(t, start, end, key)
                if not new_rows:
                    status = "NO_DATA"
                    no_data += 1
                else:
                    idx = rows_to_index(new_rows)
                    merged = list(idx.values())
                    write_csv(csv_path, merged)
                    status = "BACKFILLED"
                    backfilled += 1
                    existing = merged
                    bar_count = len(existing)
                    last_dt = last_date_in_rows(existing)
            else:
                # incremental based on last saved bar, with overlap buffer
                if last_dt:
                    start = (last_dt - timedelta(days=args.incr_buffer_days))
                else:
                    start = (now - timedelta(days=args.backfill_days))
                end = now

                inc = fetch_aggs(t, start, end, key)
                if not inc:
                    status = "OK"
                    ok += 1
                else:
                    base_idx = rows_to_index(existing or [])
                    for r in inc:
                        base_idx[r["date"]] = r
                    merged = list(base_idx.values())
                    write_csv(csv_path, merged)
                    status = "UPDATED"
                    updated += 1
                    existing = merged
                    bar_count = len(existing)
                    last_dt = last_date_in_rows(existing)

        except Exception as e:
            status = "FAIL"
            err = str(e)
            fail += 1

        # freshness
        sdays = days_stale(last_dt, now)
        if sdays is None:
            sdays_s = ""
            last_s = ""
        else:
            sdays_s = str(sdays)
            last_s = last_dt.strftime("%Y-%m-%d") if last_dt else ""
            if sdays > args.max_stale_days:
                stale += 1

        hist_state = classify_history_state(bar_count)

        rows.append(RefreshRow(
            ticker=t,
            status=status,
            bar_count=bar_count,
            last_bar_date=last_s,
            stale_days=sdays_s,
            history_state=hist_state,
            error=err
        ))

        if i % 250 == 0:
            print(f"[{i}/{len(tickers)}] processed")

        time.sleep(float(args.rate_sleep))

    total = len(tickers)
    stale_pct = (stale / total * 100.0) if total else 0.0
    fail_pct = (fail / total * 100.0) if total else 0.0

    # Write reports
    report_dir = repo_root() / "data" / "audit"
    safe_mkdir(report_dir)
    ts = now.strftime("%Y%m%d_%H%M%S")
    csv_report = report_dir / f"refresh_report_{ts}.csv"
    json_report = report_dir / f"refresh_report_{ts}.json"
    json_latest = report_dir / "refresh_report_latest.json"

    # CSV
    with csv_report.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()) if rows else [
            "ticker","status","bar_count","last_bar_date","stale_days","history_state","error"
        ])
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))

    summary = {
        "as_of_utc": iso_z(now),
        "universe": str(universe_csv),
        "outdir": str(outdir),
        "policy": {
            "max_stale_days": args.max_stale_days,
            "min_bars": args.min_bars,
            "backfill_days": args.backfill_days,
            "incr_buffer_days": args.incr_buffer_days
        },
        "counts": {
            "TOTAL": total,
            "OK": ok,
            "UPDATED": updated,
            "BACKFILLED": backfilled,
            "NO_DATA": no_data,
            "FAIL": fail,
            "STALE": stale
        },
        "pct": {
            "stale_pct": round(stale_pct, 2),
            "fail_pct": round(fail_pct, 2)
        },
        "reports": {
            "csv": str(csv_report),
            "json": str(json_report),
            "latest": str(json_latest)
        }
    }

    with json_report.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # update latest pointer
    with json_latest.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("=== REFRESH COMPLETE ===")
    print(json.dumps(summary, indent=2))

    # fail-close gate
    if args.block_if_stale_pct is not None and stale_pct > float(args.block_if_stale_pct):
        print(f"BLOCKED: stale_pct {stale_pct:.2f}% > block_if_stale_pct {float(args.block_if_stale_pct):.2f}%")
        return 2

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
