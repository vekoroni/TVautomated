"""S2b - band sensitivity: how many BLOCK_SPREAD losses become recoverable if the
delta and/or DTE bands are widened, holding the 25% spread gate fixed? READ ONLY."""
import glob, json, pathlib, sqlite3
import pandas as pd
R = "data/output/runs/20260905_151448"
OUT = pathlib.Path("audit/rca/AVS-RCA-003")
BASE = {"1_5d": {"dte": (7,21), "delta": (0.40,0.60)},
        "6_10d":{"dte": (21,35),"delta": (0.35,0.55)},
        "11_20d":{"dte":(35,60),"delta": (0.30,0.50)}}
SPREAD = 0.25
op = pd.read_csv(glob.glob(R+"/options/options_intelligence_*.csv")[0], low_memory=False)
sd = op["stand_down_reason"].fillna("").astype(str)
blocked = op[sd.str.startswith("BLOCK_SPREAD")].copy()
con = sqlite3.connect('file:data/canonical/control_plane.sqlite?mode=ro', uri=True)
uri = {t: u for t, u in con.execute(
    "select instrument_id,storage_uri from dataset_registry where dataset_type='OPTION_CHAIN' "
    "and source_run_id='20260905_151448'")}
chains = {}
for _, r in blocked.iterrows():
    tk = str(r["ticker"]); p = uri.get(tk)
    if p and tk not in chains:
        try: chains[tk] = json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
        except Exception: chains[tk] = []

def passes(tk, direction, hb, dwid, dtewid):
    band = BASE.get(hb, BASE["1_5d"])
    dlo, dhi = band["delta"][0]-dwid, band["delta"][1]+dwid
    tlo, thi = band["dte"][0]-dtewid, band["dte"][1]+dtewid
    want = "C" if direction == "CALL" else "P"
    for k in chains.get(tk, []):
        if str(k.get("right",""))[:1].upper() != want: continue
        dte = k.get("dte")
        if dte is None or not (tlo <= float(dte) <= thi): continue
        dl = k.get("delta")
        if dl is None or not (dlo <= abs(float(dl)) <= dhi): continue
        bid, ask = k.get("bid"), k.get("ask")
        if bid is None or ask is None or ask <= 0 or bid < 0 or bid > ask: continue
        mid = (bid+ask)/2.0
        if mid <= 0: continue
        if (ask-bid)/mid <= SPREAD: return True
    return False

scenarios = [("baseline (0.40-0.60 / 7-21d)", 0.00, 0),
             ("delta +/-0.05", 0.05, 0), ("delta +/-0.10", 0.10, 0), ("delta +/-0.15", 0.15, 0),
             ("dte +/-7d", 0.00, 7), ("dte +/-14d", 0.00, 14),
             ("delta +/-0.10 AND dte +/-7d", 0.10, 7),
             ("delta +/-0.15 AND dte +/-14d", 0.15, 14)]
print(f"BLOCK_SPREAD losses tested: {len(blocked)}  (spread gate held at {SPREAD:.0%})\n")
print(f"{'scenario':32s} {'recoverable':>11s} {'%':>7s}  {'CALL':>5s} {'PUT':>5s}")
res = []
for name, dw, tw in scenarios:
    ok = blocked.apply(lambda r: passes(str(r["ticker"]), str(r["final_direction"]),
                                        str(r.get("horizon_bucket") or "1_5d"), dw, tw), axis=1)
    n = int(ok.sum())
    call = int((ok & (blocked["final_direction"]=="CALL")).sum())
    put  = int((ok & (blocked["final_direction"]=="PUT")).sum())
    print(f"  {name:30s} {n:11d} {n/len(blocked)*100:6.1f}%  {call:5d} {put:5d}")
    res.append({"scenario": name, "delta_widen": dw, "dte_widen_days": tw,
                "recoverable": n, "pct": round(n/len(blocked)*100,1), "call": call, "put": put})
pd.DataFrame(res).to_csv(OUT / "05_s2b_band_sensitivity.csv", index=False)
print("\nNote: 'recoverable' = a contract exists on the SAME stored chain that clears the")
print("25% spread gate within the widened bands. It does not assert the trade is profitable;")
print("economics and the monetisability floor would still have to pass.")
