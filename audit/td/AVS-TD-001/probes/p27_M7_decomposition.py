"""p27_M7_decomposition.py -- Track M7 (discovery, RESEARCH_ONLY): what the DOI EV is made of.

Input rows: probes/p12_C_offline_assessments_all_contracts.csv, pass == GARCH_SUB (2,385 contracts of 200 families of
run 20260911_115904, valued offline by Track C through the production DOI service). Family-level picks are flagged from
probes/p12_C_offline_assessments.csv. OI / provider delta from the Track C scratch registry
probes/_scratch_c6/control_plane_scratch_garch_sub.sqlite (opened mode=ro).

Every EV value is recomputed by calling the production function domain.contract_economics_v2.evaluate_contract_economics_v2
with production inputs (canonical_data/dynamic_options_valuation.py:369-395 wiring). Reproduction vs the stored CSV is checked.

EV_net = net_return REACHABLE:LATE:BASE (the headline cell, contract_economics_v2.py:139). utility_v2 is carried beside it.
vol_component_budget  = dEV/dsigma_forecast (central FD, eps 0.005, through the vol budget) * (sigma_forecast - sigma_IV)
vol_exact             = EV(sigma_forecast) - EV(sigma_forecast := sigma_IV)   (the counterfactual)
vol_component_pricing = BS vega at entry (FD on IV, per unit premium = ask) * (sigma_forecast - sigma_IV)  [literal formula;
                        the engine prices at IV, so this channel does not enter EV_net]
drift_component       = BS delta at entry (FD on spot) * (reachable_spot - origin_spot) / ask
                        (thesis_drift*horizon = reachable move over the hold)
friction_component    = -theo(REACHABLE,LATE,BASE) * min(s/2, cap) / ask   (negative contribution)
residual              = EV_net - vol_component_budget - drift_component - friction_component
Friction variants: AS_CONFIGURED (cap .15, domain .30), CAPPED_NO_DOMAIN (cap .15, domain inf),
FULL_HALF_SPREAD (cap inf, domain inf; effective half-spread multiplier 1.0, fills: none).
"""
from __future__ import annotations
import json, math, sqlite3, sys, time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
sys.path.insert(0, str(ROOT))
from domain.contract_economics_v2 import evaluate_contract_economics_v2  # noqa: E402
from domain.volatility_budget import calculate_volatility_budget  # noqa: E402
from domain.reachability import assess_reachability  # noqa: E402
from domain.deterministic_option_valuation import dividend_adjusted_black_scholes  # noqa: E402
from canonical_data.dynamic_options_valuation import build_xnys_scenario_points, _expiration_close  # noqa: E402

P = ROOT / "audit/td/AVS-TD-001/probes"
t0 = time.time()
c = pd.read_csv(P / "p12_C_offline_assessments_all_contracts.csv", low_memory=False)
c = c[c["pass"] == "GARCH_SUB"].reset_index(drop=True)
fam = pd.read_csv(P / "p12_C_offline_assessments.csv", low_memory=False)
picks = set(zip(fam.family_id, fam.contract_symbol))
con = sqlite3.connect(f"file:{P / '_scratch_c6/control_plane_scratch_garch_sub.sqlite'}?mode=ro", uri=True)
obs = pd.read_sql("select ticker, contract_symbol, open_interest, delta as provider_delta, quote_as_of from option_contract_observations", con)
dup = int(obs.duplicated(["ticker", "contract_symbol"]).sum())
obs = obs.drop_duplicates(["ticker", "contract_symbol"])
c = c.merge(obs, on=["ticker", "contract_symbol"], how="left")

K_SIGMA = 1.5
EPS = 0.005
INF = 1e9


def nn(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)


def econ(r, fvol, cap=0.15, dom=0.30):
    h = int(r.hold_sessions)
    budget = calculate_volatility_budget(fvol, h)
    side = r.direction
    tgt = nn(r.structural_target)
    reach = assess_reachability(direction=side, origin_spot=float(r.spot), structural_target_spot=tgt,
                                budget=budget, sigma_multiple=K_SIGMA)
    move = budget.expected_move_fraction
    sign = 1.0 if side == "CALL" else -1.0
    start = pd.Timestamp(r.evidence_cutoff_utc).date()
    pts = build_xnys_scenario_points(start_session=start, planned_hold_sessions=h)
    exp_close = _expiration_close(pd.Timestamp(r.expiry).date())
    res = evaluate_contract_economics_v2(
        option_side=side, origin_spot=float(r.spot), strike=float(r.strike), expiration_utc=exp_close,
        base_iv=nn(r.iv), entry_bid=nn(r.bid), entry_ask=nn(r.ask), risk_free_rate=float(r.risk_free_rate),
        dividend_yield=float(r.dividend_yield), scenario_points=pts,
        favourable_1sigma=None if move is None else float(r.spot) * (1 + sign * move),
        favourable_2sigma=None if move is None else float(r.spot) * (1 + sign * 2 * move),
        reachable_spot=reach.reachable_target_spot, structural_target=tgt, invalidation_spot=nn(r.invalidation),
        spread_cap=cap, max_model_spread=dom, profit_floor=0.25, profit_floor_approved=True,
        profit_floor_approval_id="ACK-20260912-AVS-FIX-002", w_flat=0.5)
    cell = {s.scenario_id: s for s in res.scenarios}
    return res, cell, reach, exp_close, pts


