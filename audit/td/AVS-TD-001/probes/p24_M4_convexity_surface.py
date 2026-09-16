"""M4 cheapest-convexity surface (AVS-TD-001 discovery, RESEARCH_ONLY).

Data sources: db_copies/phantom_history.db options_greeks_history (read-only), probes/p32_labels.csv
(OHLC-derived outcomes), intelligence_lab/final_opportunity_book_<run>.csv (geometry only: contract_symbol,
contract_delta, contract_dte). Writes only probes/p24_M4_*.
"""
import json, math, random, sqlite3, sys, time
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import ndtr
from scipy.stats import spearmanr

T0 = time.time()
ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
AUD = ROOT / "audit/td/AVS-TD-001"
PR = AUD / "probes"
RUNS = ROOT / "data/output/runs"
R = 0.039          # book-era 3m T-bill (macro_snapshot extras.rates.t3m 3.86-3.92% on runs 20260809..20260906); q = 0
K_SIG = 1.5        # governed sigma_multiple
SEED = 20260912
SAMPLE_CAP = 600
CHAIN_END = "2026-09-04"
DBANDS = [(0.10, 0.25, "D010_025"), (0.25, 0.40, "D025_040"), (0.40, 0.60, "D040_060"), (0.60, 0.8500001, "D060_085")]
TBANDS = [(5, 15, "H+05_15"), (15, 30, "H+15_30"), (30, 45.0001, "H+30_45")]
WIDE = {"W040_060": (0.40, 0.60), "W030_070": (0.30, 0.70), "W020_080": (0.20, 0.80), "W010_085": (0.10, 0.85)}
out = open(PR / "p24_M4_stdout.txt", "w", encoding="utf-8")


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s); out.write(s + "\n"); out.flush()


# ---------------- XNYS calendar (weekday minus NYSE holidays; cross-checked with repo session_clock) ----------
HOL = {date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25), date(2026, 6, 19), date(2026, 5, 25)}


def is_sess(d):
    return d.weekday() < 5 and d not in HOL


try:
    sys.path.insert(0, str(ROOT))
    from canonical_data.session_clock import is_xnys_session  # pure calendar function
    d = date(2026, 6, 1); mism = 0
    while d <= date(2026, 12, 31):
        mism += int(bool(is_xnys_session(d)) != is_sess(d)); d += timedelta(days=1)
    log("calendar cross-check vs canonical_data.session_clock.is_xnys_session mismatches 2026-06..12:", mism)
    if mism == 0:
        is_sess = lambda x: bool(is_xnys_session(x))  # noqa: E731
except Exception as e:  # noqa: BLE001
    log("session_clock import failed, using local holiday list:", repr(e))


def advance(d, n):
    for _ in range(int(n)):
        d += timedelta(days=1)
        while not is_sess(d):
            d += timedelta(days=1)
    return d


def sessions_between(a, b):  # sessions s with a < s <= b
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        n += int(is_sess(d))
    return n


# ---------------- BSM ------------------------------------------------------------------------------------------
def bsm(S, K, T, sig, call):
    S = np.asarray(S, float); K = np.asarray(K, float); T = np.maximum(np.asarray(T, float), 1e-9); sig = np.maximum(np.asarray(sig, float), 1e-6)
    d1 = (np.log(S / K) + (R + 0.5 * sig ** 2) * T) / (sig * np.sqrt(T)); d2 = d1 - sig * np.sqrt(T)
    c = S * ndtr(d1) - K * np.exp(-R * T) * ndtr(d2)
    p = K * np.exp(-R * T) * ndtr(-d2) - S * ndtr(-d1)
    return np.where(call, c, p)


# sanity: Annex A worked example (T = 23/365 after 5 sessions; r=0.04 there)
_Rsave = R; R = 0.04
chk = float(bsm(106.339, 105, 23 / 365, 0.30, True)); R = _Rsave
log("Annex A reachable theoretical check (expect 4.036):", round(chk, 3))

