"""p21_M1_dispersion.py -- read-only. Per-session cross-sectional dispersion of forward
h-session log returns (h = 1,5,10,20) for the pipeline universe and the full price-store universe,
overall and within GICS sector, plus CALL/PUT thesis sets on run dates. Reports the distribution
(p10/p50/p90) ACROSS SESSIONS, never an average. Inputs: cache from p21_M1_universe.py
(_scratch_m1/close_wide.parquet), p21_M1_sector_map.csv. Outputs beside this script:
p21_M1_dispersion.csv (summary), p21_M1_dispersion_sessions.csv (per-session panel).
RESEARCH_ONLY. Nothing here authorises a trade.
"""
import os, json, time
import numpy as np, pandas as pd
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
PROBES = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes")
SCR = os.path.join(PROBES, "_scratch_m1")
t0 = time.time()
wide = pd.read_parquet(os.path.join(SCR, "close_wide.parquet"))
wide = wide.where(wide > 0)
smap = pd.read_csv(os.path.join(PROBES, "p21_M1_sector_map.csv"), index_col="ticker", dtype=str)
lp = np.log(wide)
HS = [1, 5, 10, 20]
STORE_END = wide.index[-1]
NON_SECTORS = {"ETF", "Equity Inverse ETF", "Rates / Bonds ETF", "Consumer Discretionary (ETF)", "Volatility", "Communication / Tech", "Power Generation"}

pipe = [t for t in wide.columns if smap.loc[t, "in_pipeline_universe"] == "True"] if "in_pipeline_universe" in smap else []
store = list(wide.columns)
print("pipeline in store", len(pipe), "store", len(store))
WINDOWS = {"W_recent_2026-07-23_2026-09-10": ("2026-07-23", "2026-09-10"), "W_context_2024-01-01_2026-09-10": ("2024-01-01", "2026-09-10")}

def fwd(h):
    return lp.shift(-h) - lp   # forward h-session log return, indexed at t

def xs_stats(R):
    """R: sessions x tickers forward returns. returns per-session std, iqr, p90-p10, n"""
    n = R.notna().sum(axis=1)
    std = R.std(axis=1, ddof=1)
    q = R.quantile([0.10, 0.25, 0.75, 0.90], axis=1).T
    return pd.DataFrame({"std": std, "iqr": q[0.75] - q[0.25], "p90p10": q[0.90] - q[0.10], "n_tickers": n})

sessions_rows = []
summary = []
fw = {h: fwd(h) for h in HS}
for wname, (a, b) in WINDOWS.items():
    for uname, cols in (("PIPELINE", pipe), ("STORE_ALL", store)):
        for h in HS:
            R = fw[h].loc[a:b, cols]
            R = R[R.notna().sum(axis=1) >= 20]   # a session needs >= 20 tickers with a t+h price
            st = xs_stats(R)
            st = st[st["n_tickers"] >= 20]
            for d, r in st.iterrows():
                sessions_rows.append({"window": wname, "universe": uname, "group": "ALL", "h": h, "session": d.date(), **r.to_dict()})
            for stat in ("std", "iqr", "p90p10"):
                s = st[stat]
                summary.append({"window": wname, "universe": uname, "group": "ALL", "h": h, "stat": stat,
                                "p10": s.quantile(.1), "p50": s.median(), "p90": s.quantile(.9), "min": s.min(), "max": s.max(),
                                "n_sessions": int(len(s)), "n_tickers_median": float(st["n_tickers"].median()),
                                "power": "OK" if len(s) >= 100 and st["n_tickers"].median() >= 100 else f"INSUFFICIENT_POWER(n_sessions={len(s)},n_tickers_med={int(st['n_tickers'].median()) if len(st) else 0})"})
        # within sector (pipeline universe only)
        if uname == "PIPELINE":
            sec = smap.loc[pipe, "sector"]
            for sname, tick in sec.groupby(sec).groups.items():
                if sname in NON_SECTORS or sname == "UNKNOWN": continue
                tick = list(tick)
                for h in HS:
                    R = fw[h].loc[a:b, tick]
                    st = xs_stats(R); st = st[st["n_tickers"] >= 10]
                    for d, r in st.iterrows():
                        sessions_rows.append({"window": wname, "universe": uname, "group": sname, "h": h, "session": d.date(), **r.to_dict()})
                    for stat in ("std", "iqr", "p90p10"):
                        s = st[stat]
                        summary.append({"window": wname, "universe": uname, "group": sname, "h": h, "stat": stat,
                                        "p10": s.quantile(.1), "p50": s.median(), "p90": s.quantile(.9), "min": s.min(), "max": s.max(),
                                        "n_sessions": int(len(s)), "n_tickers_median": float(st["n_tickers"].median()) if len(st) else 0,
                                        "power": "OK" if len(s) >= 100 and st["n_tickers"].median() >= 100 else f"INSUFFICIENT_POWER(n_sessions={len(s)},n_tickers_med={int(st['n_tickers'].median()) if len(st) else 0})"})
    print(wname, "done", round(time.time() - t0, 1), "s")

