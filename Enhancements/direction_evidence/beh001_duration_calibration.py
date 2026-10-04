"""BEH-001 duration evidence: holdout calibration (ACK 3 Oct 2026, anticipated-move design §4 / §9 step 3).

Fixed before results are read:
- Evidence: built on the ORIGINAL 500-ticker panel (eval_v4, refreshed bars to 2026-10-01).
- Test set: per-candidate records of the HOLDOUT panel (500 tickers never used to design a rule), scored with the
  same C12 passage rules. Each record takes the evidence group production would choose (attach_duration: the
  age-bucket group if published, else the all-ages group; INSUFFICIENT_SAMPLE groups are skipped).
- Timing: among holdout records that reached the event, the share with time_bars <= q50 and <= q80 of their
  group. Pass: pooled q50 share in [0.40, 0.60] and q80 share in [0.70, 0.90].
- Probability: predicted P(event before invalidation | resolved) = p_event / (p_event + p_invalidation) against the
  observed EVENT share among resolved holdout records, in predicted bands of 0.1. Pass: |predicted - observed|
  <= 0.05 in every band with >= 200 resolved records.
- Also reported (not a criterion): the same checks by test (ACTIVATION / OUTCOME), by timeframe, and by period
  (cuts before / from 2024-09-01), to show where calibration holds.
Usage: beh001_duration_calibration.py <evidence.json> <holdout_records.jsonl> <out.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


def choose(index, rec):
    key = (rec["timeframe"], rec["scope"], rec["signal_type"], rec["direction"], rec["test"])
    for age in (rec["age_bucket"], "ALL"):
        g = index.get(key + (age,))
        if g is not None and g.get("status") != "INSUFFICIENT_SAMPLE":
            return g
    return None


def timing(df):
    ev = df[df.cause.eq("EVENT") & df.q50.notna() & df.q80.notna()]
    return {"events": int(len(ev)), "share_le_q50": round(float((ev.time_bars <= ev.q50).mean()), 4) if len(ev) else None,
            "share_le_q80": round(float((ev.time_bars <= ev.q80).mean()), 4) if len(ev) else None}


def probability(df):
    res = df[df.cause.isin(["EVENT", "INVALIDATION"])].copy()
    res["band"] = (res.pred // 0.1 * 0.1).round(1)
    out = []
    for band, g in res.groupby("band"):
        out.append({"band": float(band), "n": int(len(g)), "predicted": round(float(g.pred.mean()), 4),
                    "observed": round(float(g.cause.eq("EVENT").mean()), 4)})
    return out


def main():
    evidence = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    index = {(g["timeframe"], g["scope"], g["signal_type"], g["direction"], g["test"], g["age_bucket"]): g
             for g in evidence["groups"]}
    rows = []
    for line in open(sys.argv[2], encoding="utf-8"):
        rec = json.loads(line)
        g = choose(index, rec)
        if g is None:
            continue
        pe, pi = g.get("p_event_at_limit"), g.get("p_invalidation_at_limit")
        rows.append({**rec, "q50": g.get("remaining_bars_q50"), "q80": g.get("remaining_bars_q80"),
                     "pred": (pe / (pe + pi)) if pe is not None and pi is not None and (pe + pi) > 0 else None})
    df = pd.DataFrame(rows)
    df = df[df.pred.notna()]
    total = sum(1 for _ in open(sys.argv[2], encoding="utf-8"))
    pooled_t = timing(df)
    bands = probability(df)
    big = [b for b in bands if b["n"] >= 200]
    report = {
        "evidence": sys.argv[1], "holdout_records": total, "matched_to_published_group": int(len(df)),
        "timing_pooled": pooled_t, "probability_bands": bands,
        "pass_timing": bool(pooled_t["share_le_q50"] is not None and 0.40 <= pooled_t["share_le_q50"] <= 0.60
                            and 0.70 <= pooled_t["share_le_q80"] <= 0.90),
        "pass_probability": bool(big) and all(abs(b["predicted"] - b["observed"]) <= 0.05 for b in big),
        "by_test": {k: {**timing(g), "bands": probability(g)} for k, g in df.groupby("test")},
        "by_timeframe": {k: timing(g) for k, g in df.groupby("timeframe")},
        "by_period": {k: timing(g) for k, g in df.groupby(df.cut < "2024-09-01")},
    }
    report["pass"] = report["pass_timing"] and report["pass_probability"]
    Path(sys.argv[3]).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("holdout_records", "matched_to_published_group", "timing_pooled",
                                              "pass_timing", "pass_probability", "pass")}, indent=1))
    print("bands:", json.dumps(bands))
    print("by_test timing:", json.dumps({k: {kk: v[kk] for kk in ("events", "share_le_q50", "share_le_q80")}
                                         for k, v in report["by_test"].items()}))
    print("by_timeframe:", json.dumps(report["by_timeframe"]))
    print("by_period (True = before 2024-09-01):", json.dumps(report["by_period"]))


if __name__ == "__main__":
    main()
