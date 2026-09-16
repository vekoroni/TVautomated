"""M8: coverage of sector / iv_rank / iv_percentile / catalyst in execution_v3_5_<run>.csv for labelled (run,ticker). Read-only."""
import os, glob, csv
import pandas as pd
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
OUT = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes")
L = pd.read_csv(os.path.join(OUT, "p32_labels.csv"), usecols=["run_id", "ticker"]).drop_duplicates()
want = ["ticker","gics_sector","gics_sector_norm","sector","iv_rank","iv_percentile","catalyst_type","catalyst_event_status","earnings_date","days_to_earnings"]
out = []
for rid in sorted(L.run_id.unique()):
    f = os.path.join(ROOT, "data", "output", "runs", rid, "execution", f"execution_v3_5_{rid}.csv")
    if not os.path.exists(f):
        print(rid, "NO execution_v3_5"); continue
    with open(f, newline="", encoding="utf-8", errors="replace") as fh: h = next(csv.reader(fh))
    cols = [c for c in want if c in h]
    B = pd.read_csv(f, usecols=cols, low_memory=False).drop_duplicates("ticker")
    lt = L[L.run_id == rid].merge(B, on="ticker", how="left")
    msg = f"{rid} n_lab={len(lt)} "
    for c in cols[1:]:
        s = lt[c]; ok = s.notna() & (s.astype(str).str.strip() != "")
        msg += f"| {c} fill={ok.mean():.2f} nuniq={s.nunique()} top={s.astype(str).value_counts().head(3).to_dict()} "
        out.append(dict(run_id=rid, column=c, fill=ok.mean(), nuniq=s.nunique()))
    print(msg[:1200])
pd.DataFrame(out).to_csv(os.path.join(OUT, "p28_M8_sibling_exec.csv"), index=False)
