"""B4.2 acceptance (read-only): event ids, status and clocks on a sample of 300 tickers (+ SOFI) of the live 10 Oct
Evening, through 2026-10-09, built exactly as Discovery builds them (engine reading -> thesis step -> governing setup
-> trigger events -> clocks). Independent check: for every directed 1d thesis the first close beyond its trigger is
recomputed from the raw daily closes and compared with Trigger_Close_Date. Writes event_clocks_replay.json."""
from __future__ import annotations

import contextlib
import json
import math
import random
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import avshunter_discovery_ULTIMATE as disc  # noqa: E402
from canonical_data.intraday_bars import CompletedIntradayIndex  # noqa: E402
from domain.structure_behaviour.engine import analyse_ticker  # noqa: E402
from domain.structure_behaviour.trade_lane import select_governing  # noqa: E402

RUN, THROUGH = "20261010_191314", "2026-10-09"
policy, _ = disc._beh001_runtime()
sessions_n = max(int(tf.get("sessions") or 0) for tf in policy["timeframes"].values())
tickers = pd.read_csv(ROOT / "data/output/runs" / RUN / "discovery" / f"discovery_candidates_ultimate_{RUN}.csv",
                      usecols=["ticker"])["ticker"].astype(str).str.upper().tolist()
random.seed(12)
sample = sorted(set(random.sample(tickers, 300)) | {"SOFI"})
index = CompletedIntradayIndex.from_registry(ROOT / "data/canonical/control_plane.sqlite")
status_all, status_gov, ready_x_status, ages = Counter(), Counter(), Counter(), []
checks = Counter()
mismatches, examples = [], []
with contextlib.closing(sqlite3.connect(
        f"file:{(ROOT / 'data/canonical/historical_prices.sqlite').as_posix()}?mode=ro", uri=True)) as conn:
    for t in sample:
        daily = pd.read_sql_query("SELECT trading_date AS date, open, high, low, close, volume FROM ohlcv_daily "
                                  "WHERE ticker = ? AND trading_date <= ? ORDER BY trading_date", conn,
                                  params=(t, THROUGH))
        if len(daily) < 60:
            continue
        daily["date"] = pd.to_datetime(daily["date"])
        intraday, st = index.bars_for(t, through_session=THROUGH, sessions=sessions_n,
                                      expected_sessions=[str(d.date()) for d in daily["date"].tail(sessions_n + 5)])
        beh = analyse_ticker(t, daily, intraday, policy, intraday_status=st)
        close = float(daily["close"].iloc[-1])
        tr = pd.concat([daily["high"] - daily["low"], (daily["high"] - daily["close"].shift()).abs(),
                        (daily["low"] - daily["close"].shift()).abs()], axis=1).max(axis=1)
        atr = float(tr.tail(14).mean())
        disc._enrich_candidate_records(beh, close=close, atr_daily=atr)
        theses, spine = disc._thesis_step(beh)
        _, governing = select_governing(beh["candidates"], price=close, atr_daily=atr, side=spine["side"],
                                        adopted_ids={x["Candidate_ID"] for x in theses
                                                     if x["Adoption_State"] == "ADOPTED"})
        disc._attach_theses(beh, theses, spine, governing)
        disc._attach_trigger_events(beh, daily, policy)
        dates = daily["date"].dt.strftime("%Y-%m-%d").tolist()
        closes = daily["close"].tolist()
        for c in beh["candidates"]:
            status_all[f"{c.get('Timeframe')}:{c.get('Event_Status')}"] += 1
            # independent recomputation of the first close beyond the trigger (1d, directed, measured)
            if c.get("Timeframe") == "1d" and c.get("Thesis_Side") in {"BULL", "BEAR"} \
                    and c.get("Events_Status") == "MEASURED" and c.get("Trigger_Level"):
                lvl = float(c["Trigger_Level"])
                origin = str(c["Candidate_ID"]).rsplit("|", 1)[-1][:10]
                up = c["Thesis_Side"] == "BULL"
                start = next((i for i, d in enumerate(dates) if d >= origin), max(1, len(dates) - 20))
                first = next((dates[i] for i in range(max(1, start), len(dates))
                              if (math.log(closes[i]) > math.log(lvl)) == up and closes[i] != lvl), None)
                checks["checked"] += 1
                if first == c.get("Trigger_Close_Date") or (c.get("Event_Status") == "FAILED"
                                                           and c.get("Trigger_Close_Date") is None):
                    checks["agree"] += 1
                else:
                    mismatches.append({"ticker": t, "candidate": c["Candidate_ID"], "engine": c.get("Trigger_Close_Date"),
                                       "recomputed": first, "status": c.get("Event_Status")})
        gov = next((c for c in beh["candidates"] if governing and c.get("Candidate_ID") == governing.get("Candidate_ID")), {})
        row = disc._event_clock_fields(gov, last_bar_date=THROUGH, read_at=None)
        status_gov[row["thesis__event_status"]] += 1
        if gov:
            ready_x_status[f"{gov.get('Readiness')} x {row['thesis__event_status']}"] += 1
            if row["thesis__trigger_age_sessions"] is not None:
                ages.append(row["thesis__trigger_age_sessions"])
            q = row["thesis__policy_qualified_at"]
            if q and row["thesis__trigger_close_date"]:
                checks["ready_with_close"] += 1
                checks["qualified_not_before_close"] += int(str(q)[:10] >= str(row["thesis__trigger_close_date"])[:10])
                # sessions between the first close and the legacy readiness (what waiting costs, in sessions)
                checks["wait_sessions_total"] += sum(1 for d in dates if row["thesis__trigger_close_date"] < d <= str(q)[:10])
        if t == "SOFI" or (gov and len(examples) < 6):
            examples.append({"ticker": t, **{k: v for k, v in row.items() if v is not None}})
ages_s = pd.Series(ages, dtype=float)
out = {"run": RUN, "through": THROUGH, "sample": len(sample),
       "candidate_event_status": dict(sorted(status_all.items())),
       "governing_event_status": dict(status_gov), "legacy_readiness_x_event_status": dict(ready_x_status),
       "trigger_age_sessions": {"n": int(len(ages_s)), "median": float(ages_s.median()) if len(ages_s) else None,
                                "le_1": int((ages_s <= 1).sum()), "le_3": int((ages_s <= 3).sum())},
       "checks": dict(checks), "mismatches": mismatches[:20], "examples": examples}
Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
print(json.dumps({k: v for k, v in out.items() if k != "examples"}, indent=1, default=str))