# ---------------- theses --------------------------------------------------------------------------------------
L = pd.read_csv(PR / "p32_labels.csv")
L = L[L.decision_session <= CHAIN_END].sort_values(["decision_session", "run_id"])
U = L.drop_duplicates(["ticker", "direction", "decision_session"], keep="first").copy()
log("p32 rows", len(L), "unique theses", len(U))
SD = pd.read_csv(PR / "p24_M4_snapshot_dates.csv")
snaps = SD.groupby("ticker").snapshot_date.apply(lambda s: sorted(s)).to_dict()


def pick_snap(r):
    ds = date.fromisoformat(r.decision_session)
    best = None
    for s in snaps.get(r.ticker, []):
        sd = date.fromisoformat(s)
        if sd <= ds and sessions_between(sd, ds) <= 2:
            best = s
    return best


U["snapshot_date"] = U.apply(pick_snap, axis=1)
U["snap_lag_sessions"] = U.apply(lambda r: sessions_between(date.fromisoformat(r.snapshot_date), date.fromisoformat(r.decision_session)) if r.snapshot_date else np.nan, axis=1)
log("match by decision_session:\n" + U.groupby("decision_session").agg(theses=("ticker", "size"), matched=("snapshot_date", lambda s: s.notna().sum())).to_string())
M = U[U.snapshot_date.notna()].copy()
M["stratum"] = M.direction + "|h" + M.hold_sessions.astype(int).astype(str)
log("matched theses by stratum:\n" + M.stratum.value_counts().to_string())

# ---------------- chain pull + family ---------------------------------------------------------------------------
con = sqlite3.connect(f"file:{AUD / 'db_copies/phantom_history.db'}?mode=ro", uri=True)
COLS = "contract_symbol,expiration_date,strike,dte,side,bid,ask,mid,iv,delta,gamma,theta,vega,underlying_price,quality_status"
chain_cache = {}


def chain(tk, sd):
    k = (tk, sd)
    if k not in chain_cache:
        chain_cache[k] = pd.read_sql(f"select {COLS} from options_greeks_history where ticker=? and snapshot_date=?", con, params=k)
    return chain_cache[k]


fam_rows, cnt_rows = [], []
qual = {}
for r in M.itertuples():
    ch = chain(r.ticker, r.snapshot_date)
    ds = date.fromisoformat(r.decision_session); sd = date.fromisoformat(r.snapshot_date); h = int(r.hold_sessions)
    tstop = advance(ds, h)
    cal_h = (tstop - sd).days  # calendar days from snapshot to governed time stop (XNYS bridge, ALG-03)
    side = "call" if r.direction == "CALL" else "put"
    c = ch[ch.side == side].copy()
    two = (c.bid > 0) & (c.ask > c.bid)
    win = (c.dte >= cal_h + 5) & (c.dte <= cal_h + 45)
    ad = c.delta.abs()
    base = two & win & c.iv.notna() & c.delta.notna()
    cr = dict(ticker=r.ticker, direction=r.direction, decision_session=r.decision_session, hold=h, stratum=r.stratum,
              snapshot_date=r.snapshot_date, cal_h=cal_h, chain_rows_side=len(c), chain_max_dte=float(c.dte.max()) if len(c) else np.nan,
              two_sided=int(two.sum()), two_sided_in_dte_window=int(base.sum()))
    for nm, (lo, hi) in WIDE.items():
        cr[nm] = int((base & (ad >= lo) & (ad <= hi)).sum())
    cnt_rows.append(cr)
    f = c[base & (ad >= 0.10) & (ad <= 0.85)].copy()
    for q in f.quality_status.fillna("NA"):
        qual[q] = qual.get(q, 0) + 1
    if len(f):
        f["ticker"] = r.ticker; f["direction"] = r.direction; f["decision_session"] = r.decision_session; f["hold"] = h
        f["stratum"] = r.stratum; f["snapshot_date"] = r.snapshot_date; f["cal_h"] = cal_h; f["time_stop"] = tstop.isoformat()
        f["thesis_spot"] = r.spot; f["sigma_a"] = r.sigma_a; f["struct_target"] = r.target
        f["run_id"] = r.run_id
        fam_rows.append(f)
