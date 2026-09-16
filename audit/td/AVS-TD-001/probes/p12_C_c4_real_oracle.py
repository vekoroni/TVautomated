"""p12_C_c4_real_oracle.py -- Track C / C4 + C10 on three REAL run-20260911_115904 contracts.

Independent oracle: scipy BSM (continuous q), own XNYS calendar (weekday minus hard-coded 2026-27 NYSE holidays,
16:00 America/New_York close, 13:00 early closes), ALG-03 bridge (h sessions -> calendar seconds / 365d),
friction_model_v1 (exit = theo * (1 - min(spread_mid/2, 0.15)); net = (exit - ask)/ask), ALG-02 reachable spot
(S0 * (1 +/- 1.5 * sigma_a * sqrt(h/252))), ALG-06 utility (median REACHABLE + min ADVERSE + 0.5 FLAT:LATE:BASE).
Compared with the production grid written by p12_C_offline_sample.py (DeterministicContractValuationService ->
evaluate_contract_economics_v2). Third case: a contract expiring inside the hold, taken from the generator's
structural-exclusion taxonomy (never valued by production) and passed directly to evaluate_contract_economics_v2.
Read-only. Output: p12_C_c4_real_oracle.out.json
"""
from __future__ import annotations
import json, math, statistics, sys
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
from scipy.stats import norm

ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
sys.path.insert(0, str(ROOT))
HERE = Path(__file__).resolve().parent
NY = ZoneInfo("America/New_York")
HOL = {date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3), date(2026, 5, 25), date(2026, 6, 19),
       date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25), date(2027, 1, 1), date(2027, 1, 18)}
EARLY = {date(2026, 11, 27), date(2026, 12, 24)}
PATHS = ["FLAT", "FAVOURABLE_1SIGMA", "FAVOURABLE_2SIGMA", "REACHABLE", "STRUCTURAL_DISCLOSURE", "ADVERSE_INVALIDATION"]
TIM = ["EARLY", "MID", "LATE"]; ST = {"CONTRACTED": .8, "BASE": 1.0, "EXPANDED": 1.2}


def is_sess(d): return d.weekday() < 5 and d not in HOL
def close_utc(d): return datetime.combine(d, dtime(13 if d in EARLY else 16), NY).astimezone(timezone.utc)
def adv(d, n):
    for _ in range(n):
        d += timedelta(days=1)
        while not is_sess(d):
            d += timedelta(days=1)
    return d
def prev_sess(d):
    while not is_sess(d):
        d -= timedelta(days=1)
    return d


def bsm(side, S, K, T, r, q, v):
    if T <= 0:
        return max(0.0, S - K) if side == "CALL" else max(0.0, K - S)
    d1 = (math.log(S / K) + (r - q + .5 * v * v) * T) / (v * math.sqrt(T)); d2 = d1 - v * math.sqrt(T)
    if side == "CALL":
        return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)


