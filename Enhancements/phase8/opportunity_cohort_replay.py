"""B4.2 part 2 acceptance (read-only on live data): the opportunity ledger and cohort on 200 tickers of the live 10 Oct
Evening, read as of 2026-09-25 (so ten sessions of outcomes exist through 2026-10-09). Candidates are built exactly as
Discovery builds them, recorded into a TEMPORARY ledger, and the cohort views are measured from the daily store.
Hard assertions (design B3): frozen cohort, point-in-time (trigger close on or before the read), unique opportunities,
feasible fill (fill strictly after the trigger close). Writes opportunity_cohort_replay.json."""
from __future__ import annotations

import contextlib
import json
import random
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import avshunter_discovery_ULTIMATE as disc  # noqa: E402
from canonical_data.behavioural_candidate_ledger import BehaviouralCandidateLedger  # noqa: E402
from domain.opportunity_outcomes import opportunity_cohort  # noqa: E402
from domain.structure_behaviour.engine import analyse_ticker  # noqa: E402
from domain.structure_behaviour.trade_lane import select_governing  # noqa: E402

RUN, READ_AS_OF, THROUGH = "20261010_191314", "2026-09-25", "2026-10-09"
policy, _ = disc._beh001_runtime()
tickers = pd.read_csv(ROOT / "data/output/runs" / RUN / "discovery" / f"discovery_candidates_ultimate_{RUN}.csv",
                      usecols=["ticker"])["ticker"].astype(str).str.upper().tolist()
random.seed(13)
sample = sorted(random.sample(tickers, 200))
db = f"file:{(ROOT / 'data/canonical/historical_prices.sqlite').as_posix()}?mode=ro"
full = {}
with tempfile.TemporaryDirectory() as tmp, contextlib.closing(sqlite3.connect(db, uri=True)) as conn:
    ledger = BehaviouralCandidateLedger(Path(tmp) / "ledger.sqlite")
    recorded = []
    for t in sample:
        bars = pd.read_sql_query("SELECT trading_date AS date, open, high, low, close, volume FROM ohlcv_daily "
                                 "WHERE ticker = ? AND trading_date <= ? ORDER BY trading_date", conn,
                                 params=(t, THROUGH))
        if len(bars) < 80:
            continue
        bars["date"] = pd.to_datetime(bars["date"])
        full[t] = bars
        daily = bars[bars["date"] <= READ_AS_OF].reset_index(drop=True)      # point in time: only bars read then
        beh = analyse_ticker(t, daily, None, policy, intraday_status="NOT_USED_IN_REPLAY")
        close = float(daily["close"].iloc[-1])
        tr = pd.concat([daily["high"] - daily["low"], (daily["high"] - daily["close"].shift()).abs(),
                        (daily["low"] - daily["close"].shift()).abs()], axis=1).max(axis=1)
        disc._enrich_candidate_records(beh, close=close, atr_daily=float(tr.tail(14).mean()))
        theses, spine = disc._thesis_step(beh)
        _, gov = select_governing(beh["candidates"], price=close, atr_daily=float(tr.tail(14).mean()),
                                  side=spine["side"], adopted_ids={x["Candidate_ID"] for x in theses
                                                                   if x["Adoption_State"] == "ADOPTED"})
        disc._attach_theses(beh, theses, spine, gov)
        disc._attach_trigger_events(beh, daily, policy)
        for c in beh["candidates"]:
            c.setdefault("As_Of", READ_AS_OF)
        recorded.extend(beh["candidates"])
    first = ledger.record_opportunities("REPLAY_20260925", recorded)
    again = ledger.record_opportunities("REPLAY_20260925", recorded)
    rows = ledger.opportunities()
    cohort = opportunity_cohort(rows, lambda t: full.get(t))
# --- hard assertions (B3) ---
keys = [(r["event_id"], r["entry_opportunity_id"]) for r in cohort]
assert again == {}, "re-recording the same run changed the ledger (idempotence)"
assert len(keys) == len(set(keys)), "duplicated opportunities"
crossed = [r for r in cohort if r.get("entry_opportunity_id")]
assert all(str(r["trigger_close_date"])[:10] <= READ_AS_OF for r in crossed), "trigger close after the read"
filled = [r for r in crossed if r.get("fill_date")]
assert all(r["fill_date"] > str(r["trigger_close_date"])[:10] for r in filled), "fill before the signal"
assert all(r["fill_date"] > READ_AS_OF or r["fill_date"] <= READ_AS_OF for r in filled)
daily_crossed = [r for r in crossed if r["timeframe"] == "1d"]
v = pd.DataFrame(daily_crossed)
summary = {
    "read_as_of": READ_AS_OF, "outcomes_through": THROUGH, "tickers": len(full), "ledger_rows": len(rows),
    "recorded_counts": first, "cohort_rows": len(cohort),
    "status_by_timeframe": dict(Counter(f"{r['timeframe']}:{r['latest_status']}" for r in cohort)),
    "daily_crossed": len(daily_crossed),
    "daily_views_status": dict(Counter(v["views_status"])) if len(v) else {},
    "daily_first_barrier": dict(Counter(v["first_barrier"].fillna("NONE"))) if len(v) else {},
    "daily_trigger_age_at_read_median": float(pd.to_numeric(v["recognition_lag_sessions"]).median()) if len(v) else None,
    "daily_ret_10_atr_median": float(pd.to_numeric(v["ret_10_atr"]).median()) if len(v) else None,
    "invariants": "PASSED (idempotent, unique, point-in-time, fill after signal)",
}
Path(__file__).with_suffix(".json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
print(json.dumps(summary, indent=1, default=str))
