"""S-DIR-3 (scenario register, ACK 20 Sep 2026): structure wins vs governed direction wins.

Definition (frozen, SCENARIO_REGISTER_20260919.md line 271-272): "For DIRECTION_CONTRADICTS_STRUCTURE rows,
measure the underlying move in both directions. U, N -> the direction-conflict decision."

Population note: true continuous 5-year "U" Wyckoff labelling does not exist - wyckoff_mode is a live
Discovery computation, only ever produced for (ticker, session) pairs that actually appeared in a pipeline
run. There is no standing replay engine that relabels raw 5-year bars with Wyckoff structure (building one
is a materially larger project, out of scope for this scenario). The best available U-style substitute,
used here, is every dated run folder's own discovery + options output still on disk
(data/output/runs/<run_id>/), reusing the exact loading pattern fx_extreme_winner_forensics.py already
built for this (DISCOVERY_FIELDS, load_run_state). That spans 2026-08-15 to 2026-09-19 (43 runs) - real,
live-computed data, not reconstructed, but a 5-week window rather than 5 years. Labelled as such throughout.

Conflict rule replicated exactly from thesis_geometry_review() (scripts/avshunter_options_intelligence.py,
_STRUCTURE_SIDE = {"ACCUMULATION": "CALL", "DISTRIBUTION": "PUT"}): a row conflicts when its governed
direction is not the side implied by its Wyckoff mode.

For each conflicting row, "the underlying move in both directions" = the realised forward return of the
underlying over fixed horizons, signed once for the governed direction and once for the structure-implied
direction (they are mirror images: structure_return = -governed_return). The comparison is which side
would have been profitable, not a magnitude claim.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import ttest_1samp

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "data" / "output" / "runs"
PRICES = REPO / "data" / "canonical" / "historical_prices.sqlite"
OUT = Path(__file__).resolve().parent / "dir3_structure_conflict.json"

_STRUCTURE_SIDE = {"ACCUMULATION": "CALL", "DISTRIBUTION": "PUT"}  # must match thesis_geometry_review()
HORIZONS = (5, 10, 20)


def _run_ids() -> list[str]:
    out = []
    for p in sorted(RUNS.iterdir()):
        if p.is_dir() and p.name[:8].isdigit() and len(p.name) >= 15:
            out.append(p.name)
    return out


def load_run_candidates(run_id: str) -> pd.DataFrame:
    disc_path = RUNS / run_id / "discovery" / f"discovery_candidates_ultimate_{run_id}.csv"
    opt_path = RUNS / run_id / "options" / f"options_intelligence_{run_id}.csv"
    if not disc_path.is_file() or not opt_path.is_file():
        return pd.DataFrame()
    disc = pd.read_csv(disc_path, low_memory=False)
    opt = pd.read_csv(opt_path, low_memory=False)
    if "wyckoff_mode" not in disc.columns:
        return pd.DataFrame()
    direction_col = next((c for c in ("governed_direction", "final_direction", "options_direction", "direction")
                          if c in opt.columns), None)
    if direction_col is None:
        return pd.DataFrame()
    session_col = next((c for c in ("session", "as_of_session", "evidence_session_date") if c in opt.columns), None)
    d = disc[["ticker", "wyckoff_mode"]].drop_duplicates("ticker")
    o_cols = ["ticker", direction_col] + ([session_col] if session_col else [])
    o = opt[o_cols].drop_duplicates("ticker").rename(columns={direction_col: "direction"})
    merged = o.merge(d, on="ticker", how="inner")
    merged["run_id"] = run_id
    if session_col:
        merged = merged.rename(columns={session_col: "session"})
    else:
        merged["session"] = run_id[:8]
        merged["session"] = pd.to_datetime(merged["session"], format="%Y%m%d").dt.strftime("%Y-%m-%d")
    return merged


def forward_returns(pairs: pd.DataFrame) -> pd.DataFrame:
    """pairs: columns ticker, session. Adds fwd_ret_{h} = close[session+h sessions] / close[session] - 1."""
    con = sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)
    tickers = tuple(sorted(pairs["ticker"].unique()))
    if not tickers:
        return pairs
    q = ("SELECT ticker, trading_date, close FROM ohlcv_daily WHERE ticker IN "
         f"({','.join('?' * len(tickers))}) AND trading_date >= '2026-08-01' AND trading_date <= '2026-09-19'")
    f = pd.read_sql_query(q, con, params=tickers)
    con.close()
    close = f.pivot_table(index="trading_date", columns="ticker", values="close", aggfunc="last").sort_index()
    idx = close.index.to_list()
    out = pairs.copy()
    for h in HORIZONS:
        vals = []
        for _, row in out.iterrows():
            s, t = row["session"], row["ticker"]
            if s not in idx or t not in close.columns:
                vals.append(np.nan)
                continue
            i = idx.index(s)
            if i + h >= len(idx):
                vals.append(np.nan)
                continue
            p0, p1 = close.loc[idx[i], t], close.loc[idx[i + h], t]
            vals.append((p1 / p0 - 1.0) if (p0 and np.isfinite(p0) and p0 > 0) else np.nan)
        out[f"fwd_ret_{h}"] = vals
    return out


def main() -> int:
    run_ids = _run_ids()
    frames = [load_run_candidates(r) for r in run_ids]
    frames = [f for f in frames if not f.empty]
    all_rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    print(f"runs scanned: {len(run_ids)} | runs with usable discovery+options: {len(frames)} | "
          f"candidate rows: {len(all_rows)}")
    if all_rows.empty:
        print("No usable rows - aborting.")
        return 1

    all_rows = all_rows[all_rows["direction"].isin(["CALL", "PUT"])].copy()
    all_rows["structure_implied"] = all_rows["wyckoff_mode"].map(_STRUCTURE_SIDE)
    conflict = all_rows[all_rows["structure_implied"].notna() &
                         (all_rows["structure_implied"] != all_rows["direction"])].copy()
    print(f"directional rows: {len(all_rows)} | DIRECTION_CONTRADICTS_STRUCTURE rows: {len(conflict)}")

    conflict = conflict.drop_duplicates(subset=["ticker", "session"])
    conflict = forward_returns(conflict[["ticker", "session", "direction", "structure_implied", "wyckoff_mode", "run_id"]])

    result = {
        "scenario": "S-DIR-3",
        "population": f"discovery+options output from {len(frames)} run folders, 2026-08-15 to 2026-09-19 "
                       "(not a full 5-year U replay - see module docstring)",
        "n_directional_rows": int(len(all_rows)),
        "n_conflict_rows_deduped": int(len(conflict)),
        "horizons": {},
    }
    for h in HORIZONS:
        col = f"fwd_ret_{h}"
        d = conflict[["direction", col]].dropna()
        if d.empty:
            continue
        sign = np.where(d["direction"] == "CALL", 1.0, -1.0)
        governed_ret = sign * d[col]
        structure_ret = -governed_ret
        # governed_ret and structure_ret are deterministic mirrors of each other (not independent samples),
        # so the only meaningful test is whether governed_ret's mean is significantly different from zero -
        # equivalent to asking whether either side has a real edge on this population.
        t_stat, p_val = ttest_1samp(governed_ret, 0.0)
        unique_tickers = int(d.index.to_series().map(lambda i: conflict.loc[i, "ticker"]).nunique())
        result["horizons"][str(h)] = {
            "n": int(len(d)),
            "unique_tickers": unique_tickers,
            "governed_direction_mean_return": round(float(governed_ret.mean()), 4),
            "governed_direction_win_rate": round(float((governed_ret > 0).mean()), 4),
            "structure_direction_mean_return": round(float(structure_ret.mean()), 4),
            "structure_direction_win_rate": round(float((structure_ret > 0).mean()), 4),
            "t_stat_governed_vs_zero": round(float(t_stat), 3),
            "p_value": round(float(p_val), 6),
        }

    OUT.write_text(__import__("json").dumps(result, indent=2))
    print(f"Written: {OUT}\n")
    for h, r in result["horizons"].items():
        print(f"horizon={h}d  n={r['n']:4d} ({r['unique_tickers']} unique tickers)  "
              f"governed: mean={r['governed_direction_mean_return']:+.4f} win={r['governed_direction_win_rate']:.3f}  |  "
              f"structure: mean={r['structure_direction_mean_return']:+.4f} win={r['structure_direction_win_rate']:.3f}  |  "
              f"t={r['t_stat_governed_vs_zero']:+.2f} p={r['p_value']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
