"""S1 (source-of-truth programme): classify every value / target / time mismatch on the GO rows of a frozen run.

Classes (review register s7, design A2.1):
- LEGITIMATE_DIFFERENT_MEASURE: two fields measure different things; both may be shown if labelled.
- SILENT_SUBSTITUTION: a consumer uses one measure where the decision owner uses another, unlabelled.
- CALCULATION_DEFECT: the value itself is wrong (e.g. valued on a level already passed).
Read-only. Writes s1/mismatch_classification_<run>.csv and prints the counts.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
COLS = ["ticker", "lab_verdict", "direction", "underlying_price", "trade_lane_setup", "thesis_event",
        "thesis_event_timeframe", "thesis_outcome_level", "anticipated_level", "anticipated_level_basis",
        "anticipated_pays_state", "target_price", "monetisability_state", "monetisability_structural_target_spot",
        "ev3_status", "ev3_ev_conservative_return", "time_horizon", "planned_hold_sessions",
        "anticipated_sessions_q50"]


def classify(r: pd.Series) -> dict:
    out = {"ticker": r.ticker}
    lane_tf = str(r.trade_lane_setup or "").split("|")[0]
    out["lineage"] = ("SILENT_SUBSTITUTION" if lane_tf and lane_tf != str(r.thesis_event_timeframe)
                      else "CONSISTENT")
    sign = 1 if str(r.direction).upper() == "CALL" else -1
    lvl, spot = r.thesis_outcome_level, r.underlying_price
    passed = pd.notna(lvl) and pd.notna(spot) and sign * (lvl - spot) <= 0
    out["thesis_level"] = "CALCULATION_DEFECT_LEVEL_ALREADY_PASSED" if passed else (
        "MISSING" if pd.isna(lvl) else "VALID_SIDE")
    # target: range extreme vs anticipated level - different measures; substitution where the range extreme
    # values the contract (monetisability) while the decision values at the anticipated level
    if pd.notna(r.target_price) and pd.notna(r.anticipated_level) and abs(r.target_price / r.anticipated_level - 1) > 0.01:
        out["target"] = "LEGITIMATE_DIFFERENT_MEASURE+SILENT_SUBSTITUTION_IN_MONETISABILITY_AND_STRIKE_FILTER"
    elif pd.isna(r.anticipated_level):
        out["target"] = "OWNER_MISSING"
    else:
        out["target"] = "AGREE"
    # value: anticipated (decision) vs monetisability (expiry intrinsic at range extreme) vs EV3 (prob-weighted net)
    if r.anticipated_pays_state == "PAYS" and r.monetisability_state == "NOT_MONETISABLE":
        out["value"] = "LEGITIMATE_DIFFERENT_MEASURE (intrinsic@range-extreme vs scenario@anticipated); MISLABELLED_AS_VERDICT"
    elif r.anticipated_pays_state in ("NOT_COMPUTED", "NOT_ASSESSED_VOLATILITY_ONLY"):
        out["value"] = "OWNER_MISSING (E12 FLAG; cause per lineage/thesis_level)"
    else:
        out["value"] = "NO_CONFLICT_ON_VERDICT"
    out["ev3"] = ("REJECTED_NO_VALUE" if r.ev3_status == "REJECTED" else
                  "LEGITIMATE_DIFFERENT_MEASURE (prob-weighted net, own target/grid)")
    # time: horizon_bucket is the contract-expiry bucket; hold is evidence q80; move is q50
    out["time"] = ("MISLABELLED (time_horizon = expiry bucket, shown as Move Window)" if pd.notna(r.time_horizon)
                   else "NO_BUCKET")
    return out


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--run-id", required=True)
    r = a.parse_args().run_id
    book = ROOT / "data" / "output" / "runs" / r / "intelligence_lab" / f"final_opportunity_book_{r}.csv"
    have = set(pd.read_csv(book, nrows=0).columns)
    df = pd.read_csv(book, usecols=[c for c in COLS if c in have], low_memory=False)
    for c in COLS:
        if c not in df:
            df[c] = pd.NA
    go = df[df.lab_verdict.isin(["GO", "GO_LIMIT"])]
    res = pd.DataFrame([classify(x) for _, x in go.iterrows()])
    res.to_csv(HERE / f"mismatch_classification_{r}.csv", index=False)
    for c in res.columns[1:]:
        print(c, res[c].value_counts().to_dict())
    return 0


if __name__ == "__main__":
    sys.exit(main())
