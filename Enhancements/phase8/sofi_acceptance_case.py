"""SOFI acceptance case: the BEH-001 engine against ACK's Soul of the Chart labelled examples. Read-only.

Teaching case (OneDrive/Soul_of_the_Chart_Labelled_Training_Examples.pdf), as of the close on 30 Sep 2026 (15.72):
- Daily (campaign): sellers in control, Phase E markdown, SOW -> LPSY continuation; contraction is not accumulation.
- 60m (swing): failed spike to 17.96, local balance gives way, SOW-like decline, weak recovery (LPSY), compression
  under a falling ceiling; bearish continuation candidate.
- 15m (setup): downside expansion breaks balance, recoveries near 16.18 fail below 16.60-16.70, lower balance under a
  falling VWAP; seller absorption breakdown candidate.
- 5m (trigger and response): 16.17 rejection, failed recoveries below the ceiling, local contraction, then a downside
  expansion bar to 15.71 on a volume spike; follow-through unobserved.
Runs the engine exactly as Discovery does (canonical daily bars, the completed 5-minute intraday index) through
2026-09-30 and writes sofi_acceptance_case.json beside this file.
"""
from __future__ import annotations

import contextlib
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from canonical_data.intraday_bars import CompletedIntradayIndex  # noqa: E402
from domain.structure_behaviour.engine import analyse_ticker  # noqa: E402
from domain.structure_behaviour.policy import load_policy  # noqa: E402

TICKER, AS_OF = "SOFI", "2026-09-30"
policy = load_policy()
with contextlib.closing(sqlite3.connect(f"file:{(ROOT / 'data/canonical/historical_prices.sqlite').as_posix()}?mode=ro", uri=True)) as conn:
    daily = pd.read_sql_query("SELECT trading_date AS date, open, high, low, close, volume FROM ohlcv_daily "
                              "WHERE ticker = ? AND trading_date <= ? ORDER BY trading_date", conn, params=(TICKER, AS_OF))
daily["date"] = pd.to_datetime(daily["date"])
index = CompletedIntradayIndex.from_registry(ROOT / "data" / "canonical" / "control_plane.sqlite")
sessions = max(int(tf.get("sessions", 0)) for tf in policy["timeframes"].values())
intraday, status = index.bars_for(TICKER, through_session=AS_OF, sessions=sessions,
                                  expected_sessions=[str(d.date()) for d in daily["date"].tail(sessions + 5)])
beh = analyse_ticker(TICKER, daily, intraday, policy, intraday_status=status)

KEEP = ("Status", "Data_Status", "Wyckoff_Phase", "Phase_Confidence", "Phase_Transition", "Local_Phase",
        "Structural_Context", "Controller", "Control_Quality", "SOT_State", "Crabel_Compression", "Movement_Maturity",
        "Control_Transfer_Condition", "Direction_Status")
out = {"ticker": TICKER, "as_of": AS_OF, "daily_bars": len(daily), "last_daily_close": float(daily["close"].iloc[-1]),
       "intraday_status": status, "intraday_bars": 0 if intraday is None else len(intraday),
       "handoff": {k: v for k, v in beh["handoff"].items() if k != "primary"},
       "handoff_primary": None if not beh["handoff"].get("primary") else
       {k: beh["handoff"]["primary"].get(k) for k in ("Timeframe", "Signal_Type", "Signal_State", "Direction",
                                                       "Trigger_Level", "Invalidation_Level", "Outcome_Level")},
       "timeframes": {}}
for tf, r in beh["readings"].items():
    cands = [{k: c.get(k) for k in ("Structure_Scope", "Signal_Type", "Signal_State", "Direction", "Wyckoff_Event",
                                    "Trigger_Level", "Invalidation_Level", "Outcome_Level", "Age_Bars", "Warning")}
             for c in r.get("candidates", [])]
    comp = {k: r.get(k) for k in r if "ompress" in k}
    out["timeframes"][tf] = {**{k: r.get(k) for k in KEEP if k in r}, "compression": comp,
                             "candidates": [c for c in cands if c["Signal_State"] in ("DETECTED", "ACTIVATED", "CONFIRMED", "MONITOR", "FAILED")]}
Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
print(json.dumps(out, indent=1, default=str))