rows = []
for i, r in c.iterrows():
    out = {k: r[k] for k in ["family_id", "ticker", "direction", "contract_symbol", "strike", "expiry", "bid", "ask", "iv",
                             "spot", "hold_sessions", "structural_target", "invalidation", "reachable_target_spot",
                             "annual_forecast_vol", "open_interest", "provider_delta", "applicability", "utility_v2",
                             "net:REACHABLE:LATE:BASE"]}
    out["stored_ev_net"] = out.pop("net:REACHABLE:LATE:BASE")
    out["is_family_pick"] = (r.family_id, r.contract_symbol) in picks
    bid, ask = nn(r.bid), nn(r.ask)
    out["spread_fraction_mid_from_bid_ask"] = (ask - bid) / ((ask + bid) / 2) if bid is not None and ask is not None and ask > 0 and bid >= 0 and (ask + bid) > 0 else None
    fvol, iv = nn(r.annual_forecast_vol), nn(r.iv)
    try:
        res, cell, reach, exp_close, pts = econ(r, fvol)
    except Exception as e:  # noqa: BLE001
        out["probe_error"] = repr(e)[:120]
        rows.append(out)
        continue
    out["repro_applicability"] = res.applicability
    if res.applicability == "APPLICABLE":
        ev = cell["REACHABLE:LATE:BASE"].net_return_fraction
        out["ev_net"] = ev
        out["utility_v2_repro"] = res.deterministic_utility
        out["repro_abs_diff_ev"] = abs(ev - r["net:REACHABLE:LATE:BASE"])
        out["repro_abs_diff_utility"] = abs(res.deterministic_utility - r.utility_v2)
        out["net_flat_late_base"] = cell["FLAT:LATE:BASE"].net_return_fraction
        out["net_inval_late_base"] = cell["ADVERSE_INVALIDATION:LATE:BASE"].net_return_fraction
        s = res.spread_fraction_mid
        theo_reach = cell["REACHABLE:LATE:BASE"].theoretical_value_per_share
        # budget-channel FD
        ef = min(EPS, fvol / 2)  # step relative to value so sigma - eps stays > 0
        up, _, _, _, _ = econ(r, fvol + ef)
        dn, _, _, _, _ = econ(r, fvol - ef)
        ev_up = {x.scenario_id: x for x in up.scenarios}["REACHABLE:LATE:BASE"].net_return_fraction
        ev_dn = {x.scenario_id: x for x in dn.scenarios}["REACHABLE:LATE:BASE"].net_return_fraction
        dEV = (ev_up - ev_dn) / (2 * ef)
        gap = fvol - iv
        out["sigma_gap"] = gap
        out["vol_component_budget"] = dEV * gap
        cf, cfcell, _, _, _ = econ(r, iv)
        out["cf_iv_applicability"] = cf.applicability
        if cf.applicability == "APPLICABLE":
            out["ev_at_sigma_iv"] = cfcell["REACHABLE:LATE:BASE"].net_return_fraction
            out["utility_at_sigma_iv"] = cf.deterministic_utility
            out["vol_exact"] = ev - out["ev_at_sigma_iv"]
        # entry greeks (production BSM, entry instant = quote time, IV)
        q_t = pd.Timestamp(r.quote_as_of if isinstance(r.quote_as_of, str) else r.evidence_cutoff_utc).to_pydatetime()
        T = max(0.0, (exp_close - q_t).total_seconds() / (365 * 86400))
        kw = dict(option_side=r.direction, strike=float(r.strike), time_to_expiry_years=T,
                  risk_free_rate=float(r.risk_free_rate), dividend_yield=float(r.dividend_yield))
        S0 = float(r.spot)
        hS = S0 * 0.001
        delta = (dividend_adjusted_black_scholes(spot=S0 + hS, volatility=iv, **kw) - dividend_adjusted_black_scholes(spot=S0 - hS, volatility=iv, **kw)) / (2 * hS)
        ev_ = max(min(EPS, iv / 2), 1e-6)  # IV can be ~0 on some provider rows
        out["iv_below_fd_step"] = iv < 2 * EPS
        vega = (dividend_adjusted_black_scholes(spot=S0, volatility=iv + ev_, **kw) - dividend_adjusted_black_scholes(spot=S0, volatility=max(iv - ev_, 0.0), **kw)) / (2 * ev_)
        out["entry_theo"] = dividend_adjusted_black_scholes(spot=S0, volatility=iv, **kw)
        out["bs_delta"] = delta
        out["abs_delta"] = abs(delta)
        out["bs_vega_per_vol"] = vega
        out["vol_component_pricing"] = vega * gap / ask
        out["drift_component"] = delta * (reach.reachable_target_spot - S0) / ask
        out["friction_component"] = -theo_reach * min(s / 2, 0.15) / ask
        out["residual"] = ev - out["vol_component_budget"] - out["drift_component"] - out["friction_component"]
        out["vol_share_of_ev"] = out["vol_component_budget"] / ev if abs(ev) > 1e-9 else None
    # friction variants on every row with valid inputs (domain lifted)
    for tag, cap, dom in [("capped_no_domain", 0.15, INF), ("full_half_spread", INF, INF)]:
        try:
            rv, cv, _, _, _ = econ(r, fvol, cap=cap, dom=dom)
            if rv.applicability == "APPLICABLE":
                out[f"ev_{tag}"] = cv["REACHABLE:LATE:BASE"].net_return_fraction
                out[f"utility_{tag}"] = rv.deterministic_utility
            out[f"app_{tag}"] = rv.applicability
        except Exception as e:  # noqa: BLE001
            out[f"app_{tag}"] = "ERROR:" + repr(e)[:60]
    rows.append(out)