CNT = pd.DataFrame(cnt_rows)
CNT.to_csv(PR / "p24_M4_candidate_counts.csv", index=False)
log("quality_status in family:", qual)
log("chain pull done", round(time.time() - T0, 1), "s")

# ---------------- sample for the surface ------------------------------------------------------------------------
random.seed(SEED)
ntot = len(M)
keys = sorted(M.stratum.unique())
sample_idx = []
for k in keys:
    idx = sorted(M.index[M.stratum == k].tolist())
    quota = len(idx) if ntot <= SAMPLE_CAP else max(1, round(SAMPLE_CAP * len(idx) / ntot))
    sample_idx += random.sample(idx, min(quota, len(idx)))
S_ = M.loc[sorted(sample_idx)]
skey = set(zip(S_.ticker, S_.direction, S_.decision_session))
log("surface sample theses:", len(S_), "of matched", ntot, S_.stratum.value_counts().to_dict())

F = pd.concat(fam_rows, ignore_index=True)
F = F[[k in skey for k in zip(F.ticker, F.direction, F.decision_session)]].copy()
call = (F.direction == "CALL").values
sgn = np.where(call, 1.0, -1.0)
S = F.underlying_price.values; Kx = F.strike.values; ask = F.ask.values; bid = F.bid.values; iv = F.iv.values
T_rem = (pd.to_datetime(F.expiration_date) - pd.to_datetime(F.time_stop)).dt.days.values / 365.0
F["T_rem_years"] = T_rem
F["sigma_h"] = F.sigma_a * np.sqrt(F.hold / 252.0)
F["reach_target"] = F.thesis_spot * (1 + sgn * K_SIG * F.sigma_h)
F["spread_frac"] = (ask - bid) / ((ask + bid) / 2)
F["premium"] = ask
F["convexity_per_dollar"] = F.gamma * S ** 2 / (2 * ask)
F["vega_per_dollar"] = F.vega / ask
F["theta_per_dollar_day"] = F.theta / ask
F["leverage_efficiency"] = F.delta.abs() * S / ask
V_reach = bsm(F.reach_target.values, Kx, T_rem, iv, call)
F["payoff_per_dollar"] = V_reach / ask
F["net_return_reach_friction"] = (V_reach * (1 - np.minimum(F.spread_frac.values / 2, 0.15)) - ask) / ask
V_flat = bsm(S, Kx, T_rem, iv, call)
F["payoff_flat_per_dollar"] = V_flat / ask
sv = (F.struct_target.values > 0) & (np.where(call, F.struct_target.values > F.thesis_spot.values, F.struct_target.values < F.thesis_spot.values))
V_str = np.where(sv, bsm(np.where(sv, F.struct_target.values, 1.0), Kx, T_rem, iv, call), np.nan)
F["payoff_struct_per_dollar"] = V_str / ask
# breakeven: underlying level at time stop where BSM value = ask + half-spread; move measured from thesis spot
need = ask + (ask - bid) / 2
lo = np.zeros(len(F)); hi = np.where(call, 5.0, 0.9999)
ok = np.where(call, True, Kx * np.exp(-R * T_rem) > need)
for _ in range(60):
    mid = (lo + hi) / 2
    v = bsm(S * (1 + sgn * mid), Kx, T_rem, iv, call)
    up = v < need
    lo = np.where(up, mid, lo); hi = np.where(up, hi, mid)
x_chain = (lo + hi) / 2
lvl = S * (1 + sgn * x_chain)
be_frac = sgn * (lvl / F.thesis_spot.values - 1)
F["breakeven_level"] = np.where(ok & (x_chain < np.where(call, 4.99, 0.999)), lvl, np.nan)
F["breakeven_move_frac"] = np.where(np.isnan(F.breakeven_level), np.nan, be_frac)
F["breakeven_over_sigma_h"] = F.breakeven_move_frac / F.sigma_h
F["dband"] = pd.cut(F.delta.abs(), [0.10, 0.25, 0.40, 0.60, 0.8500001], right=False, labels=[b[2] for b in DBANDS]).astype(str)
off = F.dte - F.cal_h
F["dte_offset"] = off
F["tband"] = pd.cut(off, [5, 15, 30, 45.0001], right=False, labels=[b[2] for b in TBANDS]).astype(str)
F.to_csv(PR / "p24_M4_family_contracts.csv", index=False)
log("family contracts (sample):", len(F), "theses with >=1 contract:", F.groupby(["ticker", "direction", "decision_session"]).ngroups)

