"""p15_F_02b: detail on p15_F_02 output. (i) oracle vs Join-2 key agreement on rows the oracle maps to a routing key;
(ii) book gics_sector vs universe sector disagreement by direction; (iii) routing object Join 2 finds via _find vs ALG-14 path;
(iv) alignment Join 2 derives from the stored routing labels."""
import sys, json
sys.dont_write_bytecode = True
from pathlib import Path
import pandas as pd
ROOT=Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"); RUN="20260911_115904"; R=ROOT/"data/output/runs"/RUN; OUT=ROOT/"audit/td/AVS-TD-001/probes"
full=pd.read_csv(OUT/"p15_F_02_routing_oracle_full.csv", dtype=str, keep_default_na=False)
mapped=full[~full["oracle_key"].isin(["NO_CALL_ROUTE_FOR_SECTOR","NO_PUT_ROUTE_FOR_SECTOR","UNMAPPED"])]
res={}
for d in ("CALL","PUT","OTHER"):
    s=mapped[mapped["direction"]==d]; a=full[full["direction"]==d]
    mm=s[s["oracle_key"]!=s["j2_key"]]
    res[d]={"n":len(a),"oracle_mapped":len(s),"j2_key_equal_on_mapped":int((s["oracle_key"]==s["j2_key"]).sum()),
            "mismatch_pairs":mm.groupby(["oracle_key","j2_key"]).size().to_dict(),
            "mismatch_examples":mm[["ticker","gics_sector","industry","oracle_key","j2_key"]].head(12).values.tolist(),
            "oracle_unmapped_j2_nonroute":int(((a["oracle_key"].isin(["NO_CALL_ROUTE_FOR_SECTOR","NO_PUT_ROUTE_FOR_SECTOR","UNMAPPED"]))&(a["j2_key"]!="NO_ROUTE")).sum()),
            "j2_alignment_on_mapped":s["j2_alignment"].value_counts().to_dict(),
            "oracle_label_on_mapped":s["oracle_label"].value_counts().to_dict()}
res={"by_direction":{str(k):{str(kk):vv for kk,vv in v.items()} for k,v in res.items()}}
res["by_direction"]={d:{k:(v if not isinstance(v,dict) else {str(x):y for x,y in v.items()}) for k,v in res["by_direction"][d].items()} for d in res["by_direction"]}
book=pd.read_csv(R/f"intelligence_lab/final_opportunity_book_{RUN}.csv", dtype=str, keep_default_na=False, usecols=["ticker","governed_direction","gics_sector","gics_sector_norm","sector"])
uni=pd.read_csv(ROOT/"data/universe/polygon_liquid_universe.csv", dtype=str, keep_default_na=False)[["ticker","sector","industry"]].rename(columns={"sector":"uni_sector"})
m=book.merge(uni,on="ticker",how="left"); m["_dir"]=m["governed_direction"].str.upper().where(m["governed_direction"].str.upper().isin(["CALL","PUT"]),"OTHER")
m["disagree"]=m["gics_sector"].str.strip()!=m["uni_sector"].fillna("").str.strip()
res["book_vs_universe_sector"]={d:{"n":int((m["_dir"]==d).sum()),"disagree":int(m.loc[m["_dir"]==d,"disagree"].sum())} for d in ("CALL","PUT","OTHER")}
res["book_vs_universe_examples"]=m.loc[m["disagree"],["ticker","_dir","gics_sector","gics_sector_norm","sector","uni_sector","industry"]].head(25).values.tolist()
m.loc[m["disagree"],["ticker","_dir","gics_sector","gics_sector_norm","sector","uni_sector","industry"]].to_csv(OUT/"p15_F_02b_sector_disagreements.csv",index=False)
snap=json.loads((R/"macro_snapshot.json").read_text(encoding="utf-8-sig")); u=snap["extras"]["us_money_index"]
alg=u["source_payload"]["options_monetisation"]["sector_routing"]["routing"]; found=u["advisory_context"]["options_monetisation"]["sector_routing"]["routing"]
res["join2_find_path"]="extras.us_money_index.advisory_context.options_monetisation.sector_routing.routing"
res["join2_routing_equals_alg14_path"]=alg==found
res["routing_label_vocab"]=sorted(set(alg.values()))
ipkt=json.loads((R/"interpreter/interpreter_macro_context.json").read_text(encoding="utf-8-sig"))
res["join1_normalised_routing_categories"]={k:sorted(v.keys()) for k,v in ipkt["us_money_index"]["sector_routing"].items()}
res["join1_sector_aliases_note"]="SECTOR_ALIASES maps GICS to TECHNOLOGY/ENERGY/RATE_SENSITIVE_REITS/WEAK_CONSUMER_DISCRETIONARY/INDUSTRIALS/FINANCIALS/HEALTH_CARE/COMMUNICATION_SERVICES"
(OUT/"p15_F_02b_routing_detail.json").write_text(json.dumps(res,indent=1,default=str),encoding="utf-8")
print(json.dumps(res,indent=1,default=str)[:7000])
