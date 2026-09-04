"""AVS-RCA-002 A1 - Market Profile / Vanguard fail-open recomputation. READ ONLY."""
import pandas as pd, json, sys, pathlib
RUN = pathlib.Path(r"data\output\runs\20260904_004338")
PREV = pathlib.Path(r"data\output\runs\20260902_232526")

def load(p):
    return pd.read_csv(p, low_memory=False)

for label, run in (("20260904_004338", RUN), ("20260902_232526", PREV)):
    vg = run / "options" / f"vanguard_signals_enriched_{run.name}.csv"
    if not vg.exists():
        cand = list((run/"options").glob("vanguard_signals_enriched_*.csv"))
        vg = cand[0] if cand else None
    if vg is None:
        print(f"[{label}] no vanguard enriched file"); continue
    df = load(vg)
    print(f"\n===== {label}  {vg}  rows={len(df)} =====")
    print("profile_type value_counts:"); print(df["layer1__profile__profile_type"].fillna("<NULL>").value_counts().to_string())
    print("auction_state value_counts:"); print(df["layer1__auction_state"].fillna("<NULL>").value_counts().to_string())
    print("ready_to_trade value_counts:"); print(df["layer1__ready_to_trade"].astype(str).value_counts().to_string())
    print("migration direction value_counts:"); print(df["layer1__migration__direction"].fillna("<NULL>").value_counts().to_string())
    for c in ("layer1__profile__poc","layer1__profile__value_area_high","layer1__profile__value_area_low"):
        s = pd.to_numeric(df[c], errors="coerce")
        print(f"{c}: zero={int((s==0).sum())} null={int(s.isna().sum())} nonzero={int((s.notna()&(s!=0)).sum())}")
    print("timeframe value_counts:"); print(df["layer1__profile__timeframe"].fillna("<NULL>").value_counts().head(10).to_string())
    # INSUFFICIENT_DATA & ALIGNED
    m = (df["layer1__profile__profile_type"]=="INSUFFICIENT_DATA") & (df["layer1__auction_state"]=="ALIGNED")
    print(f"INSUFFICIENT_DATA & ALIGNED = {int(m.sum())}")
    dircol = "direction" if "direction" in df.columns else None
    if dircol:
        print("--- by direction (all rows) ---")
        print(df[dircol].fillna("<NULL>").value_counts().to_string())
        print("--- INSUFFICIENT_DATA rows by direction ---")
        print(df.loc[df["layer1__profile__profile_type"]=="INSUFFICIENT_DATA", dircol].fillna("<NULL>").value_counts().to_string())
        print("--- INSUFFICIENT_DATA & ALIGNED by direction ---")
        print(df.loc[m, dircol].fillna("<NULL>").value_counts().to_string())
