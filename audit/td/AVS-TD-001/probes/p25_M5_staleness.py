"""M5 quote staleness as waiting cost. RESEARCH_ONLY. Read-only.
Stale rows: final_opportunity_book_20260911_115904 liquidity_state == QUOTE_STALE.
Later quote: option_contract_observations (db copy) same contract_symbol, run 20260911_115904, quote_as_of >= 2026-09-11.
Later quote source 2: EXACT_OPTION_QUOTE JSON for session 2026-09-11 indexed via dataset_registry.
"""
import os, sqlite3, numpy as np, pandas as pd
H = os.path.dirname(os.path.abspath(__file__))
BOOK = r"C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/data/output/runs/20260911_115904/intelligence_lab/final_opportunity_book_20260911_115904.csv"
cols = ["ticker","governed_direction","thesis_id","liquidity_state","quote_as_of","contract_symbol","contract_bid","contract_ask",
        "contract_mid","contract_iv","contract_delta","underlying_price","morning_contract_mid","contract_mid_change_pct","morning_transition_state"]
b = pd.read_csv(BOOK, usecols=cols, low_memory=False)
s = b[b.liquidity_state == "QUOTE_STALE"].copy()
s["sym"] = s.contract_symbol.astype(str).str.upper().str.replace("O:", "", regex=False)
c = sqlite3.connect("file:" + os.path.join(H, "..", "db_copies", "control_plane.sqlite") + "?mode=ro", uri=True)
o = pd.read_sql("select run_id, thesis_id, contract_symbol, quote_as_of, observed_at, bid, ask, spot, iv, delta, liquidity_state "
                "from option_contract_observations where run_id in ('20260910_150045','20260911_115904')", c)
o["mid"] = (o.bid + o.ask) / 2
# stale-side observation (what the book used) and the fresh one
old = o[(o.run_id == "20260911_115904") & (o.quote_as_of < "2026-09-11")].sort_values("quote_as_of").drop_duplicates("contract_symbol", keep="last")
new_obs = o[(o.run_id == "20260911_115904") & (o.quote_as_of >= "2026-09-11")]
print("fresh 11-Sep observations (option_contract_observations):", len(new_obs), "matching stale symbols:", int(new_obs.contract_symbol.isin(s.sym).sum()))
# Source 2: EXACT_OPTION_QUOTE payloads registered for session 2026-09-11 (read-only JSON under data/canonical)
import json
reg = pd.read_sql("select json_extract(scope_json,'$.extra.occ') occ, as_of, storage_uri from dataset_registry "
                  "where dataset_type='EXACT_OPTION_QUOTE' and session_date='2026-09-11'", c)
reg["occ"] = reg.occ.astype(str).str.upper()
print("exact quotes 11-Sep registered:", len(reg), "as_of>=11-Sep:", int((reg.as_of >= "2026-09-11").sum()),
      "stale symbols with any exact quote:", int(s.sym.isin(reg.occ).sum()),
      "with as_of>=11-Sep:", int(s.sym.isin(reg.loc[reg.as_of >= "2026-09-11", "occ"]).sum()))
recs = []
for _, r in reg[reg.occ.isin(s.sym)].iterrows():
    try:
        j = json.load(open(r.storage_uri, encoding="utf-8-sig"))
    except Exception as e:
        continue
    recs.append(dict(contract_symbol=r.occ, quote_as_of=j.get("quote_timestamp_utc") or r.as_of, bid=j.get("bid"), ask=j.get("ask"),
                     mid=j.get("mid"), iv=j.get("implied_vol"), delta=j.get("delta"), vega=j.get("vega"), spot=j.get("underlying_price"),
                     liquidity_state=("EXECUTABLE_NOW" if j.get("executable_now") else "NOT_EXECUTABLE_NOW"), observed_at=r.as_of))
ex = pd.DataFrame(recs, columns=["contract_symbol","quote_as_of","bid","ask","mid","iv","delta","vega","spot","liquidity_state","observed_at"])
ex.to_csv(os.path.join(H, "p25_M5_staleness_exact_quotes.csv"), index=False)
new = pd.concat([new_obs[ex.columns.intersection(new_obs.columns)], ex])
new = new[new.quote_as_of >= "2026-09-11"].sort_values("quote_as_of").drop_duplicates("contract_symbol", keep="last")
prev = o[o.run_id == "20260910_150045"].sort_values("quote_as_of").drop_duplicates("contract_symbol", keep="last")
m = s.merge(new.add_prefix("new_"), left_on="sym", right_on="new_contract_symbol", how="left") \
     .merge(old.add_prefix("old_"), left_on="sym", right_on="old_contract_symbol", how="left") \
     .merge(prev.add_prefix("p10_"), left_on="sym", right_on="p10_contract_symbol", how="left")
