"""Step 2 acceptance (read-only): observed / inferred / unresolved labels on a sample of 200 tickers of the live
10 Oct Evening, through 2026-10-09, read exactly as Discovery reads them (canonical daily bars, the step-1 intraday
index and its reconciliation). Writes basis_labels_replay.json beside this file."""
from __future__ import annotations

import contextlib
import json
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from canonical_data.intraday_bars import CompletedIntradayIndex, reconcile_with_daily  # noqa: E402
from domain.structure_behaviour.engine import analyse_ticker  # noqa: E402
from domain.structure_behaviour.policy import load_policy  # noqa: E402

RUN, THROUGH = "20261010_191314", "2026-10-09"
policy = load_policy()
rec = json.loads((ROOT / "config/governed_constants_v1.json").read_text(encoding="utf-8"))["intraday_completeness"]
sessions = max(int(tf.get("sessions") or 0) for tf in policy["timeframes"].values())
tickers = pd.read_csv(ROOT / "data/output/runs" / RUN / "discovery" / f"discovery_candidates_ultimate_{RUN}.csv",
                      usecols=["ticker"])["ticker"].astype(str).str.upper().tolist()
random.seed(11)
sample = random.sample(tickers, 200)
index = CompletedIntradayIndex.from_registry(ROOT / "data/canonical/control_plane.sqlite")
labels = defaultdict(Counter)
caps, statuses, events = Counter(), Counter(), Counter()
with contextlib.closing(sqlite3.connect(f"file:{(ROOT / 'data/canonical/historical_prices.sqlite').as_posix()}?mode=ro", uri=True)) as conn:
    for t in sample:
        daily = pd.read_sql_query("SELECT trading_date AS date, open, high, low, close, volume FROM ohlcv_daily "
                                  "WHERE ticker = ? AND trading_date <= ? ORDER BY trading_date", conn, params=(t, THROUGH))
        if len(daily) < 60:
            continue
        daily["date"] = pd.to_datetime(daily["date"])
        intraday, status = index.bars_for(t, through_session=THROUGH, sessions=sessions,
                                          expected_sessions=[str(d.date()) for d in daily["date"].tail(sessions + 5)])
        if intraday is not None and status == "OK":
            recent = sorted(daily["date"].dt.date.astype(str))[-int(rec["reconciliation_window_sessions"]):]
            bad = reconcile_with_daily(intraday, daily, high_low_tolerance=rec["high_low_tolerance"],
                                       close_tolerance=rec["close_tolerance"])
            if any(b["session"] in recent for b in bad):
                status = "INTRADAY_DISAGREES_WITH_DAILY"
        statuses[status] += 1
        beh = analyse_ticker(t, daily, intraday, policy, intraday_status=status)
        for tf, r in beh["readings"].items():
            for k in ("Controller_Basis", "Phase_Basis", "Transition_Basis", "Compression_Basis"):
                labels[f"{tf}:{k}"][r.get(k)] += 1
            if r.get("Basis_Cap"):
                caps[f"{tf}:{r['Basis_Cap']}"] += 1
            for c in r.get("candidates") or []:
                events[f"{tf}:{c.get('Event_Basis')}"] += 1
out = {"run": RUN, "through": THROUGH, "sample": len(sample), "intraday_status": dict(statuses),
       "labels": {k: dict(v) for k, v in sorted(labels.items())}, "caps": dict(caps),
       "event_basis": dict(sorted(events.items()))}
Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps(out, indent=1))
