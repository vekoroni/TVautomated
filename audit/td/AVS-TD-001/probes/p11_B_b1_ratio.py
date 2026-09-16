"""p11_B_b1_ratio: REQ-WP1-01/02, ALG-01. Read-only.
For both runs: (a) v2 field presence; (b) legacy differenced ratio l3_6_10d/l3_1_5d and garch_6_10d/garch_1_5d,
split CALL/PUT/OTHER; (c) offline v2 reproduction via domain.volatility_budget on l3_forward_realised_vol;
(d) ALG-01 and REQ-WP1-02 fixtures and edge cases. Output: p11_B_b1_ratio.csv + p11_B_b1_ratio.txt"""
import os, sys, math
import pandas as pd, numpy as np
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"; sys.path.insert(0, ROOT)
from domain.volatility_budget import checkpoint_fields, calculate_volatility_budget
RUNS = ["20260911_115904", "20260910_150045"]
lines, rows = [], []
NAN = float("nan")


def say(s):
    print(s); lines.append(s)


def stats(name, s):
    s = pd.Series(s, dtype="float64").dropna()
    if len(s) == 0:
        say(f"  {name}: n=0"); return
    inside = int(((s >= 1.407) & (s <= 1.421)).sum())
    say(f"  {name}: n={len(s)} min={s.min():.5f} max={s.max():.5f} median={s.median():.5f} in[1.407,1.421]={inside} outside={len(s)-inside}")


V2 = ["expected_move_5d_fraction", "expected_move_10d_fraction", "expected_move_20d_fraction",
      "volatility_budget_version", "horizon_convention", "forecast_horizon_basis",
      "forward_realised_vol", "l3_expected_move_legacy_deprecated", "l3_forward_realised_vol"]
for run in RUNS:
    base = os.path.join(ROOT, "data/output/runs", run)
    g = pd.read_csv(os.path.join(base, "qomega", f"garch_forecasts_{run}.csv"), low_memory=False)
    fob = pd.read_csv(os.path.join(base, "intelligence_lab", f"final_opportunity_book_{run}.csv"), low_memory=False)
    ex = pd.read_csv(os.path.join(base, "execution", f"execution_v3_5_{run}.csv"), low_memory=False)
    say(f"=== run {run}: garch_forecasts rows={len(g)} cols={list(g.columns)}")
    for name, df in (("garch_forecasts", g), ("final_opportunity_book", fob), ("execution_v3_5", ex)):
        say(f"  {name}: rows={len(df)} v2 fields present={[c for c in V2 if c in df.columns]} absent={[c for c in V2 if c not in df.columns]}")
    dirmap = fob.set_index("ticker")["governed_direction"].astype(str).str.upper().to_dict()
    g["dir"] = g["ticker"].map(dirmap).fillna("OTHER")
    g.loc[~g["dir"].isin(["CALL", "PUT"]), "dir"] = "OTHER"
    say(f"  direction split (garch_forecasts joined to final_opportunity_book on ticker): {g['dir'].value_counts().to_dict()}")
    g["legacy_ratio"] = g["l3_expected_move_6_10d"] / g["l3_expected_move_1_5d"]
    say("  LEGACY differenced ratio l3_expected_move_6_10d / l3_expected_move_1_5d (expect 0.4142 by construction, 2dp rounding noise):")
    for d in ("CALL", "PUT", "OTHER"):
        s = g.loc[g["dir"] == d, "legacy_ratio"].replace([np.inf, -np.inf], np.nan).dropna()
        near = int(((s - 0.41421).abs() < 0.01).sum()) if len(s) else 0
        say(f"    {d}: n={len(s)} min={s.min() if len(s) else NAN:.4f} max={s.max() if len(s) else NAN:.4f} within0.01of0.4142={near} nonpos_1_5d={int((g.loc[g['dir']==d,'l3_expected_move_1_5d']<=0).sum())}")
    fob["dir"] = fob["governed_direction"].astype(str).str.upper(); fob.loc[~fob["dir"].isin(["CALL", "PUT"]), "dir"] = "OTHER"
    fob["garch_ratio"] = pd.to_numeric(fob["garch_expected_move_6_10d"], errors="coerce") / pd.to_numeric(fob["garch_expected_move_1_5d"], errors="coerce")
    say("  LEGACY ratio garch_expected_move_6_10d / garch_expected_move_1_5d in final_opportunity_book:")
    for d in ("CALL", "PUT", "OTHER"):
        s = fob.loc[fob["dir"] == d, "garch_ratio"].replace([np.inf, -np.inf], np.nan).dropna()
        near = int(((s - 0.41421).abs() < 0.01).sum()) if len(s) else 0
        say(f"    {d}: n={len(s)} rows_total={int((fob['dir']==d).sum())} min={s.min() if len(s) else NAN:.4f} max={s.max() if len(s) else NAN:.4f} within0.01of0.4142={near}")
    say("  OFFLINE v2: checkpoint_fields(l3_forward_realised_vol) per garch_forecasts row -> 10d/5d and 20d/5d:")
    r10, r20, q = [], [], {}
    for _, rr in g.iterrows():
        vol = rr.get("l3_forward_realised_vol"); vol = None if pd.isna(vol) else float(vol)
        cf = checkpoint_fields(vol)
        a, b, c = cf["expected_move_5d_fraction"], cf["expected_move_10d_fraction"], cf["expected_move_20d_fraction"]
        st = calculate_volatility_budget(vol, 10).quality_state; q[st] = q.get(st, 0) + 1
        r10.append(b / a if a else np.nan); r20.append(c / a if a else np.nan)
        rows.append({"run": run, "ticker": rr["ticker"], "dir": rr["dir"], "l3_forward_realised_vol": vol,
                     "l3_em_1_5d": rr["l3_expected_move_1_5d"], "l3_em_6_10d": rr["l3_expected_move_6_10d"],
                     "legacy_ratio": rr["legacy_ratio"], "v2_5d": a, "v2_10d": b, "v2_20d": c,
                     "v2_ratio_10_5": (b / a if a else np.nan), "v2_quality_state": st,
                     "v2_version": cf["volatility_budget_version"], "horizon_convention": cf["horizon_convention"],
                     "forecast_horizon_basis": cf["forecast_horizon_basis"]})
    g["v2_ratio"] = r10; g["v2_ratio_20"] = r20
    say(f"    quality_state counts: {q}")
    for d in ("CALL", "PUT", "OTHER"):
        stats(f"{d} v2 10d/5d", g.loc[g["dir"] == d, "v2_ratio"])
        s = pd.Series(g.loc[g["dir"] == d, "v2_ratio_20"]).dropna()
        say(f"  {d} v2 20d/5d: n={len(s)} min={s.min() if len(s) else NAN:.5f} max={s.max() if len(s) else NAN:.5f}")
    v2_10 = pd.Series([r["v2_10d"] for r in rows if r["run"] == run]); v2_5 = pd.Series([r["v2_5d"] for r in rows if r["run"] == run])
    leg_10 = (g["l3_expected_move_6_10d"] / 100.0).reset_index(drop=True); leg_5 = (g["l3_expected_move_1_5d"] / 100.0).reset_index(drop=True)
    say(f"    rows where legacy 6_10d/100 == v2 10d (tol 1e-6): {int(((v2_10 - leg_10).abs() < 1e-6).sum())} of {len(g)}")
    ratio = (leg_5 / v2_5).replace([np.inf, -np.inf], np.nan).dropna()
    say(f"    legacy_1_5d/100 divided by v2_5d: n={len(ratio)} min={ratio.min():.4f} max={ratio.max():.4f} median={ratio.median():.4f} (sqrt(5/7)=0.8452 if legacy applies calendar->trading 5/7; 2dp rounding adds noise)")
