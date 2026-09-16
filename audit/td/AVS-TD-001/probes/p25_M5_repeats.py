"""M5 repeats: premium decomposition over d in {1,2,3,5} sessions and delta_p by state cell. RESEARCH_ONLY. Read-only.
Inputs: probes/p25_M5_books_panel.csv (usecols extract of 22 final books), probes/p31_presented_candidates.csv,
probes/p32_labels.csv, OPTION_CHAIN JSON via db_copies/control_plane.sqlite dataset_registry, db_copies/phantom_history.db.
Pair = same ticker + direction present in a book at session t and again at session t+d (trading sessions).
Premium at t+d = the SAME OCC contract held from t, re-priced from the stored chain (else phantom, else the t+d book row if
it carries the same symbol).
"""
import os, json, math, sqlite3, numpy as np, pandas as pd
from scipy.stats import norm
H = os.path.dirname(os.path.abspath(__file__))
cp = sqlite3.connect("file:" + os.path.join(H, "..", "db_copies", "control_plane.sqlite") + "?mode=ro", uri=True)
ph = sqlite3.connect("file:" + os.path.join(H, "..", "db_copies", "phantom_history.db") + "?mode=ro", uri=True)
REG = pd.read_sql("select session_date, upper(instrument_id) t, storage_uri from dataset_registry where dataset_type='OPTION_CHAIN'", cp)
CHAIN_SESS = set(REG.session_date.unique())
PH_SESS = {"2026-07-17", "2026-07-31", "2026-08-28", "2026-09-04"}
HOL = {"2026-07-03", "2026-09-07"}
TRADING = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-07-01", "2026-09-30") if d.strftime("%Y-%m-%d") not in HOL]
TIDX = {s: i for i, s in enumerate(TRADING)}
R_RATE = 0.045
D_LIST = (1, 2, 3, 5)

# ---------------- panel + states
P = pd.read_csv(os.path.join(H, "p25_M5_books_panel.csv"), low_memory=False)
C = pd.read_csv(os.path.join(H, "p31_presented_candidates.csv"), low_memory=False)
aligned = len(P) == len(C) and (P.ticker.astype(str).values == C.ticker.astype(str).values).all() and (P.run_id.astype(str).values == C.run_id.astype(str).values).all()
print("panel rows", len(P), "p31 rows", len(C), "positionally aligned", aligned)
assert aligned
P["decision_session"] = C.decision_session.values
P["hidden_state"] = C.hidden_state.values
P["verdict"] = C.verdict.values
P["dir3"] = P["dir"].where(P["dir"].isin(["CALL", "PUT"]), "OTHER")
qdate = pd.to_datetime(P.quote_as_of, utc=True, errors="coerce").dt.strftime("%Y-%m-%d")
P["session"] = qdate.fillna(P.decision_session)
P["session_basis"] = np.where(qdate.notna(), "quote_as_of", "p31_decision_session")
P = P[P.session.isin(TIDX)].copy()
P["ticker"] = P.ticker.astype(str).str.upper()
# keep the latest run per (session, ticker, dir3)
P = P.sort_values("run_id").drop_duplicates(["session", "ticker", "dir3"], keep="last")
print("rows after per-session dedupe", len(P), P.dir3.value_counts().to_dict())

# thesis identity stability
T = P[P.thesis_id.notna()]
tid_sessions = T.groupby("thesis_id").session.nunique()
print("thesis_id rows", len(T), "distinct thesis_id", tid_sessions.size, "thesis_id seen in >1 session", int((tid_sessions > 1).sum()),
      "thesis_id contains its own session date", float(T.apply(lambda r: str(r.session) in str(r.thesis_id) or str(r.decision_session) in str(r.thesis_id), axis=1).mean()))

# ---------------- outcome rates per state cell (label set: vol-budget label_V)
L = pd.read_csv(os.path.join(H, "p32_labels.csv"), low_memory=False)
L = L[L.label_V.isin(["TARGET_FIRST", "INVALIDATION_FIRST", "TIMEOUT", "AMBIGUOUS_TOUCH_ORDER"])]
L["fav"] = (L.label_V == "TARGET_FIRST").astype(float)
L["sc"] = L.side_correct.astype(str).eq("True").astype(float)
cell = L.groupby(["hidden_state", "verdict"]).agg(n=("fav", "size"), p_target=("fav", "mean"), p_side=("sc", "mean")).reset_index()
cell.to_csv(os.path.join(H, "p25_M5_state_cells.csv"), index=False)
hs_only = L.groupby("hidden_state").agg(n=("fav", "size"), p_target=("fav", "mean")).reset_index()
print("label cells hidden_state x verdict:\n", cell.to_string(index=False))
print("verdict vocabulary in labels by era:", L.groupby(L.run_id.astype(str) >= "20260831").verdict.value_counts().to_dict())
CELL = {(r.hidden_state, r.verdict): (r.n, r.p_target) for r in cell.itertuples()}
HS = {r.hidden_state: (r.n, r.p_target) for r in hs_only.itertuples()}

