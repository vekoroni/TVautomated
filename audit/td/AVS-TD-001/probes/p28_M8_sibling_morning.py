"""M8: coverage of thesis_state / catalyst / earnings / sector / iv_rank in morning_candidates and horizon_*; read-only."""
import os, glob, csv
import pandas as pd
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
OUT = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes")
L = pd.read_csv(os.path.join(OUT, "p32_labels.csv"), usecols=["run_id", "ticker"]).drop_duplicates()
want = ["ticker","thesis_state","catalyst_type","catalyst_event_status","earnings_date","days_to_earnings","sector","iv_rank","iv_percentile","gics_sector"]
out = []
for rid in sorted(L.run_id.unique()):
    for sub in [f"morning_validation/morning_candidates_{rid}.csv", f"horizon/horizon_6_10d_{rid}.csv"]:
        f = os.path.join(ROOT, "data", "output", "runs", rid, sub)
        if not os.path.exists(f):
            print(rid, sub, "ABSENT"); continue
        with open(f, newline="", encoding="utf-8", errors="replace") as fh: h = next(csv.reader(fh))
        cols = [c for c in want if c in h]
        B = pd.read_csv(f, usecols=cols, low_memory=False).drop_duplicates("ticker")
        lt = L[L.run_id == rid].merge(B, on="ticker", how="left")
        msg = f"{rid} {sub.split('/')[0]} rows={len(B)} "
        for c in cols[1:]:
            s = lt[c]; ok = s.notna() & (s.astype(str).str.strip() != "")
            msg += f"| {c} fill={ok.mean():.2f} top={s.astype(str).value_counts().head(3).to_dict()} "
            out.append(dict(run_id=rid, artefact=sub, column=c, fill=ok.mean(), nuniq=s.nunique()))
        print(msg[:1000])
pd.DataFrame(out).to_csv(os.path.join(OUT, "p28_M8_sibling_morning.csv"), index=False)