m["dir3"] = m.governed_direction.where(m.governed_direction.isin(["CALL", "PUT"]), "OTHER")
m["book_eq_p10_mid"] = np.isclose(m.contract_mid, m.p10_mid)
m["stale_hours"] = (pd.to_datetime(m.new_quote_as_of, utc=True) - pd.to_datetime(m.quote_as_of, utc=True)).dt.total_seconds() / 3600
m["d_mid"] = m.new_mid - m.contract_mid
m["d_mid_pct"] = m.d_mid / m.contract_mid * 100
m["abs_d_mid_pct"] = m.d_mid_pct.abs()
m["d_spot_pct"] = (pd.to_numeric(m.new_spot, errors="coerce") - m.underlying_price) / m.underlying_price * 100
m["d_iv_pct"] = (m.new_iv - m.contract_iv) / m.contract_iv * 100
m["mid_move_gt_half_spread"] = m.d_mid.abs() > (m.contract_ask - m.contract_bid) / 2
m["new_ask_vs_old_ask_pct"] = (m.new_ask - m.contract_ask) / m.contract_ask * 100
m.to_csv(os.path.join(H, "p25_M5_staleness.csv"), index=False)

def q(x):
    x = x.dropna()
    if len(x) == 0: return dict(n=0)
    return dict(n=len(x), median=round(x.median(), 2), p10=round(x.quantile(.1), 2), p25=round(x.quantile(.25), 2),
                p75=round(x.quantile(.75), 2), p90=round(x.quantile(.9), 2), mean=round(x.mean(), 2))
print("stale rows", len(s), "matched fresh", m.new_mid.notna().sum(), "book mid == 10-Sep obs mid", int(m.book_eq_p10_mid.sum()),
      "book morning_mid==contract_mid", int(np.isclose(s.contract_mid, s.morning_contract_mid).sum()),
      "contract_mid_change_pct non-null", int(s.contract_mid_change_pct.notna().sum()))
for g, x in [("ALL", m)] + list(m.groupby("dir3")):
    print(g, "stale_hours", q(x.stale_hours))
    for k in ["abs_d_mid_pct", "d_mid_pct", "d_spot_pct", "d_iv_pct", "new_ask_vs_old_ask_pct"]:
        print("  ", k, q(x[k]))
    print("   |dmid|>half-spread share", round(x.loc[x.new_mid.notna(), "mid_move_gt_half_spread"].mean(), 3))
print(m.groupby("new_liquidity_state").size())
print(m.groupby("morning_transition_state").abs_d_mid_pct.agg(["count", "median"]))

# ---- Proxy cohort (PARTIAL): contracts in the same 11-Sep book that WERE re-quoted on 11 Sep,
# priced at the same 10-Sep ~17Z quote the stale rows used, then at their 11-Sep quote.
allrows = b.copy()
allrows["sym"] = allrows.contract_symbol.astype(str).str.upper().str.replace("O:", "", regex=False)
exall = []
for _, r in reg[reg.as_of >= "2026-09-11"].iterrows():
    try:
        j = json.load(open(r.storage_uri, encoding="utf-8-sig"))
    except Exception:
        continue
    exall.append(dict(sym=r.occ, q11=j.get("quote_timestamp_utc") or r.as_of, bid11=j.get("bid"), ask11=j.get("ask"), mid11=j.get("mid"), iv11=j.get("implied_vol")))
exall = pd.DataFrame(exall).drop_duplicates("sym", keep="last")
p10u = prev.rename(columns={"contract_symbol": "sym", "quote_as_of": "q10", "bid": "bid10", "ask": "ask10", "mid": "mid10", "iv": "iv10", "spot": "spot10"})[["sym","q10","bid10","ask10","mid10","iv10","spot10"]]
px = allrows[allrows.liquidity_state != "QUOTE_STALE"].merge(p10u, on="sym").merge(exall, on="sym")
px = px[(px.mid10 > 0) & px.mid11.notna()]
px["dir3"] = px.governed_direction.where(px.governed_direction.isin(["CALL", "PUT"]), "OTHER")
px["hours"] = (pd.to_datetime(px.q11, utc=True) - pd.to_datetime(px.q10, utc=True)).dt.total_seconds() / 3600
px["d_mid_pct"] = (px.mid11 - px.mid10) / px.mid10 * 100
px["abs_d_mid_pct"] = px.d_mid_pct.abs()
px["abs_gt_half_spread"] = (px.mid11 - px.mid10).abs() > (px.ask10 - px.bid10) / 2
px["ask11_vs_mid10_pct"] = (px.ask11 - px.mid10) / px.mid10 * 100
px["d_iv_pts"] = (px.iv11 - px.iv10) * 100
px.to_csv(os.path.join(H, "p25_M5_staleness_proxy.csv"), index=False)
# how comparable is the proxy to the stale set?
print("PROXY n", len(px), "liquidity_state mix", px.liquidity_state.value_counts().to_dict())
print("stale-set mid10 median", round(m.contract_mid.median(), 3), "proxy mid10 median", round(px.mid10.median(), 3))
for g, x in [("ALL", px)] + list(px.groupby("dir3")):
    print("PROXY", g, "hours", q(x.hours))
    for k in ["abs_d_mid_pct", "d_mid_pct", "ask11_vs_mid10_pct", "d_iv_pts"]:
        print("   ", k, q(x[k]))
    print("    |dmid|>half-spread(10-Sep) share", round(x.abs_gt_half_spread.mean(), 3))
