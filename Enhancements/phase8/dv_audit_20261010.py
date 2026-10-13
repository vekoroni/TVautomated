"""Discovery / Vanguard signal audit on the live 10 Oct 2026 Evening (run 20261010_191314). Read-only.

Checks the screening layers against the governing redesign (DISCOVERY_VANGUARD_REDESIGN_20261007.md, P1-P9) and the
trade-quality register entries that live in these layers (D2, D3, D5, D6, D19):
- what characteristics of the trade each Discovery thesis carries (side, trigger, invalidation, target, timeframe,
  hold, readiness, evidence, contributors) and whether they come from one candidate (P1);
- whether retired legacy producers still write decision-path fields (P4, section 11);
- whether missing values become defaults (P5);
- what happens to UNRESOLVED tickers (P2 / section 6.3: both conditional sides carried and priced);
- what Vanguard publishes as context and whether it changes the thesis (P3, section 8).
Writes dv_audit_20261010.json beside this file.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RUN = "20261010_191314"
RD = ROOT / "data" / "output" / "runs" / RUN
out: dict = {"run": RUN}

disc = pd.read_csv(RD / "discovery" / f"discovery_candidates_ultimate_{RUN}.csv", low_memory=False)
cand = pd.read_csv(RD / "discovery" / f"behavioural_candidates_{RUN}.csv", low_memory=False)
book = pd.read_csv(RD / "intelligence_lab" / f"final_opportunity_book_{RUN}.csv", low_memory=False)
vg = pd.read_csv(RD / "vanguard" / "vanguard_signals.csv", low_memory=False)
U = lambda s: s.astype("string").str.strip().str.upper()
num = lambda s: pd.to_numeric(s, errors="coerce")


def vc(s, k=8):
    return {str(a): int(b) for a, b in U(s).value_counts(dropna=False).head(k).items()}


out["rows"] = {"discovery": len(disc), "candidates": len(cand), "book": len(book), "vanguard": len(vg)}

# 1. What a Discovery thesis carries (per ticker, governing thesis)
side = U(disc["thesis__side"])
out["side"] = vc(disc["thesis__side"])
out["readiness"] = vc(disc["thesis__readiness"])
directed = side.isin(["BULL", "BEAR"])
carry = {}
for c in ("thesis_trigger_level", "thesis_outcome_level", "governed_invalidation_level", "invalidation_eod",
          "thesis_event_timeframe", "thesis_duration_q80_bars", "thesis__last_event", "geometry_justification",
          "trade_lane_hit_holdout", "setup_rate_within_hold", "distance_to_trigger_pct"):
    if c in disc.columns:
        carry[c] = int(disc.loc[directed, c].notna().sum())
out["directed"] = int(directed.sum())
out["directed_fields_filled"] = carry

# 2. One candidate, one story (P1): the governing candidate's own levels on the ticker row and in the book
lv = cand.set_index("Candidate_ID")[["Trigger_Level", "Outcome_Level", "Invalidation_Level", "Direction"]]
lv = lv[~lv.index.duplicated()]
g = disc.loc[directed, ["ticker", "thesis_trigger_candidate_id", "thesis_trigger_level", "thesis_outcome_level",
                        "thesis__side"]].merge(lv, left_on="thesis_trigger_candidate_id", right_index=True, how="left")
close = lambda a, b: (num(a) - num(b)).abs() <= 1e-6 * num(b).abs().clip(lower=1)
out["P1_trigger_equals_candidate"] = [int(close(g["thesis_trigger_level"], g["Trigger_Level"]).sum()), len(g)]
out["P1_target_equals_candidate"] = [int(close(g["thesis_outcome_level"], g["Outcome_Level"]).sum()), len(g)]
out["P1_side_equals_candidate"] = [int((U(g["thesis__side"]) == U(g["Direction"])).sum()), len(g)]
bk = book[["ticker", "target_price", "invalidation_price", "direction", "thesis_trigger_level"]].merge(
    disc[["ticker", "thesis_outcome_level", "thesis__side", "thesis_trigger_level"]], on="ticker", how="inner",
    suffixes=("", "_disc"))
d_bk = U(bk["thesis__side"]).isin(["BULL", "BEAR"])
out["P1_book_target_equals_thesis"] = [int(close(bk.loc[d_bk, "target_price"], bk.loc[d_bk, "thesis_outcome_level"]).sum()),
                                       int(d_bk.sum())]
out["P1_book_trigger_equals_thesis"] = [int(close(bk.loc[d_bk, "thesis_trigger_level"], bk.loc[d_bk, "thesis_trigger_level_disc"]).sum()),
                                        int(d_bk.sum())]
out["P1_book_side_equals_thesis"] = [int((U(bk.loc[d_bk, "direction"]).map({"CALL": "BULL", "PUT": "BEAR"})
                                         == U(bk.loc[d_bk, "thesis__side"])).sum()), int(d_bk.sum())]

# 3. Register D2: a direction label claiming confirmation the pipeline never performed
out["D2_direction_governance_status"] = vc(book["direction_governance_status"])
out["D2_direction_resolution_evidence_count_max"] = float(num(book["direction_resolution_evidence_count"]).max())
out["D2_direction_resolution_path"] = vc(book.get("direction_resolution_path", pd.Series(dtype=str)))
out["D2_direction_validation_state"] = vc(book["direction_validation_state"])

# 4. Legacy producers still writing (P4, section 11) and still read by decisions downstream
legacy = {}
for c in ("wyckoff_mode", "phase", "wyckoff_phase_bucket", "composite_score", "composite_adjusted", "lift_proxy_score",
          "crabel_score", "precor_intent", "trigger_primary", "trigger_quality", "trigger_price", "trigger_price_source",
          "tier", "options_score", "ois_score", "csm_verdict", "tle_verdict"):
    if c in book.columns:
        legacy[c] = {"filled": int(book[c].notna().sum()), "top": vc(book[c], 4)}
out["legacy_fields_in_book"] = legacy
side_b = U(book["direction"]).map({"CALL": "BULL", "PUT": "BEAR"})
mode = U(book["wyckoff_mode"])
contra = ((side_b == "BULL") & mode.str.contains("DISTRIB", na=False)) | ((side_b == "BEAR") & mode.str.contains("ACCUM", na=False))
out["D3_legacy_mode_opposes_thesis_side"] = [int(contra.sum()), int(side_b.notna().sum())]

# 5. D6: GO rows and the legacy trigger category
go = U(book["trigger_go_eligible"]).isin(["TRUE", "1"])
out["D6"] = {"go": int(go.sum()), "go_thesis_trigger_level": int((go & num(book["thesis_trigger_level"]).notna()).sum()),
             "go_last_event": vc(book.loc[go, "thesis__last_event"], 6),
             "go_legacy_trigger_primary_empty": int((go & book["trigger_primary"].isna()).sum()),
             "trigger_price_source_on_go": vc(book.loc[go, "trigger_price_source"], 6)}

# 6. D19: the book's tier (EOD classify_tier on the legacy composite) against the thesis order
out["D19_book_tier"] = vc(book["tier"])
out["D19_tier_x_readiness"] = {f"{a}|{b}": int(n) for (a, b), n in Counter(zip(U(book["tier"]), U(book["thesis__readiness"]))).most_common(12)}

# 7. P2 / 6.3: UNRESOLVED tickers - conditional sides carried and priced?
unres = ~directed
gov_ids = set(disc.loc[unres, "trade_lane_candidate_id"].dropna()) | set(disc.loc[unres, "thesis_trigger_candidate_id"].dropna())
c_unres = cand[cand["Ticker"].isin(disc.loc[unres, "ticker"])]
out["unresolved"] = {
    "tickers": int(unres.sum()),
    "reason": vc(disc.loc[unres, "thesis__unassigned_reason"], 6),
    "candidates_with_adoption_state": vc(c_unres["Adoption_State"], 6),
    "candidates_with_both_conditional_triggers": int((c_unres["Conditional_Bull_Trigger"].notna() & c_unres["Conditional_Bear_Trigger"].notna()).sum()),
    "tickers_with_any_conditional_trigger": int(c_unres.loc[c_unres["Conditional_Bull_Trigger"].notna() | c_unres["Conditional_Bear_Trigger"].notna(), "Ticker"].nunique()),
    "book_rows_with_contract": int(book.loc[book["ticker"].isin(disc.loc[unres, "ticker"]), "contract_symbol"].notna().sum()) if "contract_symbol" in book else None,
}

# 8. Contributors (P6) and missing-is-never-neutral (P5)
contrib = {c: int(cand[c].notna().sum()) for c in cand.columns if c.endswith("_Status") or c.startswith("Distance_To_Trigger")}
out["candidate_contributors"] = contrib
out["candidate_distance_status"] = vc(cand.get("Distance_To_Trigger_ATR_Status", pd.Series(dtype=str)))
designed = ["pre_trigger_momentum", "rel_strength", "volume_participation", "iv_vs_own_history", "option_activity_state"]
out["designed_contributors_absent"] = [c for c in designed if not any(c in x.lower() for x in list(cand.columns) + list(disc.columns))]
out["P5_crabel_percentile_default_50"] = int((num(disc.get("crabel_atr_percentile", pd.Series(dtype=float))) == 50).sum()) if "crabel_atr_percentile" in disc else "field absent"

# 9. Vanguard as context (section 8)
out["vanguard"] = {
    "context_authority": vc(vg.get("layer2__vanguard_context_authority", pd.Series(dtype=str)), 4),
    "context_flags_filled": int(vg.get("layer2__vanguard_context_flags", pd.Series(dtype=str)).notna().sum()),
    "context_flags_top": vc(vg.get("layer2__vanguard_context_flags", pd.Series(dtype=str)), 6),
    "thesis_context_status": vc(vg.get("thesis_context_status", pd.Series(dtype=str)), 6),
    "actuarial_source": vc(vg["actuarial_source"], 4),
    "edge_direction_status": vc(vg.get("edge_direction_status", pd.Series(dtype=str)), 6),
    "n_observations_q": num(vg["n_observations"]).describe().round(0).to_dict(),
    "side_p_close_favourable_10d_basis": vc(vg.get("side_assigned__p_close_favourable_10d_basis", pd.Series(dtype=str)), 4),
    "auction_state": vc(vg.get("layer1__auction_state", pd.Series(dtype=str)), 6),
}
vs = vg.drop(columns=["thesis__side"], errors="ignore").merge(disc[["ticker", "thesis__side"]], on="ticker", how="left") if "ticker" in vg else None
if vs is not None and "edge_direction" in vs:
    ed = U(vs["edge_direction"]).map({"CALL": "BULL", "PUT": "BEAR", "BULL": "BULL", "BEAR": "BEAR", "LONG": "BULL", "SHORT": "BEAR"})
    both = ed.notna() & U(vs["thesis__side"]).isin(["BULL", "BEAR"])
    out["vanguard"]["edge_direction_vs_thesis_side_disagree"] = [int((both & (ed != U(vs["thesis__side"]))).sum()), int(both.sum())]

Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
print(json.dumps(out, indent=1, default=str))
