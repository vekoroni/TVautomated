"""Track B - AG/RG gate reconciliation per run. READ ONLY."""
import csv, glob, json, pathlib, sys
import pandas as pd
ROOT = pathlib.Path(".").resolve(); OUT = ROOT/"audit/pipeline_map/AVS-TST-QT-001"
def blank(s): return s.isna() | (s.astype(str).str.strip().isin(["","nan","None","NaN","<NA>"]))
def rd(p):
    f=glob.glob(str(p))
    return pd.read_csv(f[0],low_memory=False) if f else None
def split(df,mask,col="final_direction"):
    if df is None or col not in df.columns: return ""
    d=df.loc[mask,col].fillna("<NULL>").value_counts().to_dict()
    return ";".join(f"{k}={v}" for k,v in sorted(d.items()))

def gates(rid, code_state):
    R=ROOT/"data/output/runs"/rid
    vg=rd(R/"options"/f"vanguard_signals_enriched_{rid}.csv")
    if vg is None: vg=rd(R/"vanguard"/"vanguard_signals.csv")
    op=rd(R/"options"/f"options_intelligence_{rid}.csv")
    lab=rd(R/"intelligence_lab"/f"final_opportunity_book_{rid}.csv")
    mc=rd(R/"morning_validation"/f"morning_candidates_{rid}.csv")
    rows=[]
    def add(g,desc,filt,cnt,req,three=""):
        rows.append({"run_id":rid,"code_state":code_state,"gate":g,"assertion":desc,
                     "filter":filt,"count":cnt,"required":req,
                     "verdict":"PASS" if str(cnt)==str(req) else "FAIL","three_direction":three})
    if vg is not None:
        m=(vg.get("layer1__profile__profile_type","").astype(str)=="INSUFFICIENT_DATA") & \
          (vg.get("layer1__auction_state","").astype(str)=="ALIGNED")
        add("AG-01","INSUFFICIENT_DATA and ALIGNED","profile_type==INSUFFICIENT_DATA & auction_state==ALIGNED",
            int(m.sum()),0,split(vg,m,"direction"))
        poc=pd.to_numeric(vg.get("layer1__profile__poc"),errors="coerce")
        add("AG-02","POC represented as 0.0","layer1__profile__poc==0.0",int((poc==0).sum()),0)
        rt=vg.get("layer1__ready_to_trade").astype(str).str.upper().eq("TRUE") if "layer1__ready_to_trade" in vg else None
        if rt is not None:
            add("AG-03","ready_to_trade True with null POC","ready_to_trade==True & poc isna",
                int((rt & poc.isna()).sum()),0,split(vg,rt & poc.isna(),"direction"))
        tf=vg.get("layer1__profile__timeframe")
        if tf is not None:
            add("AG-04a","governed branch executed","timeframe value_counts",
                tf.astype(str).value_counts().to_dict().get("GOVERNED",0),len(vg))
    if op is not None:
        dcol="final_direction" if "final_direction" in op else "direction"
        armed=op.get("options_verdict","").astype(str).eq("ARMED")
        inv=op.get("invalidation_state","").astype(str)
        m=armed & inv.eq("MISSING")
        add("AG-05","ARMED with invalidation MISSING","options_verdict==ARMED & invalidation_state==MISSING",
            int(m.sum()),0,split(op,m,dcol))
        te=op.get("stand_down_reason","").astype(str).str.contains("unsupported operand|Traceback|Unhandled exception",na=False)
        add("AG-09","raw interpreter text in stand_down_reason","regex on stand_down_reason",
            int(te.sum()),0,split(op,te,dcol))
        if "economics_reason" in op:
            n=int(op["economics_reason"].astype(str).eq("STRUCTURAL_TARGET_UNRESOLVED").sum())
            add("AG-10","governed STRUCTURAL_TARGET_UNRESOLVED present","economics_reason==STRUCTURAL_TARGET_UNRESOLVED",
                n,n,split(op,op["economics_reason"].astype(str).eq("STRUCTURAL_TARGET_UNRESOLVED"),dcol))
        oth=op[dcol].astype(str).isin(["STRANGLE","UNRESOLVED"])
        bad=oth & ~inv.eq("NOT_APPLICABLE")
        add("RG-07","OTHER direction not NOT_APPLICABLE","direction in (STRANGLE,UNRESOLVED) & invalidation_state!=NOT_APPLICABLE",
            int(bad.sum()),0,split(op,oth,dcol))
    if lab is not None:
        b=blank(lab["invalidation_price"]) if "invalidation_price" in lab else None
        if b is not None:
            perm=lab.get("options_research_permission","").astype(str)
            m=b & perm.eq("EXECUTABLE_SUBJECT_TO_GATES")
            add("AG-08","Lab EXECUTABLE without invalidation","blank invalidation_price & permission==EXECUTABLE_SUBJECT_TO_GATES",
                int(m.sum()),0,split(lab,m))
            add("AG-08b","Lab rows blank invalidation_price","blank invalidation_price",int(b.sum()),0,split(lab,b))
        for f in ("contract_bid_size","contract_ask_size","selected_quote_timestamp_utc","execution_viability_state"):
            if f in lab.columns:
                add("AG-11:"+f,"Lab lineage populated",f"non-blank {f}",
                    int((~blank(lab[f])).sum()),len(lab))
        for f in ("macro_as_of_utc","macro_packet_sha256","monetisability_authority"):
            if f in lab.columns:
                add("AG-12/13:"+f,"lineage/authority stamp populated",f"non-blank {f}",
                    int((~blank(lab[f])).sum()),len(lab))
        add("RG-05","Lab population reconciles","nunique(trade_idea_id)==len",
            int(lab["trade_idea_id"].nunique()) if "trade_idea_id" in lab else -1,len(lab))
        if "final_direction" in lab:
            add("RG-02","Lab direction population","value_counts(final_direction)",
                len(lab),len(lab),split(lab,pd.Series([True]*len(lab))))
    if mc is not None and "invalidation_spot" in mc:
        b=blank(mc["invalidation_spot"])
        cp=mc.get("capital_permission","").astype(str)
        m=b & cp.eq("EOD_CANDIDATE_ONLY")
        add("AG-07","EOD_CANDIDATE_ONLY without invalidation","blank invalidation_spot & capital_permission==EOD_CANDIDATE_ONLY",
            int(m.sum()),0,split(mc,m))
    return rows

for rid,cs in [("20260904_122358","after IMP-002 (cycle1+adapter), legacy path"),
               ("20260905_151448","after DDD integration, before closure")]:
    rows=gates(rid,cs)
    dest=OUT/f"B_{rid}.csv"
    with dest.open("w",newline="",encoding="utf-8") as fh:
        w=csv.DictWriter(fh,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"\n{'='*74}\n{rid}  ({cs})\n{'='*74}")
    for r in rows:
        print(f"  {r['verdict']:4s} {r['gate']:34s} count={str(r['count']):>6s} req={str(r['required']):>6s}  {r['three_direction'][:60]}")
