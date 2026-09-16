"""p11_B_columns: header inventory of every CSV in both stored runs (packages/ excluded).
Read-only. Output: p11_B_columns.csv (one row per CSV: path, rows, cols, presence flags)."""
import os, csv, sys
import pandas as pd
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
RUNS = ["20260911_115904", "20260910_150045"]
WANT = ["expected_move_5d_fraction","expected_move_10d_fraction","expected_move_20d_fraction",
        "volatility_budget_version","horizon_convention","forecast_horizon_basis",
        "l3_expected_move_1_5d","l3_expected_move_6_10d","l3_expected_move_11_20d",
        "garch_expected_move_1_5d","garch_expected_move_6_10d","garch_expected_move_11_20d",
        "l3_forward_realised_vol","forward_realised_vol","garch_forecast_vol",
        "l3_expected_move_legacy_deprecated",
        "spread_fraction_mid","spread_pct_of_mid","spread_pct","spread_pct_live","options_spread_pct",
        "spread_fraction","spread_ratio","morning_contract_spread_pct","current_contract_spread_pct",
        "execution_viability_spread_pct","contract_spread_pct","live_contract_spread_fraction",
        "opportunity_tier","opportunity_tier_reason","opportunity_tier_policy_version","governed_direction"]
out = os.path.join(ROOT, "audit/td/AVS-TD-001/probes/p11_B_columns.csv")
rows = []
for run in RUNS:
    base = os.path.join(ROOT, "data/output/runs", run)
    for dp, dn, fn in os.walk(base):
        dn[:] = [d for d in dn if d != "packages"]
        for f in fn:
            if not f.lower().endswith(".csv"):
                continue
            p = os.path.join(dp, f)
            try:
                df = pd.read_csv(p, low_memory=False)
            except Exception as e:
                rows.append({"run": run, "path": os.path.relpath(p, base), "rows": "ERR", "cols": str(e)[:60]})
                continue
            cols = set(df.columns)
            spread_cols = sorted(c for c in cols if "spread" in c.lower())
            r = {"run": run, "path": os.path.relpath(p, base), "rows": len(df), "cols": len(df.columns),
                 "spread_cols": "|".join(spread_cols)}
            for w in WANT:
                r[w] = int(w in cols)
            rows.append(r)
pd.DataFrame(rows).to_csv(out, index=False)
df = pd.DataFrame(rows)
print("csv files:", len(df))
for w in WANT:
    if w in df:
        hit = df[df[w] == 1]
        print(f"{w:40s} present_in={len(hit):3d}  " + ("; ".join(f"{a}:{b}" for a, b in zip(hit.run, hit.path))[:300]))