pd.DataFrame(rows).to_csv(os.path.join(ROOT, "audit/td/AVS-TD-001/probes/p11_B_b1_ratio.csv"), index=False)
say("=== FIXTURES")
cf = checkpoint_fields(0.30)
say(f"  ALG-01 sigma=0.30: 5d={cf['expected_move_5d_fraction']:.5f} (exp 0.04226) 10d={cf['expected_move_10d_fraction']:.5f} (exp 0.05976) 20d={cf['expected_move_20d_fraction']:.5f} (exp 0.08452) ratio10/5={cf['expected_move_10d_fraction']/cf['expected_move_5d_fraction']:.5f} version={cf['volatility_budget_version']} conv={cf['horizon_convention']} basis={cf['forecast_horizon_basis']} vstate={cf['vol_validation_state']} bias={cf['bias_multiplier']}")
b = calculate_volatility_budget(0.40, 7)
say(f"  REQ-WP1-02 sigma=0.40 h=7: move={b.expected_move_fraction:.5f} (exp 0.06667) basis={b.forecast_horizon_basis} conv={b.horizon_convention} q={b.quality_state} vstate={b.validation_state} version={b.calculation_version} bias_applied={b.bias_multiplier_applied}")
for label, vol, h in (("sigma None", None, 5), ("sigma 0", 0.0, 5), ("sigma -0.1", -0.1, 5), ("sigma 3.0 boundary", 3.0, 5), ("sigma 3.01", 3.01, 5), ("sigma nan", float("nan"), 5), ("sigma inf", float("inf"), 5), ("sigma 0.30 h=1", 0.30, 1), ("sigma 0.30 h=20", 0.30, 20)):
    b = calculate_volatility_budget(vol, h); say(f"  edge {label}: move={b.expected_move_fraction} quality_state={b.quality_state} validation_state={b.validation_state}")
for label, h in (("h=0", 0), ("h=21", 21), ("h=-1", -1), ("h=5.5", 5.5), ("h=5.0", 5.0)):
    try:
        b = calculate_volatility_budget(0.30, h); say(f"  edge {label}: move={b.expected_move_fraction} q={b.quality_state} (accepted)")
    except Exception as e:
        say(f"  edge {label}: raises {type(e).__name__}: {e}")
say(f"  checkpoint_fields(None) = {checkpoint_fields(None)}")
open(os.path.join(ROOT, "audit/td/AVS-TD-001/probes/p11_B_b1_ratio.txt"), "w", encoding="utf-8").write("\n".join(lines))
