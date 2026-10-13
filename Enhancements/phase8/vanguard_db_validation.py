"""Vanguard validated against the actuarial database, not outcomes (ACK 12 Oct 2026). Read-only.

Vanguard's job: for each ticker's current state, retrieve the right history from the v7 actuarial database. This checks
its inputs and execution on the live Evening 20261010_191314:
1. Inputs - each of the ten matching dimensions Vanguard used (layer2__outcomes__original_state_key) against the value
   the database's own labeller gives on the same ticker's bars (actuarial_core_v7.calculate_core_state, last
   completed session 2026-10-09, canonical historical_prices.sqlite).
2. Execution - the key Vanguard matched (layer2__outcomes__matched_state_key) and the cohort it published (sample size,
   win rate) against the same cohort recomputed directly from the database.
3. The database itself - how far cohort win rates spread across the states Vanguard can match (can a state carry
   information at all), and the side the published rate describes.
Writes vanguard_db_validation.json beside this file.
"""
from __future__ import annotations

import contextlib
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from vanguard.core.actuarial_core_v7 import calculate_core_state, compute_technicals  # noqa: E402

RUN, SESSION = "20261010_191314", "2026-10-09"
DB = Path(r"C:\Users\ACKVerissimo\vanguard\data\actuarial_database_v7.parquet")
DIMS = ["vol_regime", "trend_direction", "structure_quality", "phase_v2", "momentum_bucket", "location_bucket",
        "wyckoff_phase_bucket", "trend_maturity", "iv_regime", "crabel_state"]


def parse_key(key) -> dict:
    out = {}
    for part in str(key or "").split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v
    return out


vg = pd.read_csv(ROOT / "data/output/runs" / RUN / "vanguard" / "vanguard_signals.csv", low_memory=False)
vg["ticker"] = vg["ticker"].astype(str).str.upper()
res: dict = {"run": RUN, "session": SESSION, "rows": len(vg)}

# 1. Inputs: live dimension values vs the database labeller on the same bars
with contextlib.closing(sqlite3.connect(f"file:{(ROOT / 'data/canonical/historical_prices.sqlite').as_posix()}?mode=ro", uri=True)) as conn:
    bars = pd.read_sql_query(
        "SELECT ticker, trading_date AS date, open, high, low, close, volume FROM ohlcv_daily "
        "WHERE trading_date <= ? AND trading_date >= ? ORDER BY ticker, trading_date",
        conn, params=(SESSION, "2025-06-01"))
bars["ticker"] = bars["ticker"].str.upper()
grouped = {t: g.drop(columns="ticker").reset_index(drop=True) for t, g in bars.groupby("ticker")}
agree, compared, missing_live, builder_none, examples = Counter(), Counter(), Counter(), 0, {}
for row in vg.itertuples():
    live = parse_key(row.layer2__outcomes__original_state_key)
    g = grouped.get(row.ticker)
    if g is None or len(g) <= 60:
        builder_none += 1
        continue
    tech = compute_technicals(g, last_rank_only=True)
    db = calculate_core_state(tech, len(tech) - 1)
    if db is None or str(db.get("date"))[:10] != SESSION:
        builder_none += 1
        continue
    for d in DIMS:
        lv = live.get(d)
        if lv in (None, "*", "", "nan"):
            missing_live[d] += 1
            continue
        compared[d] += 1
        if str(lv).upper() == str(db[d]).upper():
            agree[d] += 1
        elif d not in examples:
            examples[d] = {"ticker": row.ticker, "vanguard": lv, "database_labeller": db[d]}
res["inputs"] = {d: {"compared": compared[d], "agree": agree[d],
                     "agree_pct": round(agree[d] / compared[d], 3) if compared[d] else None,
                     "wildcard_or_missing_in_vanguard": missing_live[d]} for d in DIMS}
res["inputs_builder_not_computable"] = builder_none
res["inputs_disagreement_examples"] = examples

