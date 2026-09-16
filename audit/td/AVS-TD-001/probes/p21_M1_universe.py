"""p21_M1_universe.py -- read-only. Builds (1) pipeline universe = union of tickers across all
discovery_candidates_ultimate_*.csv (usecols only), (2) ticker->sector map from most recent run
carrying a sector per ticker, cross-checked with data/universe/polygon_liquid_universe.csv,
(3) coverage vs the price store copy, (4) final-book direction / usmi alignment counts for the
runs of 5-11 Sep, (5) caches a wide close matrix (parquet) in the SCRATCH dir for later probes.
Outputs: p21_M1_sector_map.csv, p21_M1_universe_out.json beside this script.
"""
import os, glob, json, sqlite3, sys, time
import pandas as pd, numpy as np
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
PROBES = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes")
SCRATCH = os.environ.get("M1_SCRATCH", os.path.join(PROBES, "_scratch_m1"))
os.makedirs(SCRATCH, exist_ok=True)
DB = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "db_copies", "historical_prices.sqlite")
t0 = time.time()
out = {}

# 1. pipeline universe + sector map from discovery CSVs
files = sorted(glob.glob(os.path.join(ROOT, "data", "output", "runs", "*", "discovery", "discovery_candidates_ultimate_*.csv")))
rows = []
for f in files:
    run = os.path.basename(os.path.dirname(os.path.dirname(f)))
    hdr = pd.read_csv(f, nrows=0).columns
    use = [c for c in ("ticker", "sector", "sector_etf", "industry", "scanner_sector") if c in hdr]
    d = pd.read_csv(f, usecols=use, dtype=str)
    d["run"] = run
    rows.append(d)
disc = pd.concat(rows, ignore_index=True)
disc["ticker"] = disc["ticker"].str.upper().str.strip()
out["discovery_files"] = len(files)
out["discovery_rows_total"] = int(len(disc))
pipe_univ = sorted(disc["ticker"].dropna().unique())
out["pipeline_universe_n"] = len(pipe_univ)
print("discovery files", len(files), "rows", len(disc), "pipeline universe", len(pipe_univ))
# per-ticker most recent run with non-null sector
disc_s = disc[disc["sector"].notna() & (disc["sector"].str.strip() != "")].sort_values("run")
last = disc_s.groupby("ticker").tail(1).set_index("ticker")
out["tickers_with_sector_from_discovery"] = int(len(last))
print("sector vocabulary (discovery):", disc_s["sector"].value_counts().to_dict())
out["sector_vocab_discovery"] = disc_s["sector"].value_counts().to_dict()
out["sector_etf_vocab_discovery"] = disc_s["sector_etf"].value_counts().to_dict() if "sector_etf" in disc_s else None

# final-book sector columns (primary) for cross-check
fb_path = os.path.join(ROOT, "data", "output", "runs", "20260911_115904", "intelligence_lab", "final_opportunity_book_20260911_115904.csv")
fb = pd.read_csv(fb_path, usecols=["ticker", "sector", "gics_sector", "gics_sector_norm", "sector_etf", "final_direction", "usmi_sector_alignment", "usmi_alignment_priority", "usmi_state", "usmi_packet_id"], dtype=str)
out["final_book_primary_rows"] = int(len(fb))
out["fb_gics_sector_norm_vocab"] = fb["gics_sector_norm"].value_counts(dropna=False).to_dict()
out["fb_sector_etf_vocab"] = fb["sector_etf"].value_counts(dropna=False).to_dict()
out["fb_final_direction"] = fb["final_direction"].value_counts(dropna=False).to_dict()
out["fb_usmi_sector_alignment"] = fb["usmi_sector_alignment"].value_counts(dropna=False).to_dict()
out["fb_usmi_alignment_priority"] = fb["usmi_alignment_priority"].value_counts(dropna=False).to_dict()
out["fb_usmi_state"] = fb["usmi_state"].value_counts(dropna=False).to_dict()
out["fb_usmi_packet_id"] = fb["usmi_packet_id"].value_counts(dropna=False).to_dict()
print("fb final_direction", out["fb_final_direction"]); print("fb usmi_sector_alignment", out["fb_usmi_sector_alignment"])
print("fb gics_sector_norm", out["fb_gics_sector_norm_vocab"])
# agreement between discovery sector and gics_sector_norm
m = fb.merge(last[["sector"]].rename(columns={"sector": "disc_sector"}), left_on="ticker", right_index=True, how="left")
out["fb_sector_eq_gics_norm_share"] = float((m["sector"] == m["gics_sector_norm"]).mean())
out["fb_disc_sector_eq_fb_sector_share"] = float((m["disc_sector"] == m["sector"]).mean())

# direction/alignment per run for 5-11 Sep run books (CALL/PUT thesis sets)
dir_runs = {}
for run in ["20260905_151448", "20260906_213931", "20260909_071646", "20260910_150045", "20260911_115904"]:
    p = os.path.join(ROOT, "data", "output", "runs", run, "intelligence_lab", f"final_opportunity_book_{run}.csv")
    if not os.path.exists(p):
        dir_runs[run] = "ABSENT"; continue
    hdr = pd.read_csv(p, nrows=0).columns
    use = [c for c in ("ticker", "final_direction", "usmi_sector_alignment", "usmi_packet_id") if c in hdr]
    b = pd.read_csv(p, usecols=use, dtype=str)
    b["ticker"] = b["ticker"].str.upper().str.strip()
    dir_runs[run] = {"rows": int(len(b)), "final_direction": b["final_direction"].value_counts(dropna=False).to_dict() if "final_direction" in b else None,
                     "usmi_sector_alignment": b["usmi_sector_alignment"].value_counts(dropna=False).to_dict() if "usmi_sector_alignment" in b else None,
                     "usmi_packet_id": b["usmi_packet_id"].value_counts(dropna=False).to_dict() if "usmi_packet_id" in b else None}
    b.to_csv(os.path.join(SCRATCH, f"book_dir_{run}.csv"), index=False)
    print(run, dir_runs[run]["final_direction"], dir_runs[run]["usmi_sector_alignment"])
