"""AVS-RCA-003 Part 2 Steps 2-3: per-ticker cohort + funnel. READ ONLY, no network."""
import glob, json, pathlib, re, sys
import pandas as pd
ROOT = pathlib.Path(".").resolve()
OUT = ROOT / "audit/rca/AVS-RCA-003"
RID = sys.argv[1] if len(sys.argv) > 1 else "20260905_151448"
R = ROOT / "data/output/runs" / RID
def rd(pat):
    f = glob.glob(str(R / pat))
    return pd.read_csv(f[0], low_memory=False) if f else None
def blank(s): return s.isna() | (s.astype(str).str.strip().isin(["", "nan", "None", "NaN", "<NA>"]))
def pick(df, *names):
    for n in names:
        if df is not None and n in df.columns: return df[n]
    return pd.Series(dtype=object)

disc = rd("discovery/discovery_candidates_ultimate_*.csv")
vg   = rd("options/vanguard_signals_enriched_*.csv")
op   = rd("options/options_intelligence_*.csv")
eil  = rd("superbrain/eil_enriched_*.csv")
ed   = rd("morning_validation/eod_dropoff_audit_*.csv")
mc   = rd("morning_validation/morning_candidates_*.csv")
lab  = rd("intelligence_lab/final_opportunity_book_*.csv")

c = pd.DataFrame({"ticker": disc["ticker"].astype(str)}).drop_duplicates("ticker")
c["discovery_selected"] = True
c["disc_tier"] = pick(disc, "tier", "tier_label").reindex(disc.index).values[:len(disc)] if disc is not None else ""
c = c.merge(disc[["ticker"] + [x for x in ("tier","composite_score","direction","sector") if x in disc.columns]]
            .drop_duplicates("ticker").rename(columns={"direction":"disc_direction"}), on="ticker", how="left")

def add(df, cols, prefix):
    global c
    if df is None: return
    keep = ["ticker"] + [x for x in cols if x in df.columns]
    d = df[keep].drop_duplicates("ticker").copy()
    d.columns = ["ticker"] + [prefix + x for x in keep[1:]]
    c = c.merge(d, on="ticker", how="left")

add(vg, ["layer1__auction_state", "layer1__ready_to_trade", "direction"], "vg_")
add(op, ["final_direction", "options_verdict", "economics_state", "economics_reason",
         "invalidation_state", "stand_down_reason", "contract_symbol", "structural_target",
         "contract_spread_pct", "contract_bid", "contract_ask", "contract_dte", "block_severity",
         "options_research_route", "horizon_bucket"], "op_")
add(eil, ["eil_v3_verdict"], "eil_")
add(ed, ["eod_candidate_status", "eod_dropoff_reason", "eod_candidate_reason",
         "phase10_manifest_include", "slate_rank", "capital_permission"], "eod_")
add(lab, ["monetisability_state", "monetisability_reason", "execution_viability_state",
          "final_action", "options_research_permission", "invalidation_price",
          "final_direction", "hold_period"], "lab_")

c["in_vanguard"] = c["vg_layer1__auction_state"].notna()
c["in_options"]  = c["op_options_verdict"].notna()
c["in_eod"]      = c["eod_eod_candidate_status"].notna()
c["in_lab"]      = c["lab_monetisability_state"].notna()
c["direction"]   = c["op_final_direction"].fillna(c.get("vg_direction")).fillna("UNKNOWN")
c["dir3"] = c["direction"].map(lambda d: d if d in ("CALL","PUT") else "OTHER")

def loss_stage(r):
    if not r["in_vanguard"]: return "1_DISCOVERY_TO_VANGUARD"
    if not r["in_options"]:  return "2_VANGUARD_TO_OPTIONS"
    if not r["in_eod"]:      return "3_OPTIONS_TO_EOD"
    if not r["in_lab"]:      return "4_EOD_TO_LAB"
    return "SURVIVED_TO_LAB"
