"""Evaluate the 2022-2026 point-in-time discovery replay (item 4 step 2, read-only).

Per session: cross-sectional Spearman IC of each numeric input vs the forward log return net of the session median;
for direction labels, mean signed net return and hit rate (sign-mapped labels). Also the thesis return test for the
discovery CALL/PUT: net return signed by the label, and whether numeric inputs rank the thesis return.
Statistics across sessions: mean, t with an effective count for overlapping horizons (sessions every 5 bars:
overlap = ceil(h / 5)), the number of calendar years (2022-2026) with the same sign as the overall mean, and
Benjamini-Hochberg at q = 0.10. Evidence classes:
  ROBUST            FDR-significant and the same sign in at least 4 of 5 years
  SIGNIFICANT_ONLY  FDR-significant, less consistent across years
  NO_EVIDENCE       otherwise
Baselines (past returns) are reported beside every input so an input must beat simple momentum / reversal.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
ROWS = HERE / "direction_replay_rows.parquet"
HORIZONS = (1, 5, 10, 20)
STEP = 5
MIN_TICKERS = 30
FDR_Q = 0.10
SIGN = {"CALL": 1, "PUT": -1, "BUY_SETUP": 1, "SELL_SETUP": -1, "BULLISH": 1, "BEARISH": -1, "ABOVE": 1, "BELOW": -1,
        "LONG": 1, "SHORT": -1, "BULL": 1, "BEAR": -1}


def main():
    df = pd.read_parquet(ROWS)
    df["year"] = df["session"].str[:4]
    numeric = [c for c in df.columns if c.startswith("x__") and df[c].notna().mean() >= 0.3 and df[c].nunique() > 2]
    labels = [c for c in df.columns if c.startswith("l__")]
    records = []
    for session, g in df.groupby("session"):
        if len(g) < MIN_TICKERS:
            continue
        year = g["year"].iloc[0]
        disc = g["l__direction"].map(SIGN) if "l__direction" in g else pd.Series(np.nan, index=g.index)
        for h in HORIZONS:
            net = g[f"fwd_{h}"] - g[f"fwd_{h}"].median()
            thesis = net * disc
            for c in numeric:
                ok = g[c].notna() & net.notna()
                if ok.sum() < MIN_TICKERS or g.loc[ok, c].nunique() < 3:
                    continue
                rec = {"session": session, "year": year, "input": c[3:], "kind": "NUMERIC", "horizon": h,
                       "ic_raw": stats.spearmanr(g.loc[ok, c], net[ok]).statistic}
                okt = ok & thesis.notna()
                if okt.sum() >= MIN_TICKERS:
                    rec["ic_thesis"] = stats.spearmanr(g.loc[okt, c], thesis[okt]).statistic
                records.append(rec)
            for c in labels:
                sign = g[c].map(SIGN)
                ok = sign.notna() & net.notna()
                if ok.sum() < MIN_TICKERS or sign[ok].nunique() < 2:
                    continue
                signed = sign[ok] * net[ok]
                records.append({"session": session, "year": year, "input": c[3:], "kind": "LABEL", "horizon": h,
                                "mean_signed_bps": float(signed.mean() * 1e4), "hit": float((signed > 0).mean()),
                                "share_positive_label": float((sign[ok] > 0).mean())})
    ps = pd.DataFrame(records)
    ps.to_csv(HERE / "direction_replay_per_session.csv", index=False)
    rows = []
    for (inp, kind, h), g in ps.groupby(["input", "kind", "horizon"]):
        overlap = math.ceil(h / STEP)
        for metric in (["ic_raw", "ic_thesis"] if kind == "NUMERIC" else ["mean_signed_bps"]):
            if metric not in g:
                continue
            sub = g[["year", metric]].dropna()
            v = sub[metric].to_numpy()
            if len(v) < 30:
                continue
            n_eff = len(v) / overlap
            sd = v.std(ddof=1)
            t = float(v.mean() / (sd / math.sqrt(n_eff))) if sd > 0 else 0.0
            p = float(2 * stats.t.sf(abs(t), df=max(1.0, n_eff - 1)))
            yearly = sub.groupby("year")[metric].mean()
            same_sign_years = int((np.sign(yearly) == np.sign(v.mean())).sum())
            row = {"input": inp, "kind": kind, "horizon": h, "metric": metric, "sessions": len(v), "mean": float(v.mean()),
                   "t": t, "p": p, "years": len(yearly), "same_sign_years": same_sign_years,
                   "yearly": {k: round(float(x), 4) for k, x in yearly.items()}}
            if kind == "LABEL":
                row["hit_rate"] = float(g["hit"].mean())
                row["share_positive_label"] = float(g["share_positive_label"].mean())
            rows.append(row)
    sm = pd.DataFrame(rows).sort_values("p").reset_index(drop=True)
    m = len(sm)
    sm["bh_threshold"] = FDR_Q * np.arange(1, m + 1) / m
    passed = sm["p"] <= sm["bh_threshold"]
    last = passed[passed].index.max() if passed.any() else -1
    sm["fdr_significant"] = sm.index <= last
    sm["evidence"] = np.where(sm["fdr_significant"] & (sm["same_sign_years"] >= 4), "ROBUST",
                              np.where(sm["fdr_significant"], "SIGNIFICANT_ONLY", "NO_EVIDENCE"))
    sm.to_csv(HERE / "direction_replay_evidence.csv", index=False)
    baselines = sm[sm["input"].str.startswith("baseline_past_return") & (sm["metric"] == "ic_raw")]
    payload = {
        "rows": int(len(df)), "sessions": int(df["session"].nunique()), "tickers": int(df["ticker"].nunique()),
        "first_session": df["session"].min(), "last_session": df["session"].max(), "tests": m,
        "evidence_counts": sm["evidence"].value_counts().to_dict(),
        "discovery_direction_labels": sm[(sm["kind"] == "LABEL")].head(40).to_dict("records"),
        "baselines": baselines.to_dict("records"),
        "robust_inputs": sm[sm["evidence"] == "ROBUST"].to_dict("records"),
    }
    (HERE / "direction_replay_evidence.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    cols = ["input", "kind", "horizon", "metric", "sessions", "mean", "t", "same_sign_years", "evidence"]
    print(json.dumps({k: payload[k] for k in ("rows", "sessions", "tickers", "first_session", "last_session", "tests", "evidence_counts")}, indent=1))
    print("== direction labels"); print(sm[sm["kind"] == "LABEL"].head(20)[cols + ["hit_rate"]].round(4).to_string(index=False))
    print("== baselines"); print(baselines[cols].round(4).to_string(index=False))
    print("== robust / significant numeric"); print(sm[(sm["kind"] == "NUMERIC") & (sm["evidence"] != "NO_EVIDENCE")].head(40)[cols].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
