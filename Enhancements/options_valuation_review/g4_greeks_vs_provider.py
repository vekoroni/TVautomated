"""G4 measurement v2: published contract Greeks vs MarketData EOD chain Greeks (independent source). Read-only."""
import glob, json, os, sys
import pandas as pd, numpy as np

repo, run, chain_date = sys.argv[1], sys.argv[2], sys.argv[3]
csv = f"{repo}/data/output/runs/{run}/options/options_intelligence_{run}.csv"
cols = ["ticker", "contract_occ_symbol", "recommended_contract", "contract_strike", "contract_dte", "contract_mid",
        "contract_delta", "contract_gamma", "contract_theta", "contract_vega", "contract_iv", "contract_greeks_source",
        "spot", "current_price", "signal_direction", "direction"]
df = pd.read_csv(csv, usecols=lambda c: c in cols, low_memory=False)
df = df[df["contract_delta"].notna()].copy()
df["sym"] = df["contract_occ_symbol"].fillna(df["recommended_contract"]).astype(str).str.replace(" ", "")

rows = []
for t in df["ticker"].dropna().unique():
    for f in glob.glob(f"{repo}/data/canonical/market_observations/option_chain/{chain_date}/{t}/*.json"):
        try:
            for q in json.load(open(f)):
                rows.append({k: q.get(k) for k in ("symbol", "delta", "gamma", "theta", "vega", "implied_vol",
                                                    "underlying_price", "quote_timestamp_utc")})
        except Exception:
            pass
ch = pd.DataFrame(rows).drop_duplicates("symbol", keep="last").rename(columns=lambda c: "p_" + c)
m = df.merge(ch, left_on="sym", right_on="p_symbol", how="inner")
print(f"run {run}: {len(df)} contracts, {len(m)} matched to provider chain {chain_date}")
print("source:", m["contract_greeks_source"].value_counts().to_dict())
for g in ("delta", "gamma", "theta", "vega"):
    a, p = pd.to_numeric(m[f"contract_{g}"], errors="coerce"), pd.to_numeric(m[f"p_{g}"], errors="coerce")
    ok = a.notna() & p.notna()
    err = (a[ok] - p[ok]).abs()
    rel = err / p[ok].abs().replace(0, np.nan)
    print(f"{g:5s} n={ok.sum():4d} abs err p50 {err.median():.4f} p90 {err.quantile(.9):.4f} | "
          f"rel err p50 {rel.median():.1%} p90 {rel.quantile(.9):.1%} | identical {(err < 1e-6).mean():.1%}")
d = m["contract_delta"].astype(float); pdl = m["p_delta"].astype(float)
print("abs delta err > 0.05: %.1f%%  > 0.10: %.1f%%  > 0.20: %.1f%%" % tuple(100 * ((d - pdl).abs() > x).mean() for x in (.05, .10, .20)))
print("EOD repair band |delta|<0.50 flips: %d of %d" % (((d.abs() < .5) != (pdl.abs() < .5)).sum(), len(m)))
print("sign flips:", int((np.sign(d) != np.sign(pdl)).sum()))
th, mid = m["contract_theta"].astype(float).abs(), m["contract_mid"].astype(float)
pth = m["p_theta"].astype(float).abs()
print("EV3 theta>20%%mid reject: published %d, provider %d, disagree %d" %
      ((th > .2 * mid).sum(), (pth > .2 * mid).sum(), ((th > .2 * mid) != (pth > .2 * mid)).sum()))
m["err"] = (d - pdl).abs()
print(m.sort_values("err", ascending=False).head(10)[["ticker", "sym", "contract_dte", "p_delta", "contract_delta",
      "p_implied_vol", "contract_iv"]].to_string(index=False))
