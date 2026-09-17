"""Structural edge study, supplement (read-only): tp50 trigger rate, session-equal-weight means, and an
index / sector ETF subset (no single-company earnings events) for the trades in short_vol_trades.parquet.
Uses the same structure-sanity exclusions as analyse_short_vol_trades.py.

  venv\Scripts\python.exe Enhancements\structural_edge\supplement_short_vol.py
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import analyse_short_vol_trades as A

HERE = Path(__file__).resolve().parent
ETFS = ["SPY", "QQQ", "IWM", "DIA", "XLF", "XLE", "XLK", "XLV", "XLI", "XLU", "XLP", "XLY", "XLB", "XLRE", "XLC",
        "SMH", "XBI", "GLD", "SLV", "TLT", "EEM", "EFA", "HYG", "KRE", "ARKK", "USO", "GDX", "FXI", "EWZ", "IBIT"]

df = pd.read_parquet(A.TRADES)
def strikes(col):
    return df[col].fillna("").map(lambda v: [float(x[1:]) for x in v.split(",") if x])
all_k = strikes("short_strikes") + strikes("long_strikes")
k_ok = pd.Series([all(0.6 * S <= k <= 1.6 * S for k in ks) for ks, S in zip(all_k, df["S"])], index=df.index)
straddle_bad = (df["strategy"] == "short_straddle") & ((strikes("short_strikes").map(lambda ks: ks[0] if ks else np.nan) / df["S"] - 1).abs() > 0.05)
defined_bad = (df["risk_kind"] == "defined") & (df["credit"] / (df["risk"] + df["credit"]) > 0.60)
df = df[k_ok & ~straddle_bad & ~defined_bad].copy()
df["hold_days"] = (pd.to_datetime(df["expiry"]) - pd.to_datetime(df["entry"])).dt.days
df["jump"] = df["max_abs_ret_over_sigma"] > A.JUMP_MULTIPLE
out = {"etf_list": ETFS, "cells": {}}
for (tenor, strat), g in df.groupby(["tenor", "strategy"]):
    for band in ["le10", "le20", "le35"]:
        b = g[g["max_leg_spread"] <= A.BANDS[band]]
        etf = b[b["ticker"].isin(ETFS)]
        cell = {"tp50_trigger_rate": float(b["tp50_exit_day"].notna().mean()),
                "hold_session_equal_weight_mean": float(b.groupby("entry")["ret_hold"].mean().mean()),
                "hold_mean_excluding_jump_windows_ex_post": float(b.loc[~b["jump"], "ret_hold"].mean()),
                "etf_hold": A.stats(etf, "ret_hold", A.BLOCK[tenor]) if len(etf) else {"n": 0},
                "etf_tp50": A.stats(etf, "ret_tp50", A.BLOCK[tenor], boot=False) if len(etf) else {"n": 0},
                "etf_mid": A.stats(etf, "ret_mid", A.BLOCK[tenor], boot=False) if len(etf) else {"n": 0},
                "single_names_hold": A.stats(b[~b["ticker"].isin(ETFS)], "ret_hold", A.BLOCK[tenor])}
        out["cells"][f"{tenor}|{strat}|{band}"] = cell
(HERE / "structural_edge_supplement.json").write_text(json.dumps(out, indent=1, default=str))
for k, c in out["cells"].items():
    e, s = c["etf_hold"], c["single_names_hold"]
    eci = (e.get("bootstrap") or {}).get("block_ci95") if e["n"] else None
    print(k, f"tp50 trig {c['tp50_trigger_rate']:.2f} sessEW {c['hold_session_equal_weight_mean']:+.3f} |",
          f"ETF n={e['n']} mean={e.get('mean', float('nan')):+.3f} ci={eci} p05={e.get('p05', float('nan')):+.3f} win={e.get('win_rate', float('nan')):.2f} tickers={e.get('tickers')} |",
          f"single mean={s['mean']:+.3f}")
