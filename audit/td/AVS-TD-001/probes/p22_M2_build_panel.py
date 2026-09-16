"""p22_M2_build_panel.py -- AVS-TD-001 track M2 (discovery). READ-ONLY.

Builds one panel row per (run_id, ticker) from the 22 stored garch_forecasts
CSVs, joins realised prices (ohlcv_daily copy), IV history (iv_surface_history
and iv_history_cache copies) and the run-book bucket columns, and writes
probes/p22_M2_panel.csv.  No implementation code is imported.

Conventions (stated in track_M2.md):
  * forecast session d = run_meta.dynamic_plan.last_completed_session if present,
    else the last trading date strictly before the run_id date.
  * point-in-time: only bars strictly after d are used for realised quantities.
  * sigma_f = l3_forward_realised_vol (annualised fraction).
  * forecast_h (spec)      = sigma_f * sqrt(h/252)
  * forecast_h (pipeline)  = cumulative l3_expected_move_* / 100 (which the
    engine computes as sigma_f * sqrt(h*5/7/252), layer3_forward_variance.py:174-187)
  * realised_abs_h = |ln(C_{d+h}/C_d)|; realised_signed_h; max excursion from
    high/low over bars d+1..d+h; RV_h = sqrt(252/h * sum ln(C_t/C_{t-1})^2).
  * IV_matched (surface): dte_bucket 0_7 for h=5, 8_30 for h=10 and h=20
    (h sessions ~ 7/14/28 calendar days); atm_iv averaged over call and put;
    quote_date = latest <= d within 5 sessions.
  * IV (cache): iv_history.atm_iv, latest sample_date <= d within 5 sessions.
"""
from __future__ import annotations
import json, os, sqlite3, sys, time
import numpy as np, pandas as pd

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
AUD = os.path.join(ROOT, "audit", "td", "AVS-TD-001")
DB = os.path.join(AUD, "db_copies")
OUT = os.path.join(AUD, "probes", "p22_M2_panel.csv")
LOG = os.path.join(AUD, "probes", "p22_M2_build_panel_log.txt")
H = (5, 10, 20)
MAX_IV_LAG = 5
t0 = time.time()
log_lines = []
def log(*a):
    s = " ".join(str(x) for x in a); print(s); log_lines.append(s)

def ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)

# ---------------------------------------------------------------- runs
inv = pd.read_csv(os.path.join(AUD, "probes", "p01_run_inventory_raw.csv"))
runs = []
for r in inv.run_id:
    f = os.path.join(ROOT, "data", "output", "runs", str(r), "qomega", f"garch_forecasts_{r}.csv")
    if os.path.exists(f):
        runs.append(str(r))
log("forecast runs:", len(runs))

# ---------------------------------------------------------------- calendar + prices
con = ro(os.path.join(DB, "historical_prices.sqlite"))
cal = pd.read_sql("select distinct trading_date from ohlcv_daily where trading_date >= '2026-06-01' order by 1", con)
cal = cal.trading_date.tolist()
log("calendar sessions from 2026-06-01:", len(cal), cal[0], "->", cal[-1])
cal_idx = {d: i for i, d in enumerate(cal)}

px = pd.read_sql("select ticker, trading_date, high, low, close from ohlcv_daily "
                 "where trading_date >= '2026-07-01' and adjustment_convention='POLYGON_SPLIT_ADJUSTED'", con)
con.close()
log("price rows loaded:", len(px), "tickers:", px.ticker.nunique())
C = px.pivot(index="trading_date", columns="ticker", values="close").reindex(cal)
Hh = px.pivot(index="trading_date", columns="ticker", values="high").reindex(cal)
Ll = px.pivot(index="trading_date", columns="ticker", values="low").reindex(cal)
logC = np.log(C)
r1 = logC.diff()  # ln(C_t/C_{t-1}) indexed by t

# ---------------------------------------------------------------- forecast session per run
def session_for(run_id):
    meta_p = os.path.join(ROOT, "data", "output", "runs", run_id, "run_meta.json")
    src = "rule:last_session_before_run_date"
    lcs = None
    try:
        meta = json.load(open(meta_p, encoding="utf-8"))
        lcs = (meta.get("dynamic_plan") or {}).get("last_completed_session")
    except Exception:
        pass
    if lcs:
        return str(lcs)[:10], "run_meta.dynamic_plan.last_completed_session"
    run_date = f"{run_id[:4]}-{run_id[4:6]}-{run_id[6:8]}"
    prior = [d for d in cal if d < run_date]
    return prior[-1], src

# ---------------------------------------------------------------- IV sources
con = ro(os.path.join(DB, "phantom_history.db"))
surf = pd.read_sql("select ticker, quote_date, dte_bucket, side, contract_count, atm_iv, median_iv from iv_surface_history", con)
con.close()
surf = surf[surf.atm_iv.notna() & (surf.atm_iv > 0)]
surf_w = (surf.groupby(["ticker", "quote_date", "dte_bucket"])
              .agg(atm_iv=("atm_iv", "mean"), n_sides=("side", "nunique"), contracts=("contract_count", "sum"))
              .reset_index())
