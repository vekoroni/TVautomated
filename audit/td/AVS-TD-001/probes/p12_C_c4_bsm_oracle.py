"""p12_C_c4_bsm_oracle.py -- Track C / C4: independent BSM oracle (scipy.stats.norm) + ALG-03 bridge + friction_model_v1,
run against the Annex A worked example through the production function
domain.contract_economics_v2.evaluate_contract_economics_v2 (CALL K=105 and PUT mirror K=95).
Read-only. Output beside script: p12_C_c4_bsm_oracle.out.json
"""
from __future__ import annotations
import json, math, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from scipy.stats import norm

ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
sys.path.insert(0, str(ROOT))
from domain.contract_economics_v2 import evaluate_contract_economics_v2  # noqa: E402
from canonical_data.dynamic_options_valuation import build_xnys_scenario_points, _advance_sessions  # noqa: E402
from canonical_data.session_clock import session_bounds, is_xnys_session  # noqa: E402

HERE = Path(__file__).resolve().parent


def bsm(side: str, S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    """Independent Black-Scholes-Merton, European, continuous dividend yield."""
    if T <= 0:
        return max(0.0, S - K) if side == "CALL" else max(0.0, K - S)
    if sigma <= 0:
        f = S * math.exp(-q * T) - K * math.exp(-r * T)
        return max(0.0, f) if side == "CALL" else max(0.0, -f)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if side == "CALL":
        return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)


def friction_net(theo: float, bid: float, ask: float, cap: float = 0.15) -> tuple[float, float]:
    s = (ask - bid) / ((ask + bid) / 2.0)
    exit_v = max(0.0, theo * (1.0 - min(s / 2.0, cap)))
    return exit_v, (exit_v - ask) / ask


def remaining_years(expiry_close: datetime, time_stop_close: datetime) -> float:
    return max(0.0, (expiry_close - time_stop_close).total_seconds() / (365 * 86400))


out: dict = {}
# --- Annex A ALG-03 bridge check ------------------------------------------------------------------------
ev = date(2026, 9, 11)
ts5 = _advance_sessions(ev, 5)
out["bridge"] = {
    "evidence_session": ev.isoformat(), "time_stop_h5": ts5.isoformat(), "expected": "2026-09-18",
    "h7_from_2026_09_14": _advance_sessions(date(2026, 9, 14), 7).isoformat(), "expected_h7": "2026-09-23",
    "remaining_days_to_2026_10_16_from_h5_stop": (session_bounds(date(2026, 10, 16))[1] - session_bounds(ts5)[1]).total_seconds() / 86400,
    "expected_remaining_days": 28,
    "session_close_utc_2026_09_18": session_bounds(ts5)[1].isoformat(),
}

# --- Annex A ALG-04 worked example -----------------------------------------------------------------------
S0, r, q, sigma, h, k = 100.0, 0.04, 0.0, 0.30, 5, 1.5
e_h = sigma * math.sqrt(h / 252.0)
points = build_xnys_scenario_points(start_session=ev, planned_hold_sessions=h)
late = max(points, key=lambda p: p.sessions_elapsed)
# Annex: "30 calendar DTE ... h = 5 sessions -> 7 calendar days elapsed -> T = 23/365": expiry = evidence close + 30 days
expiry_close = session_bounds(ev)[1] + timedelta(days=30)
out["worked_example_inputs"] = {"e_h": e_h, "reachable_call": S0 * (1 + k * e_h), "reachable_put": S0 * (1 - k * e_h),
                                "late_as_of_utc": late.as_of_utc.isoformat(), "expiry_close_utc": expiry_close.isoformat(),
                                "T_years_at_late": remaining_years(expiry_close, late.as_of_utc), "expected_T": 23 / 365,
                                "points": [(p.timing.value, p.sessions_elapsed, p.as_of_utc.isoformat()) for p in points]}
