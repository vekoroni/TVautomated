"""Analysis of the real-price volatility-lead test, as pre-registered (incl. the amendment).

  venv\\Scripts\\python.exe Enhancements\\direction_evidence\\volatility_lead_real_price_analysis_20260929.py OUT_DIR
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

D = Path(sys.argv[1])
d = pd.read_parquet(D / "real_price_contracts.parquet")
rng = np.random.default_rng(9)
pd.set_option("display.width", 240)
d["year"] = d["entry_date"].str[:4]
d["iv_rv"] = d["iv"] / d["rv20"]
dates = sorted(d["entry_date"].unique())
block_of = {x: i // 4 for i, x in enumerate(dates)}                 # four weekly entry dates per block
d["block"] = d["entry_date"].map(block_of)
print(f"contracts {len(d)}, tickers {d['ticker'].nunique()}, entry dates {len(dates)} ({dates[0]}..{dates[-1]})")
print("exit coverage (28 days):", round(d["real_ret_28"].notna().mean(), 3), "| iv source:",
      d["iv_source"].value_counts().to_dict())

# Q1: implied over realised volatility by tercile
print("\n== Q1: implied / realised volatility (median) by ATR tercile ==")
q1 = d[(d["rv20"] > 0) & d["iv"].between(0.02, 5)].groupby(["type", "atr_tercile", "year"])["iv_rv"].median().unstack()
print(q1.round(3).to_string())


def excess_table(col):
    x = d[d[col].notna()].copy()
    x["base"] = x.groupby(["entry_date", "type", "side"])[col].transform("mean")
    x["excess"] = x[col] - x["base"]
    rows = []
    for (t, terc, y), g in x.groupby(["type", "atr_tercile", "year"]):
        b = g.groupby("block")["excess"].agg(["sum", "count"])
        s, c = b["sum"].to_numpy(), b["count"].to_numpy()
        if len(s) >= 3:
            pk = rng.integers(0, len(s), size=(2000, len(s)))
            lo, hi = np.percentile(s[pk].sum(1) / c[pk].sum(1), [5, 95])
        else:
            lo = hi = np.nan
        rows.append({"type": t, "tercile": terc, "year": y, "n": len(g), "mean_return": g[col].mean(),
                     "excess": s.sum() / c.sum(), "lo90": lo, "hi90": hi,
                     "share_positive": (g[col] > 0).mean()})
    return pd.DataFrame(rows)


real = excess_table("real_ret_28")
model = excess_table("model_ret_28")
print("\n== Q2: REAL returns (ask entry, bid exit, 28 days) — excess over same-side, same-date contracts ==")
print(real.round(4).to_string(index=False))
print("\n== Same contracts, MODEL returns (1.1 x realised vol, 6 % spread) ==")
print(model.round(4).to_string(index=False))
real.to_csv(D / "real_excess.csv", index=False)
model.to_csv(D / "model_excess.csv", index=False)

calm = real[(real["type"] == "ITM56") & (real["tercile"] == "CALM")].set_index("year")
confirmed = ((calm["lo90"] > 0).sum() >= 2) and (calm["excess"] > 0).all() and len(calm) == 3
print("\nPRE-REGISTERED CRITERION (ITM56, CALM, 28 days):", "CONFIRMED" if confirmed else "NOT CONFIRMED")
print(calm[["n", "excess", "lo90", "hi90"]].round(4).to_string())
