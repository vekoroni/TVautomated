"""Step 1 acceptance (read-only, no provider call): the Discovery intraday index before / after F1-F2 and the F5
reconciliation, on every ticker of the live 10 Oct Evening (through session 2026-10-09). Writes
intraday_index_replay.json beside this file.
"""
from __future__ import annotations

import contextlib
import json
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from canonical_data.intraday_bars import CompletedIntradayIndex, reconcile_with_daily  # noqa: E402
from domain.structure_behaviour.policy import load_policy  # noqa: E402

RUN, THROUGH = "20261010_191314", "2026-10-09"
policy = load_policy()
sessions = max(int(tf.get("sessions") or 0) for tf in policy["timeframes"].values())
tickers = pd.read_csv(ROOT / "data/output/runs" / RUN / "discovery" / f"discovery_candidates_ultimate_{RUN}.csv",
                      usecols=["ticker", "beh__intraday_status"])
old_status = Counter(tickers["beh__intraday_status"].fillna("NA"))
with contextlib.closing(sqlite3.connect(f"file:{(ROOT / 'data/canonical/historical_prices.sqlite').as_posix()}?mode=ro", uri=True)) as conn:
    daily = pd.read_sql_query("SELECT ticker, trading_date AS date, open, high, low, close, volume FROM ohlcv_daily "
                              "WHERE trading_date >= '2026-08-01' AND trading_date <= ?", conn, params=(THROUGH,))
daily["ticker"] = daily["ticker"].str.upper()
by_daily = {t: g for t, g in daily.groupby("ticker")}
index = CompletedIntradayIndex.from_registry(ROOT / "data" / "canonical" / "control_plane.sqlite")
new_status, coverage, recon, recon_fields, started = Counter(), Counter(), Counter(), Counter(), time.time()
for t in tickers["ticker"].astype(str).str.upper():
    d = by_daily.get(t)
    expected = None if d is None else [str(x)[:10] for x in sorted(d["date"])][-(sessions + 5):]
    bars, status = index.bars_for(t, through_session=THROUGH, sessions=sessions, expected_sessions=expected)
    new_status[status] += 1
    coverage[index.coverage(t, THROUGH) or "NO_RECORD"] += 1
    if bars is not None and d is not None and status == "OK":
        bad = reconcile_with_daily(bars, d, tolerance=0.005)
        recon["DISAGREES" if bad else "AGREES"] += 1
        for b in bad:
            recon_fields["|".join(b["fields"])] += 1
out = {"run": RUN, "through": THROUGH, "window_sessions": sessions, "tickers": len(tickers),
       "status_before": dict(old_status), "status_after_no_fetch": dict(new_status),
       "latest_session_coverage": dict(coverage), "reconciliation_on_ok": dict(recon),
       "disagreeing_fields": dict(recon_fields.most_common(8)), "seconds": round(time.time() - started)}
Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps(out, indent=1))
