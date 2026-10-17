"""G4 acceptance replay (read-only): the fixed Greek enrichment on stored runs.

For each selected contract of a stored evening run, take the provider quote from the MarketData EOD chain of that
date, calibrate the Heston parameters from the same stored chain (as the evening does), run the fixed
enrich_contract_with_heston_greeks and compare with what the run published before the fix.

Usage: venv\\Scripts\\python.exe Enhancements\\options_valuation_review\\g4_acceptance_replay.py <run_id> <YYYY-MM-DD>
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import avshunter_options_intelligence as oi  # noqa: E402

run, chain_date = sys.argv[1], sys.argv[2]
cols = ["ticker", "contract_occ_symbol", "recommended_contract", "contract_dte", "contract_mid", "contract_delta",
        "contract_gamma", "contract_theta", "contract_vega", "contract_vanna", "contract_iv", "spot", "current_price"]
pub = pd.read_csv(ROOT / f"data/output/runs/{run}/options/options_intelligence_{run}.csv",
                  usecols=lambda c: c in cols, low_memory=False)
pub = pub[pub["contract_delta"].notna()].copy()
pub["sym"] = pub["contract_occ_symbol"].fillna(pub["recommended_contract"]).astype(str).str.replace(" ", "")

out = []
for ticker, group in pub.groupby("ticker"):
    quotes = []
    for f in glob.glob(str(ROOT / f"data/canonical/market_observations/option_chain/{chain_date}/{ticker}/*.json")):
        quotes.extend(json.load(open(f)))
    if not quotes:
        continue
    chain = pd.DataFrame(quotes)
    chain_df = pd.DataFrame({"strike": chain["strike"], "dte": chain["dte"], "implied_vol": chain["implied_vol"],
                             "right": chain["right"], "delta": chain["delta"],
                             "open_interest": chain["open_interest"].fillna(0)})
    spot = float(chain["underlying_price"].dropna().iloc[0])
    params = oi.calibrate_heston(chain_df, spot)
    by_symbol = chain.set_index("symbol")
    for _, row in group.iterrows():
        if row["sym"] not in by_symbol.index:
            continue
        q = by_symbol.loc[row["sym"]]
        q = q.iloc[0] if isinstance(q, pd.DataFrame) else q
        contract = {"strike": q["strike"], "dte": row["contract_dte"], "right": q["right"], "iv": q["implied_vol"],
                    "implied_vol": q["implied_vol"], "delta": q["delta"], "gamma": q["gamma"],
                    "theta": q["theta"], "vega": q["vega"]}
        new = oi.enrich_contract_with_heston_greeks(contract, params, spot)
        out.append({"ticker": ticker, "sym": row["sym"], "right": q["right"], "mid": row["contract_mid"],
                    "provider_delta": q["delta"], "provider_theta": q["theta"],
                    "old_delta": row["contract_delta"], "new_delta": new.get("delta"),
                    "old_theta": row["contract_theta"], "new_theta": new.get("theta"),
                    "old_vanna": row["contract_vanna"], "new_vanna": new.get("vanna"),
                    "model_atm_delta": new.get("model_atm_delta"), "source": oi.contract_greeks_source(new),
                    "proxy_reason": (params or {}).get("proxy_reason")})

r = pd.DataFrame(out)
print(f"run {run}: replayed {len(r)} of {len(pub)} selected contracts")
print("published delta == provider:", f"{(np.isclose(r.new_delta, r.provider_delta, atol=1e-12)).mean():.1%}",
      "| source:", r.source.value_counts().to_dict(), "| proxy reason:", r.proxy_reason.value_counts().to_dict())
print("model_atm_delta reproduces the old published delta:",
      f"{(np.isclose(r.model_atm_delta, r.old_delta, atol=1e-6)).mean():.1%}")
band_old, band_new = r.old_delta.abs() < 0.5, r.new_delta.abs() < 0.5
print(f"EOD repair band (|delta|<0.50) changes: {(band_old != band_new).sum()} "
      f"(gain +7: {(~band_old & band_new).sum()}, lose +7: {(band_old & ~band_new).sum()})")


def vanna_award(vanna, right):
    return np.where((np.abs(vanna) >= oi.VANNA_STRONG_THRESHOLD)
                    & (((right == "C") & (vanna > 0)) | ((right == "P") & (vanna < 0))), 3, 0)


old_award = vanna_award(r.old_vanna.astype(float).fillna(0), r.right)
new_award = vanna_award(r.new_vanna.astype(float).fillna(0), r.right)
print(f"OIS vanna +3 awards: before {int((old_award > 0).sum())}, after {int((new_award > 0).sum())}, "
      f"changed {int((old_award != new_award).sum())}")
th_old = r.old_theta.abs() > 0.2 * r["mid"].astype(float)
th_new = r.new_theta.abs() > 0.2 * r["mid"].astype(float)
print(f"EV3 theta > 20% of mid rejects: before {int(th_old.sum())}, after {int(th_new.sum())}")
sign_bad = ((r.right == "C") & (r.new_delta <= 0)) | ((r.right == "P") & (r.new_delta >= 0))
print(f"EV3 delta sign/unit rejects after: {int(sign_bad.sum())}")
