"""Retrospective outcome labels (ALG-08) for presented directed candidates with a full OHLC window.
Two label sets: (S) structural barriers = the row's own structural_target / invalidation;
(V) vol-budget barriers = S_d * (1 +/- 1.5 * sigma_a * sqrt(h/252)) with sigma_a from qomega/garch_forecasts_<run>.csv, invalidation = row's invalidation.
Same-session dual touch -> AMBIGUOUS_TOUCH_ORDER (Annex ALG-08). Also MFE/MAE, terminal return, sessions-to-hit, directional outcome.
Hold h: routed bucket upper bound (1_5d->5, 6_10d->10, 11_20d->20) — stated assumption. Read-only."""
import os, re, math, sqlite3, glob
import pandas as pd, numpy as np

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
OUT = os.path.join(ROOT, "audit", "td", "AVS-TD-001")
K = 1.5
P = pd.read_csv(os.path.join(OUT, "probes", "p31_presented_candidates.csv"), low_memory=False)
P = P[(P.reconstructable == "FULL_WINDOW_AVAILABLE")].copy()
# sigma_a from qomega
sig = []
for rid in P.run_id.unique():
    f = glob.glob(os.path.join(ROOT, "data", "output", "runs", rid, "qomega", "garch_forecasts_*.csv"))
    if f:
        g = pd.read_csv(f[0], usecols=["ticker", "l3_forward_realised_vol"])
        g["run_id"] = rid
        sig.append(g)
S = pd.concat(sig) if sig else pd.DataFrame(columns=["ticker", "l3_forward_realised_vol", "run_id"])
P = P.merge(S.drop_duplicates(["run_id", "ticker"]), on=["run_id", "ticker"], how="left")
P["sigma_a"] = pd.to_numeric(P.get("vol"), errors="coerce").fillna(pd.to_numeric(P.l3_forward_realised_vol, errors="coerce"))
con = sqlite3.connect("file:" + os.path.join(OUT, "db_copies", "historical_prices.sqlite") + "?mode=ro", uri=True)
tick = tuple(sorted(set(P.ticker.dropna())))
px = pd.read_sql("select ticker, trading_date, open, high, low, close from ohlcv_daily where trading_date >= '2026-07-01'", con)
px = px[px.ticker.isin(tick)].sort_values(["ticker", "trading_date"])
grp = {t: d.reset_index(drop=True) for t, d in px.groupby("ticker")}
dates = sorted(px.trading_date.unique())


def label(r):
    d = grp.get(r.ticker)
    if d is None:
        return None
    win = d[d.trading_date > r.decision_session].head(int(r.hold_sessions))
    if len(win) < int(r.hold_sessions):
        return None
    S0 = float(r.spot); dirn = r.direction
    out = {}
    for tag, tgt in (("S", float(r.target)), ("V", (S0 * (1 + K * r.sigma_a * math.sqrt(r.hold_sessions / 252.0)) if dirn == "CALL" else S0 * (1 - K * r.sigma_a * math.sqrt(r.hold_sessions / 252.0))) if pd.notna(r.sigma_a) else None)):
        inv = float(r.invalidation)
        if tgt is None or not np.isfinite(tgt):
            out[tag] = ("NO_SIGMA", None, None); continue
        lab, t_hit, s_hit = "TIMEOUT", None, None
        for i, row in enumerate(win.itertuples(), 1):
            if dirn == "CALL":
                ht, hs = row.high >= tgt, row.low <= inv
            else:
                ht, hs = row.low <= tgt, row.high >= inv
            if ht and hs:
                lab, t_hit = "AMBIGUOUS_TOUCH_ORDER", i; break
            if ht:
                lab, t_hit = "TARGET_FIRST", i; break
            if hs:
                lab, s_hit = "INVALIDATION_FIRST", i; break
        out[tag] = (lab, t_hit, s_hit, tgt)
    sgn = 1 if dirn == "CALL" else -1
    closes = win.close.values
    term = sgn * (closes[-1] / S0 - 1)
    mfe = sgn * ((win.high.max() / S0 - 1) if dirn == "CALL" else (win.low.min() / S0 - 1))
    mae = -sgn * ((win.low.min() / S0 - 1) if dirn == "CALL" else (win.high.max() / S0 - 1))
    tgt_frac = sgn * (float(r.target) / S0 - 1)
    return dict(label_S=out["S"][0], t_hit_S=out["S"][1], s_hit_S=out["S"][2], label_V=out["V"][0], t_hit_V=out["V"][1], s_hit_V=out["V"][2],
                target_V=out["V"][3] if len(out["V"]) > 3 else None, terminal_return=term, mfe=mfe, mae=mae, target_distance_frac=tgt_frac,
                side_correct=term > 0, thesis_amount_reached=(mfe >= tgt_frac) if tgt_frac > 0 else None, window_end=win.trading_date.iloc[-1])


res = []
for r in P.itertuples():
    o = label(r)
    if o is None:
        continue
    o.update(dict(run_id=r.run_id, decision_session=r.decision_session, ticker=r.ticker, direction=r.direction, hidden_state=r.hidden_state, phase=r.phase,
                  compression_bucket=r.compression_bucket, horizon_bucket=r.horizon_bucket, hold_sessions=r.hold_sessions, spot=r.spot, target=r.target,
                  invalidation=r.invalidation, sigma_a=r.sigma_a, thesis_id=r.thesis_id, verdict=r.verdict))
    res.append(o)
L = pd.DataFrame(res)
L.to_csv(os.path.join(OUT, "probes", "p32_labels.csv"), index=False)
print("labelled rows:", len(L), " unique theses:", L.drop_duplicates(["ticker", "direction", "decision_session"]).shape[0], " sigma available:", int(L.sigma_a.notna().sum()))
for tag in ("S", "V"):
    print("\n== label_" + tag + " by direction ==")
    print(pd.crosstab(L.direction, L["label_" + tag], margins=True).to_string())
print("\nside_correct by direction:\n", L.groupby("direction").side_correct.mean().round(3).to_string())
print("terminal return median by direction:\n", L.groupby("direction").terminal_return.median().round(4).to_string())
print("\nlabel_V x label_S (CALL):\n", pd.crosstab(L[L.direction == "CALL"].label_V, L[L.direction == "CALL"].label_S).to_string())
print("\nlabel_V x label_S (PUT):\n", pd.crosstab(L[L.direction == "PUT"].label_V, L[L.direction == "PUT"].label_S).to_string())
U = L.drop_duplicates(["ticker", "direction", "decision_session"])
print("\nUNIQUE theses label_V by direction x horizon:\n", pd.crosstab([U.direction, U.horizon_bucket], U.label_V).to_string())
print("\nUNIQUE theses label_V by hidden_state x direction:\n", pd.crosstab([U.hidden_state, U.direction], U.label_V).to_string())