# ---------------- pricing helpers
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


def fnum(x):
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def ivconv(v):
    v = fnum(v)
    if v is None or v <= 0:
        return None
    return v / 100 if v > 5 else v


def parse_occ(sym):
    s = str(sym).upper().replace("O:", "")
    i = len(s) - 15
    if i < 1:
        return None
    try:
        return dict(exp=pd.Timestamp("20" + s[i:i + 6]), right=s[i + 6], K=int(s[i + 7:]) / 1000)
    except Exception:
        return None


def bs(S, K, T, sig, right):
    if not all(v is not None and v > 0 for v in (S, K, sig)) or T is None:
        return None
    if T <= 0:
        return max(0.0, S - K) if right == "C" else max(0.0, K - S)
    d1 = (math.log(S / K) + (R_RATE + sig * sig / 2) * T) / (sig * math.sqrt(T)); d2 = d1 - sig * math.sqrt(T)
    if right == "C":
        return S * norm.cdf(d1) - K * math.exp(-R_RATE * T) * norm.cdf(d2)
    return K * math.exp(-R_RATE * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def bs_vega_pt(S, K, T, sig):
    if not all(v is not None and v > 0 for v in (S, K, sig, T)):
        return None
    d1 = (math.log(S / K) + (R_RATE + sig * sig / 2) * T) / (sig * math.sqrt(T))
    return S * norm.pdf(d1) * math.sqrt(T) / 100  # per 1 vol point


def quote_at(session, ticker, sym, book_row=None):
    e = chain(session, ticker).get(sym) if session in CHAIN_SESS else None
    if e is not None:
        bid, ask = fnum(e.get("bid")), fnum(e.get("ask"))
        mid = fnum(e.get("mid")) or ((bid + ask) / 2 if bid is not None and ask is not None else None)
        return dict(src="chain", mid=mid, bid=bid, ask=ask, iv=ivconv(e.get("implied_vol")), delta=fnum(e.get("delta")),
                    vega=fnum(e.get("vega")), theta=fnum(e.get("theta")), S=fnum(e.get("underlying_price")))
    if session in PH_SESS:
        r = ph.execute("select bid,ask,mid,iv,delta,vega,theta,underlying_price from options_greeks_history where ticker=? and snapshot_date=? and contract_symbol=?",
                       (ticker, session, sym)).fetchone()
        if r:
            return dict(src="phantom", mid=r[2], bid=r[0], ask=r[1], iv=ivconv(r[3]), delta=r[4], vega=r[5], theta=r[6], S=r[7])
    if book_row is not None and str(book_row.contract_symbol).upper().replace("O:", "") == sym:
        b = book_row
        return dict(src="book", mid=fnum(b.contract_mid), bid=fnum(b.contract_bid), ask=fnum(b.contract_ask), iv=ivconv(b.contract_iv),
                    delta=fnum(b.contract_delta), vega=fnum(b.get("contract_vega")), theta=fnum(b.contract_theta), S=fnum(b.underlying_price))
    return None


# ---------------- pairs
idx = {(r.session, r.ticker, r.dir3): r for r in P.itertuples(index=False)}
Pd = {k: pd.Series(v._asdict()) for k, v in idx.items()}
recs = []
vega_ratio = []
for (s0, tk, d3), row in Pd.items():
    if d3 == "OTHER":
        continue
    for d in D_LIST:
        j = TIDX[s0] + d
        if j >= len(TRADING):
            continue
        s1 = TRADING[j]
        nxt = Pd.get((s1, tk, d3))
        if nxt is None:
            continue
        sym = str(row.contract_symbol).upper().replace("O:", "") if pd.notna(row.contract_symbol) else None
        rec = dict(ticker=tk, dir3=d3, d=d, session_t=s0, session_td=s1, run_t=row.run_id, run_td=nxt.run_id, symbol=sym,
                   session_basis_t=row.session_basis, thesis_id_t=row.thesis_id, thesis_id_td=nxt.thesis_id,
                   same_thesis_id=bool(pd.notna(row.thesis_id) and row.thesis_id == nxt.thesis_id),
                   hidden_state_t=row.hidden_state, hidden_state_td=nxt.hidden_state, verdict_t=row.verdict, verdict_td=nxt.verdict,
                   liquidity_state_t=row.liquidity_state, liquidity_state_td=nxt.liquidity_state,
                   monetisability_t=row.monetisability_state, contract_changed=bool(sym is not None and str(nxt.contract_symbol).upper().replace("O:", "") != sym))
        # state cells and delta_p
        c0 = CELL.get((row.hidden_state, row.verdict), (0, None)); c1 = CELL.get((nxt.hidden_state, nxt.verdict), (0, None))
        rec.update(n_cell_t=c0[0], p_t=c0[1], n_cell_td=c1[0], p_td=c1[1])
        rec["delta_p"] = (c1[1] - c0[1]) if c0[1] is not None and c1[1] is not None else None
        rec["delta_p_power"] = "OK" if min(c0[0], c1[0]) >= 100 else "INSUFFICIENT_POWER"
        h0 = HS.get(row.hidden_state, (0, None)); h1 = HS.get(nxt.hidden_state, (0, None))
        rec["delta_p_hs_only"] = (h1[1] - h0[1]) if h0[1] is not None and h1[1] is not None else None
        rec["delta_p_hs_power"] = "OK" if min(h0[0], h1[0]) >= 100 else "INSUFFICIENT_POWER"
        occ = parse_occ(sym) if sym else None
        q0 = quote_at(s0, tk, sym, row) if occ else None
        q1 = quote_at(s1, tk, sym, nxt) if occ else None
        rec.update(src_t=q0["src"] if q0 else None, src_td=q1["src"] if q1 else None)
        if q0 and q1 and q0["mid"] and q1["mid"] and q0["mid"] > 0 and q1["mid"] is not None:
            S0 = q0["S"] or fnum(row.underlying_price); S1 = q1["S"] or fnum(nxt.underlying_price)
            iv0, iv1 = q0["iv"], q1["iv"]
            T0 = (occ["exp"] - pd.Timestamp(s0)).days / 365
            cal = (pd.Timestamp(s1) - pd.Timestamp(s0)).days
            vega0 = q0["vega"]
            bv = bs_vega_pt(S0, occ["K"], T0, iv0) if iv0 else None
            if vega0 is not None and bv and bv > 0 and vega0 > 0:
                vega_ratio.append(vega0 / bv)
            if vega0 is None:
                vega0 = bv
            p0 = bs(S0, occ["K"], T0, iv0, occ["right"]) if iv0 else None
            pdec = bs(S0, occ["K"], T0 - cal / 365, iv0, occ["right"]) if iv0 else None
            tot = q1["mid"] - q0["mid"]
            theta_c = (pdec - p0) if (p0 is not None and pdec is not None) else None
            theta_lin = (q0["theta"] * cal) if q0["theta"] is not None else None
            iv_c = (vega0 * (iv1 - iv0) * 100) if (vega0 is not None and iv0 and iv1) else None
            mv_c = (q0["delta"] * (S1 - S0)) if (q0["delta"] is not None and S0 and S1) else None
            parts = [theta_c, iv_c, mv_c]
            resid = tot - sum(parts) if all(v is not None for v in parts) else None
            # waiting inequality (payoff at vol-budget target from S(t+d), sigma proxied by IV(t+d), h = 10 sessions)
            payoff = friction = None
            if iv1 and S1:
                tgt = S1 * (1 + 1.5 * iv1 * math.sqrt(10 / 252)) if occ["right"] == "C" else S1 * (1 - 1.5 * iv1 * math.sqrt(10 / 252))
                intrinsic = max(0.0, tgt - occ["K"]) if occ["right"] == "C" else max(0.0, occ["K"] - tgt)
                payoff = intrinsic - q1["mid"]
            if q1["bid"] is not None and q1["ask"] is not None:
                friction = (q1["ask"] - q1["bid"]) / 2
            dp = rec["delta_p"]
            ineq_written = ineq_signfix = None
            if dp is not None and payoff is not None and friction is not None:
                ineq_written = bool(dp * payoff > -tot + friction)
                ineq_signfix = bool(dp * payoff > tot + friction)
            rec.update(premium_t=q0["mid"], premium_td=q1["mid"], S_t=S0, S_td=S1, iv_t=iv0, iv_td=iv1, delta_t=q0["delta"], vega_t=vega0,
                       theta_t=q0["theta"], cal_days=cal, T_t=T0, delta_premium_total=tot, theta_component=theta_c, theta_linear=theta_lin,
                       IV_component=iv_c, move_component=mv_c, residual=resid, tot_pct=tot / q0["mid"] * 100,
                       payoff_td=payoff, friction_td=friction, waiting_ineq_as_written=ineq_written, waiting_ineq_sign_corrected=ineq_signfix,
                       iv_floor=bool((iv0 is not None and iv0 <= 0.001) or (iv1 is not None and iv1 <= 0.001)))
        recs.append(rec)
R = pd.DataFrame(recs)
R.to_csv(os.path.join(H, "p25_M5_repeats.csv"), index=False)
print("vega unit check: chain vega / BS vega-per-vol-point median", round(float(np.median(vega_ratio)), 3) if vega_ratio else None, "n", len(vega_ratio))
print("pairs", len(R), "repriced", int(R.premium_td.notna().sum()) if "premium_td" in R else 0)
print(pd.crosstab([R.d], [R.dir3]))
print("same thesis_id across pair:", R.same_thesis_id.value_counts().to_dict())
print("pairs by t-session basis:", R.groupby(["session_basis_t", "d"]).size().to_dict())
print("reprice sources:", R.groupby(["src_t", "src_td"]).size().to_dict())