# ---------------- surface --------------------------------------------------------------------------------------
g = F.groupby(["direction", "hold", "dband", "tband"])
SURF = g.agg(n_contracts=("payoff_per_dollar", "size"),
             n_theses=("ticker", lambda s: F.loc[s.index, ["ticker", "decision_session"]].drop_duplicates().shape[0]),
             payoff_per_dollar_med=("payoff_per_dollar", "median"), payoff_per_dollar_p25=("payoff_per_dollar", lambda x: x.quantile(.25)),
             payoff_per_dollar_p75=("payoff_per_dollar", lambda x: x.quantile(.75)),
             net_return_reach_friction_med=("net_return_reach_friction", "median"),
             payoff_struct_per_dollar_med=("payoff_struct_per_dollar", "median"),
             payoff_flat_per_dollar_med=("payoff_flat_per_dollar", "median"),
             convexity_per_dollar_med=("convexity_per_dollar", "median"), vega_per_dollar_med=("vega_per_dollar", "median"),
             theta_per_dollar_day_med=("theta_per_dollar_day", "median"), leverage_efficiency_med=("leverage_efficiency", "median"),
             breakeven_over_sigma_h_med=("breakeven_over_sigma_h", "median"), spread_frac_med=("spread_frac", "median")).reset_index()
# per-thesis argmax cell share
tk = ["ticker", "direction", "decision_session"]
best = F.loc[F.groupby(tk).payoff_per_dollar.idxmax()]
bshare = best.groupby(["direction", "hold", "dband", "tband"]).size().rename("thesis_argmax_count").reset_index()
SURF = SURF.merge(bshare, how="left").fillna({"thesis_argmax_count": 0})
SURF["power"] = np.where(SURF.n_theses >= 100, "n>=100", "INSUFFICIENT_POWER")
SURF["data_source"] = "phantom_history.options_greeks_history; p32_labels"
SURF.to_csv(PR / "p24_M4_family_surface.csv", index=False)
log("surface cells:", len(SURF)); log(SURF[["direction", "hold", "dband", "tband", "n_contracts", "n_theses", "payoff_per_dollar_med", "net_return_reach_friction_med", "thesis_argmax_count", "breakeven_over_sigma_h_med"]].to_string())
peaks = {}
for (d_, h_), grp in SURF.groupby(["direction", "hold"]):
    p = grp.loc[grp.payoff_per_dollar_med.idxmax()]
    pa = grp.loc[grp.thesis_argmax_count.idxmax()]
    peaks[(d_, h_)] = (p.dband, p.tband)
    log(f"PEAK {d_} h{h_}: median-cell {p.dband}/{p.tband} med={p.payoff_per_dollar_med:.3f} n_theses={p.n_theses}; argmax-mode {pa.dband}/{pa.tband} count={int(pa.thesis_argmax_count)} of {best[(best.direction==d_)&(best.hold==h_)].shape[0]}")

# ---------------- selected contract vs peak ---------------------------------------------------------------------
books = {}
for run in sorted(S_.run_id.unique()):
    fp = RUNS / run / "intelligence_lab" / f"final_opportunity_book_{run}.csv"
    hdr = pd.read_csv(fp, nrows=0).columns
    use = [c for c in ["ticker", "governed_direction", "direction", "contract_symbol", "contract_delta", "contract_dte"] if c in hdr]
    b = pd.read_csv(fp, usecols=use, low_memory=False)
    b["dir_"] = (b["governed_direction"] if "governed_direction" in b else b["direction"]).astype(str).str.upper()
    b["dir_"] = np.where(b.dir_.isin(["CALL", "PUT"]), b.dir_, b.get("direction", b.dir_).astype(str).str.upper())
    books[run] = b
