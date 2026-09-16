"""p15_F_01: SECTOR_UNMAPPED / UNMAPPED / ROUTE_UNAVAILABLE / UNAVAILABLE counts by direction across artefacts; empty gics_sector per artefact; canonical store GICS coverage; manifest fraction; 19/19 GO claim."""
import json, csv
from pathlib import Path
import pandas as pd
ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"); RUN="20260911_115904"; R=ROOT/"data/output/runs"/RUN; OUT=ROOT/"audit/td/AVS-TD-001/probes"
arts = {
 "discovery_candidates_ultimate": R/f"discovery/discovery_candidates_ultimate_{RUN}.csv",
 "options_intelligence": R/f"options/options_intelligence_{RUN}.csv",
 "execution_v3_5": R/f"execution/execution_v3_5_{RUN}.csv",
 "eil_enriched": R/f"superbrain/eil_enriched_{RUN}.csv",
 "execution_gated": R/f"trades/execution_gated_{RUN}.csv",
 "morning_candidates": R/f"morning_validation/morning_candidates_{RUN}.csv",
 "morning_validated_trades": R/f"morning_validation/morning_validated_trades_{RUN}.csv",
 "lab_triage_view": R/f"intelligence_lab/lab_triage_view_{RUN}.csv",
 "final_opportunity_book": R/f"intelligence_lab/final_opportunity_book_{RUN}.csv",
 "lab_signal_book_v3": R/"intelligence_lab/lab_signal_book_v3.csv",
}
want = ["ticker","governed_direction","direction","gics_sector","gics_sector_norm","sector","sector_etf","industry","usmi_alignment_reason","usmi_sector_alignment","macro_sector_alignment","usmi_alignment_priority","lab_verdict","usmi_scenario"]
tokens = ["SECTOR_UNMAPPED","UNMAPPED","ROUTE_UNAVAILABLE","UNAVAILABLE"]
def dirb(s):
    s = str(s or "").upper().strip()
    return s if s in ("CALL","PUT") else "OTHER"
rows=[]; empties=[]
for name,p in arts.items():
    if not p.exists(): rows.append({"artefact":name,"note":"MISSING"}); continue
    cols = list(pd.read_csv(p, nrows=0).columns)
    use = [c for c in want if c in cols]
    df = pd.read_csv(p, usecols=use, dtype=str, keep_default_na=False, engine="python" if name in ("options_intelligence","execution_v3_5") else "c")
    dcol = "governed_direction" if "governed_direction" in df.columns else ("direction" if "direction" in df.columns else None)
    df["_dir"] = df[dcol].map(dirb) if dcol else "OTHER"
    n = len(df)
    e = {"artefact":name,"n_rows":n,"has_gics_sector":"gics_sector" in cols,"has_gics_sector_norm":"gics_sector_norm" in cols,"has_sector":"sector" in cols,"has_industry":"industry" in cols,"dir_col":dcol}
    for d in ("CALL","PUT","OTHER"):
        sub = df[df["_dir"]==d]; e[f"n_{d}"]=len(sub)
        for c in ("gics_sector","gics_sector_norm","sector"):
            e[f"empty_{c}_{d}"] = int((sub[c].str.strip()=="").sum()) if c in sub.columns else "NA"
    empties.append(e)
    for fld in ("usmi_alignment_reason","usmi_sector_alignment","macro_sector_alignment"):
        if fld not in df.columns:
            rows.append({"artefact":name,"field":fld,"note":"FIELD_ABSENT","n_rows":n}); continue
        for d in ("CALL","PUT","OTHER"):
            sub = df[df["_dir"]==d]
            rec = {"artefact":name,"field":fld,"direction":d,"n":len(sub)}
            for t in tokens:
                rec[t+"_exact"] = int((sub[fld].str.strip().str.upper()==t).sum())
                rec[t+"_contains"] = int(sub[fld].str.upper().str.contains(t, regex=False).sum())
            rec["value_counts"] = json.dumps(sub[fld].value_counts().head(8).to_dict())
            rows.append(rec)
