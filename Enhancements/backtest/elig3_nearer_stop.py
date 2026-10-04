"""S-ELIG-3 (scenario register, ACK 20 Sep 2026): STOP_TOO_DISTANT_NO_TARGET rows with a nearer
structural stop (most recent swing high), underlying.

Definition (frozen, SCENARIO_REGISTER_20260919.md line 336): "STOP_TOO_DISTANT_NO_TARGET rows with a
nearer structural stop (most recent swing high), underlying."

D2 context: 42 PUT rows (18 Sep sample), stop a median 44% above price, no usable 3R target - current
production behaviour is to flag for manual review, not invent a nearer stop. D2's two options: keep
flagged (current) vs. use a nearer structural level (last swing high) instead of the wide stop Discovery
currently computes.

Population: replicates thesis_geometry_review's own STOP_TOO_DISTANT_NO_TARGET condition exactly, by
calling the production function _governed_structural_target() (imported, not reimplemented) over discovery
output from the same run folders used for S-DIR-3 (15 Aug - 19 Sep 2026, 22 runs with usable discovery
data). One known fidelity gap: l1_far (layer1__scenarios__conditional_far__trigger_price) is not present
in historical discovery/vanguard CSVs and is passed as None - this only matters for the narrow case where
Discovery's own target is absent AND an L1 far-trigger price would have been usable, which is a fallback
below Discovery target in the function's own preference order.

Swing high/low: the most recent CONFIRMED local pivot in the 60 sessions before entry - a session whose
high (low, for CALLs) is the max (min) of a +/-3-session window - point-in-time safe (the pivot session
must be at least 3 sessions before entry, so its confirmation never uses data unavailable at entry time).

For rows where the nearer stop makes a 3R target usable, "the underlying" = whether the nearer stop or the
new 3R target was touched (high/low, not close) first within 20 sessions after entry.
"""
from __future__ import annotations

import sys
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
RUNS = REPO / "data" / "output" / "runs"
PRICES = REPO / "data" / "canonical" / "historical_prices.sqlite"
OUT = Path(__file__).resolve().parent / "elig3_nearer_stop.json"

from scripts.avshunter_options_intelligence import _governed_structural_target  # noqa: E402

PIVOT_K = 3
SWING_LOOKBACK = 60
HOLD_HORIZON = 20


def _run_ids() -> list[str]:
    return sorted(p.name for p in RUNS.iterdir() if p.is_dir() and p.name[:8].isdigit() and len(p.name) >= 15)


def load_run_candidates(run_id: str) -> pd.DataFrame:
    disc_path = RUNS / run_id / "discovery" / f"discovery_candidates_ultimate_{run_id}.csv"
    if not disc_path.is_file():
        return pd.DataFrame()
    d = pd.read_csv(disc_path, low_memory=False)
    need = {"ticker", "direction", "entry_price", "structural_stop", "structural_target"}
    if not need.issubset(d.columns):
        return pd.DataFrame()
    out = d[["ticker", "direction", "entry_price", "structural_stop", "structural_target"]].dropna(
        subset=["ticker", "direction", "entry_price", "structural_stop"]).drop_duplicates("ticker").copy()
    out["run_id"] = run_id
    out["session"] = pd.to_datetime(run_id[:8], format="%Y%m%d").strftime("%Y-%m-%d")
    return out


def classify(rows: pd.DataFrame) -> pd.DataFrame:
    states, targets = [], []
    for r in rows.itertuples(index=False):
        entry = float(r.entry_price)
        stop = float(r.structural_stop)
        stop_dist = abs(entry - stop)
        dtgt = float(r.structural_target) if pd.notna(r.structural_target) else None
        if dtgt is not None and (not np.isfinite(dtgt) or dtgt <= 0):
            dtgt = None
        tgt, state = _governed_structural_target(r.direction, entry, dtgt, None, stop_dist)
        states.append(state)
        targets.append(tgt)
    rows = rows.copy()
    rows["structural_target_state"] = states
    rows["governed_target"] = targets
    return rows


def load_bars(tickers) -> dict[str, pd.DataFrame]:
    con = sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)
    q = (f"SELECT ticker, trading_date, high, low, close FROM ohlcv_daily WHERE ticker IN "
         f"({','.join('?' * len(tickers))}) AND trading_date >= '2026-05-01' AND trading_date <= '2026-09-19' "
         "ORDER BY trading_date")
    f = pd.read_sql_query(q, con, params=tuple(tickers))
    con.close()
    return {t: g.reset_index(drop=True) for t, g in f.groupby("ticker")}


def swing_level(bars: pd.DataFrame, asof_session: str, direction: str) -> float | None:
    """Most recent confirmed pivot high (PUT stop) / pivot low (CALL stop) strictly before asof_session."""
    idx = bars[bars.trading_date < asof_session].index
    if len(idx) == 0:
        return None
    last = idx[-1]
    lo = max(0, last - SWING_LOOKBACK)
    col = "high" if direction == "PUT" else "low"
    window = bars.iloc[lo:last + 1]
    # scan backward for the most recent confirmed pivot (needs PIVOT_K bars on each side, all <= last)
    for i in range(last - PIVOT_K, lo - 1, -1):
        if i - PIVOT_K < lo:
            break
        seg = bars.iloc[i - PIVOT_K:i + PIVOT_K + 1]
        center = bars.at[i, col]
        if direction == "PUT" and center == seg["high"].max() and (seg["high"] < center).sum() >= len(seg) - 1:
            return float(center)
        if direction == "CALL" and center == seg["low"].min() and (seg["low"] > center).sum() >= len(seg) - 1:
            return float(center)
    return None


