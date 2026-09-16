"""M6 step 3 - per gate x run x direction: removed, survivor vs removed hit rate, difference with Newcombe (Wilson) interval,
pooled rows with a ticker-cluster Poisson bootstrap interval. RESEARCH_ONLY. Read-only.
Input p26_M6_outcomes.csv (symmetric vol-budget barrier, K=1.5). hit = hit_sym (TARGET_FIRST); also side_correct.
OTHER rows (no direction) use touch_any (either barrier touched) - a movement measure, not a directional hit.
Any arm with n < 100 -> INSUFFICIENT_POWER. Also standardised mean difference (survivor - removed) of available scores = what the gate selects on.
Outputs p26_M6_gate_table.csv."""
import os, math
import numpy as np, pandas as pd

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
RUNS = os.path.join(ROOT, "data", "output", "runs")
PR = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes")
O = pd.read_csv(os.path.join(PR, "p26_M6_outcomes.csv"), low_memory=False)
for c in ("in_book", "touch_any", "hit_sym", "side_correct"):
    O[c] = O[c].map({True: 1.0, False: 0.0, "True": 1.0, "False": 0.0})

# contract-log spread rejection and EOD manifest reason, per run
O["spread_rej"] = 0.0; O["eod_reason"] = np.nan
for run in O.run_id.unique():
    f = os.path.join(RUNS, run, "options", f"contract_rejection_log_{run}.csv")
    if os.path.exists(f):
        C = pd.read_csv(f, low_memory=False)
        s = set(C.loc[C.rejection_reason.fillna("").str.contains("SPREAD_GT"), "ticker"])
        m = (O.run_id == run) & O.ticker.isin(s); O.loc[m, "spread_rej"] = 1.0
    e = os.path.join(RUNS, run, "morning_validation", f"eod_dropoff_audit_{run}.csv")
    if os.path.exists(e):
        E = pd.read_csv(e, usecols=["ticker", "eod_dropoff_reason"]).drop_duplicates("ticker").set_index("ticker").eod_dropoff_reason
        m = O.run_id == run; O.loc[m, "eod_reason"] = O.loc[m, "ticker"].map(E)

ls = O.last_stage_reached.fillna("")
reached_disc = ~ls.isin(["UNIVERSE", "SCANNER"]) & ~O.dropoff_stage.fillna("").isin(["BETWEEN_UNIVERSE_AND_DISCOVERY", "BETWEEN_SCANNER_AND_DISCOVERY"])
reached_oi = O.oi_verdict.notna()
ib = O.in_book == 1
flags = O.audit_flags.fillna("")
GO = ["GO", "GO_LIMIT"]

