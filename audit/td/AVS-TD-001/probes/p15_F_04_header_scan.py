"""p15_F_04 (header scan): which capacity / structure / macro-v2 fields exist in each primary-run CSV header (header only, packages excluded)."""
import re
from pathlib import Path
import pandas as pd
ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"); RUN = "20260911_115904"; R = ROOT / "data/output/runs" / RUN; OUT = ROOT / "audit/td/AVS-TD-001/probes"
pat = re.compile(r"contracts_at_budget|horizon_cap|direction_factor|structure_evidence|capacity|budget|afford|account|usmi_routing_key|usmi_scenario|failed_clause|position_size|suggested_contract|size_multiplier|dg_contracts|human_determined", re.I)
files = sorted(p for p in R.rglob("*.csv") if "packages" not in p.parts)
rows = []
for p in files:
    rel = p.relative_to(R).as_posix()
    try:
        cols = list(pd.read_csv(p, nrows=0).columns)
    except Exception as e:
        rows.append({"artefact": rel, "field": "<header error>", "note": str(e)[:80]}); continue
    rows.append({"artefact": rel, "field": "<n_cols>", "note": str(len(cols))})
    for c in cols:
        if pat.search(c):
            rows.append({"artefact": rel, "field": c, "note": ""})
df = pd.DataFrame(rows)
df.to_csv(OUT / "p15_F_04_header_scan.csv", index=False)
print(len(files), "csv files scanned")
hit = df[~df["field"].str.startswith("<")]
print(hit.groupby("field")["artefact"].apply(lambda s: f"{len(s)} files: " + "; ".join(sorted(set(x.split('/')[0] for x in s)))).to_string())
