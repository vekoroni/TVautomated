"""Phase 0 data fix (ACK approved 7 Oct 2026): backfill daily history for tickers seeded from the 90-day cache.

Root cause (P0_DISCOVERY_RECALL_LOSSES.md): ~1,270 tickers start on 2026-05-26 with ~92 bars, below the
behavioural engine's 120-daily / 60-weekly / 36-monthly minimum, so they were never read and were dropped as
INTRADAY_ONLY_UNTESTED / NO_LIVE_SETUP.

Source: Polygon grouped-daily bars already on disk (Enhancements/direction_evidence/survivorship/grouped_daily,
adjusted=true, 2021-10-08 onward). No provider calls.
Rules:
  - Scope: tickers whose first stored POLYGON_SPLIT_ADJUSTED bar is on or after 2026-05-01.
  - Only dates BEFORE the ticker's first stored date are written (inserts only; no existing bar is touched).
  - Only the contiguous block that ends at the first stored date is used (a gap of more than 5 missing sessions
    stops the walk back), so an older, unrelated use of the same symbol is not attached.
  - Seam check: on the overlapping dates (>= 10 required), the grouped close must match the stored close
    (median |ratio - 1| <= 0.5%, max <= 2%). Otherwise the ticker is skipped with the reason recorded.
  - Writes go through canonical_data.historical_prices.HistoricalPriceDatabase.ingest (batches, hashes,
    provenance). A full SQLite backup is taken first. A receipt is written per ticker.
Usage: python p0_backfill_daily_history.py            (dry run, no writes)
       python p0_backfill_daily_history.py --execute  (backup, then write)
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from canonical_data.historical_prices import HistoricalPriceDatabase  # noqa: E402

DB = ROOT / "data" / "canonical" / "historical_prices.sqlite"
GROUPED = ROOT / "Enhancements" / "direction_evidence" / "survivorship" / "grouped_daily"
RECEIPTS = Path(__file__).resolve().parent / "backfill_receipts"
ADJ = "POLYGON_SPLIT_ADJUSTED"
SCOPE_FIRST_DATE = "2026-05-01"
MAX_GAP_SESSIONS = 5
SEAM_MIN_OVERLAP, SEAM_MEDIAN_TOL, SEAM_MAX_TOL = 10, 0.005, 0.02
RUN_ID = "P0_HISTORY_BACKFILL_20261007"


def coverage() -> pd.DataFrame:
    with sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True) as c:
        return pd.read_sql_query(
            "SELECT ticker, COUNT(*) n, MIN(trading_date) first, MAX(trading_date) last FROM ohlcv_daily "
            "WHERE adjustment_convention=? GROUP BY ticker", c, params=[ADJ])


def stored_closes(tickers) -> pd.DataFrame:
    with sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True) as c:
        marks = ",".join("?" * len(tickers))
        return pd.read_sql_query(
            f"SELECT ticker, trading_date, close FROM ohlcv_daily WHERE adjustment_convention=? AND ticker IN ({marks})",
            c, params=[ADJ, *tickers])


def grouped_for(tickers: set) -> pd.DataFrame:
    frames = []
    for f in sorted(GROUPED.glob("*.parquet")):
        t = pq.read_table(f)
        if "ticker" not in t.column_names or not t.num_rows:  # e.g. an empty session file (2025-01-09)
            continue
        df = t.to_pandas()
        df = df[df["ticker"].isin(tickers)]
        if len(df):
            frames.append(df)
    g = pd.concat(frames, ignore_index=True)
    g["d"] = pd.to_datetime(g["date"]).dt.strftime("%Y-%m-%d")
    return g


def plan(cov: pd.DataFrame, g: pd.DataFrame, stored: pd.DataFrame, sessions: list[str]) -> list[dict]:
    pos = {d: i for i, d in enumerate(sessions)}
    out = []
    gb = dict(tuple(g.groupby("ticker")))
    sb = dict(tuple(stored.groupby("ticker")))
    for r in cov.itertuples():
        rec = {"ticker": r.ticker, "stored_rows_before": int(r.n), "stored_first": r.first, "stored_last": r.last}
        gt = gb.get(r.ticker)
        if gt is None or gt.empty:
            out.append({**rec, "action": "SKIP", "reason": "NO_GROUPED_HISTORY"})
            continue
        gt = gt.sort_values("d").drop_duplicates("d", keep="last")
        # seam check on overlapping dates
        st = sb[r.ticker].set_index("trading_date")["close"]
        ov = gt[gt["d"].isin(st.index)]
        ratio = (ov["close"].to_numpy(float) / st.reindex(ov["d"]).to_numpy(float)) - 1.0
        ratio = ratio[np.isfinite(ratio)]
        rec.update({"seam_overlap": int(len(ratio)),
                    "seam_median_abs": float(np.median(np.abs(ratio))) if len(ratio) else None,
                    "seam_max_abs": float(np.max(np.abs(ratio))) if len(ratio) else None})
        if len(ratio) < SEAM_MIN_OVERLAP:
            out.append({**rec, "action": "SKIP", "reason": "SEAM_TOO_FEW_OVERLAP"})
            continue
        if rec["seam_median_abs"] > SEAM_MEDIAN_TOL or rec["seam_max_abs"] > SEAM_MAX_TOL:
            out.append({**rec, "action": "SKIP", "reason": "SEAM_MISMATCH"})
            continue
        # contiguous block ending at the first stored date
        before = gt[gt["d"] < r.first]
        if before.empty:
            out.append({**rec, "action": "SKIP", "reason": "NO_EARLIER_HISTORY"})
            continue
        idx = [pos.get(d) for d in before["d"]]
        keep, prev = [], pos.get(r.first)
        for d, i in sorted(zip(before["d"], idx), key=lambda x: x[0], reverse=True):
            if i is None or prev is None or prev - i - 1 > MAX_GAP_SESSIONS:
                break
            keep.append(d)
            prev = i
        if not keep:
            out.append({**rec, "action": "SKIP", "reason": "GAP_AT_SEAM"})
            continue
        rows = before[before["d"].isin(keep)]
        out.append({**rec, "action": "BACKFILL", "rows_to_add": int(len(rows)), "add_first": min(keep),
                    "add_last": max(keep), "_rows": rows[["d", "open", "high", "low", "close", "volume"]]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    cov = coverage()
    scope = cov[cov["first"] >= SCOPE_FIRST_DATE].reset_index(drop=True)
    print(f"scope tickers {len(scope)}", flush=True)
    g = grouped_for(set(scope["ticker"]))
    with sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True) as c:
        sessions = [r[0] for r in c.execute("SELECT trading_date FROM ohlcv_daily WHERE ticker='SPY' AND "
                                            "adjustment_convention=? ORDER BY trading_date", [ADJ])]
    sessions = sorted(set(sessions) | set(g["d"]))
    stored = stored_closes(list(scope["ticker"]))
    p = plan(scope, g, stored, sessions)
    summary = {"scope": len(scope), "backfill": sum(x["action"] == "BACKFILL" for x in p),
               "rows_to_add": int(sum(x.get("rows_to_add", 0) for x in p)),
               "skips": pd.Series([x["reason"] for x in p if x["action"] == "SKIP"]).value_counts().to_dict()}
    new_n = [x["stored_rows_before"] + x.get("rows_to_add", 0) for x in p]
    summary["tickers_reaching_260_bars"] = int(sum(n >= 260 for n in new_n))
    summary["tickers_reaching_120_bars"] = int(sum(n >= 120 for n in new_n))
    print(json.dumps(summary, indent=2), flush=True)
    RECEIPTS.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    receipt = {"run_id": RUN_ID, "mode": "EXECUTE" if a.execute else "DRY_RUN", "at_utc": stamp, "db": str(DB),
               "source": str(GROUPED), "rules": {"scope_first_date": SCOPE_FIRST_DATE, "max_gap_sessions": MAX_GAP_SESSIONS,
                                                 "seam": [SEAM_MIN_OVERLAP, SEAM_MEDIAN_TOL, SEAM_MAX_TOL]},
               "summary": summary, "tickers": [{k: v for k, v in x.items() if k != "_rows"} for x in p]}
    if a.execute:
        backup = DB.parent / "backups" / f"historical_prices.pre_history_backfill_{stamp}.sqlite"
        with sqlite3.connect(DB) as src, sqlite3.connect(backup) as dst:
            src.backup(dst)
        receipt["backup"] = str(backup)
        print(f"backup -> {backup}", flush=True)
        db = HistoricalPriceDatabase(DB)
        fetched = datetime.fromtimestamp(max(f.stat().st_mtime for f in GROUPED.glob("*.parquet")), timezone.utc)
        results = {}
        for x in p:
            if x["action"] != "BACKFILL":
                continue
            rows = x["_rows"].rename(columns={"d": "date"})
            res = db.ingest(x["ticker"], rows, provider="POLYGON", source_kind="GROUPED_DAILY_BACKFILL",
                            source_run_id=RUN_ID, fetched_at=fetched)
            results[x["ticker"]] = {"batch_id": res.batch_id, "inserted": res.inserted_rows,
                                    "revised": res.revised_rows, "unchanged": res.unchanged_rows,
                                    "rejected": res.rejected_rows}
        receipt["ingest"] = results
        receipt["ingest_totals"] = {k: int(sum(v[k] for v in results.values()))
                                    for k in ("inserted", "revised", "unchanged", "rejected")}
        after = coverage().set_index("ticker")
        receipt["after"] = {"tickers_ge_260": int((after.loc[after.index.isin(scope["ticker"]), "n"] >= 260).sum()),
                            "tickers_ge_120": int((after.loc[after.index.isin(scope["ticker"]), "n"] >= 120).sum())}
        print(json.dumps({"ingest_totals": receipt["ingest_totals"], "after": receipt["after"]}, indent=2))
    out = RECEIPTS / f"daily_history_backfill_{receipt['mode'].lower()}_{stamp}.json"
    out.write_text(json.dumps(receipt, indent=1, default=str))
    print(f"receipt -> {out}")


if __name__ == "__main__":
    main()