DI = {b[2]: i for i, b in enumerate(DBANDS)}; TI = {b[2]: i for i, b in enumerate(TBANDS)}


def band_of(v, bands):
    for lo_, hi_, nm in bands:
        if lo_ <= v < hi_:
            return nm
    return "OUT_LOW" if v < bands[0][0] else "OUT_HIGH"


sel_rows = []
for r in S_.itertuples():
    b = books[r.run_id]; hit = b[(b.ticker == r.ticker) & (b.dir_ == r.direction)]
    rec = dict(ticker=r.ticker, direction=r.direction, decision_session=r.decision_session, hold=int(r.hold_sessions), run_id=r.run_id,
               snapshot_date=r.snapshot_date, book_rows=len(hit))
    fam = F[(F.ticker == r.ticker) & (F.direction == r.direction) & (F.decision_session == r.decision_session)]
    rec["family_size"] = len(fam)
    if len(fam):
        bb = fam.loc[fam.payoff_per_dollar.idxmax()]
        rec.update(best_symbol=bb.contract_symbol, best_dband=bb.dband, best_tband=bb.tband, best_payoff=bb.payoff_per_dollar, best_delta=bb.delta, best_dte=bb.dte)
    pk = peaks.get((r.direction, int(r.hold_sessions)))
    rec["bucket_peak_cell"] = f"{pk[0]}/{pk[1]}" if pk else None
    sym = hit.contract_symbol.dropna().astype(str) if len(hit) else pd.Series([], dtype=str)
    sym = sym[sym.str.len() > 5]
    if not len(sym):
        rec["sel_status"] = "NO_SELECTED_CONTRACT_IN_BOOK"; sel_rows.append(rec); continue
    s0 = sym.iloc[0]; h0 = hit.loc[sym.index[0]]
    rec.update(sel_symbol=s0, book_contract_delta=h0.get("contract_delta"), book_contract_dte=h0.get("contract_dte", np.nan))
    try:
        body = s0[-15:]; exp = date(2000 + int(body[0:2]), int(body[2:4]), int(body[4:6])); cp = body[6]
    except Exception:  # noqa: BLE001
        rec["sel_status"] = "SYMBOL_UNPARSEABLE"; sel_rows.append(rec); continue
    cal_h = (advance(date.fromisoformat(r.decision_session), int(r.hold_sessions)) - date.fromisoformat(r.snapshot_date)).days
    dte_sym = (exp - date.fromisoformat(r.snapshot_date)).days
    rec.update(sel_side_char=cp, sel_dte_from_symbol=dte_sym, sel_dte_offset=dte_sym - cal_h)
    inf = fam[fam.contract_symbol == s0]
    ch = chain(r.ticker, r.snapshot_date); inch = ch[ch.contract_symbol == s0]
    if len(inf):
        x = inf.iloc[0]; rec.update(sel_status="IN_FAMILY", sel_dband=x.dband, sel_tband=x.tband, sel_payoff=x.payoff_per_dollar,
                                    sel_be_over_sigma_h=x.breakeven_over_sigma_h, sel_chain_delta=x.delta)
    else:
        dv = abs(float(inch.delta.iloc[0])) if len(inch) and pd.notna(inch.delta.iloc[0]) else (abs(float(h0.contract_delta)) if pd.notna(h0.get("contract_delta")) else np.nan)
        rec.update(sel_status="IN_CHAIN_OUTSIDE_FAMILY" if len(inch) else "NOT_IN_CHAIN_SNAPSHOT",
                   sel_dband=band_of(dv, DBANDS) if pd.notna(dv) else None, sel_tband=band_of(dte_sym - cal_h, TBANDS), sel_chain_delta=dv)
        if len(inch):
            y = inch.iloc[0]
            rec["sel_outside_reason"] = ";".join(k for k, c_ in [("side", (y.side == "call") != (r.direction == "CALL")), ("one_sided", not (y.bid > 0 and y.ask > y.bid)),
                                                                   ("delta", not (0.10 <= abs(y.delta or 0) <= 0.85)), ("dte_window", not (cal_h + 5 <= y.dte <= cal_h + 45))] if c_)
    for ref, (db_, tb_) in (("peak", pk or (None, None)), ("thesis_best", (rec.get("best_dband"), rec.get("best_tband")))):
        if db_ and rec.get("sel_dband") in DI and db_ in DI:
            rec[f"d_steps_vs_{ref}"] = DI[rec["sel_dband"]] - DI[db_]
        if tb_ and rec.get("sel_tband") in TI and tb_ in TI:
            rec[f"t_steps_vs_{ref}"] = TI[rec["sel_tband"]] - TI[tb_]
    if rec.get("sel_payoff") is not None and rec.get("best_payoff"):
        rec["sel_payoff_over_best"] = rec["sel_payoff"] / rec["best_payoff"]
    sel_rows.append(rec)