def oracle(r):
    side = r["direction"]; S0 = r["spot"]; h = int(r["hold_sessions"]); sign = 1 if side == "CALL" else -1
    e = r["annual_forecast_vol"] * math.sqrt(h / 252.0)
    start = pd.Timestamp(r["evidence_cutoff_utc"]).date()
    early = max(1, math.ceil(h / 3)); mid = max(early, math.ceil(2 * h / 3))
    pts = {"EARLY": close_utc(adv(start, early)), "MID": close_utc(adv(start, mid)), "LATE": close_utc(adv(start, h))}
    exp_close = close_utc(prev_sess(date.fromisoformat(r["expiry"])))
    bid, ask = r["bid"], r["ask"]; s = (ask - bid) / ((ask + bid) / 2); disc = 1 - min(s / 2, .15)
    spots = {"FLAT": S0, "FAVOURABLE_1SIGMA": S0 * (1 + sign * e), "FAVOURABLE_2SIGMA": S0 * (1 + sign * 2 * e),
             "REACHABLE": S0 * (1 + sign * 1.5 * e), "STRUCTURAL_DISCLOSURE": r["structural_target"], "ADVERSE_INVALIDATION": r["invalidation"]}
    grid = {}; worst_theo = 0.0; worst_net_mine = 0.0; worst_net_given_prod_theo = 0.0; over = []; worst_key = {}; floor_rel = []; floored = []
    for p, sp in spots.items():
        for t, at in pts.items():
            T = max(0.0, (exp_close - at).total_seconds() / (365 * 86400))
            for stn, m in ST.items():
                th = bsm(side, sp, r["strike"], T, r["risk_free_rate"], r["dividend_yield"], r["iv"] * m)
                net = (th * disc - ask) / ask
                k = f"{p}:{t}:{stn}"; pth = r[f"theo:{k}"]; pnet = r[f"net:{k}"]
                rel = abs(pth - th) / th if th > 0.01 else abs(pth - th)
                if rel > worst_theo:
                    worst_key = {"key": k, "theo_prod": pth, "theo_mine": th, "T_mine": T, "spot": sp, "as_of_mine": at.isoformat(),
                                 "net_prod": pnet, "net_mine": net}
                worst_theo = max(worst_theo, rel); worst_net_mine = max(worst_net_mine, abs(pnet - net))
                if rel > 0.005:
                    over.append(k)
                # variant with the production no-arbitrage floor (max(intrinsic, S e^-qT - K e^-rT)) to isolate the gap
                if T > 0:
                    df_s = sp * math.exp(-r["dividend_yield"] * T); df_k = r["strike"] * math.exp(-r["risk_free_rate"] * T)
                    intr = max(0.0, sp - r["strike"]) if side == "CALL" else max(0.0, r["strike"] - sp)
                    lo = max(intr, df_s - df_k) if side == "CALL" else max(intr, df_k - df_s)
                    thf = min(sp if side == "CALL" else r["strike"], max(lo, th))
                else:
                    thf = th
                floor_rel.append(abs(pth - thf) / thf if thf > 0.01 else abs(pth - thf))
                if thf != th:
                    floored.append(k)
                worst_net_given_prod_theo = max(worst_net_given_prod_theo, abs(pnet - (pth * disc - ask) / ask))
                grid[k] = net
    u = statistics.median([grid[f"REACHABLE:{t}:{s_}"] for t in TIM for s_ in ST]) + \
        min(grid[f"ADVERSE_INVALIDATION:{t}:{s_}"] for t in TIM for s_ in ST) + .5 * grid["FLAT:LATE:BASE"]
    return {"ticker": r["ticker"], "direction": side, "contract": r["contract_symbol"], "K": r["strike"], "expiry": r["expiry"],
            "bid": bid, "ask": ask, "iv": r["iv"], "S0": S0, "h": h, "r": r["risk_free_rate"], "q": r["dividend_yield"],
            "sigma_a": r["annual_forecast_vol"], "time_stop_close_utc_mine": pts["LATE"].isoformat(), "expiry_close_utc_mine": exp_close.isoformat(),
            "T_late_years_mine": (exp_close - pts["LATE"]).total_seconds() / (365 * 86400),
            "reachable_mine": spots["REACHABLE"], "reachable_prod": r["reachable_target_spot"],
            "reachable_abs_diff": abs(spots["REACHABLE"] - r["reachable_target_spot"]),
            "max_theo_rel_diff_54": worst_theo, "worst_theo_scenario": worst_key, "scenarios_theo_rel_diff_gt_0_5pct": over,
            "scenarios_where_production_floor_binds": floored, "max_theo_rel_diff_54_vs_floored_oracle": max(floor_rel), "max_net_abs_diff_mine_vs_prod_54": worst_net_mine,
            "max_net_abs_diff_friction_on_prod_theo_54": worst_net_given_prod_theo,
            "net_REACHABLE_LATE_BASE": {"prod": r["net:REACHABLE:LATE:BASE"], "mine": grid["REACHABLE:LATE:BASE"]},
            "net_FLAT_LATE_BASE": {"prod": r["net:FLAT:LATE:BASE"], "mine": grid["FLAT:LATE:BASE"]},
            "net_ADVERSE_LATE_BASE": {"prod": r["net:ADVERSE_INVALIDATION:LATE:BASE"], "mine": grid["ADVERSE_INVALIDATION:LATE:BASE"]},
            "net_STRUCTURAL_LATE_BASE": {"prod": r["net:STRUCTURAL_DISCLOSURE:LATE:BASE"], "mine": grid["STRUCTURAL_DISCLOSURE:LATE:BASE"]},
            "utility_v2": {"prod": r["utility_v2"], "mine": u, "abs_diff": abs(u - r["utility_v2"])},
            "state_prod": r["monetisability_state"], "applicability_prod": r["applicability"]}


allc = pd.read_csv(HERE / "p12_C_offline_assessments_all_contracts.csv", low_memory=False)
g = allc.loc[(allc["pass"] == "GARCH_SUB") & (allc["applicability"] == "APPLICABLE")
             & allc["structural_target"].notna() & allc["iv"].notna()]
out = {"cases": []}
for side in ("CALL", "PUT"):
    s = g.loc[g.direction == side].sort_values(["ticker", "contract_symbol"])
    # prefer the legacy-selected contract, else first in sort order (deterministic)
    pick = s.loc[s["selected_by_legacy_jsonl"]] if s["selected_by_legacy_jsonl"].any() else s
    out["cases"].append(oracle(pick.iloc[0].to_dict()))

