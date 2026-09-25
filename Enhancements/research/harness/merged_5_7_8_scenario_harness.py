#!/usr/bin/env python
"""Research harness: merged Model 5 (event/scenario repricing) + Model 7 (execution friction)
+ Model 8 (net payoff and decision), run against a COMPLETED pipeline run.

State: EXPLORATORY_NO_AUTHORITY. Read-only. It never imports pipeline entry points,
never opens a database, never writes under data/. Output goes to Enhancements/research/output/.

Sources of the method:
  - ALG-04 scenario_valuation_v2 (docs/requirements/AVS-REQ-FIX-002_Annex_A_algorithms_and_models.md)
  - friction_model_v1: entry at ask, exit haircut = min(spread_fraction_mid / 2, 0.15)
  - ALG-07 calibrated_utility_v2 shape: p_T * payoff_reach + p_I * payoff_inval + p_O * payoff_flat
  - AVS-RANK-001 §3 normal-density grid as the probability-free alternative
The BSM pricer is a self-contained replica (r configurable, q = 0), cross-checked against the
ALG-04 worked example by --selftest. It is not the production pricer and carries no authority.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HARNESS_VERSION = "merged_5_7_8_harness_v0.1"
SESSIONS_PER_YEAR = 252
CAL_PER_SESSION = 365.0 / 252.0
FRICTION_CAP = 0.15
REACHABLE_K = 1.5
IV_STRESSES = {"CONTRACTED": 0.8, "BASE": 1.0, "EXPANDED": 1.2}
HORIZON_TO_HOLD = {"1_5D": 5, "6_10D": 10, "11_20D": 20}
GRID_SIGMAS = (-3, -2, -1, 0, 1, 2, 3)


# ── pricing ────────────────────────────────────────────────────────────────────
def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bsm(side: str, s: float, k: float, t_years: float, sigma: float, r: float) -> float:
    """European BSM with q = 0. T <= 0 or sigma <= 0 degrade to intrinsic."""
    if t_years <= 0 or sigma <= 0:
        return max(s - k, 0.0) if side == "CALL" else max(k - s, 0.0)
    sq = sigma * math.sqrt(t_years)
    d1 = (math.log(s / k) + (r + 0.5 * sigma * sigma) * t_years) / sq
    d2 = d1 - sq
    if side == "CALL":
        return s * _ncdf(d1) - k * math.exp(-r * t_years) * _ncdf(d2)
    return k * math.exp(-r * t_years) * _ncdf(-d2) - s * _ncdf(-d1)


def _num(v):
    try:
        if v in (None, "", "null"):
            return None
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


# ── one row ────────────────────────────────────────────────────────────────────
def value_row(row: dict, r: float, hold_source: str = "planned", bias: float = 1.0) -> dict:
    out = {
        "harness_version": HARNESS_VERSION,
        "ticker": row.get("ticker"),
        "lab_verdict": row.get("lab_verdict"),
        "contract_symbol": row.get("selected_contract_symbol"),
        "direction": str(row.get("options_direction") or row.get("final_direction") or row.get("direction") or "").upper(),
        "hidden_state_label": row.get("hidden_state_label"),
        "phase": row.get("phase"),
        "time_horizon": row.get("time_horizon"),
        "applicability": "OK",
        "reason": "",
    }
    side = out["direction"]
    spot = _num(row.get("underlying_price"))
    strike = _num(row.get("strike"))
    dte = _num(row.get("contract_dte")) or _num(row.get("dte"))
    iv = _num(row.get("contract_iv"))
    bid = _num(row.get("contract_bid"))
    ask = _num(row.get("contract_ask"))
    target = _num(row.get("structural_target")) or _num(row.get("target_price"))
    inval = _num(row.get("invalidation_price"))
    vol = _num(row.get("garch_forecast_vol"))
    horizon_hold = HORIZON_TO_HOLD.get(str(row.get("time_horizon") or "").upper(), 0)
    planned_hold = int(_num(row.get("planned_hold_sessions")) or 0)
    hold = planned_hold if hold_source == "planned" and planned_hold else horizon_hold
    out["hold_source"] = "planned_hold_sessions" if (hold_source == "planned" and planned_hold) else "time_horizon_bucket"

    missing = [n for n, v in (("spot", spot), ("strike", strike), ("dte", dte), ("iv", iv), ("bid", bid),
                              ("ask", ask), ("target", target), ("invalidation", inval), ("forecast_vol", vol)) if v is None]
    if side not in {"CALL", "PUT"}:
        missing.append("direction")
    if hold < 1 or hold > 20:
        missing.append("hold_sessions")
    if missing:
        out.update(applicability="INDETERMINATE", reason="MISSING:" + ",".join(missing))
        return out
    if bid <= 0 or ask <= bid:
        out.update(applicability="INDETERMINATE", reason="QUOTE_NOT_TWO_SIDED")
        return out
    if hold * CAL_PER_SESSION >= dte:
        out.update(applicability="INDETERMINATE", reason="HOLD_BEYOND_EXPIRY")
        return out
    fav_ok = (target > spot) if side == "CALL" else (target < spot)
    inv_ok = (inval < spot) if side == "CALL" else (inval > spot)
    if not fav_ok or not inv_ok:
        out.update(applicability="INDETERMINATE", reason="GEOMETRY_WRONG_SIDE")
        return out

    # Model 7 — friction_model_v1
    mid = 0.5 * (bid + ask)
    s_frac = (ask - bid) / mid
    haircut = min(s_frac / 2.0, FRICTION_CAP)
    entry = ask
    friction_state = "CURRENT_SPREAD_PROXY_CAPPED" if s_frac <= 0.30 else "FRICTION_OUT_OF_RANGE"
    if friction_state == "FRICTION_OUT_OF_RANGE":
        # ALG-04: outside the friction model domain the row is INDETERMINATE; never manufacture confidence by capping
        out.update(applicability="INDETERMINATE", reason="FRICTION_OUT_OF_RANGE", spread_fraction_mid=round(s_frac, 4))
        return out

    # Vol budget (canonical cumulative form, bias multiplier 1.0, UNVALIDATED)
    e_h = vol * bias * math.sqrt(hold / SESSIONS_PER_YEAR)  # bias != 1.0 is a SENSITIVITY setting, not a validated multiplier
    sgn = 1.0 if side == "CALL" else -1.0
    t_late = (dte - hold * CAL_PER_SESSION) / 365.0

    def net(scn_spot: float, iv_mult: float) -> float:
        scn_spot = max(scn_spot, 1e-6 * spot)  # arithmetic scenarios can cross zero when e_h > 1/3
        theo = bsm(side, scn_spot, strike, t_late, iv * iv_mult, r)
        exit_v = max(0.0, theo * (1.0 - haircut))
        return (exit_v - entry) / entry

    scenarios = {
        "FLAT": spot,
        "FAVOURABLE_1SIGMA": spot * (1 + sgn * e_h),
        "FAVOURABLE_2SIGMA": spot * (1 + sgn * 2 * e_h),
        "FAVOURABLE_REACHABLE": spot * (1 + sgn * REACHABLE_K * e_h),
        "FAVOURABLE_STRUCTURAL": target,
        "ADVERSE_INVALIDATION": inval,
    }
    for name, sp in scenarios.items():
        for stress, m in IV_STRESSES.items():
            out[f"payoff_{name.lower()}_{stress.lower()}_net_return_fraction"] = round(net(sp, m), 4)
    p_flat = out["payoff_flat_base_net_return_fraction"]
    p_reach = out["payoff_favourable_reachable_base_net_return_fraction"]
    p_struct = out["payoff_favourable_structural_base_net_return_fraction"]
    p_inval = out["payoff_adverse_invalidation_base_net_return_fraction"]

    # Model 8a — probability-free normal-density grid (RANK-001 §3), p_direction = 0.5
    weights = [math.exp(-0.5 * z * z) for z in GRID_SIGMAS]
    wsum = sum(weights)
    grid_ret = [net(spot * math.exp(z * e_h), 1.0) for z in GRID_SIGMAS]  # lognormal terminal grid
    ev_grid = sum(w * g for w, g in zip(weights, grid_ret)) / wsum
    p_pos_grid = sum(w for w, g in zip(weights, grid_ret) if g > 0) / wsum

    # Model 8b — ALG-07 shape with whatever probability the row carries (labelled, UNVALIDATED)
    p_t, p_src = None, "NONE"
    for key in ("doi_p_target_before_invalidation", "ev3_p_target", "layer2__adjusted_prob_target_hit"):
        v = _num(row.get(key))
        if v is not None and 0.0 < v < 1.0:
            p_t, p_src = v, key
            break
    if p_t is not None:
        p_i = min(1.0 - p_t, 0.5 * (1.0 - p_t) + 0.0)  # split residual evenly between invalidation and timeout
        p_o = 1.0 - p_t - p_i
        utility = p_t * p_reach + p_i * p_inval + p_o * p_flat
        out.update(utility_alg07_shape=round(utility, 4), p_target_first=p_t, p_invalidation_first=round(p_i, 4),
                   p_timeout=round(p_o, 4), p_source=p_src)
    else:
        out.update(utility_alg07_shape=None, p_target_first=None, p_invalidation_first=None, p_timeout=None, p_source="NONE")

    decision = "NET_POSITIVE_GRID" if ev_grid > 0 else "NO_POSITIVE_EDGE_GRID"
    out.update(
        entry_ask=entry, spread_fraction_mid=round(s_frac, 4), exit_haircut_fraction=round(haircut, 4),
        friction_assumption=friction_state, hold_sessions=hold, remaining_years_at_late=round(t_late, 4),
        vol_budget_move_fraction=round(e_h, 4), iv_minus_forecast_vol=round(iv - vol, 4),
        ev_grid_net_return_fraction=round(ev_grid, 4), p_positive_net_exit_grid=round(p_pos_grid, 4),
        downside_scenario_net_return_fraction=p_inval, decision_grid=decision,
        validation_state="UNVALIDATED", bias_multiplier_applied=(bias != 1.0), vol_budget_bias_sensitivity=bias,
        legacy_rr_structural_intrinsic=_num(row.get("rr_underlying")),
        structural_vs_reachable_gap=round(p_struct - p_reach, 4),
    )
    return out


# ── self-test against the ALG-04 worked example ────────────────────────────────
def selftest() -> int:
    s, k, dte, sigma, r = 100.0, 105.0, 30, 0.30, 0.04
    bid, ask = 1.562, 1.762
    theo_entry = bsm("CALL", s, k, dte / 365.0, sigma, r)
    hair = min(((ask - bid) / (0.5 * (ask + bid))) / 2.0, FRICTION_CAP)
    t = 23 / 365.0
    expect = {"FLAT": (100.0, -0.323), "1SIGMA": (104.23, 0.541), "2SIGMA": (108.45, 1.878),
              "REACHABLE": (106.34, 1.153), "STRUCTURAL": (112.0, 3.319), "INVALIDATION": (97.0, -0.675)}
    ok = abs(theo_entry - 1.662) < 0.01
    print(f"entry theoretical {theo_entry:.3f} (expect 1.662) {'OK' if ok else 'FAIL'}")
    for name, (sp, exp) in expect.items():
        v = (max(0.0, bsm("CALL", sp, k, t, sigma, r) * (1 - hair)) - ask) / ask
        good = abs(v - exp) <= 0.006
        ok &= good
        print(f"  {name:13s} {v:+.3f} (expect {exp:+.3f}) {'OK' if good else 'FAIL'}")
    return 0 if ok else 1


# ── main ───────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="20260924_085940")
    ap.add_argument("--rate", type=float, default=0.04)
    ap.add_argument("--scope", default="GO,GO_LIMIT", help="lab_verdict values to value; ALL for every row")
    ap.add_argument("--hold-source", choices=("planned", "horizon"), default="planned",
                    help="planned = book's planned_hold_sessions (D2 thesis window); horizon = 1_5d/6_10d/11_20d bucket")
    ap.add_argument("--bias", type=float, default=1.0, help="vol-budget multiplier; != 1.0 is a sensitivity setting, never a validated multiplier")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    root = Path(__file__).resolve().parents[3]
    book = root / "data" / "output" / "runs" / a.run_id / "intelligence_lab" / f"final_opportunity_book_{a.run_id}.json"
    if not book.exists():
        print(f"book not found: {book}")
        return 2
    d = json.loads(book.read_text(encoding="utf-8"))
    rows = d if isinstance(d, list) else (d.get("rows") or d.get("opportunities") or d.get("items") or d.get("book"))
    scope = None if a.scope.upper() == "ALL" else {s.strip().upper() for s in a.scope.split(",")}
    rows = [r for r in rows if scope is None or str(r.get("lab_verdict") or "").upper() in scope]

    results = [value_row(r, a.rate, a.hold_source, a.bias) for r in rows]
    out_dir = root / "Enhancements" / "research" / "output" / a.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fields = sorted({k for r in results for k in r})
    csv_path = out_dir / f"merged_5_7_8_hold-{a.hold_source}_bias-{a.bias}_{stamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(results)

    ok = [r for r in results if r["applicability"] == "OK"]
    def col(k): return [r[k] for r in ok if r.get(k) is not None]
    def q(xs, p): return round(statistics.quantiles(xs, n=100)[p - 1], 4) if len(xs) >= 2 else None
    summary = {
        "harness_version": HARNESS_VERSION, "run_id": a.run_id, "state": "EXPLORATORY_NO_AUTHORITY", "hold_source": a.hold_source, "vol_budget_bias_sensitivity": a.bias,
        "rate": a.rate, "scope": a.scope, "rows_in_scope": len(results), "rows_valued": len(ok),
        "indeterminate_reasons": dict(Counter(r["reason"] for r in results if r["applicability"] != "OK")),
        "decision_grid": dict(Counter(r["decision_grid"] for r in ok)),
        "p_source": dict(Counter(r["p_source"] for r in ok)),
        "friction_assumption": dict(Counter(r["friction_assumption"] for r in ok)),
        "by_direction": dict(Counter(r["direction"] for r in ok)),
        "medians": {k: round(statistics.median(col(k)), 4) for k in (
            "payoff_flat_base_net_return_fraction", "payoff_favourable_1sigma_base_net_return_fraction",
            "payoff_favourable_reachable_base_net_return_fraction", "payoff_favourable_structural_base_net_return_fraction",
            "payoff_adverse_invalidation_base_net_return_fraction", "ev_grid_net_return_fraction",
            "p_positive_net_exit_grid", "spread_fraction_mid", "iv_minus_forecast_vol", "structural_vs_reachable_gap") if col(k)},
        "ev_grid_quantiles": {"p10": q(col("ev_grid_net_return_fraction"), 10), "p50": q(col("ev_grid_net_return_fraction"), 50),
                              "p90": q(col("ev_grid_net_return_fraction"), 90)},
        "utility_alg07_shape_median": round(statistics.median(col("utility_alg07_shape")), 4) if col("utility_alg07_shape") else None,
        "iv_above_forecast_share": round(sum(1 for r in ok if r["iv_minus_forecast_vol"] > 0) / len(ok), 4) if ok else None,
        "output_csv": str(csv_path),
    }
    (out_dir / f"merged_5_7_8_hold-{a.hold_source}_bias-{a.bias}_{stamp}_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
