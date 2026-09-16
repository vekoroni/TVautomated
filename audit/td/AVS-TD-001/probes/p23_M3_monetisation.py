"""p23_M3_monetisation: Track M3 (discovery). Did the selected contract monetise over the thesis window?
Inputs: probes/p32_labels.csv (coordinator p32 labels); each run's intelligence_lab/final_opportunity_book_<run>.csv
(selected contract: contract_symbol, strike, expiry, dte, spread_pct, contract_delta/iv/bid/ask/mid/theta where present);
db_copies/phantom_history.db options_greeks_history (per ticker + date range), chain_snapshots fallback (per ticker + date range).
Entry = book contract_ask (quote at run time). Window = snapshot dates d with decision_session < d <= min(window_end, expiry).
monetised_125 = best bid in window >= 1.25 x entry ask (governed profit floor); monetised_entry = best bid >= entry ask.
NOTE: option history carries only sparse snapshot dates (no daily bars) -> 'best daily bid' is best bid over available snapshots.
Attribution (side-correct & not monetised), first-binding in the listed order:
 1 MFE_LT_STRIKE_DIST  mfe < signed spot->strike distance
 2 IV_DOWN_10PCT       last in-window snapshot iv / entry contract_iv - 1 <= -0.10   (needs option history)
 3 SPREAD_GT_15PCT     entry (ask-bid)/mid > 0.15 (book bid/ask; falls back to spread_pct/100)
 4 FLAT_DECAY_GE_25PCT BS value at flat spot after hold*7/5 calendar days / entry BS value - 1 <= -0.25 (r=0.045, q=0, entry iv) [threshold defined here]
 5 DTE_LT_HOLD         contract calendar DTE < hold_sessions*7/5
 6 REACH_RATIO_GT_1_5  structural target distance / (sigma_a*sqrt(h/252)) > 1.5 (valid structural target only)
Outputs: p23_M3_monetisation.csv (row per presented labelled row), p23_M3_monetisation_tables.txt. Read-only. RESEARCH_ONLY."""
import os, sys, re, time, math, sqlite3
import numpy as np, pandas as pd
from scipy.stats import norm

OUT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(OUT, "..", "..", "..", ".."))
lines = []
def P(s):
    lines.append(str(s)); print(s, flush=True)

L = pd.read_csv(os.path.join(OUT, "p32_labels.csv"), low_memory=False)
L["condition"] = np.where(L.run_id < "20260831", "UNGOVERNED_PRE", "GOVERNED")
WANT = ["ticker", "direction", "governed_direction", "contract_symbol", "strike", "expiry", "dte", "contract_dte", "spread_pct", "contract_delta",
        "contract_iv", "contract_bid", "contract_ask", "contract_mid", "contract_theta"]
books = []
for rid in sorted(L.run_id.unique()):
    f = os.path.join(ROOT, "data", "output", "runs", rid, "intelligence_lab", f"final_opportunity_book_{rid}.csv")
    cols = list(pd.read_csv(f, nrows=0).columns)
    use = [c for c in WANT if c in cols]
    b = pd.read_csv(f, usecols=use, low_memory=False)
    b["run_id"] = rid
    b["dir_key"] = b["governed_direction"].where(b.get("governed_direction").isin(["CALL", "PUT"]), b["direction"]) if "governed_direction" in b else b["direction"]
    dups = int(b.duplicated(["ticker", "dir_key"]).sum())
    P(f"{rid}: rows {len(b)} missing cols {[c for c in WANT if c not in cols]} dup(ticker,dir) {dups} | populated: " +
      ", ".join(f"{c}={b[c].notna().mean():.2f}" for c in ["contract_symbol", "strike", "expiry", "contract_bid", "contract_ask", "contract_iv", "spread_pct"] if c in b) +
      f" | strike==0 {float((b.strike==0).mean()):.2f} ask>0 {float((b.contract_ask>0).mean()):.2f}")
    books.append(b.drop_duplicates(["ticker", "dir_key"]))