SEL = pd.DataFrame(sel_rows)
SEL.to_csv(PR / "p24_M4_selected_vs_peak.csv", index=False)
log("selected status:\n" + SEL.groupby(["direction", "hold", "sel_status"]).size().to_string())

# ---------------- breakeven vs outcome (per thesis) -------------------------------------------------------------
agg = F.groupby(tk).agg(be_min=("breakeven_over_sigma_h", "min"), be_med=("breakeven_over_sigma_h", "median"),
                        be_frac_min=("breakeven_move_frac", "min"), be_frac_med=("breakeven_move_frac", "median"), fam=("payoff_per_dollar", "size")).reset_index()
O = agg.merge(S_[tk + ["hold_sessions", "label_V", "side_correct", "mfe", "terminal_return", "sigma_a"]], on=tk)
O = O.merge(SEL[tk + ["sel_be_over_sigma_h"]], on=tk, how="left")
O["sigma_h"] = O.sigma_a * np.sqrt(O.hold_sessions / 252)
O["mfe_over_sigma_h"] = O.mfe / O.sigma_h
O["mfe_ge_be_min"] = O.mfe >= O.be_frac_min
O["mfe_ge_be_med"] = O.mfe >= O.be_frac_med
O["term_ge_be_med"] = O.terminal_return >= O.be_frac_med
O["target_first"] = O.label_V == "TARGET_FIRST"
O["be_med_bin"] = pd.cut(O.be_med, [-np.inf, 0.5, 1.0, 1.5, 2.0, np.inf], labels=["<0.5", "0.5-1.0", "1.0-1.5", "1.5-2.0", ">=2.0"]).astype(str)
O.to_csv(PR / "p24_M4_breakeven_outcomes.csv", index=False)
BT = O.groupby(["direction", "hold_sessions", "be_med_bin"]).agg(n=("be_med", "size"), target_first=("target_first", "mean"), side_correct=("side_correct", "mean"),
                                                                  mfe_ge_be_med=("mfe_ge_be_med", "mean"), term_ge_be_med=("term_ge_be_med", "mean")).reset_index()
BT.to_csv(PR / "p24_M4_breakeven_bins.csv", index=False)
log(BT.to_string())
summ = {}
for d_, grp in O.groupby("direction"):
    rho = spearmanr(grp.be_med, grp.mfe_over_sigma_h, nan_policy="omit")
    summ[d_] = dict(n=len(grp), be_min_q=grp.be_min.quantile([.1, .25, .5, .75, .9]).round(3).tolist(), be_med_q=grp.be_med.quantile([.1, .25, .5, .75, .9]).round(3).tolist(),
                    sel_be_q=grp.sel_be_over_sigma_h.dropna().quantile([.25, .5, .75]).round(3).tolist(), sel_be_n=int(grp.sel_be_over_sigma_h.notna().sum()),
                    mfe_over_sigma_h_med=round(grp.mfe_over_sigma_h.median(), 3), share_mfe_ge_be_min=round(grp.mfe_ge_be_min.mean(), 3),
                    share_mfe_ge_be_med=round(grp.mfe_ge_be_med.mean(), 3), share_term_ge_be_med=round(grp.term_ge_be_med.mean(), 3),
                    side_correct=round(grp.side_correct.mean(), 3), target_first=round(grp.target_first.mean(), 3),
                    spearman_be_med_vs_mfe_over_sigma_h=[round(float(rho.statistic), 3), float(rho.pvalue)],
                    target_first_rate_by_be_med_below_median=round(grp[grp.be_med < grp.be_med.median()].target_first.mean(), 3),
                    target_first_rate_by_be_med_above_median=round(grp[grp.be_med >= grp.be_med.median()].target_first.mean(), 3),
                    side_correct_below_median_be=round(grp[grp.be_med < grp.be_med.median()].side_correct.mean(), 3),
                    side_correct_above_median_be=round(grp[grp.be_med >= grp.be_med.median()].side_correct.mean(), 3))