# CALL / PUT thesis sets on run dates. Reference session = last completed session at run time.
RUN_REF = {"20260905_151448": "2026-09-04", "20260906_213931": "2026-09-04", "20260909_071646": "2026-09-08",
           "20260910_150045": "2026-09-09", "20260911_115904": "2026-09-10"}
thesis_rows = []
for run, ref in RUN_REF.items():
    p = os.path.join(SCR, f"book_dir_{run}.csv")
    if not os.path.exists(p): continue
    bk = pd.read_csv(p, dtype=str)
    ref_ts = pd.Timestamp(ref)
    if ref_ts not in wide.index: continue
    pos = wide.index.get_loc(ref_ts)
    avail = len(wide.index) - 1 - pos   # forward sessions available in store
    for dirn in ("CALL", "PUT", "STRANGLE", "UNRESOLVED"):
        tick = [t for t in bk.loc[bk["final_direction"] == dirn, "ticker"].unique() if t in wide.columns]
        for h in HS:
            if h > avail:
                thesis_rows.append({"run": run, "ref_session": ref, "direction": dirn, "h": h, "n_tickers": len(tick), "std": np.nan, "iqr": np.nan, "p90p10": np.nan, "mean": np.nan,
                                    "state": f"DATA_UNAVAILABLE(store_ends_{STORE_END.date()},fwd_sessions_available={avail})"})
                continue
            r = (lp.iloc[pos + h][tick] - lp.iloc[pos][tick]).dropna()
            if len(r) < 5:
                thesis_rows.append({"run": run, "ref_session": ref, "direction": dirn, "h": h, "n_tickers": len(r), "std": np.nan, "iqr": np.nan, "p90p10": np.nan, "mean": np.nan, "state": "INSUFFICIENT_POWER"}); continue
            thesis_rows.append({"run": run, "ref_session": ref, "direction": dirn, "h": h, "n_tickers": int(len(r)), "std": r.std(ddof=1), "iqr": r.quantile(.75) - r.quantile(.25),
                                "p90p10": r.quantile(.9) - r.quantile(.1), "mean": r.mean(), "state": f"INSUFFICIENT_POWER(n_sessions=1,n_tickers={len(r)})"})
th = pd.DataFrame(thesis_rows)
th.to_csv(os.path.join(PROBES, "p21_M1_dispersion_thesis_sets.csv"), index=False)
S = pd.DataFrame(summary); S.to_csv(os.path.join(PROBES, "p21_M1_dispersion.csv"), index=False)
pd.DataFrame(sessions_rows).to_csv(os.path.join(PROBES, "p21_M1_dispersion_sessions.csv"), index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
print(S[(S["group"] == "ALL") & (S["stat"] == "std")].round(4).to_string())
print(S[(S["group"] != "ALL") & (S["stat"] == "std") & (S["h"] == 5)].round(4).to_string())
print(th.round(4).to_string())
print("runtime", round(time.time() - t0, 1))
