"""p27_M7_reachability.py -- Track M7 reachability, three estimators (discovery, RESEARCH_ONLY).

Rows: thesis geometry per family from probes/p12_C_offline_assessments_all_contracts.csv (pass GARCH_SUB, deduplicated on
family_id); contract payoffs from probes/p27_M7_decomposition.csv (APPLICABLE contracts; must run after p27_M7_decomposition.py).

Coordinates: u = sign * ln(S/S0) (sign +1 CALL, -1 PUT), so the favourable barrier is b_T = sign*ln(T/S0) > 0 and the
invalidation barrier b_I = sign*ln(I/S0) < 0. sigma = row annual forecast vol (annual_forecast_vol), horizon
T = hold_sessions/252, daily steps dt = 1/252.
Drift (log, favourable direction): ZERO -> nu = 0 ; THESIS -> nu = ln(R/S0)*sign / T where R = reachable target
(the move implied by the reachable target over the hold).
Barrier targets: STRUCTURAL (row structural target, as instructed) and REACHABLE (reachable target, variant).
 (1) PIPELINE : domain.reachability.assess_reachability -> reach_ratio, reachable target. Not a probability. The pipeline
               values the contract as if the reachable target is reached at LATE (implicit p_target = 1).
 (2) SINGLE   : closed-form first passage of drifted BM to b_T within T (ignores invalidation):
               P = N((-b + nu T)/(s sqrt T)) + exp(2 nu b / s^2) N((-b - nu T)/(s sqrt T)).
 (3) DOUBLE MC: daily Euler steps of u, Brownian-bridge crossing correction per step for each barrier
               p_cross_up = exp(-2 (b_T-u0)(b_T-u1)/(s^2 dt)), p_cross_dn = exp(-2 (u0-b_I)(u1-b_I)/(s^2 dt));
               the first barrier touched stops the path; if both are touched inside one step the order is drawn 50/50
               (count reported). Returns p_target + p_invalid + p_timeout = 1. Seed 20260912 (numpy default_rng, one
               generator, rows in sorted family_id order), N_PATHS paths per row. A single-barrier MC column
               (invalidation ignored) checks (2).
EV recompute per contract: EV3 = p_T * net(REACHABLE,LATE,BASE) + p_I * net(ADVERSE_INVALIDATION,LATE,BASE)
                                + p_O * net(FLAT,LATE,BASE);  EV1 = net(REACHABLE,LATE,BASE) (pipeline headline).
"""
from __future__ import annotations
import json, math, time
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import norm

ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
P = ROOT / "audit/td/AVS-TD-001/probes"
SEED, N_PATHS, DT = 20260912, 20000, 1 / 252
t0 = time.time()

c = pd.read_csv(P / "p12_C_offline_assessments_all_contracts.csv", low_memory=False)
c = c[c["pass"] == "GARCH_SUB"]
g = (c.sort_values("family_id").drop_duplicates("family_id")
       [["family_id", "ticker", "direction", "spot", "structural_target", "invalidation", "hold_sessions",
         "annual_forecast_vol", "expected_move_hold_fraction", "reachable_target_spot", "reach_ratio"]].reset_index(drop=True))
g = g[g.structural_target.notna() & g.invalidation.notna() & g.annual_forecast_vol.notna()
      & g.reachable_target_spot.notna()].reset_index(drop=True)


def single_closed(b, nu, s, T):
    if b <= 0:
        return 1.0
    sT = s * math.sqrt(T)
    a = norm.cdf((-b + nu * T) / sT)
    # exp term in log space to avoid overflow
    lt = 2 * nu * b / s ** 2 + norm.logcdf((-b - nu * T) / sT)
    return float(min(1.0, a + math.exp(lt)))


rng = np.random.default_rng(SEED)


def mc(bT, bI, nu, s, h, double=True):
    n = N_PATHS
    u = np.zeros(n)
    alive = np.ones(n, bool)
    hitT = np.zeros(n, bool); hitI = np.zeros(n, bool)
    both = 0
    for _ in range(h):
        z = rng.standard_normal(n)
        uu = rng.random(n); ud = rng.random(n); coin = rng.random(n)
        u1 = u + nu * DT + s * math.sqrt(DT) * z
        endT = u1 >= bT
        pu = np.where((u < bT) & (u1 < bT), np.exp(-2 * (bT - u) * (bT - u1) / (s * s * DT)), 1.0)
        cT = endT | (uu < pu)
        if double:
            endI = u1 <= bI
            pdn = np.where((u > bI) & (u1 > bI), np.exp(-2 * (u - bI) * (u1 - bI) / (s * s * DT)), 1.0)
            cI = endI | (ud < pdn)
        else:
            cI = np.zeros(n, bool)
        bb = alive & cT & cI
        both += int(bb.sum())
        tT = alive & cT & (~cI | (coin < 0.5))
        tI = alive & cI & (~cT | (coin >= 0.5))
        hitT |= tT; hitI |= tI
        alive &= ~(tT | tI)
        u = u1
    return hitT.mean(), hitI.mean(), alive.mean(), both


