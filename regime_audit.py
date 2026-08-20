import pandas as pd
from pathlib import Path

from vanguard.core.actuarial_registry import canonical_cache_path

# ─────────────────────────────────────────────
# LOAD ACTUARIAL CACHE
# ─────────────────────────────────────────────
cache_path = canonical_cache_path()

df = pd.read_parquet(cache_path)

print("\n=== RAW CACHE LOADED ===")
print("Rows:", len(df))

# ─────────────────────────────────────────────
# SPLIT STATE KEY
# ─────────────────────────────────────────────
dimension_specs = df["state_dimensions"].dropna().astype(str).unique().tolist()
if len(dimension_specs) != 1:
    raise RuntimeError(f"Expected one governed state-dimension contract, got: {dimension_specs}")
state_cols = dimension_specs[0].split("|")

split = df["state_key"].str.split("|", expand=True)
split.columns = state_cols

df = pd.concat([df, split], axis=1)

# ─────────────────────────────────────────────
# BUILD AUDIT TABLE
# ─────────────────────────────────────────────
audit = df.groupby(state_cols).agg({
    "sample_size": "mean",
    "valid": "mean",
    "win_rate_10d": "mean",
    "expected_move_10d": "mean",
    "efficiency_10d": "mean"
}).reset_index()

# ─────────────────────────────────────────────
# DERIVE EDGE METRICS (KEY UPGRADE)
# ─────────────────────────────────────────────

# Expected Value (core edge metric)
audit["ev_10d"] = audit["win_rate_10d"] * audit["expected_move_10d"]

# Risk-adjusted EV (optional but useful)
audit["ev_risk_adj"] = audit["ev_10d"] / (abs(audit["efficiency_10d"]) + 1e-6)

# Flags
audit["has_edge"] = audit["ev_10d"] > 0
audit["strong_edge"] = audit["ev_10d"] > 0.005
audit["usable"] = (audit["sample_size"] >= 30)

# ─────────────────────────────────────────────
# SUMMARY OUTPUT
# ─────────────────────────────────────────────
print("\n=== REGIME COVERAGE SUMMARY ===")

total = len(audit)
usable = audit["usable"].sum()
edge = audit["has_edge"].sum()
strong_edge = audit["strong_edge"].sum()

print("Total states:", total)
print("Usable states (n>=30):", usable)
print("States with positive EV:", edge)
print("States with strong EV:", strong_edge)

# ─────────────────────────────────────────────
# TOP EV STATES (THIS IS YOUR EDGE)
# ─────────────────────────────────────────────
print("\n=== TOP EV STATES ===")

display_cols = state_cols + [
    "sample_size", "win_rate_10d", "expected_move_10d", "efficiency_10d", "ev_10d"
]
print(audit.sort_values("ev_10d", ascending=False).head(20)[display_cols])

# ─────────────────────────────────────────────
# WORST EV STATES (AVOID THESE)
# ─────────────────────────────────────────────
print("\n=== WORST EV STATES ===")

print(audit.sort_values("ev_10d", ascending=True).head(20)[display_cols])

# ─────────────────────────────────────────────
# SAVE OUTPUT
# ─────────────────────────────────────────────
out = Path("regime_audit_ev.csv")
audit.to_csv(out, index=False)

print("\nSaved:", out)
