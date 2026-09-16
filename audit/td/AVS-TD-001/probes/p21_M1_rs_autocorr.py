"""p21_M1_rs_autocorr.py -- read-only. Persistence of sector relative strength.
Sector composite = equal-weight mean of daily log returns of store tickers mapped to the sector
(p21_M1_sector_map.csv; sector join DERIVED by this track from Discovery CSVs + data/universe file, not from F1-F3).
RS5(t) = sector 5-session log return - all-mapped-universe EW 5-session log return.
Autocorrelation of RS5 at lags 1,5,10,20 sessions over 2024-01-01 -> 2026-09-10.
Overlapping 5-session windows mechanically induce autocorrelation at lags < 5; the non-overlapping
reading (every 5th session, lag 1/2/4 blocks) is reported beside it. Also RS1 (1-session RS) and
sector-ETF RS5 where the SPDR ETF is in the store. Output: p21_M1_rs_autocorr.csv. RESEARCH_ONLY.
"""
import os, time
import numpy as np, pandas as pd

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
PROBES = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes")
SCR = os.path.join(PROBES, "_scratch_m1")
t0 = time.time()
wide = pd.read_parquet(os.path.join(SCR, "close_wide.parquet"))
wide = wide.where(wide > 0).loc["2023-11-01":"2026-09-10"]
smap = pd.read_csv(os.path.join(PROBES, "p21_M1_sector_map.csv"), index_col="ticker", dtype=str)
r1 = np.log(wide).diff()
r1 = r1.where(r1.abs() < 0.5)  # drop split / bad-print jumps (|log ret| >= 0.5)
GICS = ["Information Technology", "Health Care", "Industrials", "Consumer Discretionary", "Financials", "Energy",
        "Materials", "Real Estate", "Consumer Staples", "Communication Services", "Utilities"]
ETF = {"Information Technology": "XLK", "Health Care": "XLV", "Industrials": "XLI", "Consumer Discretionary": "XLY",
       "Financials": "XLF", "Energy": "XLE", "Materials": "XLB", "Real Estate": "XLRE", "Consumer Staples": "XLP",
       "Communication Services": "XLC", "Utilities": "XLU"}
LAGS = [1, 5, 10, 20]


def ac(s, L):
    s = s.dropna()
    return s.autocorr(L) if len(s) > L + 30 else np.nan


rows = []
for uname, flag in (("PIPELINE", "in_pipeline_universe"), ("STORE_ALL", "in_store")):
    cols = [c for c in r1.columns if c in smap.index and smap.loc[c, flag] == "True" and smap.loc[c, "sector"] in GICS]
    sec = smap.loc[cols, "sector"]
    mkt = r1[cols].mean(axis=1)
    for s in GICS:
        tk = list(sec.index[sec == s])
        comp = r1[tk].mean(axis=1)
        nmed = int(r1[tk].notna().sum(axis=1).loc["2024-01-01":].median())
        rel1 = comp - mkt
        rs5 = rel1.rolling(5).sum().loc["2024-01-01":"2026-09-10"]
        rs1 = rel1.loc["2024-01-01":"2026-09-10"]
        rec = {"universe": uname, "sector": s, "series": "RS5_EW", "n_sessions": int(rs5.notna().sum()), "n_tickers_median": nmed}
        rec.update({f"ac_lag{L}": ac(rs5, L) for L in LAGS})
        nb = rs5.dropna().iloc[::5]
        rec.update({"nonoverlap_n_blocks": int(len(nb)), "nonoverlap_ac_5": ac(nb, 1), "nonoverlap_ac_10": ac(nb, 2), "nonoverlap_ac_20": ac(nb, 4)})
        rows.append(rec)
        rec1 = {"universe": uname, "sector": s, "series": "RS1_EW", "n_sessions": int(rs1.notna().sum()), "n_tickers_median": nmed}
        rec1.update({f"ac_lag{L}": ac(rs1, L) for L in LAGS})
        rows.append(rec1)
        if uname == "STORE_ALL" and ETF[s] in r1.columns:
            e = (r1[ETF[s]] - mkt).rolling(5).sum().loc["2024-01-01":"2026-09-10"]
            rece = {"universe": "ETF_vs_STORE_EW", "sector": s, "series": f"RS5_{ETF[s]}", "n_sessions": int(e.notna().sum()), "n_tickers_median": 1}
            rece.update({f"ac_lag{L}": ac(e, L) for L in LAGS})
            nb = e.dropna().iloc[::5]
            rece.update({"nonoverlap_n_blocks": int(len(nb)), "nonoverlap_ac_5": ac(nb, 1), "nonoverlap_ac_10": ac(nb, 2), "nonoverlap_ac_20": ac(nb, 4)})
            rows.append(rece)
D = pd.DataFrame(rows)
acc = [c for c in D.columns if c.startswith("ac_") or c.startswith("nonoverlap_ac")]
summ = []
for (u, se), g in D.groupby(["universe", D["series"].str[:3]]):
    rec = {"universe": u, "sector": "CROSS_SECTOR_MEDIAN", "series": se + "_summary", "n_sessions": int(g["n_sessions"].median())}
    for c in acc:
        rec[c] = g[c].median()
        rec[c.replace("ac", "min", 1) if c.startswith("ac_") else c + "_min"] = g[c].min()
        rec[c.replace("ac", "max", 1) if c.startswith("ac_") else c + "_max"] = g[c].max()
    summ.append(rec)
out = pd.concat([D, pd.DataFrame(summ)], ignore_index=True)
out.to_csv(os.path.join(PROBES, "p21_M1_rs_autocorr.csv"), index=False)
pd.set_option("display.width", 300); pd.set_option("display.max_columns", 40)
print(D.round(3).to_string())
print(pd.DataFrame(summ).round(3).T.to_string())
print("runtime", round(time.time() - t0, 1))
