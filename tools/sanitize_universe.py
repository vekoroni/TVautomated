# -*- coding: utf-8 -*-
r"""
Universe Sanitation v2 (schema-preserving)

- Filters out invalid / foreign / contaminated tickers (e.g., *.V).
- De-duplicates by ticker.
- PRESERVES ALL OTHER COLUMNS (sector, sector_etf, industry, etc.).
- Writes:
    <outdir>/clean_universe.csv
    <outdir>/bad_universe.csv

Usage:
  .\venv\Scripts\python.exe tools\sanitize_universe.py --input data\universe\universe_latest.csv --outdir data\universe
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple

TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,15}$")

FOREIGN_SUFFIXES = [
    ".V",   # TSXV
]

def norm_ticker(raw: str) -> str:
    return (raw or "").strip().upper()

def reject_reason(t: str) -> str | None:
    if not t:
        return "EMPTY"
    for suf in FOREIGN_SUFFIXES:
        if t.endswith(suf):
            return f"FOREIGN_SUFFIX_{suf}"
    if not TICKER_RE.fullmatch(t):
        return "INVALID_TICKER"
    return None

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Input universe CSV with at least 'ticker' column")
    ap.add_argument("--outdir", required=True, help="Output directory")
    args = ap.parse_args()

    inp = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    clean_path = outdir / "clean_universe.csv"
    bad_path = outdir / "bad_universe.csv"

    if not inp.exists():
        print(f"ERROR: input not found: {inp}")
        return 2

    seen = set()
    total = 0
    kept = 0
    rejected = 0

    with inp.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            print("ERROR: empty CSV / no header row")
            return 2
        if "ticker" not in [h.strip() for h in reader.fieldnames]:
            print("ERROR: CSV must include a 'ticker' column")
            return 2

        # Preserve original schema order; ensure 'ticker' is first
        fields = [h for h in reader.fieldnames]
        if "ticker" in fields:
            fields = ["ticker"] + [h for h in fields if h != "ticker"]

        # bad file schema: original fields + reject_reason + raw_input
        bad_fields = fields + ["reject_reason", "raw_input"]

        with clean_path.open("w", encoding="utf-8", newline="") as f_clean, \
             bad_path.open("w", encoding="utf-8", newline="") as f_bad:
            w_clean = csv.DictWriter(f_clean, fieldnames=fields)
            w_bad = csv.DictWriter(f_bad, fieldnames=bad_fields)
            w_clean.writeheader()
            w_bad.writeheader()

            for row in reader:
                total += 1
                raw = row.get("ticker", "")
                t = norm_ticker(raw)
                rr = reject_reason(t)

                if rr is not None:
                    rejected += 1
                    bad_row = {k: row.get(k, "") for k in fields}
                    bad_row["ticker"] = t or raw
                    bad_row["reject_reason"] = rr
                    bad_row["raw_input"] = raw
                    w_bad.writerow(bad_row)
                    continue

                if t in seen:
                    # de-dupe silently (keep first)
                    continue

                seen.add(t)
                row_out = {k: row.get(k, "") for k in fields}
                row_out["ticker"] = t
                w_clean.writerow(row_out)
                kept += 1

    print("=== UNIVERSE SANITATION COMPLETE (v2 schema-preserving) ===")
    print(f"Total: {total}")
    print(f"Clean: {kept} ({(kept/total*100):.1f}%)" if total else "Clean: 0")
    print(f"Rejected: {rejected} ({(rejected/total*100):.1f}%)" if total else "Rejected: 0")
    print(f"Output: {clean_path}, {bad_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
