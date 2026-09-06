"""S2 - for every BLOCK_SPREAD loss, did a contract exist on the stored chain
that would have passed the horizon's own DTE/delta/spread gates? READ ONLY."""
import glob, json, pathlib, sqlite3
import pandas as pd, numpy as np
OUT = pathlib.Path("audit/rca/AVS-RCA-003")
R = "data/output/runs/20260905_151448"
BANDS = {"1_5d":  {"dte":(7,21),  "spread":0.15, "delta":(0.40,0.60)},
         "6_10d": {"dte":(21,35), "spread":0.25, "delta":(0.35,0.55)},
         "11_20d":{"dte":(35,60), "spread":0.35, "delta":(0.30,0.50)}}
FLAT_SPREAD = 0.25   # MAX_SPREAD_PCT, the terminal gate

op = pd.read_csv(glob.glob(R+"/options/options_intelligence_*.csv")[0], low_memory=False)
sd = op["stand_down_reason"].fillna("").astype(str)
blocked = op[sd.str.startswith("BLOCK_SPREAD")].copy()

con = sqlite3.connect('file:data/canonical/control_plane.sqlite?mode=ro', uri=True)
uri = {t: u for t, u in con.execute(
    "select instrument_id,storage_uri from dataset_registry "
    "where dataset_type='OPTION_CHAIN' and source_run_id='20260905_151448'")}

rows = []
for _, r in blocked.iterrows():
    tk = str(r["ticker"]); direction = str(r["final_direction"])
    hb = str(r.get("horizon_bucket") or "1_5d"); band = BANDS.get(hb, BANDS["1_5d"])
    p = uri.get(tk)
    if not p or not pathlib.Path(p).exists():
        rows.append({"ticker": tk, "direction": direction, "horizon": hb,
                     "chain_rows": 0, "verdict": "DATA_chain_absent"}); continue
    try:
        chain = json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    except Exception:
        rows.append({"ticker": tk, "direction": direction, "horizon": hb,
                     "chain_rows": 0, "verdict": "DATA_chain_unreadable"}); continue
    want = "C" if direction == "CALL" else "P"
    n_side = n_dte = n_delta = n_spread = 0
    best = None
    for k in chain:
        if str(k.get("right", ""))[:1].upper() != want: continue
        n_side += 1
        dte = k.get("dte")
        if dte is None or not (band["dte"][0] <= float(dte) <= band["dte"][1]): continue
        n_dte += 1
        dl = k.get("delta")
        if dl is None or not (band["delta"][0] <= abs(float(dl)) <= band["delta"][1]): continue
        n_delta += 1
        bid, ask = k.get("bid"), k.get("ask")
        if bid is None or ask is None or ask <= 0 or bid < 0 or bid > ask: continue
        mid = (bid + ask) / 2.0
        if mid <= 0: continue
        sp = (ask - bid) / mid
        if sp <= min(band["spread"], FLAT_SPREAD):
            n_spread += 1
            if best is None or sp < best[0]: best = (sp, k.get("strike"), dte, abs(float(dl)), mid)
    if n_side == 0:      v = "DATA_no_side_on_chain"
    elif n_dte == 0:     v = "ECONOMIC_no_expiry_in_dte_band"
    elif n_delta == 0:   v = "ECONOMIC_no_strike_in_delta_band"
    elif n_spread == 0:  v = "ECONOMIC_no_tradeable_spread_in_band"
    else:                v = "DESIGN_viable_contract_existed"
    rows.append({"ticker": tk, "direction": direction, "horizon": hb,
                 "chain_rows": len(chain), "side_rows": n_side, "in_dte_band": n_dte,
                 "in_delta_band": n_delta, "passing_spread": n_spread,
                 "best_spread_pct": round(best[0]*100, 1) if best else None,
                 "best_strike": best[1] if best else None,
                 "best_dte": best[2] if best else None,
                 "best_abs_delta": round(best[3], 3) if best else None,
                 "best_mid": best[4] if best else None,
                 "verdict": v})
df = pd.DataFrame(rows)
df.to_csv(OUT / "05_s2_contract_selection.csv", index=False)
print(f"BLOCK_SPREAD losses examined: {len(df)}")
print("\n=== verdict distribution ===")
vc = df["verdict"].value_counts()
for k, v in vc.items(): print(f"  {v:5d}  {k}")
print("\n=== by direction ===")
print(pd.crosstab(df["verdict"], df["direction"]).to_string())
print("\n=== where a viable contract DID exist (DESIGN) ===")
w = df[df["verdict"] == "DESIGN_viable_contract_existed"]
print(f"  count: {len(w)}  ({len(w)/max(len(df),1)*100:.1f}% of BLOCK_SPREAD losses)")
if len(w):
    print(f"  best alternative spread: median {w['best_spread_pct'].median():.1f}%  "
          f"p25 {w['best_spread_pct'].quantile(.25):.1f}%  p75 {w['best_spread_pct'].quantile(.75):.1f}%")
    print(f"  best alternative mid: median ${w['best_mid'].median():.2f}")
    print(w[["ticker","direction","horizon","best_strike","best_dte","best_abs_delta",
             "best_spread_pct","best_mid"]].head(15).to_string(index=False))
print("\n=== gate-by-gate survivorship (how far chains get before failing) ===")
for c_ in ("side_rows","in_dte_band","in_delta_band","passing_spread"):
    if c_ in df: print(f"  {c_:16s} median per ticker: {df[c_].median():.0f}   zero for {int((df[c_]==0).sum())} tickers")