cases = {
    "CALL": dict(K=105.0, bid=1.562, ask=1.762, Ts=112.0, I=97.0,
                 expect={"entry_theo": 1.662, "FLAT": -0.323, "REACHABLE": 1.153, "ADVERSE_INVALIDATION": -0.675,
                         "FAVOURABLE_1SIGMA": 0.541, "FAVOURABLE_2SIGMA": 1.878, "STRUCTURAL_DISCLOSURE": 3.319,
                         "theo": {"FLAT": 1.269, "FAVOURABLE_1SIGMA": 2.890, "FAVOURABLE_2SIGMA": 5.397, "REACHABLE": 4.036,
                                  "STRUCTURAL_DISCLOSURE": 8.098, "ADVERSE_INVALIDATION": 0.610}}),
    "PUT": dict(K=95.0, bid=None, ask=None, Ts=88.0, I=103.0,
                expect={"entry_theo": 1.333, "theo": {"FLAT": 1.021, "FAVOURABLE_1SIGMA": 2.383, "REACHABLE": 3.413}}),
}
results = {}
for side, c in cases.items():
    sign = 1 if side == "CALL" else -1
    entry_theo_mine = bsm(side, S0, c["K"], 30 / 365, r, q, sigma)
    bid, ask = c["bid"], c["ask"]
    if bid is None:  # PUT mirror: Annex gives entry theoretical only; mirror the CALL spread (same absolute +-0.1)
        bid, ask = entry_theo_mine - 0.1, entry_theo_mine + 0.1
    spots = {"FLAT": S0, "FAVOURABLE_1SIGMA": S0 * (1 + sign * e_h), "FAVOURABLE_2SIGMA": S0 * (1 + sign * 2 * e_h),
             "REACHABLE": S0 * (1 + sign * k * e_h), "STRUCTURAL_DISCLOSURE": c["Ts"], "ADVERSE_INVALIDATION": c["I"]}
    T = remaining_years(expiry_close, late.as_of_utc)
    mine = {}
    for name, S in spots.items():
        theo = bsm(side, S, c["K"], T, r, q, sigma)
        exit_v, net = friction_net(theo, bid, ask)
        mine[name] = {"spot": S, "theo": theo, "exit": exit_v, "net": net}
    econ = evaluate_contract_economics_v2(
        option_side=side, origin_spot=S0, strike=c["K"], expiration_utc=expiry_close, base_iv=sigma,
        entry_bid=bid, entry_ask=ask, risk_free_rate=r, dividend_yield=q, scenario_points=points,
        favourable_1sigma=spots["FAVOURABLE_1SIGMA"], favourable_2sigma=spots["FAVOURABLE_2SIGMA"],
        reachable_spot=spots["REACHABLE"], structural_target=c["Ts"], invalidation_spot=c["I"],
        spread_cap=0.15, max_model_spread=0.30, profit_floor=0.25, profit_floor_approved=True,
        profit_floor_approval_id="ACK-20260912-AVS-FIX-002", w_flat=0.5)
    prod = {sc.path: {"spot": sc.spot, "theo": sc.theoretical_value_per_share, "exit": sc.exit_value_after_friction_per_share,
                      "net": sc.net_return_fraction, "T": sc.remaining_calendar_years}
            for sc in econ.scenarios if sc.timing == "LATE" and sc.iv_stress == "BASE"}
    comp = {}
    for name in spots:
        m, p = mine[name], prod[name]
        exp_net = c["expect"].get(name)
        exp_theo = c["expect"].get("theo", {}).get(name)
        comp[name] = {
            "spot": round(p["spot"], 4), "theo_prod": round(p["theo"], 4), "theo_mine": round(m["theo"], 4),
            "theo_rel_diff_prod_vs_mine": abs(p["theo"] - m["theo"]) / max(m["theo"], 1e-12),
            "net_prod": round(p["net"], 4), "net_mine": round(m["net"], 4), "net_abs_diff": abs(p["net"] - m["net"]),
            "annex_theo": exp_theo, "annex_net": exp_net,
            "theo_vs_annex_rel": None if exp_theo is None else abs(p["theo"] - exp_theo) / exp_theo,
            "net_vs_annex_abs_pp": None if exp_net is None else abs(p["net"] - exp_net) * 100,
        }
    results[side] = {
        "entry_theo_mine_T30": entry_theo_mine, "annex_entry_theo": c["expect"]["entry_theo"],
        "bid": bid, "ask": ask, "spread_fraction_mid": (ask - bid) / ((ask + bid) / 2),
        "exit_haircut": min(((ask - bid) / ((ask + bid) / 2)) / 2, 0.15),
        "scenarios_LATE_BASE": comp,
        "production_state": {"applicability": econ.applicability, "monetisability_state": econ.monetisability_state,
                             "monetisability_reason": econ.monetisability_reason, "utility_v2": econ.deterministic_utility,
                             "convexity_score": econ.convexity_score, "convexity_label": econ.convexity_label,
                             "profit_floor_applied": econ.profit_floor_applied, "friction_version": econ.friction_version,
                             "calendar_version": econ.calendar_version, "basis": econ.basis, "n_scenarios": len(econ.scenarios)},
        "monotonic_property_raise_S_raises_call_lowers_put": None,
    }
    # property checks: raising S raises CALL / lowers PUT theoretical; raising spread never raises net
    t1 = bsm(side, 100, c["K"], T, r, q, sigma); t2 = bsm(side, 101, c["K"], T, r, q, sigma)
    results[side]["monotonic_property_raise_S_raises_call_lowers_put"] = (t2 > t1) if side == "CALL" else (t2 < t1)
    n_lo = friction_net(t1, ask - 0.10, ask)[1]; n_hi = friction_net(t1, ask - 0.30, ask)[1]
    results[side]["property_raising_spread_never_raises_net"] = n_hi <= n_lo
    # utility v2 recompute from the production grid
    reach = [sc.net_return_fraction for sc in econ.scenarios if sc.path == "REACHABLE"]
    adv = [sc.net_return_fraction for sc in econ.scenarios if sc.path == "ADVERSE_INVALIDATION"]
    flat_late = next(sc.net_return_fraction for sc in econ.scenarios if sc.path == "FLAT" and sc.timing == "LATE" and sc.iv_stress == "BASE")
    import statistics
    u_mine = statistics.median(reach) + min(adv) + 0.5 * flat_late
    results[side]["utility_v2_recomputed"] = u_mine
    results[side]["utility_v2_abs_diff"] = abs(u_mine - econ.deterministic_utility)
    results[side]["n_reachable_grid"] = len(reach)