surf_dates = sorted(surf_w.quote_date.unique())
log("iv_surface quote dates:", surf_dates)
BUCKET_FOR_H = {5: "0_7", 10: "8_30", 20: "8_30"}

con = ro(os.path.join(DB, "iv_history_cache.db"))
ivc = pd.read_sql("select ticker, sample_date, atm_iv, source from iv_history where sample_date >= '2026-06-01'", con)
con.close()
ivc = ivc[ivc.atm_iv.notna() & (ivc.atm_iv > 0)]
ivc_w = ivc.groupby(["ticker", "sample_date"]).agg(atm_iv=("atm_iv", "mean"), source=("source", lambda s: "+".join(sorted(set(s))))).reset_index()
ivc_dates = sorted(ivc_w.sample_date.unique())
log("iv_history_cache sample dates >= 2026-06-01:", ivc_dates)

def nearest_prior(dates, d, max_lag):
    """latest date <= d whose session lag (in calendar index) <= max_lag."""
    best = None
    for q in dates:
        if q <= d:
            best = q
    if best is None:
        return None, None
    # lag in sessions: count of cal entries in (best, d]
    if best in cal_idx and d in cal_idx:
        lag = cal_idx[d] - cal_idx[best]
    else:
        lag = sum(1 for x in cal if best < x <= d)
    if lag > max_lag:
        return None, None
    return best, lag

# ---------------------------------------------------------------- build
BOOK_COLS = ["ticker", "hidden_state_label", "phase", "governed_direction", "direction",
             "iv_vs_hv", "garch_iv_tailwind_score", "iv_rank", "contract_iv", "atm_iv", "garch_forecast_vol"]
frames = []
for run_id in runs:
    d, d_src = session_for(run_id)
    fc = pd.read_csv(os.path.join(ROOT, "data", "output", "runs", run_id, "qomega", f"garch_forecasts_{run_id}.csv"),
                     usecols=["ticker", "l3_forward_realised_vol", "l3_vol_forecast_conf", "l3_expected_move_1_5d",
                              "l3_expected_move_6_10d", "l3_expected_move_11_20d", "l3_method", "l3_n_bars", "l3_error"])
    fc["run_id"] = run_id
    fc["forecast_session"] = d
    fc["session_source"] = d_src
    # book buckets
    bp = os.path.join(ROOT, "data", "output", "runs", run_id, "intelligence_lab", f"final_opportunity_book_{run_id}.csv")
    if os.path.exists(bp):
        hdr = pd.read_csv(bp, nrows=0).columns
        use = [c for c in BOOK_COLS if c in hdr]
        bk = pd.read_csv(bp, usecols=use, low_memory=False).drop_duplicates("ticker")
        bk = bk.rename(columns={c: f"book_{c}" for c in use if c != "ticker"})
        fc = fc.merge(bk, on="ticker", how="left")
        fc["book_rows"] = len(bk)
    else:
        fc["book_rows"] = 0
    frames.append(fc)
    log(f"{run_id} session={d} ({d_src}) forecasts={len(fc)} book_rows={fc.book_rows.iloc[0]}")
P = pd.concat(frames, ignore_index=True)
P = P.rename(columns={"l3_forward_realised_vol": "sigma_f"})
for c in ["book_hidden_state_label", "book_phase", "book_governed_direction", "book_direction"]:
    if c not in P.columns:
        P[c] = np.nan
def dir3(x):
    s = str(x).upper()
    if "CALL" in s: return "CALL"
    if "PUT" in s: return "PUT"
    return "OTHER"
P["direction_raw"] = P.book_governed_direction.where(P.book_governed_direction.notna(), P.book_direction)
P["direction_field"] = np.where(P.book_governed_direction.notna(), "governed_direction", np.where(P.book_direction.notna(), "direction", "absent"))
P["direction"] = P.direction_raw.map(dir3)
P.loc[P.direction_raw.isna(), "direction"] = "OTHER"
P["hidden_state"] = P.book_hidden_state_label.fillna("UNKNOWN").astype(str)
log("direction counts:", P.direction.value_counts().to_dict())
log("direction raw values:", P.direction_raw.astype(str).value_counts().head(12).to_dict())
log("direction field used:", P.direction_field.value_counts().to_dict())
log("hidden_state values:", P.hidden_state.value_counts().head(15).to_dict())

