"""M5 early-lane number reproduction. RESEARCH_ONLY. Read-only.
IV of the SAME OCC contract at selection vs an earlier stored session.
Sources: final_opportunity_book (structure: contract_symbol, contract_iv, monetisability_state),
options_intelligence_20260905_151448.csv (W3.6 population), stored OPTION_CHAIN JSON indexed via
db_copies/control_plane.sqlite dataset_registry, db_copies/phantom_history.db options_greeks_history (weekly).
"""
import os, json, sqlite3, numpy as np, pandas as pd
H = os.path.dirname(os.path.abspath(__file__))
RUNS = r"C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/data/output/runs"
cp = sqlite3.connect("file:" + os.path.join(H, "..", "db_copies", "control_plane.sqlite") + "?mode=ro", uri=True)
ph = sqlite3.connect("file:" + os.path.join(H, "..", "db_copies", "phantom_history.db") + "?mode=ro", uri=True)
REG = pd.read_sql("select session_date, upper(instrument_id) t, storage_uri from dataset_registry where dataset_type='OPTION_CHAIN'", cp)
CHAIN_SESS = sorted(REG.session_date.unique())
HOL = {"2026-07-03", "2026-09-07"}
TRADING = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-07-01", "2026-09-11") if d.strftime("%Y-%m-%d") not in HOL]
_cache = {}


def chain(session, ticker):
    k = (session, ticker)
    if k not in _cache:
        rec = {}
        for u in REG[(REG.session_date == session) & (REG.t == ticker)].storage_uri.tolist():
            try:
                for e in json.load(open(u, encoding="utf-8-sig")):
                    rec[str(e.get("symbol") or "").upper()] = e
            except Exception:
                pass
        _cache[k] = rec
    return _cache[k]


def iv_w36(e):  # the W3.6 conversion rule, reproduced
    if e is None:
        return None
    try:
        v = float(e.get("implied_vol"))
    except (TypeError, ValueError):
        return None
    if v != v or v <= 0:
        return None
    return v / 100 if v > 5 else v


def phantom_iv(date, ticker, sym):
    r = ph.execute("select iv from options_greeks_history where ticker=? and snapshot_date=? and contract_symbol=?",
                   (ticker, date, sym)).fetchone()
    return r[0] if r and r[0] and r[0] > 0 else None