GATES = [
    # name, population mask, removed mask, removes-from-pipeline, selects-on description
    ("DISCOVERY_SCOPE", pd.Series(True, index=O.index), ~reached_disc, True,
     "avshunter_discovery_ULTIMATE liquidity/price/tier-4 filters + no horizon signal (seven causes under one reason code)"),
    ("VANGUARD_REJECT", reached_disc, ls.eq("VANGUARD_REJECT"), True, "package/OHLCV validation failure (DATA_FAILURE_NO_OHLCV)"),
    ("OPTIONS_INTEL_SCOPE_tier_WAIT_merge", reached_disc & ~ls.eq("VANGUARD_REJECT"),
     ls.eq("VANGUARD") & O.dropoff_stage.eq("BETWEEN_VANGUARD_AND_OPTIONS"), True, "discovery tier not in {0,1,2} or intent WAIT without Vanguard support; merge miss"),
    ("EIL_EXECUTION_STAGE_prebook", reached_oi, reached_oi & ~ib, True, "EIL/EOD manifest exclusion before the book (older runs; EXECUTION/SHADOW_BOOK last stage)"),
    ("OI_VERDICT_STAND_DOWN", reached_oi, O.oi_verdict.eq("STAND_DOWN"), False, "Options Intelligence verdict STAND_DOWN (no usable contract / gate block / non-directional)"),
    ("SPREAD_contract_log_GT_25PCT", reached_oi, O.spread_rej.eq(1.0), False, "any contract for the ticker rejected SPREAD_GT_25PCT"),
    ("OPEN_INTEREST_LOW_OI_flag", reached_oi, flags.str.contains("LOW_OI"), False, "dropoff audit flag LOW_OI on the OI contract"),
    ("EOD_MANIFEST_reason_not_preserved", ib & O.eod_reason.notna(), ib & O.eod_reason.notna() & O.eod_reason.ne("PRESERVED_TO_MORNING_VALIDATION"), False,
     "eod_dropoff_reason other than PRESERVED_TO_MORNING_VALIDATION (contract repair flags, data insufficient, no options route)"),
    ("EIL_SIGNAL_not_EXECUTE", ib & O.eil_signal_verdict.notna(), ib & O.eil_signal_verdict.notna() & ~O.eil_signal_verdict.isin(["EXECUTE", "EXECUTE_WITH_CAUTION"]), False,
     "eil_signal_verdict BLOCKED / WATCHLIST / NOT_EVALUATED"),
    ("LAB_VERDICT_BLOCKED", ib & O.lab_verdict.notna(), ib & O.lab_verdict.eq("BLOCKED"), False, "lab_verdict BLOCKED"),
    ("LAB_VERDICT_not_GO", ib & O.lab_verdict.notna(), ib & O.lab_verdict.notna() & ~O.lab_verdict.isin(GO), False, "lab_verdict other than GO / GO_LIMIT"),
    ("MORNING_GATE_not_GO", ib & O.morning_execution_permission.notna(), ib & O.morning_execution_permission.notna() & ~O.morning_execution_permission.isin(GO + ["CONTRACT_REPAIR"]), False,
     "morning_execution_permission NOT_ELIGIBLE / NO_GO_* / LIQUIDITY_STILL_PENDING / WAIT"),
    ("OPPORTUNITY_TIER_BLOCK", ib & O.opportunity_tier.notna(), ib & O.opportunity_tier.eq("BLOCK"), False, "opportunity_tier hard veto (spread ceiling, invalidation, direction, target)"),
    ("QUOTE_FRESHNESS_not_fresh", ib & O.quote_freshness.notna(), ib & O.quote_freshness.notna() & ~O.quote_freshness.isin(["FRESH", "SESSION_ALIGNED"]), False,
     "quote_freshness SYNTHETIC_NOT_EXECUTABLE / UNAVAILABLE"),
    ("LIQUIDITY_STATE_not_EXECUTABLE_NOW", ib & O.liquidity_state.notna(), ib & O.liquidity_state.notna() & O.liquidity_state.ne("EXECUTABLE_NOW"), False, "liquidity_state"),
    ("MACRO_ROUTE_usmi_not_neutral", ib & O.usmi_sector_alignment.notna(), ib & O.usmi_sector_alignment.notna() & ~O.usmi_sector_alignment.isin(["NEUTRAL", "UNAVAILABLE", "ALIGNED"]), False,
     "usmi_sector_alignment headwind/conflict (no row carries such a value)"),
    ("FINAL_ACTION_BLOCK", ib & O.final_action.notna(), ib & O.final_action.eq("BLOCK"), False, "final_action BLOCK"),
]
SCORES = ["discovery_composite_score", "scanner_score", "vanguard_probability_edge", "oi_options_score", "sigma", "composite_score", "options_score",
          "trigger_score", "priority_score", "eil_composite_eod", "ev3_ev_lower_bound_return"]
for s in SCORES:
    O[s] = pd.to_numeric(O[s], errors="coerce")


def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan, np.nan)
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, c - h, c + h


def newcombe(k1, n1, k2, n2):
    p1, l1, u1 = wilson(k1, n1); p2, l2, u2 = wilson(k2, n2)
    if n1 == 0 or n2 == 0:
        return (np.nan, np.nan, np.nan)
    d = p1 - p2
    return d, d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)


rng = np.random.default_rng(20260913)


def cluster_boot(df, rem, metric, reps=500):
    d = pd.DataFrame({"t": df.ticker.values, "r": rem.values, "y": df[metric].values})
    g = d.groupby("t").apply(lambda x: pd.Series({"ns": (~x.r).sum(), "ks": x.y[~x.r].sum(), "nr": x.r.sum(), "kr": x.y[x.r].sum()}), include_groups=False)
    if len(g) < 5:
        return (np.nan, np.nan)
    W = rng.poisson(1.0, size=(len(g), reps))
    ns, ks, nr, kr = [(W * g[c].values.astype(float)[:, None]).sum(0) for c in ("ns", "ks", "nr", "kr")]
    with np.errstate(invalid="ignore", divide="ignore"):
        diff = ks / ns - kr / nr
    diff = diff[np.isfinite(diff)]
    return (np.percentile(diff, 2.5), np.percentile(diff, 97.5)) if len(diff) > 50 else (np.nan, np.nan)


