"""S2 #1 design evidence (ACK 6 Oct 2026, "write the design for #1"): replay ONE governing-setup selection on a
frozen run, read-only, and measure what would change. Nothing in the pipeline is touched.

Proposed rule (design S2-1, section D1):
  trade-side live setups (lane table live_states), excluding any whose Outcome_Level is not ahead of the price on the
  trade side (LEVEL_ALREADY_PASSED); lane A before B before C; tested timeframe first; then ACTIVATED before DETECTED,
  higher holdout hit rate, more duration evidence (Duration_Level_N), nearer level, newer event (Age_Bars), and the
  Candidate_ID only as the last deterministic tie-break. That one setup sets the lane AND supplies the move level,
  duration evidence and invalidation.

    venv\\Scripts\\python.exe Enhancements\\assessment\\AVS_LAB_SOURCE_OF_TRUTH_20261006\\s2_lineage\\replay_governing_setup.py \\
        --run-id 20261006_060401
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from domain.structure_behaviour.trade_lane import candidate_lane, load_lanes  # noqa: E402

ORDER = {"A": 0, "B": 1, "C": 2}
SPB = json.loads((ROOT / "config" / "governed_constants_v1.json").read_text(encoding="utf-8"))
SPB = next(v["sessions_per_bar"] for v in [SPB.get("anticipated_move", {})] if "sessions_per_bar" in v) \
    if "sessions_per_bar" in SPB.get("anticipated_move", {}) else {"1d": 1.0, "1w": 5.0, "1mo": 21.0}


def _f(x):
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def govern(cands: list[dict], side: str, price: float, atr: float | None, table) -> dict:
    sign = 1 if side == "BULL" else -1
    untested = set(table["untested_timeframes"])
    best, passed = None, 0
    for c in cands:
        if c.get("Direction") != side:
            continue
        level = _f(c.get("Outcome_Level"))
        if level is not None and price is not None and sign * (level - price) <= 0:
            if str(c.get("Signal_State")).upper() in table["live_states"]:
                passed += 1
            continue
        lane = candidate_lane(c, table, price, atr)
        if not lane:
            continue
        hit = lane.get("hit") or [None, None]
        key = (ORDER[lane["lane"]], 1 if c.get("Timeframe") in untested else 0,
               0 if str(c.get("Signal_State")).upper() == "ACTIVATED" else 1,
               -(hit[1] or 0), -(_f(c.get("Duration_Level_N")) or 0),
               abs(level - price) if level is not None and price else 1e18,
               _f(c.get("Age_Bars")) or 1e9, str(c.get("Candidate_ID")))
        if best is None or key < best[0]:
            best = (key, lane, c)
    if best is None:
        return {"g_lane": "NO_LIVE_SETUP_AFTER_PASSED_FILTER" if passed else "NO_LIVE_SETUP", "g_passed_excluded": passed}
    _, lane, c = best
    spb = SPB.get(str(c.get("Timeframe")), None)
    q50, q80 = _f(c.get("Duration_Level_Q50_Bars")), _f(c.get("Duration_Level_Q80_Bars"))
    return {"g_lane": lane["lane"] if c.get("Timeframe") not in untested else "INTRADAY_ONLY_UNTESTED",
            "g_basis": lane["basis"], "g_candidate_id": c.get("Candidate_ID"), "g_tf": c.get("Timeframe"),
            "g_setup": f'{c.get("Timeframe")}|{c.get("Signal_Type")}|{c.get("Signal_State")}',
            "g_outcome_level": _f(c.get("Outcome_Level")), "g_invalidation": _f(c.get("Invalidation_Level")),
            "g_q50_sessions": None if q50 is None or spb is None else round(q50 * spb, 1),
            "g_q80_sessions": None if q80 is None or spb is None else round(q80 * spb, 1),
            "g_duration_status": c.get("Duration_Level_Status"), "g_passed_excluded": passed}


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--run-id", required=True)
    r = a.parse_args().run_id
    run = ROOT / "data" / "output" / "runs" / r
    table = load_lanes()
    cands = pd.read_csv(run / "discovery" / f"behavioural_candidates_{r}.csv", low_memory=False)
    by_ticker = {t: g.to_dict("records") for t, g in cands.groupby("Ticker")}
    mv_cols = ["ticker", "direction", "underlying_price", "morning_gate_verdict", "trade_lane", "trade_lane_setup",
               "thesis_event_timeframe", "thesis_outcome_level", "invalidation_spot",
               "anticipated_pays_state", "anticipated_sessions_q50", "atr_14", "atr"]
    mv_path = run / "morning_validation" / f"morning_validated_trades_{r}.csv"
    have = set(pd.read_csv(mv_path, nrows=0).columns)
    mv = pd.read_csv(mv_path, usecols=[c for c in mv_cols if c in have], low_memory=False)
    disc = pd.read_csv(run / "discovery" / f"discovery_candidates_ultimate_{r}.csv",
                       usecols=lambda c: c in ("ticker", "stock_price", "ATR_14", "thesis_event_candidate_id"), low_memory=False).drop_duplicates("ticker")
    mv = mv.merge(disc, on="ticker", how="left")          # the session close and ATR the lane was set with
    mv["underlying_price"] = mv["stock_price"]
    rows = []
    for _, x in mv.iterrows():
        side = {"CALL": "BULL", "PUT": "BEAR"}.get(str(x.direction).upper())
        if side is None:
            continue
        atr = _f(x.get("ATR_14"))
        g = govern(by_ticker.get(x.ticker, []), side, _f(x.underlying_price), atr, table)
        rows.append({**x.to_dict(), **g})
    df = pd.DataFrame(rows)
    df.to_csv(HERE / f"replay_governing_setup_{r}.csv", index=False)

    go = df[df.morning_gate_verdict == "GO"]
    px = go.underlying_price
    rep = {
        "rows_with_side": int(len(df)),
        "lane_now": df.trade_lane.value_counts(dropna=False).to_dict(),
        "lane_governed": df.g_lane.value_counts(dropna=False).to_dict(),
        "rows_with_a_passed_level_excluded": int((df.g_passed_excluded > 0).sum()),
        "GO_rows": int(len(go)),
        "GO_governed_lane": go.g_lane.value_counts(dropna=False).to_dict(),
        "GO_governed_timeframe": go.g_tf.value_counts(dropna=False).to_dict(),
        "GO_valued_setup_changes": int((go.g_candidate_id != go.thesis_event_candidate_id).sum()),
        "GO_governed_level_present": int(go.g_outcome_level.notna().sum()),
        "GO_unvalued_today_that_gain_a_level": go[go.anticipated_pays_state.isin(
            ["NOT_COMPUTED", "NOT_ASSESSED_VOLATILITY_ONLY"]) & go.g_outcome_level.notna()]["ticker"].tolist(),
        "GO_duration_evidence_status": go.g_duration_status.value_counts(dropna=False).to_dict(),
        "GO_q50_sessions_now_median": float(pd.to_numeric(go.anticipated_sessions_q50, errors="coerce").median()),
        "GO_q50_sessions_governed_median": float(pd.to_numeric(go.g_q50_sessions, errors="coerce").median()),
        "GO_invalidation_distance_pct_now_median": round(float(((go.invalidation_spot - px).abs() / px * 100).median()), 2),
        "GO_invalidation_distance_pct_governed_median": round(float(((go.g_invalidation - px).abs() / px * 100).median()), 2),
        "GO_move_to_level_pct_now_median": round(float(((go.thesis_outcome_level - px).abs() / px * 100).median()), 2),
        "GO_move_to_level_pct_governed_median": round(float(((go.g_outcome_level - px).abs() / px * 100).median()), 2),
    }
    (HERE / f"replay_governing_setup_{r}.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    print(json.dumps(rep, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