# third: expiring inside the hold (remaining_sessions < hold) from the generator taxonomy
rw = pd.read_csv(HERE / "p12_C_offline_runway_excluded.csv")
rw["inside_hold"] = rw["remaining_sessions"] < rw["hold"]
out["runway_excluded_counts"] = {"contracts": len(rw), "expire_inside_hold": int(rw["inside_hold"].sum()),
                                 "inside_buffer_only": int((~rw["inside_hold"]).sum()),
                                 "by_dir_inside_hold": rw.loc[rw.inside_hold, "direction"].value_counts().to_dict(),
                                 "in_display_set": int(rw["in_display"].sum())}
cand = rw.loc[rw.inside_hold & (rw["bid"] > 0) & (rw["ask"] > rw["bid"])].copy()
cand["spread_mid"] = (cand["ask"] - cand["bid"]) / ((cand["ask"] + cand["bid"]) / 2)
out["inside_hold_two_sided"] = {"n": len(cand), "spread_gt_0_30_would_report_FRICTION_OUT_OF_RANGE": int((cand["spread_mid"] > 0.30).sum()),
                                "spread_le_0_30_would_report_HORIZON_LIMITED": int((cand["spread_mid"] <= 0.30).sum()),
                                "by_dir_spread_gt_0_30": cand.loc[cand.spread_mid > 0.30, "direction"].value_counts().to_dict(),
                                "by_dir_spread_le_0_30": cand.loc[cand.spread_mid <= 0.30, "direction"].value_counts().to_dict()}
# prefer an in-model-domain spread so the horizon branch (not the spread branch) is exercised
cand = cand.loc[cand.ticker.isin(g.ticker) & (cand["spread_mid"] <= 0.30)].sort_values(["ticker", "contract_symbol"])
if not cand.empty:
    c = cand.iloc[0]; fr = g.loc[g.ticker == c.ticker].iloc[0]
    from domain.contract_economics_v2 import evaluate_contract_economics_v2
    from canonical_data.dynamic_options_valuation import build_xnys_scenario_points, _expiration_close
    side = c.direction; sign = 1 if side == "CALL" else -1; e = fr["expected_move_hold_fraction"]
    pts = build_xnys_scenario_points(start_session=pd.Timestamp(fr["evidence_cutoff_utc"]).date(), planned_hold_sessions=int(fr["hold_sessions"]))
    econ = evaluate_contract_economics_v2(
        option_side=side, origin_spot=fr["spot"], strike=float(c.strike), expiration_utc=_expiration_close(date.fromisoformat(c.expiry)),
        base_iv=float(fr["iv"]), entry_bid=float(c.bid), entry_ask=float(c.ask), risk_free_rate=fr["risk_free_rate"],
        dividend_yield=fr["dividend_yield"], scenario_points=pts, favourable_1sigma=fr["spot"] * (1 + sign * e),
        favourable_2sigma=fr["spot"] * (1 + sign * 2 * e), reachable_spot=fr["reachable_target_spot"],
        structural_target=fr["structural_target"], invalidation_spot=fr["invalidation"], profit_floor=0.25,
        profit_floor_approved=True, profit_floor_approval_id="ACK-20260912-AVS-FIX-002")
    late = adv(pd.Timestamp(fr["evidence_cutoff_utc"]).date(), int(fr["hold_sessions"]))
    out["cases"].append({"ticker": c.ticker, "direction": side, "contract": c.contract_symbol, "expiry": c.expiry,
                         "remaining_sessions": int(c.remaining_sessions), "hold": int(c.hold), "required_sessions": int(c.required_sessions),
                         "time_stop_session_mine": late.isoformat(), "expires_before_time_stop_mine": date.fromisoformat(c.expiry) <= late,
                         "generator_state": c.state, "in_display_set": bool(c.in_display),
                         "iv_used_note": "family-row IV of a sibling contract (taxonomy carries no IV); irrelevant to the HORIZON_LIMITED branch",
                         "prod_direct_call": {"applicability": econ.applicability, "applicability_reason": econ.applicability_reason,
                                              "monetisability_state": econ.monetisability_state, "monetisability_reason": econ.monetisability_reason,
                                              "n_scenarios": len(econ.scenarios), "utility": econ.deterministic_utility,
                                              "has_dte_inside_hold_field": "dte_inside_hold" in econ.to_dict()}})
(HERE / "p12_C_c4_real_oracle.out.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(json.dumps(out, indent=2, default=str))
