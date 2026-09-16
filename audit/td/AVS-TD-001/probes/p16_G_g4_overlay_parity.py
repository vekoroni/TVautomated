"""p16_G_g4_overlay_parity.py -- Track G / G4 (REQ-WP6-04 overlay parity oracle).  READ-ONLY.

Mini parity check between the desk-gate overlay outputs and the Lab books for run 20260911_115904:
  desk_gate_20260911_115904_evening.csv (1,444) vs final_opportunity_book_<run>.csv (1,444)
  desk_gate_20260911_115904_morning.csv (19)    vs lab_signal_book_v3.csv (19)
  rank_20260911_115904_evening.csv               vs final book (population only)
Fields: ticker population, preferred contract identity (contract_symbol), direction, lab_verdict,
monetisability_state, opportunity_tier, thesis_state (if carried), invalidation/target.  All by direction.
Also: does any Lab book column carry the overlay vocabulary TRADE_PROBE / WATCH / NO_TRADE?
Outputs p16_G_g4_overlay_parity.json beside this file.
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
RUN = "20260911_115904"
R = ROOT / "data/output/runs" / RUN / "intelligence_lab"
C = ROOT / "dropbox/macro/coaching"
OUT = Path(__file__).with_suffix(".json")
rd = lambda p: pd.read_csv(p, dtype=str, keep_default_na=False)
fb, v3 = rd(R / f"final_opportunity_book_{RUN}.csv"), rd(R / "lab_signal_book_v3.csv")
de, dm = rd(C / "desk_gate/desk_gate_20260911_115904_evening.csv"), rd(C / "desk_gate/desk_gate_20260911_115904_morning.csv")
rk = rd(C / "rank/rank_20260911_115904_evening.csv")
def dirs(df):
    d = df["final_direction"] if "final_direction" in df.columns else df["direction"]
    return d.str.upper().map(lambda x: x if x in ("CALL", "PUT") else "OTHER")

def parity(lab, ov, label, pairs):
    lab = lab.copy(); ov = ov.copy(); lab["_dir"] = dirs(lab)
    out = {"label": label, "lab_rows": len(lab), "overlay_rows": len(ov), "overlay_columns": list(ov.columns)[:70]}
    L, O = set(lab["ticker"]), set(ov["ticker"])
    out["population"] = {"lab_tickers": len(L), "overlay_tickers": len(O), "intersection": len(L & O), "lab_only": sorted(L - O)[:20], "overlay_only": sorted(O - L)[:20],
                         "lab_dup_tickers": int(lab["ticker"].duplicated().sum()), "overlay_dup_tickers": int(ov["ticker"].duplicated().sum())}
    j = lab.merge(ov, on="ticker", how="inner", suffixes=("_lab", "_ov"))
    out["joined"] = len(j)
    fields = {}
    for lab_col, ov_col in pairs:
        if lab_col not in lab.columns or ov_col not in ov.columns:
            fields[f"{lab_col}~{ov_col}"] = "COLUMN ABSENT"; continue
        a = j[lab_col + "_lab"] if lab_col + "_lab" in j.columns else j[lab_col]
        b = j[ov_col + "_ov"] if ov_col + "_ov" in j.columns else j[ov_col]
        def feq(x, y):
            if x == y: return True
            try: return float(x) == float(y)
            except ValueError: return False
        m = pd.Series([feq(x, y) for x, y in zip(a, b)], index=j.index)
        by = {}
        for d in ("CALL", "PUT", "OTHER"):
            sel = j["_dir"] == d
            if sel.any():
                by[d] = f"{int(m[sel].sum())}/{int(sel.sum())}"
        ex = j.loc[~m, ["ticker", "_dir"]].assign(lab=a[~m].values, overlay=b[~m].values).head(4).values.tolist()
        fields[f"{lab_col}~{ov_col}"] = {"agree": int(m.sum()), "of": len(j), "by_dir": by, "disagree_examples": ex}
    out["fields"] = fields
    return out

PAIRS = [("contract_symbol", "contract_symbol"), ("final_direction", "direction"), ("lab_verdict", "lab_verdict"), ("final_action", "final_action"),
         ("opportunity_tier", "opportunity_tier"), ("monetisability_state", "monetisability_state"), ("invalidation_price", "invalidation_price"),
         ("structural_target", "target_price"), ("contract_ask", "contract_ask"), ("spread_pct", "spread_pct"), ("thesis_state", "thesis_state"),
         ("execution_viability_state", "execution_viability_state"), ("usmi_sector_alignment", "dg_macro_route_label")]
res = {"run": RUN,
       "evening_vs_final_book": parity(fb, de, "desk_gate evening vs final_opportunity_book", PAIRS),
       "morning_vs_v3_book": parity(v3, dm, "desk_gate morning vs lab_signal_book_v3", PAIRS),
       "rank_vs_final_book_population": parity(fb, rk, "rank evening vs final_opportunity_book", [("contract_symbol", "contract_symbol"), ("final_direction", "direction")])}
# overlay vocabulary leakage into the Lab books
VOC = {"TRADE_PROBE", "WATCH", "NO_TRADE"}
leak = {}
for name, df in (("final_opportunity_book", fb), ("lab_signal_book_v3", v3)):
    hits = {}
    for c in df.columns:
        if c.startswith("source_payload") or c.endswith("_json"):
            continue
        vals = set(df[c].unique())
        h = VOC & vals
        if h:
            hits[c] = {v: int((df[c] == v).sum()) for v in h}
    leak[name] = hits
res["overlay_vocabulary_in_lab_books"] = leak
res["desk_gate_dg_verdict_values"] = de["dg_verdict"].value_counts().to_dict() if "dg_verdict" in de.columns else None
OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
print(json.dumps(res, indent=1, default=str)[:9000])