B = pd.concat(books, ignore_index=True)
M = L.merge(B.drop(columns=["direction"]).rename(columns={"dir_key": "direction"}), on=["run_id", "ticker", "direction"], how="left", suffixes=("", "_book"))
P(f"labelled rows {len(L)} merged {len(M)} with book row {int(M.contract_ask.notna().sum())}")

occ = M.contract_symbol.astype(str).str.extract(r"^([A-Z.]+)(\d{6})([CP])(\d{8})$")
M["sym_root"], M["sym_side"] = occ[0], occ[2]
M["sym_expiry"] = pd.to_datetime(occ[1], format="%y%m%d", errors="coerce")
M["sym_strike"] = pd.to_numeric(occ[3], errors="coerce") / 1000.0
M["side_match"] = ((M.sym_side == "C") & (M.direction == "CALL")) | ((M.sym_side == "P") & (M.direction == "PUT"))
M["root_match"] = M.sym_root == M.ticker
M["book_strike_eq_sym"] = np.isclose(M.strike.fillna(-1), M.sym_strike.fillna(-2))
dsess = pd.to_datetime(M.decision_session)
M["cal_dte"] = (M.sym_expiry - dsess).dt.days
M["entry_ask"] = M.contract_ask.where(M.contract_ask > 0)
M["entry_bid"] = M.contract_bid.where(M.contract_bid >= 0)
mid = (M.entry_ask + M.entry_bid) / 2
M["entry_spread_frac"] = ((M.entry_ask - M.entry_bid) / mid).where(M.entry_bid.notna(), M.spread_pct / 100.0)
M["contract_state"] = np.select(
    [M.contract_symbol.isna(), occ[0].isna(), ~M.root_match, ~M.side_match, M.entry_ask.isna(), M.sym_expiry <= dsess],
    ["NO_SYMBOL", "SYMBOL_UNPARSEABLE", "ROOT_MISMATCH", "SIDE_MISMATCH", "NO_ENTRY_ASK", "EXPIRED_AT_DECISION"], "VALID")
P("contract_state by condition x direction:\n" + pd.crosstab([M.condition, M.direction], M.contract_state, margins=True).to_string())

# ---- option history per ticker ----
con = sqlite3.connect("file:" + os.path.join(OUT, "..", "db_copies", "phantom_history.db") + "?mode=ro", uri=True)
V = M[M.contract_state == "VALID"]
hist, tick_dates, t0 = [], {}, time.time()
for i, (t, g) in enumerate(V.groupby("ticker")):
    lo, hi = g.decision_session.min(), min(g.window_end.max(), g.sym_expiry.max().strftime("%Y-%m-%d"))
    syms = set(g.contract_symbol)
    q = pd.read_sql("select contract_symbol, snapshot_date as d, bid, ask, mid, iv, underlying_price from options_greeks_history where ticker=? and snapshot_date between ? and ?", con, params=(t, lo, hi))
    tick_dates[t] = set(q.d)
    q = q[q.contract_symbol.isin(syms)]; q["src"] = "OGH"
    miss = syms - set(q.contract_symbol)
    if miss:
        c = pd.read_sql("select option_symbol as contract_symbol, quote_date as d, bid, ask, mid, iv, underlying_price from chain_snapshots where ticker=? and quote_date between ? and ?", con, params=(t, lo, hi))
        tick_dates[t] |= set(c.d)
        c = c[c.contract_symbol.isin(miss)]; c["src"] = "CHAIN"
        q = pd.concat([q, c])
    q["ticker"] = t
    hist.append(q)
    if i % 200 == 0:
        P(f"  tickers {i} elapsed {time.time()-t0:.0f}s")
H = pd.concat(hist, ignore_index=True) if hist else pd.DataFrame()
P(f"history rows fetched {len(H)}; distinct snapshot dates {sorted(H.d.unique()) if len(H) else []}; src {H.src.value_counts().to_dict() if len(H) else {}}")
H.to_csv(os.path.join(OUT, "p23_M3_option_snapshots.csv"), index=False)
Hg = {k: g for k, g in H.groupby("contract_symbol")} if len(H) else {}

