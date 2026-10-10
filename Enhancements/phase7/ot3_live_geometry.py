"""Output-trust item 3 acceptance on the live 8 Oct book (run 20261008_220129): replay assess_trade_geometry on the
book's own levels (target, invalidation, trigger, readiness, lane hits) with ATR_14 from that run's Discovery file,
and count how many ready (GO) rows the decision-1 rule would hold back. Read-only; writes a JSON receipt beside it.
"""
import collections
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from domain.structure_behaviour.trade_lane import load_lanes  # noqa: E402
from domain.trade_geometry import assess_trade_geometry  # noqa: E402

RUN = "20261008_220129"
RUN_DIR = ROOT / "data" / "output" / "runs" / RUN
book = json.loads((RUN_DIR / "intelligence_lab" / f"final_opportunity_book_{RUN}.json").read_text(encoding="utf-8"))
rows = book if isinstance(book, list) else (book.get("rows") or book.get("opportunities"))
disc = pd.read_csv(RUN_DIR / "discovery" / f"discovery_candidates_ultimate_{RUN}.csv", usecols=["ticker", "ATR_14"])
atr = dict(zip(disc["ticker"].astype(str).str.upper(), disc["ATR_14"]))
table = load_lanes()
n_by = {}
for lane in ("lane_a_trade_now", "lane_b_early_entry"):
    for tf, entries in table[lane].items():
        if isinstance(entries, list):
            for e in entries:
                n_by[(lane[5].upper(), f"{tf}|{e['type']}|{e['state']}")] = e["n"]

reasons = collections.Counter()
states, ready_states, examples = collections.Counter(), collections.Counter(), []
lane_ready = collections.defaultdict(collections.Counter)
for r in rows:
    side = {"CALL": "BULL", "PUT": "BEAR"}.get(str(r.get("direction") or "").upper())
    n = n_by.get((str(r.get("trade_lane") or ""), str(r.get("trade_lane_setup") or "")), [None, None])
    lane = {"trade_lane_hit_original": r.get("trade_lane_hit_original"), "trade_lane_hit_holdout": r.get("trade_lane_hit_holdout"),
            "trade_lane_hit_n_original": n[0], "trade_lane_hit_n_holdout": n[1]}
    g = assess_trade_geometry(side=side, readiness=r.get("thesis__readiness"), session_price=r.get("signal_price"),
                              trigger_level=r.get("thesis_trigger_level"), target=r.get("target_price") or r.get("structural_target"),  # the governing Outcome_Level (P0-04); see note
                              invalidation=r.get("invalidation_price"), early_warning=r.get("early_warning_invalidation_level"),
                              atr_daily=atr.get(str(r.get("ticker")).upper()), lane=lane)
    states[g["geometry_justification"]] += 1
    if g["geometry_justification"] == "NOT_ASSESSABLE" and r.get("thesis__readiness") == "READY_FOR_HUMAN_REVIEW":
        reasons[g["geometry_reason"]] += 1
    if r.get("thesis__readiness") == "READY_FOR_HUMAN_REVIEW":
        ready_states[g["geometry_justification"]] += 1
        lane_ready[str(r.get("trade_lane"))][g["geometry_justification"]] += 1
        if r["ticker"] in ("SMCI", "NEO", "HAFN", "COHR") or (g["geometry_justification"] == "JUSTIFIED" and len(examples) < 8):
            examples.append({k: r.get(k) for k in ("ticker", "trade_lane", "trade_lane_setup")} |
                            {k: g[k] for k in ("geometry_justification", "geometry_reward_atr", "geometry_risk_atr",
                                               "geometry_breakeven_hit_rate", "geometry_measured_hit_rate", "geometry_hit_n")})
out = {"run": RUN, "rows": len(rows), "all_rows": dict(states), "ready_rows": dict(ready_states),
       "ready_by_lane": {k: dict(v) for k, v in lane_ready.items()}, "ready_not_assessable_reasons": dict(reasons), "examples": examples}
(Path(__file__).with_suffix(".json")).write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps(out, indent=1))