res = []
for _, r in g.iterrows():
    sign = 1.0 if r.direction == "CALL" else -1.0
    S0, s, h = float(r.spot), float(r.annual_forecast_vol), int(r.hold_sessions)
    T = h / 252
    bI = sign * math.log(float(r.invalidation) / S0)
    for barrier in ["STRUCTURAL", "REACHABLE"]:
        tgt = float(r.structural_target) if barrier == "STRUCTURAL" else float(r.reachable_target_spot)
        bT = sign * math.log(tgt / S0)
        for drift in ["ZERO", "THESIS"]:
            nu = 0.0 if drift == "ZERO" else sign * math.log(float(r.reachable_target_spot) / S0) / T
            p2 = single_closed(bT, nu, s, T)
            pT, pI, pO, both = mc(bT, bI, nu, s, h, double=True)
            pT1, _, _, _ = mc(bT, bI, nu, s, h, double=False)
            res.append({"family_id": r.family_id, "ticker": r.ticker, "direction": r.direction, "barrier_target": barrier,
                        "drift": drift, "spot": S0, "target_spot": tgt, "invalidation": r.invalidation, "hold_sessions": h,
                        "sigma_forecast": s, "nu_log_annual": nu, "b_T": bT, "b_I": bI,
                        "reach_ratio_pipeline": r.reach_ratio, "reachable_target_pipeline": r.reachable_target_spot,
                        "p1_pipeline_implicit": 1.0, "p2_single_closed": p2, "p_single_mc": pT1,
                        "p3_target": pT, "p3_invalid": pI, "p3_timeout": pO, "p3_sum": pT + pI + pO,
                        "both_touched_in_step_paths": both, "n_paths": N_PATHS})
rp = pd.DataFrame(res)
rp.to_csv(P / "p27_M7_reachability.csv", index=False)

# ---- EV recompute per contract
dec = pd.read_csv(P / "p27_M7_decomposition.csv", low_memory=False)
dec = dec[dec.repro_applicability == "APPLICABLE"]
ev = dec.merge(rp, on=["family_id", "direction", "ticker"], how="inner")
ev["ev3"] = ev.p3_target * ev.ev_net + ev.p3_invalid * ev.net_inval_late_base + ev.p3_timeout * ev.net_flat_late_base
ev["ev1_pos"] = ev.ev_net > 0; ev["ev3_pos"] = ev.ev3 > 0
ev["sign_flip"] = ev.ev1_pos != ev.ev3_pos
ev[["family_id", "ticker", "direction", "contract_symbol", "is_family_pick", "barrier_target", "drift", "ev_net",
    "net_inval_late_base", "net_flat_late_base", "p3_target", "p3_invalid", "p3_timeout", "ev3", "sign_flip"]].to_csv(
    P / "p27_M7_reachability_ev.csv", index=False)

S = {"families_with_geometry": int(len(g)), "families_by_dir": g.direction.value_counts().to_dict(),
     "n_paths": N_PATHS, "seed": SEED, "max_abs_p3_sum_minus_1": float((rp.p3_sum - 1).abs().max())}
summ = []
for (bt, dr, dn), f in rp.groupby(["barrier_target", "drift", "direction"]):
    e = ev[(ev.barrier_target == bt) & (ev.drift == dr) & (ev.direction == dn)]
    ep = e[e.is_family_pick]
    rel = (f.p3_target - f.p2_single_closed) / f.p2_single_closed.where(f.p2_single_closed > 1e-9)
    summ.append({"barrier_target": bt, "drift": dr, "direction": dn, "families": len(f),
                 "families_power": "OK" if len(f) >= 100 else "INSUFFICIENT_POWER",
                 "median_reach_ratio": float(f.reach_ratio_pipeline.median()),
                 "median_p2_single": float(f.p2_single_closed.median()), "median_p_single_mc": float(f.p_single_mc.median()),
                 "max_abs_single_closed_minus_mc": float((f.p2_single_closed - f.p_single_mc).abs().max()),
                 "median_p3_target": float(f.p3_target.median()), "median_p3_invalid": float(f.p3_invalid.median()),
                 "median_p3_timeout": float(f.p3_timeout.median()),
                 "median_rel_diff_p3T_vs_p2": float(rel.median()), "iqr_rel_diff": [float(rel.quantile(.25)), float(rel.quantile(.75))],
                 "contracts": len(e), "contracts_power": "OK" if len(e) >= 100 else "INSUFFICIENT_POWER",
                 "ev1_pos": int(e.ev1_pos.sum()), "ev3_pos": int(e.ev3_pos.sum()), "sign_flips": int(e.sign_flip.sum()),
                 "flips_pos_to_nonpos": int((e.ev1_pos & ~e.ev3_pos).sum()), "median_ev1": float(e.ev_net.median()) if len(e) else None,
                 "median_ev3": float(e.ev3.median()) if len(e) else None,
                 "family_pick_contracts": len(ep), "family_pick_sign_flips": int(ep.sign_flip.sum())})
S["summary"] = summ
S["elapsed_s"] = round(time.time() - t0, 1)
pd.DataFrame(summ).to_csv(P / "p27_M7_reachability_summary.csv", index=False)
(P / "p27_M7_reachability.out.json").write_text(json.dumps(S, indent=1, default=str))
print(pd.DataFrame(summ).to_string())
print(json.dumps({k: v for k, v in S.items() if k != "summary"}, indent=1))