res = []
for r in M.itertuples():
    o = dict(n_ticker_snap_in_window=np.nan, n_contract_snap_in_window=np.nan, best_bid=np.nan, best_bid_date=None, last_iv=np.nan, entry_db_ask=np.nan, snap_src=None)
    if r.contract_state == "VALID":
        end = min(r.window_end, r.sym_expiry.strftime("%Y-%m-%d"))
        o["n_ticker_snap_in_window"] = sum(1 for d in tick_dates.get(r.ticker, ()) if r.decision_session < d <= end)
        g = Hg.get(r.contract_symbol)
        if g is not None:
            e = g[g.d == r.decision_session]
            if len(e): o["entry_db_ask"] = e.ask.iloc[0]
            w = g[(g.d > r.decision_session) & (g.d <= end)].sort_values("d")
            o["n_contract_snap_in_window"] = len(w)
            if len(w) and w.bid.notna().any():
                j = w.bid.idxmax(); o["best_bid"] = w.bid.max(); o["best_bid_date"] = w.loc[j, "d"]; o["snap_src"] = w.loc[j, "src"]
                o["last_iv"] = w.iv.dropna().iloc[-1] if w.iv.notna().any() else np.nan
        else:
            o["n_contract_snap_in_window"] = 0
    res.append(o)
M = pd.concat([M.reset_index(drop=True), pd.DataFrame(res)], axis=1)
M["coverage_state"] = np.select(
    [M.contract_state != "VALID", M.n_ticker_snap_in_window == 0, M.n_contract_snap_in_window == 0, M.best_bid.isna()],
    ["CONTRACT_" + M.contract_state, "NO_SNAPSHOT_DATE_IN_WINDOW", "SYMBOL_ABSENT_FROM_HISTORY", "NO_BID_IN_SNAPSHOT"], "PRICED")
pr = M.coverage_state == "PRICED"
M["monetised_125"] = np.where(pr, M.best_bid >= 1.25 * M.entry_ask, np.nan)
M["monetised_entry"] = np.where(pr, M.best_bid >= M.entry_ask, np.nan)
M["best_bid_over_ask"] = M.best_bid / M.entry_ask

# ---- attribution inputs ----
sgn = np.where(M.direction == "CALL", 1.0, -1.0)
M["strike_dist"] = sgn * (M.sym_strike / M.spot - 1)
M["iv_change_rel"] = M.last_iv / M.contract_iv - 1


def bs(S, K, T, s, call, r=0.045):
    if not (S > 0 and K > 0 and s > 0):
        return np.nan
    if T <= 0:
        return max(S - K, 0) if call else max(K - S, 0)
    d1 = (math.log(S / K) + (r + 0.5 * s * s) * T) / (s * math.sqrt(T)); d2 = d1 - s * math.sqrt(T)
    return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2) if call else K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


fd = []
for r in M.itertuples():
    if r.contract_state != "VALID" or not (r.contract_iv > 0):
        fd.append(np.nan); continue
    T0 = r.cal_dte / 365.0; T1 = (r.cal_dte - r.hold_sessions * 7 / 5) / 365.0
    v0 = bs(r.spot, r.sym_strike, T0, r.contract_iv, r.direction == "CALL"); v1 = bs(r.spot, r.sym_strike, T1, r.contract_iv, r.direction == "CALL")
    fd.append(v1 / v0 - 1 if v0 and v0 > 0 else np.nan)
M["flat_decay_frac"] = fd
vb_sig = M.sigma_a * np.sqrt(M.hold_sessions / 252.0)
M["reach_ratio"] = np.where(M.target_distance_frac > 0, M.target_distance_frac / vb_sig, np.nan)
C = {"MFE_LT_STRIKE_DIST": M.mfe < M.strike_dist, "IV_DOWN_10PCT": M.iv_change_rel <= -0.10, "SPREAD_GT_15PCT": M.entry_spread_frac > 0.15,
     "FLAT_DECAY_GE_25PCT": M.flat_decay_frac <= -0.25, "DTE_LT_HOLD": M.cal_dte < M.hold_sessions * 7 / 5, "REACH_RATIO_GT_1_5": M.reach_ratio > 1.5}
