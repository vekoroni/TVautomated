"""Item 10.2 receipt (read-only): the forward calibration state on the books already written.

The C12 store holds no setup labels yet (they travel from the next run's book). This rebuilds them for every book
that already carries trade_lane_setup / trade_lane_side, takes each setup's stated rate and hold from
config/setup_rates_v1.json (the same lookup the trade lane uses), joins the book row to its C12 prediction (run id +
ticker) and its latest underlying outcome, and runs domain.forward_calibration with the governed policy.
Writes Enhancements/phase7/ot10_forward_receipt.json. Never writes to data/.
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

from avshunter.c12_outcome.adapters.storage import DEFAULT_STORE  # noqa: E402
from domain.forward_calibration import forward_calibration, forward_policy, hold_sessions, sessions_elapsed  # noqa: E402
from domain.structure_behaviour.trade_lane import setup_rate_fields  # noqa: E402

RUNS = ROOT / "data" / "output" / "runs"


def main() -> None:
    policy = forward_policy()
    with contextlib.closing(sqlite3.connect(f"file:{DEFAULT_STORE.as_posix()}?mode=ro", uri=True)) as conn:
        ids = {(run, ticker): (pid, session) for pid, run, ticker, session in conn.execute(
            "SELECT DISTINCT s.prediction_id, s.run_id, p.ticker, p.evidence_session FROM prediction_sightings s "
            "JOIN prediction_records p USING (prediction_id)")}
        outcomes = {pid: (state, observed, resolution, as_of) for pid, state, observed, resolution, as_of in conn.execute(
            "SELECT prediction_id, state, sessions_observed, resolution_session, MAX(as_of_session) "
            "FROM underlying_outcomes GROUP BY prediction_id")}
    rows, books, first_seen = [], 0, set()
    for book in sorted(RUNS.glob("*/intelligence_lab/final_opportunity_book_*.csv")):
        frame = pd.read_csv(book, low_memory=False)
        if "trade_lane_setup" not in frame.columns or "trade_lane_side" not in frame.columns:
            continue
        books += 1
        run_id = book.parents[1].name
        for rec in frame.to_dict(orient="records"):
            setup, side = rec.get("trade_lane_setup"), rec.get("trade_lane_side")
            if not isinstance(setup, str) or not isinstance(side, str) or setup.count("|") != 2:
                continue
            tf, signal_type, state = setup.split("|")
            rate = setup_rate_fields({"Timeframe": tf, "Signal_Type": signal_type, "Signal_State": state,
                                      "Direction": side})
            key = ids.get((run_id, str(rec.get("ticker") or "").upper()))
            if rate["setup_rate_within_hold"] is None or key is None or key[0] in first_seen:
                continue
            first_seen.add(key[0])                                   # first issue of each prediction only
            outcome = outcomes.get(key[0])
            if outcome is None:
                continue
            rows.append({"ticker": rec.get("ticker"), "evidence_session": key[1], "setup": setup, "side": side,
                         "stated_rate": rate["setup_rate_within_hold"],
                         "planned_hold_sessions": hold_sessions(setup, rate["setup_hold_bars"], policy),
                         "state": outcome[0], "sessions_observed": outcome[1], "sessions_to_resolution": outcome[2],
                         "sessions_elapsed": sessions_elapsed(key[1], outcome[3])})
    report = forward_calibration(rows, policy=policy)
    totals = {k: sum(s[k] for s in report["setups"].values())
              for k in ("resolved", "hits", "pending", "beyond_scorer_window", "not_scorable")}
    out = {"books_with_setup_labels": books, "predictions": len(rows), "totals": totals,
           "state": report["state"], "setups": report["setups"], "policy": report["policy"]}
    (Path(__file__).with_suffix(".json")).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("books_with_setup_labels", "predictions", "totals", "state")}, indent=1))
    for name, s in sorted(report["setups"].items(), key=lambda kv: -kv[1]["resolved"])[:6]:
        print(f'{name}: {s["state"]} resolved {s["resolved"]} hits {s["hits"]} pending {s["pending"]} '
              f'beyond {s["beyond_scorer_window"]} stated {s["stated_rate"]} observed {s["observed_rate"]}')


if __name__ == "__main__":
    main()
