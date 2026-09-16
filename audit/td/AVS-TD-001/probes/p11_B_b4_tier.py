"""p11_B_b4_tier: REQ-WP1-03 opportunity_tier. Read-only.
For both runs, final_opportunity_book: stored tier distribution by governed_direction; BLOCK reason distribution;
BLOCK rows whose only trigger is spread <= 0.25 (recompute the veto chain from contracts/opportunity_tier.py:101-141
on the stored inputs, with the row's spread read as a FRACTION as v1 documented); offline recompute with the current
derive_tier() on the stored rows and compare tiers. Outputs: p11_B_b4_tier.txt, p11_B_b4_tier_rows.csv"""
import os, sys, math
import pandas as pd, numpy as np
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"; sys.path.insert(0, ROOT)
from contracts.opportunity_tier import derive_tier, _hard_veto, _tier_spread_fraction, SPREAD_TIER_2_MAX, TIER_POLICY_VERSION, _number, _first, _upper, _text
RUNS = ["20260911_115904", "20260910_150045"]
lines, outrows = [], []


def say(s):
    print(s); lines.append(s)


def clean(row):
    return {k: (None if (isinstance(v, float) and math.isnan(v)) else v) for k, v in row.items()}


def veto_chain(row):
    """Re-evaluate each veto condition of contracts/opportunity_tier.py:101-141 independently (ignoring order)."""
    hits = []
    direction = _upper(_first(row, "canonical_direction", "governed_direction", "final_direction", "direction"))
    if direction not in {"CALL", "PUT"}: hits.append("DIRECTION_NOT_RESOLVED")
    if not _text(_first(row, "governed_direction_record_sha256", "direction_lineage_hash")): hits.append("DIRECTION_LINEAGE_HASH_MISSING")
    inv_state = _upper(row.get("invalidation_state")); inv = _number(_first(row, "invalidation_price", "invalidation_spot"))
    if inv_state and inv_state != "AVAILABLE": hits.append("GOVERNED_INVALIDATION_NOT_AVAILABLE")
    if inv is None or inv <= 0: hits.append("GOVERNED_INVALIDATION_MISSING")
    target = _number(_first(row, "structural_target", "target_price", "target_spot"))
    if target is None or target <= 0: hits.append("STRUCTURAL_TARGET_UNRESOLVED")
    elif inv is not None and ((direction == "CALL" and target <= inv) or (direction == "PUT" and target >= inv)): hits.append("TARGET_ON_WRONG_SIDE_OF_INVALIDATION")
    viability = _upper(row.get("execution_viability_state"))
    if viability in {"PATHOLOGICAL_SPREAD", "NO_LIQUIDITY", "INVALID_QUOTE", "EXPIRED_CONTRACT", "STALE_DATA"}: hits.append(f"EXECUTION_VIABILITY_{viability}")
    spread_raw = _number(row.get("spread_pct"))
    if spread_raw is not None and spread_raw > SPREAD_TIER_2_MAX: hits.append("SPREAD_RAW_ABOVE_0.25")
    return hits, spread_raw


