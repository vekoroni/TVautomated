r"""POST-HOC robustness check (7 Oct 2026), NOT pre-registered - labelled exploratory.

The pre-registered magnitude event (±3 x current ATR) is scaled by the variable M1 selects on (a compressed current
ATR), so part of M1's result is mechanical volatility mean reversion. This check rescales the event by each name's
NORMAL volatility - the median ATR(14) of its previous 250 sessions - and the move-vs-volatility ratio by its
previous-250-session realised volatility. Same cuts, universe and M1/M2 flags as magnitude_strength_study.py.

    venv\Scripts\python.exe Enhancements\direction_evidence\magnitude_posthoc_normal_vol.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "survivorship"))

from measure_survivorship import entity_map, load_bars, load_reference  # noqa: E402
from top_down_bias_study import boot, first_passage, lag  # noqa: E402

CUT_STEP, BLOCK_CUTS, LOOKBACK = 10, 6, 252


def main():
    rec = pd.read_parquet(HERE / "magnitude_strength_records_20261007.parquet")
    raw = load_bars()
    raw["date"] = pd.to_datetime(raw["date"]).astype("datetime64[ns]")
    active, dl = load_reference(raw.groupby("ticker")["date"].max())
    bars = entity_map(raw, active, dl)
    del raw
    wide = {k: bars.pivot(index="date", columns="entity", values=k).astype("float64") for k in ("high", "low", "close")}
    dates, ents = wide["close"].index, wide["close"].columns
    H, L, C = (wide[k].to_numpy() for k in ("high", "low", "close"))
    atr = pd.DataFrame(np.fmax(H - L, np.fmax(np.abs(H - lag(C, 1)), np.abs(L - lag(C, 1))))) \
        .rolling(14, min_periods=14).mean()
    atr_normal = atr.rolling(250, min_periods=200).median().shift(1).to_numpy()
    logret = pd.DataFrame(np.log(C / lag(C, 1)))
    rv_normal = logret.rolling(250, min_periods=200).std().shift(1).to_numpy()
    pos = {d.strftime("%Y-%m-%d"): i for i, d in enumerate(dates)}
    col_of = {e: j for j, e in enumerate(ents)}
    out = []
    for r in rec.itertuples(index=False):
        i, j = pos[r.cut], col_of[r.entity]
        a = atr_normal[i, j]
        if not np.isfinite(a) or a <= 0:
            continue
        o = first_passage(H, L, C, i, j, 3, 20, a, "hl")
        end = i + 20
        ret20 = C[end, j] / C[i, j] - 1 if end < len(dates) else np.nan
        out.append({"cut": r.cut, "block": r.block, "entity": r.entity, "m1": r.m1, "m1_key": r.m1_rank_key,
                    "m2": r.m2, "m2_key": r.m2_rank_key, "o": o,
                    "mvv_n": abs(ret20) / (rv_normal[i, j] * np.sqrt(20)) if np.isfinite(rv_normal[i, j]) else np.nan})
    d = pd.DataFrame(out)
    d = d[d["o"].isin(["UP", "DOWN", "AMBIGUOUS", "NEITHER"])].copy()
    d["big"] = (d["o"] != "NEITHER").astype(float)
    d["big_ex"] = d["big"] - d["cut"].map(d.groupby("cut")["big"].mean())
    d["mvv_ex"] = d["mvv_n"] - d["cut"].map(d.groupby("cut")["mvv_n"].mean())
    report = {"label": "POST_HOC_EXPLORATORY_NOT_PREREGISTERED", "base_rate": round(float(d["big"].mean()), 4)}
    for sig, key, asc in (("m1", "m1_key", True), ("m2", "m2_key", False)):
        f = d[d[sig]].sort_values(["cut", key, "entity"], ascending=[True, asc, True])
        f["rank"] = f.groupby("cut").cumcount() + 1
        t = f[f["rank"] <= 100].sort_values(["entity", "cut"])
        cutn = t["cut"].map({c: n for n, c in enumerate(sorted(d["cut"].unique()))})
        same = t.groupby("entity")["cut"].shift(1).map({c: n for n, c in enumerate(sorted(d["cut"].unique()))}) == cutn - 1
        ep = t[~same]
        report[sig] = {"top100_big_rate": round(float(ep["big"].mean()), 4),
                       "top100_big_excess": boot(ep["big_ex"], ep["block"]),
                       "top100_move_vs_normal_vol_excess": boot(ep["mvv_ex"].dropna(), ep.dropna(subset=["mvv_ex"])["block"]),
                       "all_flagged_big_excess": boot(f["big_ex"], f["block"])}
    (HERE / "magnitude_posthoc_normal_vol_20261007.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