def stats(x):
    x = pd.Series(x, dtype=float).dropna()
    if len(x) == 0:
        return dict(n=0)
    o = sorted(x); n = len(o)
    return dict(n=n, median=round(x.median(), 3), w36_p25=round(o[n // 4], 3), w36_p75=round(o[(3 * n) // 4], 3),
                p10=round(x.quantile(.1), 3), p25=round(x.quantile(.25), 3), p75=round(x.quantile(.75), 3),
                p90=round(x.quantile(.9), 3), iqr=round(x.quantile(.75) - x.quantile(.25), 3),
                share_ge_20=round((x >= 20).mean(), 4), mean=round(x.mean(), 1), insufficient_power=n < 100)


out = []


def run_population(label, df, iv_col, sym_col, dir_col, sel_session, lookbacks):
    for lb_name, then_session, src in lookbacks:
        for _, r in df.iterrows():
            t = str(r["ticker"]).upper()
            sym = str(r[sym_col]).upper().replace("O:", "")
            try:
                now = float(r[iv_col])
            except (TypeError, ValueError):
                continue
            if now != now or now <= 0:
                continue
            if now > 5:
                now /= 100
            if then_session is None:
                then = None
            elif src == "chain":
                then = iv_w36(chain(then_session, t).get(sym))
            else:
                then = phantom_iv(then_session, t, sym)
            d = str(r[dir_col]) if pd.notna(r.get(dir_col)) else ""
            out.append(dict(population=label, lookback=lb_name, then_session=then_session, source=src, ticker=t, symbol=sym,
                            dir3=d if d in ("CALL", "PUT") else "OTHER", sel_session=sel_session, iv_now=now, iv_then=then,
                            iv_change_pct=(now - then) / then * 100 if then else None,
                            iv_change_pts=(now - then) * 100 if then else None,
                            iv_then_floor=bool(then is not None and then <= 0.001)))


def tback(s, d):
    return TRADING[TRADING.index(s) - d]


# --- Population W36: options_intelligence rows for MONETISABLE tickers of run 20260905_151448 (W3.6 selection logic)
R = "20260905_151448"
book = pd.read_csv(f"{RUNS}/{R}/intelligence_lab/final_opportunity_book_{R}.csv",
                   usecols=["ticker", "monetisability_state", "contract_symbol", "contract_iv", "governed_direction"], low_memory=False)
mt = set(book.loc[book.monetisability_state == "MONETISABLE", "ticker"].astype(str).str.upper())
hdr = pd.read_csv(f"{RUNS}/{R}/options/options_intelligence_{R}.csv", nrows=0).columns
oi = pd.read_csv(f"{RUNS}/{R}/options/options_intelligence_{R}.csv",
                 usecols=[c for c in ["ticker", "recommended_contract", "contract_iv", "final_direction", "direction", "evidence_session_date"] if c in hdr],
                 low_memory=False)
oi = oi[oi.ticker.astype(str).str.upper().isin(mt) & oi.recommended_contract.notna() & oi.contract_iv.notna()].copy()
fd = oi["final_direction"] if "final_direction" in oi else pd.Series(index=oi.index, dtype=object)
oi["dirx"] = fd.fillna(oi["direction"]) if "direction" in oi else fd
print("W36 population: MONETISABLE book rows", int((book.monetisability_state == "MONETISABLE").sum()),
      "distinct tickers", len(mt), "options rows", len(oi),
      "evidence_session", list(oi["evidence_session_date"].dropna().astype(str).str[:10].unique()[:3]) if "evidence_session_date" in oi else None)
sel = "2026-09-04"
earlier = [s for s in CHAIN_SESS if s < sel]
run_population("W36_options_intelligence_20260905", oi, "contract_iv", "recommended_contract", "dirx", sel,
               [("stored_chain_3_back(W36)", earlier[-3], "chain"), ("stored_chain_4_back", earlier[-4], "chain")])
# --- Population BOOK 20260905 MONETISABLE rows; lookback counted in TRADING sessions
bm = book[book.monetisability_state == "MONETISABLE"]
lbs = [(f"trading_{d}_back", tback(sel, d) if tback(sel, d) in CHAIN_SESS else None, "chain") for d in (1, 2, 3, 4, 5)]
lbs.append(("trading_5_back_phantom", "2026-08-28", "phantom"))
run_population("BOOK_20260905_MONETISABLE", bm, "contract_iv", "contract_symbol", "governed_direction", sel, lbs)
# --- Books 20260910_150045 and 20260911_115904 (selection quote session 2026-09-10)
for R2 in ("20260910_150045", "20260911_115904"):
    b2 = pd.read_csv(f"{RUNS}/{R2}/intelligence_lab/final_opportunity_book_{R2}.csv",
                     usecols=["ticker", "monetisability_state", "contract_symbol", "contract_iv", "governed_direction"], low_memory=False)
    b2 = b2[b2.monetisability_state == "MONETISABLE"]
    lbs = [(f"trading_{d}_back", tback("2026-09-10", d) if tback("2026-09-10", d) in CHAIN_SESS else None, "chain") for d in (1, 2, 3, 4, 5)]
    lbs.append(("trading_4_back_phantom", "2026-09-04", "phantom"))
    run_population(f"BOOK_{R2}_MONETISABLE", b2, "contract_iv", "contract_symbol", "governed_direction", "2026-09-10", lbs)

res = pd.DataFrame(out)
res.to_csv(os.path.join(H, "p25_M5_earlylane.csv"), index=False)
summ = []
for (pop, lb, src), g in res.groupby(["population", "lookback", "source"], dropna=False):
    ts = g.then_session.iloc[0]
    for dd, gg in [("ALL", g)] + list(g.groupby("dir3")):
        st = stats(gg.iv_change_pct); sp = stats(gg.iv_change_pts)
        summ.append(dict(population=pop, lookback=lb, then_session=ts, source=src, dir3=dd, rows=len(gg), matched=st["n"],
                         **{k: v for k, v in st.items() if k != "n"}, median_pts=sp.get("median"), p10_pts=sp.get("p10"),
                         p90_pts=sp.get("p90"), iqr_pts=sp.get("iqr"), iv_then_floor_n=int(gg.iv_then_floor.sum())))
S = pd.DataFrame(summ)
S.to_csv(os.path.join(H, "p25_M5_earlylane_summary.csv"), index=False)
pd.set_option("display.width", 300); pd.set_option("display.max_columns", 40)
print(S[S.dir3 == "ALL"].drop(columns=["dir3"]).to_string(index=False))
print(S[S.dir3 != "ALL"][["population", "lookback", "dir3", "rows", "matched", "median", "p25", "p75", "p10", "p90", "median_pts"]].to_string(index=False))
