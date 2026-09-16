"""M8: which conditioning columns exist per run final book (header only). Read-only."""
import os, glob, re, csv
import pandas as pd
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
OUT = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes")
L = pd.read_csv(os.path.join(OUT, "p32_labels.csv"), usecols=["run_id"])
pat = re.compile(r"sector|catalyst|iv_rank|iv_percentile|iv_pct|contract_delta|delta_band|contract_dte|dte|regime|usmi|morning_execution_permission|thesis_state|trigger_primary|confirm", re.I)
rows = []
for rid in sorted(L.run_id.unique()):
    f = glob.glob(os.path.join(ROOT, "data", "output", "runs", rid, "intelligence_lab", f"final_opportunity_book_{rid}.csv"))
    if not f:
        rows.append(dict(run_id=rid, column="<NO_BOOK>")); continue
    with open(f[0], newline="", encoding="utf-8", errors="replace") as fh:
        hdr = next(csv.reader(fh))
    for c in hdr:
        if pat.search(c):
            rows.append(dict(run_id=rid, column=c))
D = pd.DataFrame(rows)
D.to_csv(os.path.join(OUT, "p28_M8_columns.csv"), index=False)
piv = D.assign(v=1).pivot_table(index="column", columns="run_id", values="v", aggfunc="max", fill_value=0)
piv["n_runs"] = piv.sum(axis=1)
print(len(L.run_id.unique()), "runs")
print(piv["n_runs"].sort_values(ascending=False).to_string())