def touch_outcome(bars: pd.DataFrame, asof_session: str, direction: str, entry: float, stop: float,
                  target: float) -> str | None:
    idx = bars[bars.trading_date > asof_session].index
    if len(idx) == 0:
        return None
    fwd = bars.loc[idx[:HOLD_HORIZON]]
    if fwd.empty:
        return None
    for _, row in fwd.iterrows():
        if direction == "PUT":
            stop_hit = row["high"] >= stop
            target_hit = row["low"] <= target
        else:
            stop_hit = row["low"] <= stop
            target_hit = row["high"] >= target
        if stop_hit and target_hit:
            return "AMBIGUOUS_SAME_DAY"
        if stop_hit:
            return "STOP_FIRST"
        if target_hit:
            return "TARGET_FIRST"
    return "NEITHER_WITHIN_HORIZON"


def main() -> int:
    run_ids = _run_ids()
    frames = [load_run_candidates(r) for r in run_ids]
    frames = [f for f in frames if not f.empty]
    all_rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    print(f"runs scanned: {len(run_ids)} | runs with usable discovery data: {len(frames)} | rows: {len(all_rows)}")
    if all_rows.empty:
        return 1

    all_rows = all_rows[all_rows["direction"].isin(["CALL", "PUT"])]
    classified = classify(all_rows)
    pop = classified[classified["structural_target_state"] == "TARGET_3R_NON_POSITIVE"].drop_duplicates(
        subset=["ticker", "session"]).copy()
    print(f"STOP_TOO_DISTANT_NO_TARGET rows (deduped): {len(pop)} | direction split: "
          f"{pop['direction'].value_counts().to_dict()}")

    bars_by_ticker = load_bars(sorted(pop["ticker"].unique()))

    alt_stops, alt_states, alt_targets, outcomes = [], [], [], []
    for r in pop.itertuples(index=False):
        bars = bars_by_ticker.get(r.ticker)
        if bars is None or bars.empty:
            alt_stops.append(None); alt_states.append(None); alt_targets.append(None); outcomes.append(None)
            continue
        alt_stop = swing_level(bars, r.session, r.direction)
        if alt_stop is None:
            alt_stops.append(None); alt_states.append(None); alt_targets.append(None); outcomes.append(None)
            continue
        entry = float(r.entry_price)
        alt_dist = abs(entry - alt_stop)
        dtgt = float(r.structural_target) if pd.notna(r.structural_target) else None
        if dtgt is not None and (not np.isfinite(dtgt) or dtgt <= 0):
            dtgt = None
        alt_tgt, alt_state = _governed_structural_target(r.direction, entry, dtgt, None, alt_dist)
        alt_stops.append(alt_stop); alt_states.append(alt_state); alt_targets.append(alt_tgt)
        if alt_state == "TARGET_3R" and alt_tgt is not None:
            outcomes.append(touch_outcome(bars, r.session, r.direction, entry, alt_stop, alt_tgt))
        else:
            outcomes.append(None)

    pop = pop.copy()
    pop["alt_stop"] = alt_stops
    pop["alt_target_state"] = alt_states
    pop["alt_target"] = alt_targets
    pop["outcome"] = outcomes

    n_resolved = int(pop["alt_target_state"].eq("TARGET_3R").sum())
    print(f"nearer-stop rows where a swing pivot was found: {pop['alt_stop'].notna().sum()} | "
          f"of those, 3R target becomes usable: {n_resolved}")

    outcome_counts = pop["outcome"].value_counts(dropna=True).to_dict()
    tested = pop[pop["outcome"].notna()]
    stop_first = int((tested["outcome"] == "STOP_FIRST").sum())
    target_first = int((tested["outcome"] == "TARGET_FIRST").sum())
    resolved_n = stop_first + target_first
    win_rate = round(target_first / resolved_n, 4) if resolved_n else None

    result = {
        "scenario": "S-ELIG-3",
        "population": f"discovery output from {len(frames)} run folders, 15 Aug - 19 Sep 2026 "
                       "(STOP_TOO_DISTANT_NO_TARGET rows, thesis_geometry_review's own rule replicated "
                       "via _governed_structural_target, l1_far omitted - not present historically)",
        "n_stop_too_distant_rows": int(len(pop)),
        "direction_split": pop["direction"].value_counts().to_dict(),
        "n_with_swing_pivot_found": int(pop["alt_stop"].notna().sum()),
        "n_where_nearer_stop_makes_3r_usable": n_resolved,
        "outcome_counts": outcome_counts,
        "stop_first_excl_ambiguous": stop_first,
        "target_first_excl_ambiguous": target_first,
        "win_rate_target_first_vs_stop_first": win_rate,
    }
    OUT.write_text(__import__("json").dumps(result, indent=2, default=str))
    print(f"Written: {OUT}\n")
    print(f"outcome counts: {outcome_counts}")
    print(f"win rate (target-first / (target-first+stop-first), excl. ambiguous/neither): {win_rate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