# 2. Execution: the published cohort against the same cohort recomputed from the database
cols = DIMS + ["date", "mature_20d", "outcome_20d_return"]
dbf = pd.read_parquet(DB, columns=cols)
dbf = dbf[dbf["mature_20d"].astype(bool)]
dbf["win"] = (pd.to_numeric(dbf["outcome_20d_return"], errors="coerce") > 0).astype(int)
base_win = float(dbf["win"].mean())
full = dbf.groupby(DIMS, dropna=False, observed=True).agg(n=("win", "size"), wins=("win", "sum")).reset_index()
cache: dict = {}


def cohort(key_dims: dict):
    k = tuple(sorted(key_dims.items()))
    if k not in cache:
        m = pd.Series(True, index=full.index)
        for d, v in key_dims.items():
            if d in DIMS:
                m &= full[d].astype(str).str.upper() == str(v).upper()
        sub = full[m]
        n = int(sub["n"].sum())
        cache[k] = (n, float(sub["wins"].sum() / n) if n else None)
    return cache[k]


rows = []
for row in vg.itertuples():
    kd = parse_key(row.layer2__outcomes__matched_state_key)
    n, wr = cohort({d: v for d, v in kd.items() if v not in ("*", "")})
    rows.append({"ticker": row.ticker, "method": row.layer2__outcomes__state_match_method,
                 "pub_n": pd.to_numeric(row.layer2__outcomes__sample_size, errors="coerce"),
                 "pub_wr": pd.to_numeric(row.layer2__outcomes__win_rate, errors="coerce"),
                 "db_n": n, "db_wr": wr, "dims_used": len(kd)})
ex = pd.DataFrame(rows)
ex["n_ratio"] = ex["pub_n"] / ex["db_n"].replace(0, np.nan)
ex["wr_diff_pts"] = (ex["pub_wr"] - ex["db_wr"]) * 100
res["execution"] = {
    "db_mature_rows": int(len(dbf)), "db_base_win_rate_20d": round(base_win, 4),
    "published_n_equals_db_n": int((ex["pub_n"] == ex["db_n"]).sum()),
    "n_ratio_q": ex["n_ratio"].describe().round(3).to_dict(),
    "win_rate_diff_pts_q": ex["wr_diff_pts"].describe().round(2).to_dict(),
    "abs_win_rate_diff_over_1pt": int((ex["wr_diff_pts"].abs() > 1).sum()),
    "by_method": {m: {"rows": int(len(g)), "median_n_ratio": round(float(g["n_ratio"].median()), 3),
                      "median_abs_wr_diff_pts": round(float(g["wr_diff_pts"].abs().median()), 2)}
                  for m, g in ex.groupby("method")},
    "worst_examples": ex.reindex(ex["wr_diff_pts"].abs().sort_values(ascending=False).index).head(5).to_dict("records"),
}

# 3. The database: spread of cohort win rates across the states Vanguard can match (full ten-dimension states)
big = full[full["n"] >= 60].copy()
big["wr"] = big["wins"] / big["n"]
w = np.repeat(big["wr"].values, big["n"].values.astype(int)) if len(big) else np.array([])
res["database"] = {
    "states_with_n_ge_60": int(len(big)), "rows_in_them": int(big["n"].sum()),
    "state_win_rate_q_weighted": {q: round(float(np.quantile(w, q)), 4) for q in (0.05, 0.25, 0.5, 0.75, 0.95)} if len(w) else None,
    "published_cohort_win_rate_q": ex["pub_wr"].describe().round(4).to_dict(),
    "published_rate_is_upside_only": "win_rate = P(20d return > 0); for a BEAR thesis the favourable rate is 1 - win_rate",
}
side = vg.get("thesis__side", pd.Series(dtype=str)).astype("string").str.upper()
fav = pd.to_numeric(vg.get("side_assigned__p_close_favourable_20d"), errors="coerce")
res["side_check"] = {
    "bear_rows": int((side == "BEAR").sum()),
    "bear_side_rate_equals_1_minus_win_rate": int(((side == "BEAR") & ((fav - (1 - ex["pub_wr"])).abs() < 0.01)).sum()),
    "bull_side_rate_equals_win_rate": int(((side == "BULL") & ((fav - ex["pub_wr"]).abs() < 0.01)).sum()),
    "bull_rows": int((side == "BULL").sum()),
}
Path(__file__).with_suffix(".json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
print(json.dumps(res, indent=1, default=str))