d = pd.DataFrame(rows)
d.to_csv(P / "p27_M7_decomposition.csv", index=False)

# ---------------- summaries
S = {"input_rows": len(d), "obs_duplicates_dropped": dup, "elapsed_s": None}
a = d[d.repro_applicability == "APPLICABLE"].copy()
S["repro"] = {"applicable_repro": len(a), "applicable_stored": int((d.applicability == "APPLICABLE").sum()),
              "state_mismatch": int(((d.applicability == "APPLICABLE") != (d.repro_applicability == "APPLICABLE")).sum()),
              "max_abs_diff_ev": float(a.repro_abs_diff_ev.max()), "max_abs_diff_utility": float(a.repro_abs_diff_utility.max())}


def q(x):
    x = pd.Series(x).dropna()
    return {"n": int(len(x)), "p10": float(x.quantile(.1)) if len(x) else None, "p25": float(x.quantile(.25)) if len(x) else None,
            "median": float(x.median()) if len(x) else None, "p75": float(x.quantile(.75)) if len(x) else None,
            "p90": float(x.quantile(.9)) if len(x) else None}


def per_dir(frame, fn):
    return {k: fn(frame[frame.direction == k]) for k in ["CALL", "PUT"]} | {"OTHER": "n=0 (no OTHER assessments: DOI raises on non-CALL/PUT)"}


for scope, frame in [("all_contracts", a), ("family_picks", a[a.is_family_pick])]:
    S[scope] = per_dir(frame, lambda f: {
        "n": len(f),
        "ev_net": q(f.ev_net), "utility_v2": q(f.utility_v2_repro),
        "sigma_gap": q(f.sigma_gap), "share_forecast_above_iv": float((f.sigma_gap > 0).mean()) if len(f) else None,
        "vol_component_budget": q(f.vol_component_budget), "vol_exact": q(f.vol_exact),
        "vol_component_pricing": q(f.vol_component_pricing), "drift_component": q(f.drift_component),
        "friction_component": q(f.friction_component), "residual": q(f.residual),
        "vol_share_of_ev": q(f.vol_share_of_ev),
        "vol_share_of_ev_positive_ev_rows": q(f[f.ev_net > 0].vol_share_of_ev),
        "ev_pos": int((f.ev_net > 0).sum()),
        "ev_pos_retained_at_sigma_iv": int(((f.ev_net > 0) & (f.ev_at_sigma_iv > 0)).sum()),
        "ev_pos_cf_not_applicable": int(((f.ev_net > 0) & f.ev_at_sigma_iv.isna()).sum()),
        "ev_ge_floor": int((f.ev_net >= .25).sum()),
        "ev_ge_floor_retained_at_sigma_iv": int(((f.ev_net >= .25) & (f.ev_at_sigma_iv >= .25)).sum()),
        "utility_pos": int((f.utility_v2_repro > 0).sum()),
        "utility_pos_retained_at_sigma_iv": int(((f.utility_v2_repro > 0) & (f.utility_at_sigma_iv > 0)).sum()),
        "spearman_ev_absdelta": float(f.ev_net.corr(f.abs_delta, method="spearman")) if len(f) > 2 else None,
        "spearman_ev_ask": float(f.ev_net.corr(f.ask, method="spearman")) if len(f) > 2 else None,
        "spearman_ev_voldelta_share": float(f.ev_net.corr(f.vol_component_budget, method="spearman")) if len(f) > 2 else None,
    })