# dte_inside_hold: contract expiring inside the hold (expiry 16 Sep 2026 close, h = 5 -> LATE 18 Sep)
econ_inside = evaluate_contract_economics_v2(
    option_side="CALL", origin_spot=S0, strike=105.0, expiration_utc=session_bounds(date(2026, 9, 16))[1], base_iv=sigma,
    entry_bid=1.562, entry_ask=1.762, risk_free_rate=r, dividend_yield=q, scenario_points=points,
    favourable_1sigma=104.23, favourable_2sigma=108.45, reachable_spot=106.34, structural_target=112.0, invalidation_spot=97.0,
    profit_floor=0.25, profit_floor_approved=True, profit_floor_approval_id="ACK-20260912-AVS-FIX-002")
results["dte_inside_hold_fixture"] = {"applicability": econ_inside.applicability, "applicability_reason": econ_inside.applicability_reason,
                                      "monetisability_state": econ_inside.monetisability_state,
                                      "monetisability_reason": econ_inside.monetisability_reason,
                                      "n_scenarios": len(econ_inside.scenarios), "utility": econ_inside.deterministic_utility}
# spread out of model domain
econ_wide = evaluate_contract_economics_v2(
    option_side="CALL", origin_spot=S0, strike=105.0, expiration_utc=expiry_close, base_iv=sigma,
    entry_bid=1.0, entry_ask=1.762, risk_free_rate=r, dividend_yield=q, scenario_points=points,
    favourable_1sigma=104.23, favourable_2sigma=108.45, reachable_spot=106.34, structural_target=112.0, invalidation_spot=97.0,
    profit_floor=0.25, profit_floor_approved=True, profit_floor_approval_id="X")
results["friction_out_of_range_fixture"] = {"spread": econ_wide.spread_fraction_mid, "applicability": econ_wide.applicability,
                                            "monetisability_state": econ_wide.monetisability_state,
                                            "monetisability_reason": econ_wide.monetisability_reason}
# profit floor not approved
econ_na = evaluate_contract_economics_v2(
    option_side="CALL", origin_spot=S0, strike=105.0, expiration_utc=expiry_close, base_iv=sigma,
    entry_bid=1.562, entry_ask=1.762, risk_free_rate=r, dividend_yield=q, scenario_points=points,
    favourable_1sigma=104.23, favourable_2sigma=108.45, reachable_spot=106.34, structural_target=112.0, invalidation_spot=97.0,
    profit_floor=0.25, profit_floor_approved=False)
results["profit_floor_not_approved_fixture"] = {"monetisability_state": econ_na.monetisability_state, "reason": econ_na.monetisability_reason}
out["results"] = results
(HERE / "p12_C_c4_bsm_oracle.out.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(json.dumps(out, indent=2, default=str))
