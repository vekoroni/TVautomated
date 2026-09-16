"""p21_M1_joinability.py -- read-only. Is the macro/USMI -> ticker join testable on stored artefacts?
(1) Primary + comparison run artefacts: every column whose name contains sector / usmi / regime_alignment / routing,
    with fill share and top values (structure only, Rule 10).
(2) decision_outcome_ledger copy census already extracted by p21_M1_ledger.py (p21_M1_ledger_usmi.csv): usmi_* fill by run.
(3) Duplicate tickers in morning_validated_trades (AMBIGUOUS_JOIN exposure, comprehension item 13).
Output: p21_M1_joinability_out.json beside this script. RESEARCH_ONLY.
"""
import os, re, json, glob
import pandas as pd

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
PROBES = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes")
PAT = re.compile(r"sector|usmi|regime_alignment|routing", re.I)
out = {}
for run in ("20260911_115904", "20260910_150045"):
    base = os.path.join(ROOT, "data", "output", "runs", run)
    arts = [os.path.join(base, "intelligence_lab", f"final_opportunity_book_{run}.csv"),
            os.path.join(base, "intelligence_lab", "lab_signal_book_v3.csv"),
            os.path.join(base, "morning_validation", f"morning_validated_trades_{run}.csv"),
            os.path.join(base, "trades", f"execution_gated_{run}.csv"),
            os.path.join(base, "discovery", f"discovery_candidates_ultimate_{run}.csv")]
    r = {}
    for a in arts:
        if not os.path.exists(a):
            r[os.path.relpath(a, base)] = "ABSENT"
            continue
        hdr = pd.read_csv(a, nrows=0).columns
        cols = [c for c in hdr if PAT.search(c)]
        use = list(dict.fromkeys(["ticker"] + cols)) if "ticker" in hdr else cols
        d = pd.read_csv(a, usecols=use, dtype=str)
        info = {"rows": int(len(d)), "matching_columns": len(cols)}
        if "ticker" in d:
            info["duplicate_ticker_rows"] = int(d["ticker"].duplicated(keep=False).sum())
        for c in cols:
            s = d[c]
            filled = s.notna() & (s.str.strip() != "") & (~s.str.upper().isin(["NAN", "NONE", "NULL"]))
            info[c] = {"fill_share": round(float(filled.mean()), 4), "n_unique": int(s[filled].nunique()),
                       "top": {k: int(v) for k, v in s[filled].value_counts().head(4).items()}}
        r[os.path.relpath(a, base)] = info
    out[run] = r
L = pd.read_csv(os.path.join(PROBES, "p21_M1_ledger_usmi.csv"), dtype=str)
out["ledger"] = {"rows": int(len(L)),
                 "event_type": L["event_type"].value_counts().to_dict(),
                 "usmi_sector_alignment_by_run": {k: v.value_counts(dropna=False).to_dict() for k, v in L.groupby("run_id")["usmi_sector_alignment"]},
                 "usmi_packet_id": L["usmi_packet_id"].value_counts(dropna=False).to_dict(),
                 "direction": L["direction"].value_counts(dropna=False).to_dict()}
# does any run artefact column carry the 4-label vocabulary?
voc = ["PRIORITY_UPGRADE", "ADVERSE_REGIME_RS_REQUIRED", "PRIORITY_WATCH", "NOT_YET_CONFIRMED"]
hits = {}
for run in ("20260911_115904",):
    for a in glob.glob(os.path.join(ROOT, "data", "output", "runs", run, "**", "*.csv"), recursive=True):
        if os.path.getsize(a) > 60_000_000:
            continue
        try:
            txt = open(a, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        n = {v: txt.count(v) for v in voc if v in txt}
        if n:
            hits[os.path.relpath(a, ROOT)] = n
out["four_label_vocab_in_primary_run_csvs"] = hits
json.dump(out, open(os.path.join(PROBES, "p21_M1_joinability_out.json"), "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str)[:20000])
