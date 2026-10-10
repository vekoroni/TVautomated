"""Phase 2 acceptance on real data (offline replay, read-only; same sample as Phase 1).

Checks: every candidate carries a thesis decision and reason; the ticker side comes from the thesis step
(top-down rule, ACK 8 Oct 2026); one-story rules from Phase 1 still hold; how the side changed against the legacy
daily-primary handoff; intraday alignment labels.
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "Enhancements" / "direction_evidence"))
import avshunter_discovery_ULTIMATE as disc  # noqa: E402
from WyckoffEngine_3101_v2 import WyckoffEngine_3101_v2 as W  # noqa: E402
from dir002_replay import read_bars  # noqa: E402

life = pd.read_parquet(ROOT / "tests/fixtures/phase0/lifecycle.parquet")
rng = np.random.default_rng(8)
sample = {c: list(rng.choice(sorted(life.loc[life.reason_code == c, "ticker"]), 40, replace=False))
          for c in ("INTRADAY_ONLY_UNTESTED", "NO_LIVE_SETUP", "DISCOVERY_SURVIVOR")}
cfg, wy = disc.UltimateConfig(), W()
rows, cands = [], []
for was, ts in sample.items():
    for t in ts:
        b = read_bars(t); b = b[b.date <= "2026-10-05"].reset_index(drop=True)
        s, d = disc._scan_with_lifecycle(t, b, cfg, wy)
        if s is None:
            rows.append({"ticker": t, "was": was, "now": d["reason_code"]}); continue
        cs = s.get("_beh001_candidates") or []
        cands += [{**{k: c.get(k) for k in ("Candidate_ID", "Timeframe", "Adoption_State", "Deciding_Reason",
                                             "Spine_Role", "Thesis_Side", "Levels_Status")}, "ticker": t} for c in cs]
        gov = {c["Candidate_ID"]: c for c in cs}.get(s.get("thesis_trigger_candidate_id"))
        rows.append({"ticker": t, "was": was, "now": "SURVIVE", "side": s.get("thesis__side"),
                     "legacy_side": s.get("legacy_beh_daily_primary_side"), "top_tf": s.get("thesis__top_timeframe"),
                     "reason": s.get("thesis__unassigned_reason"), "intraday": s.get("thesis__intraday_alignment"),
                     "conflicts": s.get("thesis__conflicting_count"), "lane": s.get("trade_lane"),
                     "one_story": gov is not None and abs(float(s.get("structural_target") or np.nan) - float(gov["Outcome_Level"])) < 1e-6
                                  and s.get("trade_lane_candidate_id") == gov["Candidate_ID"]})
r, c = pd.DataFrame(rows), pd.DataFrame(cands)
sv = r[r.now == "SURVIVE"]
out = {"sample": {k: len(v) for k, v in sample.items()},
       "now": r.now.value_counts().to_dict(),
       "candidates": len(c), "candidates_with_decision": int(c.Adoption_State.notna().sum()),
       "adoption": c.Adoption_State.value_counts().to_dict(), "deciding_reason": c.Deciding_Reason.value_counts().to_dict(),
       "spine_roles": c.Spine_Role.value_counts().to_dict(),
       "ticker_side_new": sv.side.value_counts().to_dict(), "ticker_side_legacy": sv.legacy_side.value_counts().to_dict(),
       "side_vs_legacy": pd.crosstab(sv.legacy_side, sv.side).to_dict(),
       "top_timeframe": sv.top_tf.fillna("<none>").value_counts().to_dict(),
       "unresolved_reason": sv.loc[~sv.side.isin(["BULL", "BEAR"]), "reason"].value_counts().to_dict(),
       "intraday_alignment": sv.intraday.value_counts().to_dict(),
       "directed": int(sv.side.isin(["BULL", "BEAR"]).sum()),
       "one_story_directed": f"{int(sv[sv.side.isin(['BULL','BEAR'])].one_story.sum())}/{int(sv.side.isin(['BULL','BEAR']).sum())}"}
(Path(__file__).parent / "p2_replay_acceptance.json").write_text(json.dumps(out, indent=2, default=str))
print(json.dumps(out, indent=2, default=str))