rows = []
for name, pop, rem, leaves, desc in GATES:
    for scope, runs in [("POOLED", None)] + [(r, [r]) for r in sorted(O.run_id.unique())]:
        base = pop if runs is None else pop & O.run_id.isin(runs)
        for d3 in ("CALL", "PUT", "OTHER"):
            m = base & O.direction3.eq(d3)
            n_pop = int(m.sum()); n_rem = int((m & rem).sum())
            if n_pop == 0:
                continue
            ok = m & O.recon.eq("OK")
            metric = "touch_any" if d3 == "OTHER" else "hit_sym"
            s_ok, r_ok = ok & ~rem, ok & rem
            ns, nr = int(s_ok.sum()), int(r_ok.sum())
            ks, kr = O.loc[s_ok, metric].sum(), O.loc[r_ok, metric].sum()
            d, lo, hi = newcombe(ks, ns, kr, nr)
            rec = dict(gate=name, scope=scope, direction=d3, condition="TEST|sym_vol_budget_K1.5|h=row_or_10", leaves_pipeline=leaves, selects_on=desc,
                       n_population=n_pop, n_removed=n_rem, n_survived=n_pop - n_rem, n_surv_resolved=ns, n_rem_resolved=nr, outcome_metric=metric,
                       surv_rate=ks / ns if ns else np.nan, rem_rate=kr / nr if nr else np.nan, diff_surv_minus_rem=d, diff_lo_newcombe=lo, diff_hi_newcombe=hi)
            if d3 != "OTHER":
                ks2, kr2 = O.loc[s_ok, "side_correct"].sum(), O.loc[r_ok, "side_correct"].sum()
                d2, lo2, hi2 = newcombe(ks2, ns, kr2, nr)
                rec.update(surv_side_correct=ks2 / ns if ns else np.nan, rem_side_correct=kr2 / nr if nr else np.nan, side_diff=d2, side_lo=lo2, side_hi=hi2,
                           surv_med_dir_ret_sig=O.loc[s_ok, "dir_ret_sig"].median(), rem_med_dir_ret_sig=O.loc[r_ok, "dir_ret_sig"].median())
            else:
                rec.update(surv_med_abs_move_sig=O.loc[s_ok, "abs_move_sig"].median(), rem_med_abs_move_sig=O.loc[r_ok, "abs_move_sig"].median())
            rec["power"] = "INSUFFICIENT_POWER" if min(ns, nr) < 100 else "n>=100"
            rec["removed_rate_above_survivor"] = bool(nr and ns and rec["rem_rate"] > rec["surv_rate"])
            rec["interval_excludes_zero"] = bool(np.isfinite(lo) and (lo > 0 or hi < 0))
            if scope == "POOLED" and min(ns, nr) >= 100:
                rec["boot_lo_ticker_cluster"], rec["boot_hi_ticker_cluster"] = cluster_boot(O[s_ok | r_ok], rem[s_ok | r_ok], metric)
            if scope == "POOLED":
                for s in SCORES:
                    a, b = O.loc[m & ~rem, s].dropna(), O.loc[m & rem, s].dropna()
                    if len(a) >= 20 and len(b) >= 20:
                        sd = math.sqrt((a.var() + b.var()) / 2)
                        rec["smd_" + s] = (a.mean() - b.mean()) / sd if sd > 0 else np.nan
            rows.append(rec)
T = pd.DataFrame(rows)
T.to_csv(os.path.join(PR, "p26_M6_gate_table.csv"), index=False)
pd.set_option("display.width", 250)
P = T[T.scope == "POOLED"]
print(P[["gate", "direction", "n_population", "n_removed", "n_surv_resolved", "n_rem_resolved", "surv_rate", "rem_rate", "diff_surv_minus_rem", "diff_lo_newcombe",
         "diff_hi_newcombe", "boot_lo_ticker_cluster", "boot_hi_ticker_cluster", "power"]].round(4).to_string(index=False))
print(P[["gate", "direction", "surv_side_correct", "rem_side_correct", "side_diff", "side_lo", "side_hi", "surv_med_dir_ret_sig", "rem_med_dir_ret_sig", "surv_med_abs_move_sig", "rem_med_abs_move_sig"]].round(4).to_string(index=False))
print(P[["gate", "direction"] + [c for c in P.columns if c.startswith("smd_")]].round(2).to_string(index=False))
R = T[(T.scope != "POOLED")]
print("per-run cells:", len(R), " with both arms n>=100:", int((R.power == "n>=100").sum()))
print(R[R.power == "n>=100"][["gate", "scope", "direction", "n_surv_resolved", "n_rem_resolved", "surv_rate", "rem_rate", "diff_lo_newcombe", "diff_hi_newcombe"]].round(3).to_string(index=False))