# realised
tick_ok = P.ticker.isin(C.columns)
log("forecast rows:", len(P), "with price column:", int(tick_ok.sum()))
Cv, Hv, Lv, R1 = C.values, Hh.values, Ll.values, r1.values
col_idx = {t: j for j, t in enumerate(C.columns)}
P["i_d"] = P.forecast_session.map(cal_idx)
P["S_t"] = np.nan
rows_j = np.array([col_idx.get(t, -1) for t in P.ticker])
rows_i = P.i_d.values.astype(int)
valid = rows_j >= 0
P.loc[valid, "S_t"] = Cv[rows_i[valid], rows_j[valid]]
nT = len(cal)
for h in H:
    cols = {}
    S_h = np.full(len(P), np.nan); rv = np.full(len(P), np.nan); mx_up = np.full(len(P), np.nan); mx_dn = np.full(len(P), np.nan); ok = np.zeros(len(P), bool); nbar = np.zeros(len(P), int)
    for k in np.where(valid)[0]:
        i, j = rows_i[k], rows_j[k]
        if i + h >= nT:
            continue
        seg = Cv[i:i + h + 1, j]
        nbar[k] = int(np.isfinite(seg).sum()) - 1
        if not np.all(np.isfinite(seg)):
            continue
        S_h[k] = seg[-1]
        rr = R1[i + 1:i + h + 1, j]
        rv[k] = np.sqrt(252.0 / h * np.nansum(rr ** 2))
        hh = Hv[i + 1:i + h + 1, j]; ll = Lv[i + 1:i + h + 1, j]
        mx_up[k] = np.log(np.nanmax(hh) / seg[0]) if np.isfinite(hh).any() else np.nan
        mx_dn[k] = np.log(seg[0] / np.nanmin(ll)) if np.isfinite(ll).any() else np.nan
        ok[k] = True
    P[f"S_t{h}"] = S_h
    P[f"fwd_ok_{h}"] = ok
    P[f"fwd_bars_avail_{h}"] = nbar
    P[f"real_signed_{h}"] = np.log(S_h / P.S_t.values)
    P[f"real_abs_{h}"] = np.abs(P[f"real_signed_{h}"])
    P[f"max_exc_up_{h}"] = mx_up
    P[f"max_exc_dn_{h}"] = mx_dn
    P[f"max_exc_abs_{h}"] = np.fmax(mx_up, mx_dn)
    P[f"RV_{h}"] = rv
    P[f"fcst_spec_{h}"] = P.sigma_f * np.sqrt(h / 252.0)
    P[f"ratio_RV_{h}"] = P[f"RV_{h}"] / P.sigma_f
    P[f"cover_{h}"] = (P[f"real_abs_{h}"] <= P[f"fcst_spec_{h}"]).where(P[f"real_abs_{h}"].notna())
    log(f"h={h}: rows with complete forward window: {int(ok.sum())}")
P["fcst_pipe_5"] = P.l3_expected_move_1_5d / 100.0
P["fcst_pipe_10"] = (P.l3_expected_move_1_5d + P.l3_expected_move_6_10d) / 100.0
P["fcst_pipe_20"] = (P.l3_expected_move_1_5d + P.l3_expected_move_6_10d + P.l3_expected_move_11_20d) / 100.0

# IV joins
sess = sorted(P.forecast_session.unique())
surf_match = {d: nearest_prior(surf_dates, d, MAX_IV_LAG) for d in sess}
ivc_match = {d: nearest_prior(ivc_dates, d, MAX_IV_LAG) for d in sess}
log("surface match per session:", surf_match)
log("cache match per session:", ivc_match)
P["iv_surf_date"] = P.forecast_session.map(lambda d: surf_match[d][0])
P["iv_surf_lag"] = P.forecast_session.map(lambda d: surf_match[d][1])
for b in ["0_7", "8_30", "31_60"]:
    sb = surf_w[surf_w.dte_bucket == b][["ticker", "quote_date", "atm_iv", "n_sides", "contracts"]].rename(
        columns={"quote_date": "iv_surf_date", "atm_iv": f"iv_surf_{b}", "n_sides": f"iv_surf_{b}_sides", "contracts": f"iv_surf_{b}_contracts"})
    P = P.merge(sb, on=["ticker", "iv_surf_date"], how="left")
for h in H:
    P[f"IV_surf_{h}"] = P[f"iv_surf_{BUCKET_FOR_H[h]}"]
    P[f"IV_surf_bucket_{h}"] = BUCKET_FOR_H[h]
P["iv_cache_date"] = P.forecast_session.map(lambda d: ivc_match[d][0])
P["iv_cache_lag"] = P.forecast_session.map(lambda d: ivc_match[d][1])
P = P.merge(ivc_w.rename(columns={"sample_date": "iv_cache_date", "atm_iv": "IV_cache", "source": "iv_cache_source"}),
            on=["ticker", "iv_cache_date"], how="left")
for h in H:
    log(f"h={h}: surface IV joined & fwd ok: {int((P[f'IV_surf_{h}'].notna() & P[f'fwd_ok_{h}']).sum())}; "
        f"cache IV joined & fwd ok: {int((P['IV_cache'].notna() & P[f'fwd_ok_{h}']).sum())}")
P["frac_6_10_lt_1_5"] = (P.l3_expected_move_6_10d < P.l3_expected_move_1_5d)
P.to_csv(OUT, index=False)
log("panel rows:", len(P), "cols:", len(P.columns), "->", OUT, f"({time.time()-t0:.1f}s)")
open(LOG, "w", encoding="utf-8").write("\n".join(log_lines))
