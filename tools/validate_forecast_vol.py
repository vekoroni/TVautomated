"""AVS-VAL-001 time-ordered forecast-vol validation report builder."""
from __future__ import annotations
import argparse, json, math
from pathlib import Path
from statistics import median
import pandas as pd

VERSION="vol_validation_v1"

def build_report(frame: pd.DataFrame, *, minimum_n: int = 200) -> dict:
    required={"forecast_vol_annual_fraction","realised_vol_annual_fraction","hidden_state_label"}
    missing=required-set(frame.columns)
    if missing: raise ValueError("missing validation columns: "+",".join(sorted(missing)))
    rows=frame.copy()
    rows["ratio"]=pd.to_numeric(rows.realised_vol_annual_fraction,errors="coerce")/pd.to_numeric(rows.forecast_vol_annual_fraction,errors="coerce")
    rows=rows[rows.ratio.map(lambda x: pd.notna(x) and math.isfinite(float(x)) and float(x)>0)]
    def summary(group):
        values=sorted(float(x) for x in group.ratio)
        n=len(values); med=median(values) if values else None
        q1=float(pd.Series(values).quantile(.25)) if values else None
        q3=float(pd.Series(values).quantile(.75)) if values else None
        multiplier=max(.5,min(1.5,med)) if med is not None else 1.0
        return {"n":n,"median_realised_to_forecast":med,"iqr":[q1,q3],
                "candidate_bias_multiplier":multiplier,"eligible_to_validate":n>=minimum_n}
    buckets={str(name):summary(group) for name,group in rows.groupby("hidden_state_label",dropna=False)}
    overall=summary(rows)
    # A report is diagnostic until a separate time-ordered holdout supplies
    # coverage_1sigma and both governed pass bands are satisfied.
    return {"report_version":VERSION,"validation_state":"UNVALIDATED",
            "applied_bias_multiplier":1.0,"bias_multiplier_applied":False,
            "minimum_validation_n":minimum_n,"overall":overall,"buckets":buckets}

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("input",type=Path); p.add_argument("output",type=Path)
    p.add_argument("--minimum-n",type=int,default=200); a=p.parse_args(argv)
    report=build_report(pd.read_csv(a.input,low_memory=False),minimum_n=a.minimum_n)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    tmp=a.output.with_suffix(a.output.suffix+".tmp"); tmp.write_text(json.dumps(report,indent=2),encoding="utf-8"); tmp.replace(a.output)
    return 0
if __name__=="__main__": raise SystemExit(main())
