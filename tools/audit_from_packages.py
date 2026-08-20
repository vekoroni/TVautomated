#!/usr/bin/env python3
"""
AVSHUNTER Data Integrity Audit (Package-First)

Why this exists:
- Your update process emits per-ticker JSON "packages" that already contain:
  - data_contract.n_daily_bars
  - data_contract.timeseries_source
  - ohlcv_daily.t (date list) in many cases
- Auditing from packages is faster and matches what Vanguard/Core actually consumes.

Outputs:
- data_integrity_from_packages.csv
- data_integrity_from_packages_summary.json

Usage (PowerShell, from repo root):
  .\venv\Scripts\python.exe tools\audit_from_packages.py --packages_dir data\\output\\runs\\20260211_220924\\packages --outdir data\\audit

If you don't have a packages folder, point it at wherever your per-ticker JSON files live.
"""

from __future__ import annotations
import argparse
import csv
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

DATE_FMT = "%Y-%m-%d"

@dataclass
class Row:
    ticker: str
    package_file: str
    package_kind: str
    timeseries_source: str
    timeseries_status: str
    n_daily_bars: int
    last_bar_date: str
    days_old: Optional[int]
    ema200_ready: bool
    status: str
    note: str

def parse_iso_date(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s, DATE_FMT).date()
    except Exception:
        return None

def get_last_bar(payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[int]]:
    """
    Try to infer last bar date and bar count from package content.
    Prefer data_contract.n_daily_bars; confirm via ohlcv_daily.t when present.
    """
    dc = payload.get("data_contract", {}) or {}
    n_bars = dc.get("n_daily_bars")
    last_dt = None

    # Many packages contain ohlcv_daily.t list; take the last item if present.
    ohlcv = payload.get("ohlcv_daily", {}) or {}
    t_list = ohlcv.get("t")
    if isinstance(t_list, list) and t_list:
        last_dt = t_list[-1]
        # if n_bars missing, infer from t_list length
        if n_bars is None:
            n_bars = len(t_list)

    # Fallback: if only CSV exists, we can't read it here (by design).
    return (str(last_dt) if last_dt else None), (int(n_bars) if n_bars is not None else None)

def classify(n_bars: Optional[int], days_old: Optional[int], min_bars: int, max_stale_days: int) -> Tuple[bool, str]:
    if n_bars is None:
        return False, "NO_BARCOUNT"
    if n_bars < min_bars:
        return False, "THIN_HISTORY"
    if days_old is None:
        return True, "OK_NO_DATE"
    if days_old > max_stale_days:
        return False, "STALE"
    return True, "OK"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--packages_dir", required=True, help="Folder containing per-ticker JSON package files")
    ap.add_argument("--outdir", default="data/audit", help="Output folder")
    ap.add_argument("--min_bars", type=int, default=260, help="Bars required for EMA200 readiness (default 260)")
    ap.add_argument("--max_stale_days", type=int, default=5, help="Max days since last bar before STALE (default 5)")
    ap.add_argument("--asof", default=None, help="Override 'today' as YYYY-MM-DD (optional)")
    args = ap.parse_args()

    packages_dir = Path(args.packages_dir)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    asof = parse_iso_date(args.asof) if args.asof else date.today()
    if asof is None:
        raise SystemExit("Invalid --asof date")

    files = sorted(packages_dir.glob("*.json"))
    if not files:
        raise SystemExit(f"No .json files found in: {packages_dir}")

    rows: list[Row] = []
    counts = {
        "TOTAL": 0,
        "OK": 0,
        "OK_NO_DATE": 0,
        "STALE": 0,
        "THIN_HISTORY": 0,
        "NO_BARCOUNT": 0,
        "PARSE_ERROR": 0,
    }

    for fp in files:
        counts["TOTAL"] += 1
        try:
            payload = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:
            counts["PARSE_ERROR"] += 1
            rows.append(Row(
                ticker=fp.stem,
                package_file=str(fp),
                package_kind="",
                timeseries_source="",
                timeseries_status="",
                n_daily_bars=-1,
                last_bar_date="",
                days_old=None,
                ema200_ready=False,
                status="PARSE_ERROR",
                note=str(e)[:200],
            ))
            continue

        ticker = payload.get("ticker") or payload.get("discovery", {}).get("ticker") or fp.stem
        dc = payload.get("data_contract", {}) or {}
        package_kind = dc.get("package_kind", "")
        timeseries_source = dc.get("timeseries_source", "")
        timeseries_status = dc.get("timeseries_status", "")

        last_bar_date, n_bars = get_last_bar(payload)
        last_dt = parse_iso_date(last_bar_date) if last_bar_date else None
        days_old = (asof - last_dt).days if (asof and last_dt) else None

        ok, status = classify(n_bars, days_old, args.min_bars, args.max_stale_days)
        ema200_ready = bool(n_bars is not None and n_bars >= args.min_bars)

        if status in counts:
            counts[status] += 1
        else:
            # Shouldn't happen, but keep it safe.
            counts[status] = counts.get(status, 0) + 1

        note = ""
        if status == "THIN_HISTORY":
            note = f"bars={n_bars} < {args.min_bars}"
        elif status == "STALE":
            note = f"days_old={days_old} > {args.max_stale_days}"
        elif status == "NO_BARCOUNT":
            note = "data_contract.n_daily_bars missing and ohlcv_daily.t absent"

        rows.append(Row(
            ticker=str(ticker),
            package_file=str(fp),
            package_kind=str(package_kind),
            timeseries_source=str(timeseries_source),
            timeseries_status=str(timeseries_status),
            n_daily_bars=int(n_bars) if n_bars is not None else -1,
            last_bar_date=str(last_bar_date or ""),
            days_old=int(days_old) if days_old is not None else None,
            ema200_ready=ema200_ready,
            status=status,
            note=note
        ))

    # Write CSV
    out_csv = outdir / "data_integrity_from_packages.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "ticker","package_file","package_kind","timeseries_source","timeseries_status",
            "n_daily_bars","last_bar_date","days_old","ema200_ready","status","note"
        ])
        for r in rows:
            w.writerow([
                r.ticker, r.package_file, r.package_kind, r.timeseries_source, r.timeseries_status,
                r.n_daily_bars, r.last_bar_date, "" if r.days_old is None else r.days_old,
                "TRUE" if r.ema200_ready else "FALSE", r.status, r.note
            ])

    # Summary JSON
    out_json = outdir / "data_integrity_from_packages_summary.json"
    summary = {
        "asof": asof.strftime(DATE_FMT),
        "min_bars": args.min_bars,
        "max_stale_days": args.max_stale_days,
        "counts": counts,
        "output_csv": str(out_csv),
    }
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Console summary
    total = counts["TOTAL"]
    ok_total = counts.get("OK", 0) + counts.get("OK_NO_DATE", 0)
    ok_pct = (ok_total / total * 100) if total else 0.0
    print("=== PACKAGE-FIRST DATA INTEGRITY AUDIT ===")
    print(json.dumps(summary, indent=2))
    print(f"OK (incl OK_NO_DATE): {ok_total}/{total} ({ok_pct:.1f}%)")
    print(f"CSV: {out_csv}")
    print(f"JSON: {out_json}")

if __name__ == "__main__":
    main()
