"""S1 - re-value NOT_MONETISABLE / LIMITED rows with time value retained.
Black-Scholes, r=0, q=0, sigma = the contract's own implied vol held constant,
valued at the structural target on the final session of the planned hold.
Read-only; no network."""
import glob, math, pathlib
import pandas as pd, numpy as np
OUT = pathlib.Path("audit/rca/AVS-RCA-003")
R = "data/output/runs/20260905_151448"
lab = pd.read_csv(glob.glob(R + "/intelligence_lab/final_opportunity_book_*.csv")[0], low_memory=False)

def N(x):  # standard normal cdf
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
def bs(S, K, T, sig, is_call):
    if T <= 0 or sig <= 0 or S <= 0 or K <= 0:
        return max(S - K, 0.0) if is_call else max(K - S, 0.0)
    d1 = (math.log(S / K) + 0.5 * sig * sig * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    return S * N(d1) - K * N(d2) if is_call else K * N(-d2) - S * N(-d1)

HOLD = {"1_5d": 5, "6_10d": 10, "11_20d": 20}
num = lambda c: pd.to_numeric(lab.get(c), errors="coerce")
rows = []
for i, r in lab.iterrows():
    state = str(r.get("monetisability_state") or "")
    ask = pd.to_numeric(r.get("monetisability_entry_ask"), errors="coerce")
    K   = pd.to_numeric(r.get("monetisability_strike"), errors="coerce")
    tgt = pd.to_numeric(r.get("monetisability_structural_target_spot"), errors="coerce")
    iv  = pd.to_numeric(r.get("contract_iv"), errors="coerce")
    dte = pd.to_numeric(r.get("dte"), errors="coerce")
    if any(pd.isna(x) for x in (ask, K, tgt, iv, dte)) or ask <= 0:
        continue
    is_call = str(r.get("final_direction")) == "CALL"
    hold = HOLD.get(str(r.get("hold_period")), 5)
    T = max(dte - hold, 0) / 365.0
    tv_val = bs(float(tgt), float(K), T, float(iv), is_call)
    intr = max(float(tgt) - float(K), 0.0) if is_call else max(float(K) - float(tgt), 0.0)
    pp_intr = (intr - ask) / ask * 100.0
    pp_tv   = (tv_val - ask) / ask * 100.0
    minp = float(r.get("monetisability_minimum_profit_pct") or 20.0)
    new_state = "MONETISABLE" if pp_tv >= minp else ("LIMITED" if pp_tv > 0 else "NOT_MONETISABLE")
    rows.append({"ticker": r.get("ticker"), "direction": r.get("final_direction"),
                 "state_now": state, "reason_now": r.get("monetisability_reason"),
                 "entry_ask": round(float(ask),2), "strike": float(K),
                 "target_spot": float(tgt), "dte": float(dte), "hold_days": hold,
                 "residual_dte_at_target": round(float(dte)-hold,1), "iv": round(float(iv),4),
                 "intrinsic_at_target": round(intr,4), "bs_value_at_target": round(tv_val,4),
                 "time_value_ignored": round(tv_val-intr,4),
                 "profit_pct_intrinsic": round(pp_intr,2), "profit_pct_timevalue": round(pp_tv,2),
                 "min_profit_pct": minp, "state_under_timevalue": new_state,
                 "flips": state != new_state})
df = pd.DataFrame(rows)
df.to_csv(OUT / "05_s1_timevalue_revaluation.csv", index=False)
print(f"rows valued: {len(df)} of {len(lab)} (need ask/strike/target/iv/dte all present)")
print("\n=== transition matrix: intrinsic-only  ->  time-value ===")
print(pd.crosstab(df["state_now"], df["state_under_timevalue"]).to_string())
print("\n=== flips out of NOT_MONETISABLE / LIMITED ===")
sub = df[df["state_now"].isin(["NOT_MONETISABLE","LIMITED"])]
print(f"  population: {len(sub)}  flipping to MONETISABLE: {int((sub['state_under_timevalue']=='MONETISABLE').sum())}"
      f"  to LIMITED: {int((sub['state_under_timevalue']=='LIMITED').sum())}  staying NOT: {int((sub['state_under_timevalue']=='NOT_MONETISABLE').sum())}")
print("  by direction:")
print(pd.crosstab(sub["direction"], sub["state_under_timevalue"]).to_string())
print("\n=== reverse test: do any MONETISABLE rows FAIL under time value? ===")
mon = df[df["state_now"]=="MONETISABLE"]
print(f"  MONETISABLE valued: {len(mon)}  now failing: {int((mon['state_under_timevalue']!='MONETISABLE').sum())}")
print("  (BS value >= intrinsic always, so intrinsic-only is a strict LOWER bound:")
print("   it can only create false negatives, never false positives)")
print("\n=== magnitude of the ignored time value ===")
tv = df["time_value_ignored"]
print(f"  median ${tv.median():.2f}  p75 ${tv.quantile(.75):.2f}  p90 ${tv.quantile(.90):.2f}  max ${tv.max():.2f}")
print(f"  as % of entry ask: median {(df['time_value_ignored']/df['entry_ask']*100).median():.1f}%")
print("\n=== the flippers ===")
f = sub[sub["flips"]].sort_values("profit_pct_timevalue", ascending=False)
print(f[["ticker","direction","state_now","entry_ask","dte","residual_dte_at_target","iv",
         "profit_pct_intrinsic","profit_pct_timevalue","state_under_timevalue"]].to_string(index=False))