pd.DataFrame(rows).to_csv(OUT/"p15_F_01_token_counts.csv", index=False)
pd.DataFrame(empties).to_csv(OUT/"p15_F_01_empty_sector_by_artefact.csv", index=False)
print(pd.DataFrame(empties).to_string())
print(pd.DataFrame(rows)[["artefact","field","direction","n","SECTOR_UNMAPPED_exact","UNMAPPED_exact","ROUTE_UNAVAILABLE_contains","UNAVAILABLE_exact","note"]].to_string() if "note" in pd.DataFrame(rows).columns else pd.DataFrame(rows).to_string())
# canonical store
uni = pd.read_csv(ROOT/"data/universe/polygon_liquid_universe.csv", dtype=str, keep_default_na=False)
uni["ticker"]=uni["ticker"].str.upper().str.strip()
book = pd.read_csv(arts["final_opportunity_book"], usecols=["ticker","governed_direction","gics_sector","sector","usmi_alignment_reason","lab_verdict"], dtype=str, keep_default_na=False)
book["_dir"]=book["governed_direction"].map(dirb)
m = book.merge(uni[["ticker","sector","industry"]].rename(columns={"sector":"uni_sector","industry":"uni_industry"}), on="ticker", how="left", indicator=True)
summary = {
 "universe_file":"data/universe/polygon_liquid_universe.csv","universe_n":len(uni),
 "universe_empty_sector":int((uni["sector"].str.strip()=="").sum()),"universe_empty_industry":int((uni["industry"].str.strip()=="").sum()),
 "universe_sector_values":uni["sector"].value_counts().to_dict(),
 "book_n":len(book),"book_tickers_not_in_universe":int((m["_merge"]=="left_only").sum()),
 "book_tickers_missing_gics_in_store":int(((m["_merge"]=="left_only")|(m["uni_sector"].fillna("").str.strip()=="")).sum()),
 "book_empty_gics_sector":int((book["gics_sector"].str.strip()=="").sum()),"book_empty_sector":int((book["sector"].str.strip()=="").sum()),
}
for d in ("CALL","PUT","OTHER"):
    s=m[m["_dir"]==d]; summary[f"{d}_n"]=len(s); summary[f"{d}_missing_gics_in_store"]=int(((s["_merge"]=="left_only")|(s["uni_sector"].fillna("").str.strip()=="")).sum()); summary[f"{d}_SECTOR_UNMAPPED"]=int((s["usmi_alignment_reason"].str.strip()=="SECTOR_UNMAPPED").sum()); summary[f"{d}_book_empty_gics_sector"]=int((s["gics_sector"].str.strip()=="").sum())
# duplicates
summary["book_duplicate_tickers"]=int(book["ticker"].duplicated().sum())
man = json.loads((R/"interpreter/macro_ticker_context_manifest.json").read_text(encoding="utf-8-sig"))["diagnostics"]
summary["manifest_available"]=man["macro_ticker_context_available"]; summary["manifest_requested"]=man["macro_ticker_context_requested"]; summary["manifest_fraction"]=man["macro_ticker_context_available"]/max(1,man["macro_ticker_context_requested"]); summary["manifest_stale"]=man["macro_ticker_context_stale"]; summary["manifest_conflicting"]=man["macro_ticker_context_conflicting"]; summary["manifest_sector_only"]=man["macro_ticker_context_sector_only"]
go = pd.read_csv(arts["lab_signal_book_v3"], usecols=["ticker","governed_direction","gics_sector","sector","usmi_alignment_reason","usmi_sector_alignment","macro_sector_alignment","lab_verdict"], dtype=str, keep_default_na=False)
summary["go_n"]=len(go); summary["go_SECTOR_UNMAPPED"]=int((go["usmi_alignment_reason"]=="SECTOR_UNMAPPED").sum()); summary["go_by_dir"]=go["governed_direction"].map(dirb).value_counts().to_dict(); summary["go_empty_gics_sector"]=int((go["gics_sector"].str.strip()=="").sum()); summary["go_sector_nonempty"]=int((go["sector"].str.strip()!="").sum()); summary["go_lab_verdict"]=go["lab_verdict"].value_counts().to_dict(); summary["go_usmi_sector_alignment"]=go["usmi_sector_alignment"].value_counts().to_dict(); summary["go_macro_sector_alignment"]=go["macro_sector_alignment"].value_counts().to_dict()
# one package: does it carry gics?
pk = sorted((R/"packages").glob("*.package.json"))[0]; d=json.loads(pk.read_text(encoding="utf-8-sig"))
disc = d.get("discovery") if isinstance(d.get("discovery"), dict) else {}
summary["package_example"]=pk.name; summary["package_discovery_sector_keys"]={k:disc.get(k) for k in disc if "sector" in k.lower() or "gics" in k.lower() or "industry" in k.lower()}
(OUT/"p15_F_01_summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
print(json.dumps(summary, indent=1, default=str))