c["loss_stage"] = c.apply(loss_stage, axis=1)

def reason(r):
    s = r["loss_stage"]
    if s == "1_DISCOVERY_TO_VANGUARD": return "VANGUARD_REJECT_OR_NO_ROW"
    if s == "2_VANGUARD_TO_OPTIONS":   return "OPTIONS_STAGE_ABSENT"
    if s == "3_OPTIONS_TO_EOD":        return "EOD_ROW_ABSENT"
    if s == "4_EOD_TO_LAB":
        st = str(r.get("eod_eod_candidate_status") or "")
        if st in ("EOD_NO_OPTIONS_ROUTE", "EOD_STRUCTURAL_BLOCK"):
            dr = str(r.get("eod_eod_dropoff_reason") or "")
            return f"{st}:{dr.split(':')[-1][:44]}" if dr else st
        sd = str(r.get("op_stand_down_reason") or "")
        if sd.startswith("BLOCK_SPREAD"): return "OPTIONS_BLOCKED:BLOCK_SPREAD"
        if "INVALIDATION_MISSING" in sd:  return "OPTIONS_BLOCKED:INVALIDATION_MISSING"
        if "STRUCTURAL_TARGET_UNRESOLVED" in sd: return "OPTIONS_BLOCKED:STRUCTURAL_TARGET_UNRESOLVED"
        if "No contract passed quality gates" in sd: return "OPTIONS_BLOCKED:NO_CONTRACT_PASSED_QUALITY_GATES"
        if "No governed long CALL/PUT direction" in sd: return "OPTIONS_BLOCKED:NO_GOVERNED_DIRECTION"
        if "CONTRACT_REVIEWABLE_SPREAD" in sd: return "OPTIONS_BLOCKED:CONTRACT_REVIEWABLE_SPREAD"
        return f"EOD_NOT_IN_MANIFEST:{st or 'UNKNOWN'}"
    return "SURVIVED"
c["loss_reason"] = c.apply(reason, axis=1)
c.to_csv(OUT / f"02_cohort_{RID}.csv", index=False)

print(f"=== COHORT {RID}: {len(c)} discovery-selected tickers ===")
print("\n--- funnel by stage (three-direction) ---")
rows = []
stages = [("discovery_selected", c["discovery_selected"]), ("in_vanguard", c["in_vanguard"]),
          ("in_options", c["in_options"]), ("in_eod", c["in_eod"]), ("in_lab", c["in_lab"])]
prev = None
for name, mask in stages:
    n = int(mask.sum())
    d = c.loc[mask, "dir3"].value_counts().to_dict()
    delta = "" if prev is None else f"  (-{prev - n})"
    print(f"  {name:22s} {n:5d}{delta:12s} CALL={d.get('CALL',0):4d} PUT={d.get('PUT',0):4d} OTHER={d.get('OTHER',0):4d}")
    rows.append({"boundary": name, "survivors": n, "call": d.get("CALL",0),
                 "put": d.get("PUT",0), "other": d.get("OTHER",0),
                 "lost_vs_prev": (prev - n) if prev is not None else 0})
    prev = n
pd.DataFrame(rows).to_csv(OUT / f"03_funnel_{RID}.csv", index=False)

print("\n--- losses by reason (top 20) ---")
lost = c[c["loss_stage"] != "SURVIVED_TO_LAB"]
g = lost.groupby("loss_reason")["dir3"].value_counts().unstack(fill_value=0)
g["TOTAL"] = g.sum(axis=1)
g = g.sort_values("TOTAL", ascending=False)
print(g.head(20).to_string())
print(f"\ntotal lost: {len(lost)}  survived: {int(c['in_lab'].sum())}  sum={len(lost)+int(c['in_lab'].sum())} of {len(c)}")
print("RECONCILES:", len(lost) + int(c["in_lab"].sum()) == len(c))