for run in RUNS:
    base = os.path.join(ROOT, "data/output/runs", run)
    fob = pd.read_csv(os.path.join(base, "intelligence_lab", f"final_opportunity_book_{run}.csv"), low_memory=False)
    fob["dir"] = fob["governed_direction"].astype(str).str.upper(); fob.loc[~fob["dir"].isin(["CALL", "PUT"]), "dir"] = "OTHER"
    say(f"=== run {run}: final_opportunity_book rows={len(fob)} policy_version={fob['opportunity_tier_policy_version'].dropna().unique().tolist()} current TIER_POLICY_VERSION={TIER_POLICY_VERSION}")
    say("  stored opportunity_tier distribution by direction:")
    ct = pd.crosstab(fob["dir"], fob["opportunity_tier"].fillna("<NA>"))
    for d in ("CALL", "PUT", "OTHER"):
        say(f"    {d}: " + (ct.loc[d].to_dict().__repr__() if d in ct.index else "n=0"))
    blk = fob[fob["opportunity_tier"] == "BLOCK"]
    say(f"  stored BLOCK reasons (all directions): {blk['opportunity_tier_reason'].value_counts().to_dict()}")
    sp = pd.to_numeric(fob["spread_pct"], errors="coerce")
    say(f"  book spread_pct unit characterisation: n={int(sp.notna().sum())} min={sp.min():.4g} max={sp.max():.4g} n<=0.25={int((sp<=0.25).sum())} n(0.25,1]={int(((sp>0.25)&(sp<=1)).sum())} n(1,2]={int(((sp>1)&(sp<=2)).sum())} n>2={int((sp>2).sum())}")
    spb = pd.to_numeric(blk["spread_pct"], errors="coerce")
    say(f"  spread_pct on stored BLOCK rows: n={int(spb.notna().sum())} n<=0.25={int((spb<=0.25).sum())} n(0.25,1]={int(((spb>0.25)&(spb<=1)).sum())} n(1,2]={int(((spb>1)&(spb<=2)).sum())} n>2={int((spb>2).sum())}")
    # only-trigger analysis on stored BLOCK rows with spread reason
    only_spread = {"CALL": 0, "PUT": 0, "OTHER": 0}; only_spread_le025 = {"CALL": 0, "PUT": 0, "OTHER": 0}; spread_reason = {"CALL": 0, "PUT": 0, "OTHER": 0}
    changed = {"CALL": 0, "PUT": 0, "OTHER": 0}; same = {"CALL": 0, "PUT": 0, "OTHER": 0}
    new_ct = {}
    for i, r in fob.iterrows():
        row = clean(r.to_dict()); d = r["dir"]
        hits, spread_raw = veto_chain(row)
        stored_tier = _text(row.get("opportunity_tier")); stored_reason = _text(row.get("opportunity_tier_reason"))
        new_tier, new_reason = derive_tier(row)
        new_ct.setdefault(d, {}); new_ct[d][new_tier] = new_ct[d].get(new_tier, 0) + 1
        if stored_tier == new_tier: same[d] += 1
        else: changed[d] += 1
        if stored_tier == "BLOCK" and stored_reason == "SPREAD_ABOVE_REVIEWABLE_CEILING":
            spread_reason[d] += 1
            others = [h for h in hits if not h.startswith("SPREAD_")]
            if not others:
                only_spread[d] += 1
                if spread_raw is not None and spread_raw <= 0.25: only_spread_le025[d] += 1
        outrows.append({"run": run, "ticker": row.get("ticker"), "dir": d, "stored_tier": stored_tier, "stored_reason": stored_reason, "new_tier": new_tier, "new_reason": new_reason,
                        "spread_pct_raw": spread_raw, "adapter_spread_fraction": _tier_spread_fraction(row), "veto_hits": "|".join(hits), "execution_viability_state": row.get("execution_viability_state"), "monetisability_state": row.get("monetisability_state")})
    say(f"  stored BLOCK with reason SPREAD_ABOVE_REVIEWABLE_CEILING by dir: {spread_reason}")
    say(f"  ...of which NO other veto fires on the row's inputs (spread is the ONLY trigger): {only_spread}")
    say(f"  ...of which the row's raw spread_pct <= 0.25 (i.e. BLOCK on a spread that is <=25% if read as fraction): {only_spread_le025}")
    say(f"  OFFLINE recompute with current derive_tier() on stored rows: tier unchanged={same} changed={changed}")
    for d in ("CALL", "PUT", "OTHER"):
        say(f"    {d} recomputed tier distribution: {new_ct.get(d, {})}")
    sub = pd.DataFrame([o for o in outrows if o["run"] == run])
    ch = sub[sub["stored_tier"] != sub["new_tier"]]
    say(f"  transitions stored->new (top): {ch.groupby(['stored_tier','new_tier']).size().sort_values(ascending=False).head(12).to_dict()}")
    say(f"  new BLOCK reasons: {sub[sub['new_tier']=='BLOCK']['new_reason'].value_counts().head(10).to_dict()}")
    stored_spread_block = sub[(sub["stored_tier"] == "BLOCK") & (sub["stored_reason"] == "SPREAD_ABOVE_REVIEWABLE_CEILING")]
    say(f"  stored spread-BLOCK rows: new tiers = {stored_spread_block['new_tier'].value_counts().to_dict()}; new reasons = {stored_spread_block['new_reason'].value_counts().head(8).to_dict()}")
    say(f"  adapter_spread_fraction on those rows: min={stored_spread_block['adapter_spread_fraction'].min()} max={stored_spread_block['adapter_spread_fraction'].max()} n>0.25={int((stored_spread_block['adapter_spread_fraction']>0.25).sum())} n<=0.25={int((stored_spread_block['adapter_spread_fraction']<=0.25).sum())}")
pd.DataFrame(outrows).to_csv(os.path.join(ROOT, "audit/td/AVS-TD-001/probes/p11_B_b4_tier_rows.csv"), index=False)
open(os.path.join(ROOT, "audit/td/AVS-TD-001/probes/p11_B_b4_tier.txt"), "w", encoding="utf-8").write("\n".join(lines))
