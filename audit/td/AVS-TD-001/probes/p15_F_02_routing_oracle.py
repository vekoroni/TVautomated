"""p15_F_02: routing oracle. 20 tickers (random.seed(20260912)) stratified across sectors from the primary final book.
Oracle = desk_gate.map_routing (imported read-only, no bytecode written) on routing at
macro_snapshot.extras.us_money_index.source_payload.options_monetisation.sector_routing.routing.
Compared to: stored usmi_routing_key (contract field), stored usmi_alignment_priority/reason/alignment,
offline Join 1 (contracts.interpreter_macro_context.advisory_fields_for_row on the stored interpreter packet, (a) with the
row's empty handoff sector and (b) with gics_sector filled) and offline Join 2 (domain.macro_advisory_context.project_usmi_context
on macro_snapshot.json). Also full-population (1,444) counts. Nothing is written except probe outputs."""
import sys, json, random, importlib.util
sys.dont_write_bytecode = True
from pathlib import Path
import pandas as pd
ROOT=Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"); sys.path.insert(0,str(ROOT))
RUN="20260911_115904"; R=ROOT/"data/output/runs"/RUN; OUT=ROOT/"audit/td/AVS-TD-001/probes"
spec=importlib.util.spec_from_file_location("desk_gate_ro", ROOT/"dropbox/macro/coaching/desk_gate/desk_gate.py")
dg=importlib.util.module_from_spec(spec); spec.loader.exec_module(dg)
from contracts.interpreter_macro_context import advisory_fields_for_row
from domain.macro_advisory_context import project_usmi_context
snap=json.loads((R/"macro_snapshot.json").read_text(encoding="utf-8-sig"))
routing=snap["extras"]["us_money_index"]["source_payload"]["options_monetisation"]["sector_routing"]["routing"]
ipkt=json.loads((R/"interpreter/interpreter_macro_context.json").read_text(encoding="utf-8-sig"))
book=pd.read_csv(R/f"intelligence_lab/final_opportunity_book_{RUN}.csv", dtype=str, keep_default_na=False)
keep=[c for c in ["ticker","governed_direction","gics_sector","sector","usmi_routing_key","usmi_sector_alignment","usmi_alignment_priority","usmi_alignment_reason","usmi_scenario"] if c in book.columns]
book=book[keep].copy()
uni=pd.read_csv(ROOT/"data/universe/polygon_liquid_universe.csv", dtype=str, keep_default_na=False)[["ticker","sector","industry"]].rename(columns={"sector":"uni_sector"})
book=book.merge(uni, on="ticker", how="left")
book["industry"]=book["industry"].fillna("")
book["_dir"]=book["governed_direction"].str.upper().where(book["governed_direction"].str.upper().isin(["CALL","PUT"]),"OTHER")
gate=pd.read_csv(R/f"trades/execution_gated_{RUN}.csv", dtype=str, keep_default_na=False, usecols=lambda c: c in {"ticker","sector","gics_sector","gics_sector_norm","industry","governed_direction","direction"})
gate=gate.drop_duplicates("ticker").set_index("ticker")
def evaluate(r):
    d=r["_dir"]; sec=r["gics_sector"]; ind=r["industry"]
    ok_key, ok_label, basis = dg.map_routing(sec, ind, d, routing)
    j2=project_usmi_context(packet=snap, sector=sec, industry=ind, direction=d)
    g=gate.loc[r["ticker"]].to_dict() if r["ticker"] in gate.index else {}
    hand={"ticker":r["ticker"],"governed_direction":r["governed_direction"], **{k:g.get(k,"") for k in ("sector","gics_sector","gics_sector_norm","industry")}}
    j1a=advisory_fields_for_row(ipkt, hand, packet_sha256="x")
    j1b=advisory_fields_for_row(ipkt, {**hand,"gics_sector":sec,"industry":ind}, packet_sha256="x")
    return {"ticker":r["ticker"],"direction":d,"gics_sector":sec,"industry":ind,
        "oracle_key":ok_key,"oracle_label":ok_label,"oracle_basis":basis,
        "stored_usmi_routing_key":r.get("usmi_routing_key","<FIELD_ABSENT>") if "usmi_routing_key" in r else "<FIELD_ABSENT>",
        "stored_alignment":r["usmi_sector_alignment"],"stored_priority":r["usmi_alignment_priority"],"stored_reason":r["usmi_alignment_reason"],
        "handoff_sector_seen_by_join1":"|".join(str(hand[k]) for k in ("gics_sector_norm","gics_sector","sector")),
        "j1_empty_alignment":j1a["usmi_sector_alignment"],"j1_empty_priority":j1a["usmi_alignment_priority"],"j1_empty_reason":j1a["usmi_alignment_reason"],
        "j1_filled_alignment":j1b["usmi_sector_alignment"],"j1_filled_priority":j1b["usmi_alignment_priority"],"j1_filled_reason":j1b["usmi_alignment_reason"],
        "j2_key":j2["usmi_alignment_priority"],"j2_alignment":j2["usmi_sector_alignment"],"j2_reason":j2["usmi_alignment_reason"],"j2_scenario":j2["usmi_scenario"],"j2_failed":j2["usmi_scenario_failed_clause"],
        "oracle_eq_j2_key": ok_key==j2["usmi_alignment_priority"],
        "oracle_eq_stored_key": ok_key==r.get("usmi_routing_key",None),
    }
