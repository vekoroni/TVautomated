"""p15_F_06: options_intelligence stored macro-gate/bonus fields vs options verdict and direction (read-only)."""
import json, re
from pathlib import Path
import pandas as pd
ROOT=Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"); RUN="20260911_115904"; R=ROOT/"data/output/runs"/RUN; OUT=ROOT/"audit/td/AVS-TD-001/probes"
p=R/f"options/options_intelligence_{RUN}.csv"
cols=list(pd.read_csv(p,nrows=0).columns)
mac=[c for c in cols if re.search(r"macro_(hard_gate|gate|bonus|filter|alignment_state|direction_authority|confirmation_level|routing_state|multiplier)|options_macro", c)]
verd=[c for c in cols if c in ("options_verdict","options_route_verdict","final_route","governed_direction","direction","options_score","execution_permission")]
df=pd.read_csv(p,dtype=str,keep_default_na=False,usecols=mac+verd,engine="python")
df["_dir"]=df["governed_direction"].str.upper().where(df["governed_direction"].str.upper().isin(["CALL","PUT"]),"OTHER") if "governed_direction" in df else "OTHER"
res={"n":len(df),"macro_cols":mac,"verdict_cols":verd,"value_counts":{c:df[c].value_counts().head(6).to_dict() for c in mac}}
v=next((c for c in ("options_verdict","options_route_verdict","final_route") if c in df.columns),None)
for c in mac:
    if 1<df[c].nunique()<=8 and v: res.setdefault("crosstab",{})[f"{c} x {v}"]={str(k):int(x) for k,x in pd.crosstab(df[c],df[v]).stack().items() if x}
    if 1<df[c].nunique()<=8: res.setdefault("crosstab_dir",{})[c]={str(k):int(x) for k,x in pd.crosstab(df[c],df["_dir"]).stack().items() if x}
(OUT/"p15_F_06_oi_macro_gate.json").write_text(json.dumps(res,indent=1,default=str),encoding="utf-8")
print(json.dumps(res,indent=1,default=str)[:6000])