# cross-tabs
bands = [0, .25, .40, .60, 1.01]
blab = ["<0.25", "0.25-0.40", "0.40-0.60", ">=0.60"]
xt = []
for k in ["CALL", "PUT"]:
    f = a[a.direction == k].copy()
    f["ev_rank_pct"] = f.ev_net.rank(pct=True)
    f["delta_band"] = pd.cut(f.abs_delta, bands, labels=blab, right=False)
    f["premium_tercile"] = pd.qcut(f.ask, 3, labels=["T1_low", "T2_mid", "T3_high"])
    for dim in ["delta_band", "premium_tercile"]:
        for lab, g in f.groupby(dim, observed=False):
            xt.append({"direction": k, "dimension": dim, "cell": str(lab), "n": len(g),
                       "power": "OK" if len(g) >= 100 else "INSUFFICIENT_POWER",
                       "median_ev_rank_pct": float(g.ev_rank_pct.median()) if len(g) else None,
                       "median_ev_net": float(g.ev_net.median()) if len(g) else None,
                       "share_ev_pos": float((g.ev_net > 0).mean()) if len(g) else None,
                       "top_quintile_share": float((g.ev_rank_pct > .8).mean()) if len(g) else None,
                       "ask_range": f"{g.ask.min():.2f}-{g.ask.max():.2f}" if len(g) else None})
    # joint
    for (b, t), g in f.groupby(["delta_band", "premium_tercile"], observed=False):
        xt.append({"direction": k, "dimension": "delta_band x premium_tercile", "cell": f"{b}|{t}", "n": len(g),
                   "power": "OK" if len(g) >= 100 else "INSUFFICIENT_POWER",
                   "median_ev_rank_pct": float(g.ev_rank_pct.median()) if len(g) else None,
                   "median_ev_net": float(g.ev_net.median()) if len(g) else None,
                   "share_ev_pos": float((g.ev_net > 0).mean()) if len(g) else None,
                   "top_quintile_share": float((g.ev_rank_pct > .8).mean()) if len(g) else None, "ask_range": None})
pd.DataFrame(xt).to_csv(P / "p27_M7_crosstab.csv", index=False)

# friction survivors
fr = {}
for k in ["CALL", "PUT"]:
    f = d[d.direction == k]
    fr[k] = {
        "contracts": len(f),
        "as_configured_applicable": int((f.repro_applicability == "APPLICABLE").sum()),
        "as_configured_ev_pos": int((f.ev_net > 0).sum()),
        "as_configured_friction_out_of_range": int((f.repro_applicability == "FRICTION_OUT_OF_RANGE").sum()),
        "capped_no_domain_applicable": int((f.app_capped_no_domain == "APPLICABLE").sum()),
        "capped_no_domain_ev_pos": int((f.ev_capped_no_domain > 0).sum()),
        "full_half_spread_applicable": int((f.app_full_half_spread == "APPLICABLE").sum()),
        "full_half_spread_ev_pos": int((f.ev_full_half_spread > 0).sum()),
        "inside_domain_capped_vs_full_identical": bool(np.allclose(
            f.loc[f.repro_applicability == "APPLICABLE", "ev_net"], f.loc[f.repro_applicability == "APPLICABLE", "ev_full_half_spread"])),
        "outside_domain_rows": int((f.spread_fraction_mid_from_bid_ask > .30).sum()),
        "outside_domain_ev_pos_capped": int(((f.spread_fraction_mid_from_bid_ask > .30) & (f.ev_capped_no_domain > 0)).sum()),
        "outside_domain_ev_pos_full": int(((f.spread_fraction_mid_from_bid_ask > .30) & (f.ev_full_half_spread > 0)).sum()),
        "utility_pos_as_configured": int((f.utility_v2_repro > 0).sum()),
        "utility_pos_capped_no_domain": int((f.utility_capped_no_domain > 0).sum()),
        "utility_pos_full_half_spread": int((f.utility_full_half_spread > 0).sum()),
    }
S["friction_survivors"] = fr
S["probe_errors"] = int(d.get("probe_error", pd.Series(dtype=object)).notna().sum())
S["elapsed_s"] = round(time.time() - t0, 1)
(P / "p27_M7_decomposition.out.json").write_text(json.dumps(S, indent=1, default=str))
print(json.dumps(S, indent=1, default=str))