# sample: random.seed(20260912); one per distinct gics_sector (sorted), then fill to 20 from remaining rows
random.seed(20260912)
idx_by_sector={}
for i,s in zip(book.index, book["gics_sector"]): idx_by_sector.setdefault(s,[]).append(i)
picked=[random.choice(idx_by_sector[s]) for s in sorted(idx_by_sector)]
rest=[i for i in book.index if i not in set(picked)]
picked+=random.sample(rest, max(0,20-len(picked)))
picked=picked[:20]
sample=pd.DataFrame([evaluate(book.loc[i]) for i in picked])
sample.to_csv(OUT/"p15_F_02_routing_oracle_sample20.csv", index=False)
full=pd.DataFrame([evaluate(book.loc[i]) for i in book.index])
full.to_csv(OUT/"p15_F_02_routing_oracle_full.csv", index=False)
five={"SUPPORTIVE","OPPOSED","NEUTRAL","UNCERTAIN","UNAVAILABLE"}
def summ(df):
    o={}
    for d in ("CALL","PUT","OTHER"):
        s=df[df["direction"]==d]
        o[d]={"n":len(s),"oracle_eq_j2_key":int(s["oracle_eq_j2_key"].sum()),"oracle_eq_stored_key":int(s["oracle_eq_stored_key"].sum()),
              "oracle_in_routing":int((s["oracle_label"]!="NOT_IN_ROUTING").sum()) ,
              "oracle_keys":s["oracle_key"].value_counts().to_dict(),"oracle_labels":s["oracle_label"].value_counts().to_dict(),
              "stored_alignment":s["stored_alignment"].value_counts().to_dict(),"stored_priority":s["stored_priority"].value_counts().head(5).to_dict(),
              "stored_alignment_in_five":int(s["stored_alignment"].isin(five).sum()),"stored_OPPOSED":int((s["stored_alignment"]=="OPPOSED").sum()),
              "j1_empty_reason":s["j1_empty_reason"].value_counts().to_dict(),"j1_filled_alignment":s["j1_filled_alignment"].value_counts().to_dict(),"j1_filled_reason":s["j1_filled_reason"].value_counts().head(8).to_dict(),
              "j2_alignment":s["j2_alignment"].value_counts().to_dict(),"j2_reason":s["j2_reason"].value_counts().head(8).to_dict(),"j2_scenario":s["j2_scenario"].value_counts().to_dict(),
              "mismatch_oracle_vs_j2":s.loc[~s["oracle_eq_j2_key"],["ticker","gics_sector","industry","oracle_key","j2_key"]].head(15).values.tolist()}
    return o
res={"routing_source_path":"macro_snapshot.extras.us_money_index.source_payload.options_monetisation.sector_routing.routing","routing":routing,
     "stored_has_usmi_routing_key":"usmi_routing_key" in book.columns,"book_n":len(book),"universe_industry_empty_in_book":int((book["industry"]=="").sum()),
     "sample_tickers":sample["ticker"].tolist(),"sample_sectors":sample["gics_sector"].value_counts().to_dict(),
     "sample20":summ(sample),"full":summ(full)}
(OUT/"p15_F_02_routing_oracle_summary.json").write_text(json.dumps(res,indent=1,default=str),encoding="utf-8")
print(json.dumps(res,indent=1,default=str)[:9000])
