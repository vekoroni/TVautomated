"""M5 panel: structural fields of every final_opportunity_book (usecols). RESEARCH_ONLY. Read-only."""
import glob, os, pandas as pd
RUNS = r"C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/data/output/runs"
OUT = os.path.join(os.path.dirname(__file__), "p25_M5_books_panel.csv")
WANT = ["ticker","governed_direction","direction","thesis_id","contract_symbol","contract_bid","contract_ask","contract_mid",
        "contract_iv","contract_delta","contract_vega","contract_theta","underlying_price","quote_as_of","liquidity_state",
        "morning_execution_permission","monetisability_state","lab_verdict","hidden_state_label","contract_dte",
        "morning_contract_mid","contract_mid_change_pct","morning_transition_state"]
frames = []
for f in sorted(glob.glob(RUNS + "/*/intelligence_lab/final_opportunity_book_*.csv")):
    run = os.path.basename(os.path.dirname(os.path.dirname(f)))
    hdr = pd.read_csv(f, nrows=0).columns
    use = [c for c in WANT if c in hdr]
    d = pd.read_csv(f, usecols=use, low_memory=False)
    d["run_id"] = run
    d["dir"] = d["governed_direction"] if "governed_direction" in d else d.get("direction")
    if "governed_direction" in d and "direction" in d:
        d["dir"] = d["governed_direction"].fillna(d["direction"])
    frames.append(d)
    print(run, len(d), "missing:", [c for c in WANT if c not in hdr])
p = pd.concat(frames, ignore_index=True)
p.to_csv(OUT, index=False)
print("rows", len(p))
