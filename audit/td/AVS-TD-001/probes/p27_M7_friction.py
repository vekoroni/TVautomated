"""p27_M7_friction.py -- Track M7 friction (discovery, RESEARCH_ONLY; structure only).

Quoted spread as a fraction of mid, recomputed from bid/ask: s = (ask - bid) / ((ask + bid) / 2).
bid == 0 with ask > 0 gives s = 2.0 (kept, counted separately). Rows with no quote are excluded and counted.
Sources:
  BOOK_11SEP  data/output/runs/20260911_115904/intelligence_lab/final_opportunity_book_20260911_115904.csv
              (contract_bid, contract_ask, contract_delta, contract_oi, governed_direction, spread_pct)
  BOOK_10SEP  same for 20260910_150045 (units check of bare spread_pct only)
  OFFLINE     probes/_scratch_c6/control_plane_scratch_garch_sub.sqlite option_contract_observations (2,385 contracts, mode=ro)
Unit resolution: compares the book's bare spread_pct with s and with 100*s.
|delta| bands <0.25, 0.25-0.40, 0.40-0.60, >=0.60 ; OI buckets 0, 1-9, 10-99, 100-999, >=1000.
"""
from __future__ import annotations
import json, sqlite3
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
P = ROOT / "audit/td/AVS-TD-001/probes"
RUNS = ROOT / "data/output/runs"


def spread(bid, ask):
    bid = pd.to_numeric(bid, errors="coerce"); ask = pd.to_numeric(ask, errors="coerce")
    ok = ask.gt(0) & bid.ge(0) & bid.le(ask)
    return ((ask - bid) / ((ask + bid) / 2)).where(ok)


def bucket(frame, dcol, oicol):
    f = frame.copy()
    f["abs_delta"] = pd.to_numeric(f[dcol], errors="coerce").abs()
    f["delta_band"] = pd.cut(f.abs_delta, [0, .25, .40, .60, 1.0001], labels=["<0.25", "0.25-0.40", "0.40-0.60", ">=0.60"], right=False)
    f["oi_bucket"] = pd.cut(pd.to_numeric(f[oicol], errors="coerce"), [-0.5, 0.5, 9.5, 99.5, 999.5, np.inf], labels=["0", "1-9", "10-99", "100-999", ">=1000"])
    return f


def table(f, source):
    out = []
    for dirn in ["CALL", "PUT", "OTHER"]:
        g0 = f[f.direction == dirn]
        for dim in ["delta_band", "oi_bucket", "ALL"]:
            groups = [("ALL", g0)] if dim == "ALL" else list(g0.groupby(dim, observed=False))
            for lab, g in groups:
                s = g.s.dropna()
                out.append({"source": source, "direction": dirn, "dimension": dim, "cell": str(lab), "n": int(len(s)),
                            "power": "OK" if len(s) >= 100 else "INSUFFICIENT_POWER",
                            "median_s": float(s.median()) if len(s) else None, "p25_s": float(s.quantile(.25)) if len(s) else None,
                            "p75_s": float(s.quantile(.75)) if len(s) else None,
                            "share_s_gt_0_30": float((s > .30).mean()) if len(s) else None,
                            "share_bid_zero": float((g.loc[s.index, "bid"] == 0).mean()) if len(s) else None,
                            "median_half_spread_uncapped": float((s / 2).median()) if len(s) else None,
                            "median_half_spread_capped": float(np.minimum(s / 2, .15).median()) if len(s) else None})
    return out


rows, S = [], {}
cols = ["ticker", "governed_direction", "contract_bid", "contract_ask", "contract_delta", "contract_oi", "spread_pct"]
for run in ["20260911_115904", "20260910_150045"]:
    fb = pd.read_csv(RUNS / run / f"intelligence_lab/final_opportunity_book_{run}.csv", usecols=lambda c: c in cols, low_memory=False)
    fb["direction"] = fb.governed_direction.where(fb.governed_direction.isin(["CALL", "PUT"]), "OTHER")
    fb["bid"] = pd.to_numeric(fb.contract_bid, errors="coerce"); fb["ask"] = pd.to_numeric(fb.contract_ask, errors="coerce")
    fb["s"] = spread(fb.bid, fb.ask)
    sp = pd.to_numeric(fb.spread_pct, errors="coerce")
    both = fb.s.notna() & sp.notna()
    S[run] = {"rows": len(fb), "direction_counts": fb.direction.value_counts().to_dict(),
              "governed_direction_values": fb.governed_direction.value_counts(dropna=False).to_dict(),
              "quoted_rows": int(fb.s.notna().sum()), "no_quote_rows": int(fb.s.isna().sum()),
              "bid_zero_rows": int((fb.bid == 0).sum()),
              "spread_pct_vs_s_rows": int(both.sum()),
              "spread_pct_eq_s_within_1pct_rel": int((np.abs(sp[both] - fb.s[both]) <= 0.01 * fb.s[both].abs() + 1e-6).sum()),
              "spread_pct_eq_100s_within_1pct_rel": int((np.abs(sp[both] - 100 * fb.s[both]) <= 0.01 * 100 * fb.s[both].abs() + 1e-4).sum()),
              "spread_pct_range": [float(sp.min()), float(sp.max())] if sp.notna().any() else None}
    if run == "20260911_115904":
        rows += table(bucket(fb, "contract_delta", "contract_oi"), "BOOK_11SEP")

con = sqlite3.connect(f"file:{P / '_scratch_c6/control_plane_scratch_garch_sub.sqlite'}?mode=ro", uri=True)
ob = pd.read_sql("select ticker, contract_symbol, option_side as direction, bid, ask, delta, open_interest, spread_pct from option_contract_observations", con)
ob["s"] = spread(ob.bid, ob.ask)
spo = pd.to_numeric(ob.spread_pct, errors="coerce"); both = ob.s.notna() & spo.notna()
S["OFFLINE"] = {"rows": len(ob), "direction_counts": ob.direction.value_counts().to_dict(), "quoted_rows": int(ob.s.notna().sum()),
                "store_spread_pct_eq_s": int((np.abs(spo[both] - ob.s[both]) < 1e-9).sum()), "store_spread_pct_rows": int(both.sum())}
rows += table(bucket(ob, "delta", "open_interest"), "OFFLINE_SAMPLE")
S["fills"] = "0 FILL_RECORDED in decision_outcome_ledger copy (Track H); effective half-spread multiplier unestimable; 1.0 only supportable assumption (MEASURED)"
pd.DataFrame(rows).to_csv(P / "p27_M7_friction.csv", index=False)
(P / "p27_M7_friction.out.json").write_text(json.dumps(S, indent=1, default=str))
print(json.dumps(S, indent=1, default=str))
print(pd.DataFrame(rows).to_string())
