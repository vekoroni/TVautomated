"""p15_F_05: F4 data cross-tab (macro fields vs direction/verdict/permission), F5 capacity fields present and their values,
F6 structure_evidence_state presence + offline derivation on stored inputs. Read-only."""
import sys, json
sys.dont_write_bytecode = True
from pathlib import Path
import pandas as pd
ROOT=Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"); sys.path.insert(0,str(ROOT)); RUN="20260911_115904"; R=ROOT/"data/output/runs"/RUN; OUT=ROOT/"audit/td/AVS-TD-001/probes"
from domain.structure_evidence import derive_structure_evidence
def dirb(s):
    s=str(s or "").upper().strip(); return s if s in ("CALL","PUT") else "OTHER"
res={}
mv_cols={"ticker","governed_direction","morning_execution_permission","morning_verdict","gate_verdict","final_verdict","macro_size_multiplier_advisory","ticker_sector_alignment","macro_filter_advisory","regime_changed","check_macro_permission_pass","check_macro_permission_reason","sb_position_size_pct","horizon_size_multiplier","contract_ask","contract_symbol","selected_contract_symbol","preferred_contract_symbol"}
mv=pd.read_csv(R/f"morning_validation/morning_validated_trades_{RUN}.csv", dtype=str, keep_default_na=False, usecols=lambda c: c in mv_cols)
mv["_dir"]=mv["governed_direction"].map(dirb)
res["mv_columns_found"]=sorted(mv.columns)
xt={}
decision=[c for c in ("morning_execution_permission","morning_verdict","gate_verdict","final_verdict") if c in mv.columns]
for macro in [c for c in ("macro_size_multiplier_advisory","ticker_sector_alignment","macro_filter_advisory","regime_changed","check_macro_permission_pass") if c in mv.columns]:
    for dec in decision+["_dir"]:
        xt[f"{macro} x {dec}"]={str(k):v for k,v in pd.crosstab(mv[macro],mv[dec]).stack().to_dict().items()}
res["F4_crosstabs_morning_validated"]=xt
fb_cols={"ticker","governed_direction","lab_verdict","morning_execution_permission","position_size_display","hidden_state_label","phase","trigger_primary","usmi_sector_alignment","macro_sector_alignment","structure_evidence_state","contract_ask","contracts_at_budget","horizon_cap_advisory","direction_factor_advisory"}
fb=pd.read_csv(R/f"intelligence_lab/final_opportunity_book_{RUN}.csv", dtype=str, keep_default_na=False, usecols=lambda c: c in fb_cols)
fb["_dir"]=fb["governed_direction"].map(dirb)
res["fb_columns_found"]=sorted(fb.columns)
res["F4_final_lab_verdict_x_dir"]={str(k):v for k,v in pd.crosstab(fb["lab_verdict"],fb["_dir"]).stack().to_dict().items()}
res["F4_macro_field_cardinality_final"]={c:int(fb[c].nunique()) for c in ("usmi_sector_alignment","macro_sector_alignment") if c in fb.columns}
res["F5_position_size_display_by_dir"]={d:fb.loc[fb["_dir"]==d,"position_size_display"].value_counts().to_dict() for d in ("CALL","PUT","OTHER")}
res["F5_sb_position_size_pct_nonempty_by_dir"]={d:int((mv.loc[mv["_dir"]==d,"sb_position_size_pct"].str.strip()!="").sum()) for d in ("CALL","PUT","OTHER")} if "sb_position_size_pct" in mv.columns else "ABSENT"
res["F5_sb_position_size_pct_values"]=mv["sb_position_size_pct"].value_counts().head(8).to_dict() if "sb_position_size_pct" in mv.columns else "ABSENT"
res["F5_macro_size_multiplier_advisory_values"]=mv["macro_size_multiplier_advisory"].value_counts().head(8).to_dict() if "macro_size_multiplier_advisory" in mv.columns else "ABSENT"
res["F5_contracts_at_budget_present"]="contracts_at_budget" in fb.columns
res["F5_horizon_cap_or_direction_factor_present"]=[c for c in ("horizon_cap_advisory","direction_factor_advisory") if c in fb.columns]
# pse_suggested_contracts in execution_v3_5
ex_cols=list(pd.read_csv(R/f"execution/execution_v3_5_{RUN}.csv", nrows=0).columns)
ex_use=[c for c in ("ticker","governed_direction","pse_suggested_contracts","contract_ask","tier_size_multiplier","eil_size_multiplier") if c in ex_cols]
ex=pd.read_csv(R/f"execution/execution_v3_5_{RUN}.csv", dtype=str, keep_default_na=False, usecols=ex_use, engine="python")
ex["_dir"]=ex["governed_direction"].map(dirb)
res["F5_execution_v3_5_pse_suggested_contracts_by_dir"]={d:ex.loc[ex["_dir"]==d,"pse_suggested_contracts"].value_counts().head(6).to_dict() for d in ("CALL","PUT","OTHER")} if "pse_suggested_contracts" in ex.columns else "ABSENT"
# F6: offline derivation on the stored final book inputs
der=fb.apply(lambda r: derive_structure_evidence(hidden_state_label=r.get("hidden_state_label"),phase=r.get("phase"),trigger_primary=r.get("trigger_primary"))["structure_evidence_state"],axis=1)
fb["_ses_offline"]=der
res["F6_structure_evidence_state_in_final_book"]="structure_evidence_state" in fb.columns
res["F6_offline_state_by_dir"]={d:fb.loc[fb["_dir"]==d,"_ses_offline"].value_counts().to_dict() for d in ("CALL","PUT","OTHER")}
low=fb["hidden_state_label"].str.upper().str.contains("LOW_ENERGY")
res["F6_low_energy_rows_by_dir"]={d:int((low&(fb["_dir"]==d)).sum()) for d in ("CALL","PUT","OTHER")}
res["F6_low_energy_offline_NO_EDGE"]=int((fb.loc[low,"_ses_offline"]=="NO_EDGE").sum())
go=pd.read_csv(R/"intelligence_lab/lab_signal_book_v3.csv", dtype=str, keep_default_na=False, usecols=lambda c: c in {"ticker","governed_direction","hidden_state_label","phase","trigger_primary"})
go["_ses"]=go.apply(lambda r: derive_structure_evidence(hidden_state_label=r["hidden_state_label"],phase=r["phase"],trigger_primary=r["trigger_primary"])["structure_evidence_state"],axis=1)
go["_low"]=go["hidden_state_label"].str.upper().str.contains("LOW_ENERGY")
res["F6_go_low_energy"]=int(go["_low"].sum()); res["F6_go_offline_state"]=go["_ses"].value_counts().to_dict()
res["F6_trigger_primary_values_final"]=fb["trigger_primary"].value_counts().head(10).to_dict()
res["F6_hidden_state_values_final"]=fb["hidden_state_label"].value_counts().head(10).to_dict()
(OUT/"p15_F_05_capacity_structure.json").write_text(json.dumps(res,indent=1,default=str),encoding="utf-8")
print(json.dumps(res,indent=1,default=str)[:9000])