log(json.dumps(summ, indent=1))

# ---------------- candidate count summary (full matched set) -----------------------------------------------------
cs = {}
for keyname, grp in list(CNT.groupby("direction")) + [("ALL", CNT)]:
    cs[keyname] = {nm: dict(n=len(grp), median=float(grp[nm].median()), p25=float(grp[nm].quantile(.25)), p75=float(grp[nm].quantile(.75)),
                            zero=int((grp[nm] == 0).sum()), zero_share=round(float((grp[nm] == 0).mean()), 3)) for nm in WIDE}
    cs[keyname]["two_sided_in_dte_window_median"] = float(grp.two_sided_in_dte_window.median())
    cs[keyname]["chain_max_dte_median"] = float(grp.chain_max_dte.median())
for (d_, h_), grp in CNT.groupby(["direction", "hold"]):
    cs[f"{d_}|h{h_}"] = {nm: dict(n=len(grp), median=float(grp[nm].median()), zero=int((grp[nm] == 0).sum())) for nm in WIDE}
tick = CNT.groupby("ticker")[list(WIDE)].max()
cs["PER_TICKER_MAX"] = {nm: dict(n=len(tick), median=float(tick[nm].median()), zero=int((tick[nm] == 0).sum())) for nm in WIDE}
log(json.dumps(cs, indent=1))

# premise: structural vs reachable
pv = F[F.payoff_struct_per_dollar.notna()]
prem = dict(n_contracts=len(pv), n_theses=pv.groupby(tk).ngroups,
            struct_over_reach_median=float((pv.payoff_struct_per_dollar / pv.payoff_per_dollar.replace(0, np.nan)).median()),
            struct_med=float(pv.payoff_struct_per_dollar.median()), reach_med=float(pv.payoff_per_dollar.median()),
            argmax_cell_differs_share=None)
if len(pv):
    bs = pv.loc[pv.groupby(tk).payoff_struct_per_dollar.idxmax(), tk + ["dband", "tband"]].rename(columns={"dband": "sd", "tband": "st"})
    br = pv.loc[pv.groupby(tk).payoff_per_dollar.idxmax(), tk + ["dband", "tband"]]
    j = bs.merge(br, on=tk)
    prem["argmax_cell_differs_share"] = float(((j.sd != j.dband) | (j.st != j.tband)).mean())
    prem["argmax_dband_struct_counts"] = j.sd.value_counts().to_dict(); prem["argmax_dband_reach_counts"] = j.dband.value_counts().to_dict()
    prem["by_direction"] = {d_: dict(n_theses=int(gg.groupby(tk).ngroups), ratio_med=float((gg.payoff_struct_per_dollar / gg.payoff_per_dollar.replace(0, np.nan)).median())) for d_, gg in pv.groupby("direction")}
log("PREMISE", json.dumps(prem, indent=1, default=str))
json.dump(dict(candidate_counts=cs, breakeven=summ, premise=prem, peaks={f"{k[0]}|h{k[1]}": v for k, v in peaks.items()},
               matched=int(ntot), sample=int(len(S_)), r=R, runtime_s=round(time.time() - T0, 1)),
          open(PR / "p24_M4_summary.json", "w"), indent=1, default=str)
log("done", round(time.time() - T0, 1), "s")
