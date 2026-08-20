#!/usr/bin/env python3
"""
Universe Sector Enrichment (Polygon)
Adds 'sector' and 'industry' columns to universe file.
"""

import argparse
import csv
import json
import os
import time
from pathlib import Path

import requests

def polygon_lookup(api_key, ticker):
    url = f"https://api.polygon.io/v3/reference/tickers/{ticker}"
    r = requests.get(url, params={"apiKey": api_key}, timeout=20)
    if r.status_code != 200:
        return None, None, f"HTTP_{r.status_code}"
    payload = r.json().get("results", {})
    sector = payload.get("sector")
    industry = payload.get("industry") or payload.get("sic_description")
    return sector, industry, "OK"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--outdir", default="data/universe")
    ap.add_argument("--api_key", default=None)
    ap.add_argument("--rate_sleep", type=float, default=0.25)
    args = ap.parse_args()

    api_key = args.api_key or os.getenv("POLYGON_API_KEY")
    if not api_key:
        raise SystemExit("Missing POLYGON_API_KEY")

    in_path = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    with in_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        ticker_col = fieldnames[0]
        rows = list(reader)

    if "sector" not in fieldnames:
        fieldnames.append("sector")
    if "industry" not in fieldnames:
        fieldnames.append("industry")

    failures = []
    ok_count = 0

    for i, row in enumerate(rows, start=1):
        ticker = row.get(ticker_col, "").strip().upper()
        if not ticker:
            failures.append({"ticker": "", "reason": "EMPTY"})
            continue

        sector, industry, status = polygon_lookup(api_key, ticker)

        row["sector"] = sector or ""
        row["industry"] = industry or ""

        if status == "OK" and (sector or industry):
            ok_count += 1
        else:
            failures.append({"ticker": ticker, "reason": status})

        if i % 250 == 0:
            print(f"[{i}/{len(rows)}] Processed")

        time.sleep(args.rate_sleep)

    enriched_path = outdir / (in_path.stem + "__with_sector.csv")
    failures_path = outdir / "sector_enrichment_failures.csv"
    summary_path = outdir / "sector_enrichment_run_summary.json"

    with enriched_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    with failures_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "reason"])
        w.writeheader()
        for fr in failures:
            w.writerow(fr)

    summary = {
        "total": len(rows),
        "success": ok_count,
        "failures": len(failures),
        "output": str(enriched_path)
    }

    summary_path.write_text(json.dumps(summary, indent=2))

    print("=== SECTOR ENRICHMENT COMPLETE ===")
    print(summary)

if __name__ == "__main__":
    main()