out["direction_by_run"] = dir_runs

# 2. governed universe file
gu = pd.read_csv(os.path.join(ROOT, "data", "universe", "polygon_liquid_universe.csv"), dtype=str)
gu["ticker"] = gu["ticker"].str.upper().str.strip()
out["governed_universe_n"] = int(len(gu))
out["governed_sector_vocab"] = gu["sector"].value_counts(dropna=False).to_dict()
out["governed_industry_n_unique"] = int(gu["industry"].nunique())
ind_counts = gu["industry"].value_counts()
ind_counts.to_csv(os.path.join(PROBES, "p21_M1_industry_vocab.csv"), header=["n"])
print("governed universe", len(gu), "sectors", out["governed_sector_vocab"])
print("industries", gu["industry"].nunique())

# 3. price store tickers
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
px = pd.read_sql("select ticker, trading_date, close from ohlcv_daily", con)
con.close()
px["ticker"] = px["ticker"].str.upper()
wide = px.pivot(index="trading_date", columns="ticker", values="close").sort_index()
wide.index = pd.to_datetime(wide.index)
store_tickers = set(wide.columns)
out["store_tickers_n"] = len(store_tickers); out["store_sessions_n"] = int(len(wide))
out["store_first"] = str(wide.index[0].date()); out["store_last"] = str(wide.index[-1].date())
wide.to_parquet(os.path.join(SCRATCH, "close_wide.parquet"))
print("price wide", wide.shape, "cached")

# 4. build sector map: priority = discovery most recent run > governed file > UNKNOWN
smap = pd.DataFrame(index=sorted(store_tickers | set(pipe_univ) | set(gu["ticker"])))
smap.index.name = "ticker"
smap["sector_disc"] = last["sector"].reindex(smap.index)
smap["sector_etf_disc"] = last["sector_etf"].reindex(smap.index) if "sector_etf" in last else None
smap["industry_disc"] = last["industry"].reindex(smap.index) if "industry" in last else None
smap["sector_run"] = last["run"].reindex(smap.index)
g = gu.set_index("ticker")
smap["sector_gov"] = g["sector"].reindex(smap.index)
smap["sector_etf_gov"] = g["sector_etf"].reindex(smap.index)
smap["industry_gov"] = g["industry"].reindex(smap.index)
smap["sector"] = smap["sector_disc"].fillna(smap["sector_gov"]).fillna("UNKNOWN")
smap["sector_etf"] = smap["sector_etf_disc"].fillna(smap["sector_etf_gov"]).fillna("UNKNOWN")
smap["industry"] = smap["industry_disc"].fillna(smap["industry_gov"]).fillna("UNKNOWN")
smap["source"] = np.where(smap["sector_disc"].notna(), "discovery_run", np.where(smap["sector_gov"].notna(), "governed_universe_file", "UNKNOWN"))
smap["in_store"] = smap.index.isin(store_tickers)
smap["in_pipeline_universe"] = smap.index.isin(pipe_univ)
smap["in_governed"] = smap.index.isin(gu["ticker"])
both = smap["sector_disc"].notna() & smap["sector_gov"].notna()
out["disc_vs_gov_agree_share"] = float((smap.loc[both, "sector_disc"] == smap.loc[both, "sector_gov"]).mean()); out["disc_vs_gov_both_n"] = int(both.sum())
smap.to_csv(os.path.join(PROBES, "p21_M1_sector_map.csv"))
cov = {
    "store_tickers": int(smap["in_store"].sum()),
    "store_with_sector": int((smap["in_store"] & (smap["sector"] != "UNKNOWN")).sum()),
    "store_unknown": int((smap["in_store"] & (smap["sector"] == "UNKNOWN")).sum()),
    "pipeline_tickers": int(smap["in_pipeline_universe"].sum()),
    "pipeline_in_store": int((smap["in_pipeline_universe"] & smap["in_store"]).sum()),
    "pipeline_with_sector": int((smap["in_pipeline_universe"] & (smap["sector"] != "UNKNOWN")).sum()),
    "pipeline_unknown": int((smap["in_pipeline_universe"] & (smap["sector"] == "UNKNOWN")).sum()),
    "pipeline_sector_from_discovery": int((smap["in_pipeline_universe"] & (smap["source"] == "discovery_run")).sum()),
    "pipeline_sector_from_governed": int((smap["in_pipeline_universe"] & (smap["source"] == "governed_universe_file")).sum()),
    "governed_in_store": int((smap["in_governed"] & smap["in_store"]).sum()),
    "governed_not_in_store": int((smap["in_governed"] & ~smap["in_store"]).sum()),
    "pipeline_not_in_store": sorted(smap.index[smap["in_pipeline_universe"] & ~smap["in_store"]].tolist())[:50],
}
out["coverage"] = cov
out["sector_counts_pipeline"] = smap.loc[smap["in_pipeline_universe"], "sector"].value_counts().to_dict()
out["sector_counts_store"] = smap.loc[smap["in_store"], "sector"].value_counts().to_dict()
print(json.dumps(cov, indent=1)); print(out["sector_counts_pipeline"])
out["runtime_s"] = round(time.time() - t0, 1)
json.dump(out, open(os.path.join(PROBES, "p21_M1_universe_out.json"), "w"), indent=1, default=str)
print("done", out["runtime_s"], "s")
