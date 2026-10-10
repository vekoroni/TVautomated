"""This week's tradeable Morning signals (runs 20261005_072245 and 20261006_060401) and what the stock did next.

Read-only: run outputs and the canonical daily bars. A row is a signal the Morning released for human review
(verdict GO, or permission HUMAN_APPROVAL_REQUIRED / GO / GO_LIMIT). Outcome is measured from the signal session's
close in the trade direction: next-session close, latest close, best and worst close since, and whether a close beyond
the recorded invalidation happened (first date).
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Enhancements" / "direction_evidence"))
from dir002_replay import read_bars  # noqa: E402

RUNS = {"20261005_072245": "2026-10-02", "20261006_060401": "2026-10-05"}
KEEP = ["ticker", "lab_verdict", "verdict", "execution_permission", "morning_execution_permission", "governed_direction",
        "contract_symbol", "signal_price", "invalidation_price", "structural_target", "anticipated_level",
        "trade_lane", "trade_lane_setup", "thesis_category"]
rows = []
for run, session in RUNS.items():
    m = pd.read_csv(ROOT / f"data/output/runs/{run}/morning_validation/morning_validated_trades_{run}.csv",
                    low_memory=False)
    released = m[(m["verdict"].astype(str).str.upper() == "GO")
                 | m["execution_permission"].astype(str).str.upper().isin({"HUMAN_APPROVAL_REQUIRED", "GO", "GO_LIMIT"})]
    # The Morning file does not carry the levels; the Lab book of the same run does (what the card showed).
    book = pd.read_csv(ROOT / f"data/output/runs/{run}/intelligence_lab/final_opportunity_book_{run}.csv",
                       low_memory=False, usecols=lambda c: c in {"ticker", "invalidation_price", "anticipated_level",
                                                                 "lab_verdict", "signal_price"})
    book = book.drop_duplicates("ticker").set_index("ticker")
    for r in released.to_dict("records"):
        if r.get("ticker") in book.index:
            for k in ("invalidation_price", "anticipated_level", "lab_verdict"):
                if pd.isna(pd.to_numeric(r.get(k), errors="coerce")) if k != "lab_verdict" else not r.get(k):
                    r[k] = book.at[r["ticker"], k]
        rec = {"run": run, "signal_session": session, **{k: r.get(k) for k in KEEP if k in r}}
        side = 1.0 if str(r.get("governed_direction") or "").upper() == "CALL" else -1.0
        try:
            bars = read_bars(str(r["ticker"]))
        except Exception as error:  # read-only report: record, never hide
            rec["outcome_status"] = f"NO_BARS:{type(error).__name__}"
            rows.append(rec)
            continue
        base = bars[bars.date <= session]
        after = bars[bars.date > session].reset_index(drop=True)
        if base.empty or after.empty:
            rec["outcome_status"] = "NO_LATER_BARS"
            rows.append(rec)
            continue
        c0 = float(base.close.iloc[-1])
        moves = side * (after.close.astype(float) / c0 - 1) * 100
        inv = pd.to_numeric(r.get("invalidation_price"), errors="coerce")
        hit = None
        if pd.notna(inv):
            beyond = after[(after.close.astype(float) > inv) if side < 0 else (after.close.astype(float) < inv)]
            hit = beyond.date.iloc[0] if not beyond.empty else None
        rec.update({"outcome_status": "MEASURED", "signal_close": c0,
                    "next_close_move_pct": round(float(moves.iloc[0]), 2),
                    "latest_close_date": after.date.iloc[-1], "latest_move_pct": round(float(moves.iloc[-1]), 2),
                    "best_close_move_pct": round(float(moves.max()), 2),
                    "worst_close_move_pct": round(float(moves.min()), 2),
                    "invalidation_distance_pct": round(abs(float(inv) / c0 - 1) * 100, 2) if pd.notna(inv) else None,
                    "invalidation_closed_beyond_on": hit})
        rows.append(rec)
out = pd.DataFrame(rows)
path = Path(__file__).parent / "WEEK_SIGNALS_OUTCOMES_20261008.csv"
out.to_csv(path, index=False)
meas = out[out.outcome_status == "MEASURED"]
print(f"rows {len(out)} measured {len(meas)} -> {path}")
for run, g in meas.groupby("run"):
    print(run, "signals", len(g), "| latest move in trade direction: mean %.2f%%, median %.2f%%, up %d / down %d"
          % (g.latest_move_pct.mean(), g.latest_move_pct.median(), (g.latest_move_pct > 0).sum(),
             (g.latest_move_pct <= 0).sum()),
          "| invalidation closed beyond:", int(g.invalidation_closed_beyond_on.notna().sum()),
          "| median stop distance %.2f%%" % g.invalidation_distance_pct.median())
