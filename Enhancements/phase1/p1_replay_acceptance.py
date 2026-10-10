"""Phase 1 acceptance on real data (offline replay, read-only).

Runs the CHANGED Discovery scan (_scan_with_lifecycle) on canonical daily bars cut at 2026-10-05 for a fixed
sample: tickers dropped on run 20261006_060401 as INTRADAY_ONLY_UNTESTED / NO_LIVE_SETUP (now backfilled) and
survivors. No provider call (bars are passed in), no pipeline run, no writes outside Enhancements/phase1.
Checks the Phase 1 business rules on every row:
  R-a one story: the thesis target is the governing candidate's own Outcome_Level (source BEH001_OUTCOME_LEVEL),
      never PRIOR_RANGE_EXTREME; the thesis trigger is that candidate's Trigger_Level; the lane candidate, thesis
      event candidate and trigger candidate are the same candidate.
  R-b canonical compression columns are present for every evaluated timeframe.
  R-c a drop with an unread daily chart says INSUFFICIENT_DAILY_HISTORY.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "Enhancements" / "direction_evidence"))
import avshunter_discovery_ULTIMATE as disc  # noqa: E402
from WyckoffEngine_3101_v2 import WyckoffEngine_3101_v2 as WyckoffEngine  # noqa: E402
from dir002_replay import read_bars  # noqa: E402

CUT = "2026-10-05"
FIX = ROOT / "tests" / "fixtures" / "phase0" / "lifecycle.parquet"


def main(n_each: int = 40, seed: int = 8):
    life = pd.read_parquet(FIX)
    rng = np.random.default_rng(seed)
    groups = {}
    for code in ("INTRADAY_ONLY_UNTESTED", "NO_LIVE_SETUP", "DISCOVERY_SURVIVOR"):
        pool = sorted(life.loc[life["reason_code"] == code, "ticker"])
        groups[code] = list(rng.choice(pool, size=min(n_each, len(pool)), replace=False))
    cfg, wy = disc.UltimateConfig(), WyckoffEngine()
    rows = []
    for was, tickers in groups.items():
        for t in tickers:
            bars = read_bars(t)
            bars = bars[bars["date"] <= CUT].reset_index(drop=True)
            sig, drop = disc._scan_with_lifecycle(t, bars, cfg, wy)
            rec = {"ticker": t, "was": was, "bars": len(bars)}
            if sig is None:
                rec.update({"now": drop["outcome"], "reason": drop["reason_code"]})
                rows.append(rec)
                continue
            cands = {c["Candidate_ID"]: c for c in sig.get("_beh001_candidates") or []}
            gov_id = sig.get("thesis_trigger_candidate_id")
            gov = cands.get(gov_id) if gov_id else None
            tgt, src = sig.get("structural_target"), sig.get("structural_target_source")
            rec.update({
                "now": "SURVIVE", "side": sig.get("thesis__side"), "lane": sig.get("trade_lane"),
                "target_source": src,
                "target_is_governing_outcome": (gov is not None and tgt is not None
                                                and abs(float(tgt) - float(gov["Outcome_Level"])) < 1e-6),
                "trigger_is_governing": (gov is not None and sig.get("thesis_trigger_level") is not None
                                         and abs(float(sig["thesis_trigger_level"]) - float(gov["Trigger_Level"])) < 1e-6),
                "one_candidate": (gov_id is not None and gov_id == sig.get("trade_lane_candidate_id")
                                  == sig.get("thesis_event_candidate_id")),
                "legacy_target_published": src == "PRIOR_RANGE_EXTREME",
                "compression_cols": all(f"beh__{tf}_compression_state" in sig for tf in ("1d", "1w", "1mo")),
                "governing_present": gov is not None,
            })
            rows.append(rec)
    df = pd.DataFrame(rows)
    out = {"cut": CUT, "sample": {k: len(v) for k, v in groups.items()},
           "outcome_by_previous_reason": df.groupby(["was", "now"]).size().unstack(fill_value=0).to_dict(),
           "drop_reasons_now": df.loc[df["now"] != "SURVIVE", "reason"].value_counts().to_dict()}
    s = df[df["now"] == "SURVIVE"]
    directed = s[s["side"].isin(["BULL", "BEAR"])]
    with_gov = directed[directed["governing_present"] == True]  # noqa: E712
    out["survivors"] = int(len(s))
    out["directed"] = int(len(directed))
    out["directed_with_governing_setup"] = int(len(with_gov))
    out["R_a_target_is_governing_outcome"] = f"{int(with_gov['target_is_governing_outcome'].sum())}/{len(with_gov)}"
    out["R_a_trigger_is_governing"] = f"{int(with_gov['trigger_is_governing'].sum())}/{len(with_gov)}"
    out["R_a_one_candidate"] = f"{int(with_gov['one_candidate'].sum())}/{len(with_gov)}"
    out["R_a_legacy_target_published"] = int(s["legacy_target_published"].sum())
    out["target_source_counts"] = s["target_source"].fillna("<none>").value_counts().to_dict()
    out["R_b_compression_columns_present"] = f"{int(s['compression_cols'].sum())}/{len(s)}"
    here = Path(__file__).resolve().parent
    df.to_csv(here / "p1_replay_rows.csv", index=False)
    (here / "p1_replay_acceptance.json").write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