for k, v in C.items():
    M["cause_" + k] = v.fillna(False).astype(bool)
M["n_causes"] = M[["cause_" + k for k in C]].sum(axis=1)
M["first_binding"] = np.select([M["cause_" + k] for k in C], list(C), "NO_CAUSE_IDENTIFIED")
M.to_csv(os.path.join(OUT, "p23_M3_monetisation.csv"), index=False)
P("saved p23_M3_monetisation.csv")

pd.options.display.float_format = "{:.3f}".format
P("\nUNIT CHECK: median db iv / book contract_iv on priced rows: %.3f ; median entry_db_ask/entry_ask where both: %.3f (n=%d)" % (
    (M.last_iv / M.contract_iv)[pr].median(), (M.entry_db_ask / M.entry_ask).median(), int(M.entry_db_ask.notna().sum())))
for lvl, D in (("ROWS", M), ("UNIQUE_THESES", M.sort_values("run_id").drop_duplicates(["ticker", "direction", "decision_session"]))):
    P(f"\n===== {lvl} =====")
    P("coverage_state by condition x direction:\n" + pd.crosstab([D.condition, D.direction], D.coverage_state, margins=True).to_string())
    Dp = D[D.coverage_state == "PRICED"].copy()
    Dp["mon125"] = Dp.monetised_125.astype(bool); Dp["mon_entry"] = Dp.monetised_entry.astype(bool)
    P("four-cell side_correct x monetised_125 (PRICED only):\n" + pd.crosstab([Dp.condition, Dp.direction, Dp.side_correct], Dp.mon125, margins=True).to_string())
    P("four-cell side_correct x monetised_entry (PRICED only):\n" + pd.crosstab([Dp.condition, Dp.direction, Dp.side_correct], Dp.mon_entry, margins=True).to_string())
    P("four-cell TARGET_FIRST_V x monetised_125 (PRICED only):\n" + pd.crosstab([Dp.condition, Dp.direction, Dp.label_V == "TARGET_FIRST"], Dp.mon125, margins=True).to_string())
    P("monetised rates by condition x direction x horizon (PRICED):\n" + Dp.groupby(["condition", "direction", "horizon_bucket"]).agg(
        n=("mon125", "size"), mon125=("mon125", "mean"), mon_entry=("mon_entry", "mean"), med_bid_over_ask=("best_bid_over_ask", "median"),
        med_snaps=("n_contract_snap_in_window", "median")).to_string())
    S = Dp[Dp.side_correct & ~Dp.mon125]
    P(f"side-correct-not-monetised_125 (PRICED): n={len(S)}")
    P("first_binding by condition x direction:\n" + pd.crosstab(S.first_binding, [S.condition, S.direction], margins=True).to_string())
    P("cause incidence (multi-cause) by condition x direction:\n" + S.groupby(["condition", "direction"])[["cause_" + k for k in C] + ["n_causes"]].mean().to_string())
    P("n_causes distribution:\n" + pd.crosstab(S.n_causes, [S.condition, S.direction]).to_string())
    A = D[(D.contract_state == "VALID") & D.side_correct]
    P(f"history-free causes on ALL side-correct rows with a VALID contract (coverage-independent): n={len(A)}")
    P(A.groupby(["condition", "direction"])[["cause_MFE_LT_STRIKE_DIST", "cause_SPREAD_GT_15PCT", "cause_FLAT_DECAY_GE_25PCT", "cause_DTE_LT_HOLD", "cause_REACH_RATIO_GT_1_5"]].agg(["mean", "size"]).to_string())
    P("entry geometry (VALID contracts) medians by condition x direction:\n" + D[D.contract_state == "VALID"].groupby(["condition", "direction"]).agg(
        n=("ticker", "size"), strike_dist=("strike_dist", "median"), spread=("entry_spread_frac", "median"), cal_dte=("cal_dte", "median"),
        flat_decay=("flat_decay_frac", "median"), delta=("contract_delta", "median"), vb_dist=("sigma_a", lambda s: np.nan)).to_string())
open(os.path.join(OUT, "p23_M3_monetisation_tables.txt"), "w").write("\n".join(lines))
