#!/usr/bin/env python3
"""Read-only probe: can the standalone options tool reuse the option chains the evening run already fetched? (12 Oct 2026)

Opens both databases read-only (no locks taken for writing, nothing changed) and answers four questions:
  1. Does the canonical registry (data/canonical/control_plane.sqlite) hold OPTION_CHAIN datasets for recent sessions,
     where are their files, and what scope (strikes/expiries) did the run fetch?
  2. How many MarketData requests did Friday's run make for option chains (api_request_ledger)?
  3. Which quote dates does Phantom (data/phantom/phantom_history.db, table chain_snapshots) hold?
  4. For the names in the newest decision ledger's focus list: does Phantom have that session's chain, how many
     contracts, which expiries and strikes - i.e. could the tool read them instead of calling MarketData?

Run from the repo root when no Phantom backfill is writing (it only reads, but avoids competing for the disk):
    venv\\Scripts\\python.exe data\\scratch\\workaround\\probe_chain_reuse.py
Writes data/scratch/workaround/probe_chain_reuse_<timestamp>.json and prints a summary. No keys are touched.
"""
from __future__ import annotations

import glob
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

CONTROL = Path("data") / "canonical" / "control_plane.sqlite"
PHANTOM = Path("data") / "phantom" / "phantom_history.db"
WORK = Path("data") / "scratch" / "workaround"


def ro(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def q(con, sql, args=()):
    t = time.time()
    rows = [dict(r) for r in con.execute(sql, args).fetchall()]
    return rows, round(time.time() - t, 1)


def main():
    out = {"probe_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    hits = sorted(h for h in glob.glob(str(WORK / "decision_ledger_*.csv")) if not h.endswith(("_outcomes.csv", "_summary.csv")))
    L = pd.read_csv(hits[-1]) if hits else pd.DataFrame()
    focus = L[L["focus_v3"].astype(str).str.upper() == "TRUE"] if len(L) else L
    session = str(L["evidence_as_of"].dropna().iloc[0])[:10] if "evidence_as_of" in L and len(L) else None
    run = str(L["source_run"].dropna().iloc[0]) if "source_run" in L and len(L) else None
    out["ledger"] = {"file": hits[-1] if hits else None, "focus_names": int(focus["ticker"].nunique()) if len(focus) else 0,
                     "evidence_session": session, "source_run": run}

    if CONTROL.exists():
        con = ro(CONTROL)
        r, s = q(con, "SELECT session_date, COUNT(*) AS datasets, COUNT(DISTINCT instrument_id) AS tickers, "
                      "SUM(completeness_status='COMPLETE') AS complete FROM dataset_registry "
                      "WHERE dataset_type='OPTION_CHAIN' AND session_date >= date('now','-14 day') GROUP BY session_date ORDER BY session_date")
        out["control_option_chain_by_session"] = r
        out["control_query_seconds"] = s
        if session:
            r, _ = q(con, "SELECT instrument_id, provider, completeness_status, storage_uri, scope_json, source_run_id "
                          "FROM dataset_registry WHERE dataset_type='OPTION_CHAIN' AND session_date=? LIMIT 3", (session,))
            out["control_samples"] = r
            for x in r:
                x["file_exists"] = Path(x["storage_uri"]).is_file()
        if run:
            r, _ = q(con, "SELECT dataset_type, resolution, COUNT(*) AS requests, SUM(physical_request_count) AS physical "
                          "FROM api_request_ledger WHERE run_id=? GROUP BY dataset_type, resolution ORDER BY requests DESC", (run,))
            out["control_api_requests_for_run"] = r
        con.close()
    else:
        out["control"] = "NOT_FOUND"

    if PHANTOM.exists():
        con = ro(PHANTOM)
        out["phantom_chain_columns"] = [c["name"] for c in q(con, "PRAGMA table_info(chain_snapshots)")[0]]
        r, _ = q(con, "SELECT DISTINCT quote_date FROM chain_snapshots WHERE ticker='SPY' ORDER BY quote_date DESC LIMIT 8")
        out["phantom_recent_quote_dates_SPY"] = [x["quote_date"] for x in r]
        if session and len(focus):
            rows, t0 = [], time.time()
            for tk in sorted(focus["ticker"].astype(str).str.upper().unique()):
                r, _ = q(con, "SELECT COUNT(*) AS contracts, COUNT(DISTINCT expiration_ts) AS expiries, MIN(strike) AS kmin, "
                              "MAX(strike) AS kmax, MIN(dte) AS dte_min, MAX(dte) AS dte_max, MAX(updated_ts) AS last_update, "
                              "MAX(source) AS source, SUM(bid > 0) AS with_bid FROM chain_snapshots WHERE ticker=? AND quote_date=?",
                         (tk, session))
                rows.append({"ticker": tk, **r[0]})
            cov = pd.DataFrame(rows)
            have = cov[cov["contracts"] > 0]
            out["phantom_focus_coverage"] = {
                "session": session, "names": len(cov), "with_chain": len(have),
                "median_contracts": float(have["contracts"].median()) if len(have) else None,
                "median_expiries": float(have["expiries"].median()) if len(have) else None,
                "median_max_dte": float(have["dte_max"].median()) if len(have) else None,
                "sources": have["source"].value_counts().to_dict() if len(have) else {},
                "missing_examples": cov.loc[cov["contracts"] == 0, "ticker"].head(25).tolist(),
                "seconds": round(time.time() - t0, 1)}
        con.close()
    else:
        out["phantom"] = "NOT_FOUND"

    WORK.mkdir(parents=True, exist_ok=True)
    dest = WORK / f"probe_chain_reuse_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    dest.write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k not in ("control_samples",)}, indent=1, default=str)[:4000])
    print("saved:", dest)


if __name__ == "__main__":
    main()
