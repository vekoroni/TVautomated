"""p14_E_e1_labels: Track E1 (read-only).
Sample 30 rows (15 CALL, 15 PUT; random.seed(20260912); rows with sigma_a present) from probes/p32_labels.csv.
For each row, independently of p32:
  - re-read spot / structural target / invalidation / hold bucket from that run's archived
    intelligence_lab/final_opportunity_book_<run>.csv (same column-precedence list as p31);
  - sigma_a from that run's qomega/garch_forecasts_<run>.csv (l3_forward_realised_vol), or the
    book's garch_forecast_vol when the book carries it (p31 precedence);
  - decision session from run_meta.json dynamic_plan.last_completed_session, else prior price-store date;
  - daily OHLC from db_copies/historical_prices.sqlite (mode=ro), bar_status COMPLETE, sessions d+1..d+h.
Labels: V = vol-budget target S_d(1 +/- 1.5 sigma_a sqrt(h/252)); S = structural target (valid only if >0 and correct side).
Tie rules: Annex (same-session dual touch -> AMBIGUOUS_TOUCH_ORDER) and prompt (-> INVALIDATION_FIRST).
Production: domain.decision_outcome.evaluate_outcome_path + domain.outcome_learning.competing_event_label
(the path used by canonical_data/outcome_maturation.py -> canonical_data/outcome_learning.py).
Outputs: p14_E_e1_labels.csv, p14_E_e1_labels_out.json
"""
import os, sys, json, math, random, sqlite3, glob
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, REPO)
from domain.decision_outcome import evaluate_outcome_path
from domain.outcome_learning import competing_event_label

K = 1.5
HOLD = {"1_5d": 5, "6_10d": 10, "11_20d": 20}
L = pd.read_csv(os.path.join(HERE, "p32_labels.csv"), low_memory=False)
elig = L[L.sigma_a.notna()].reset_index(drop=True)
random.seed(20260912)
ci = [i for i in elig.index if elig.at[i, "direction"] == "CALL"]
pi = [i for i in elig.index if elig.at[i, "direction"] == "PUT"]
idx = random.sample(ci, 15) + random.sample(pi, 15)
S = elig.loc[idx].reset_index(drop=True)

con = sqlite3.connect("file:" + os.path.join(HERE, "..", "db_copies", "historical_prices.sqlite") + "?mode=ro", uri=True)
RUNS = os.path.join(REPO, "data", "output", "runs")
SPOT = ["origin_spot", "entry_price", "stock_price", "current_price", "underlying_price", "close", "last_price", "price",
        "reference_price", "spot", "current_close", "last_close"]
_book, _q, _meta = {}, {}, {}


def book(run):
    if run not in _book:
        f = glob.glob(os.path.join(RUNS, run, "intelligence_lab", "final_opportunity_book_*.csv"))[0]
        _book[run] = pd.read_csv(f, low_memory=False)
    return _book[run]


def pick(df, *names):
    return next((n for n in names if n in df.columns), None)


def qvol(run, t):
    if run not in _q:
        f = glob.glob(os.path.join(RUNS, run, "qomega", "garch_forecasts_*.csv"))
        _q[run] = pd.read_csv(f[0], usecols=["ticker", "l3_forward_realised_vol"]).drop_duplicates("ticker").set_index("ticker")["l3_forward_realised_vol"].to_dict() if f else {}
    return _q[run].get(t)


def dsession(run):
    if run not in _meta:
        mp = os.path.join(RUNS, run, "run_meta.json")
        m = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
        d = (m.get("dynamic_plan") or {}).get("last_completed_session")
        if not d:
            rd = f"{run[:4]}-{run[4:6]}-{run[6:8]}"
            d = con.execute("select max(trading_date) from ohlcv_daily where ticker='SPY' and trading_date < ?", (rd,)).fetchone()[0]
        _meta[run] = d
    return _meta[run]


def bars(t, d, h):
    r = con.execute("select trading_date, open, high, low, close from ohlcv_daily where ticker=? and bar_status='COMPLETE' "
                    "and trading_date > ? order by trading_date limit ?", (t, d, h)).fetchall()
    return [dict(date=x[0], open=x[1], high=x[2], low=x[3], close=x[4]) for x in r]


def mine(direction, bs, tgt, inv, tie):
    for i, b in enumerate(bs, 1):
        ht = b["high"] >= tgt if direction == "CALL" else b["low"] <= tgt
        hs = b["low"] <= inv if direction == "CALL" else b["high"] >= inv
        if ht and hs:
            return ("AMBIGUOUS_TOUCH_ORDER" if tie == "ANNEX" else "INVALIDATION_FIRST"), i
        if ht:
            return "TARGET_FIRST", i
        if hs:
            return "INVALIDATION_FIRST", i
    return "TIMEOUT", None


def prod(direction, S0, bs, h, tgt, inv):
    ev = evaluate_outcome_path(direction=direction, reference_price=S0, future_bars=bs, horizon_sessions=h, target_price=tgt, invalidation_price=inv)
    if ev.data_status != "OBSERVED_COMPLETED_SESSIONS":
        return ev.data_status, ev
    return competing_event_label(ev.first_passage_state).value, ev


rows = []
for r in S.itertuples():
    B = book(r.run_id)
    cdir = pick(B, "governed_direction", "final_direction", "direction", "canonical_direction")
    ctg = pick(B, "structural_target", "target_price", "target_spot")
    cinv = pick(B, "invalidation_price", "invalidation_spot", "governed_invalidation_spot", "stop_loss")
    chold = pick(B, "hold_period", "planned_hold_sessions", "hold_days", "time_horizon", "hold_window")
    cspot = pick(B, *SPOT)
    cvol = pick(B, "garch_forecast_vol")
    br = B[(B.ticker.astype(str) == r.ticker) & (B[cdir] == r.direction)]
    br = br.iloc[0]
    S0 = float(br[cspot]); inv = float(br[cinv]); tgt_s = float(br[ctg]) if pd.notna(br[ctg]) else None
    h = HOLD.get(str(br[chold]))
    sig = float(br[cvol]) if cvol and pd.notna(br[cvol]) else qvol(r.run_id, r.ticker)
    sig_src = "book.garch_forecast_vol" if cvol and pd.notna(br[cvol]) else "qomega.l3_forward_realised_vol"
    d = dsession(r.run_id)
    bs = bars(r.ticker, d, h)
    sgn = 1 if r.direction == "CALL" else -1
    tgt_v = S0 * (1 + sgn * K * sig * math.sqrt(h / 252.0))
    myV, tV = mine(r.direction, bs, tgt_v, inv, "ANNEX")
    myV_prompt, _ = mine(r.direction, bs, tgt_v, inv, "PROMPT")
    pV, evV = prod(r.direction, S0, bs, h, tgt_v, inv)
    s_valid = tgt_s is not None and tgt_s > 0 and sgn * (tgt_s / S0 - 1) > 0
    if s_valid:
        myS, _ = mine(r.direction, bs, tgt_s, inv, "ANNEX")
        pS, _ = prod(r.direction, S0, bs, h, tgt_s, inv)
    else:
        myS = pS = "STRUCTURAL_TARGET_INVALID"
    coordS = r.label_S if s_valid else "STRUCTURAL_TARGET_INVALID"
    rows.append(dict(run_id=r.run_id, ticker=r.ticker, direction=r.direction, decision_session_mine=d, decision_session_coord=r.decision_session,
                     hold_h=h, hold_coord=r.hold_sessions, spot_mine=S0, spot_coord=r.spot, invalidation_mine=inv, invalidation_coord=r.invalidation,
                     sigma_mine=sig, sigma_src=sig_src, sigma_coord=r.sigma_a, target_V_mine=round(tgt_v, 6), target_V_coord=r.target_V,
                     structural_target=tgt_s, structural_valid=s_valid, n_bars=len(bs), first_bar=bs[0]["date"] if bs else None, last_bar=bs[-1]["date"] if bs else None,
                     label_V_mine=myV, label_V_mine_prompt_tie=myV_prompt, label_V_coord=r.label_V, label_V_prod=pV, sessions_to_event_mine=tV,
                     prod_target_hit=evV.target_first_hit_session, prod_stop_hit=evV.stop_first_hit_session,
                     label_S_mine=myS, label_S_coord=coordS, label_S_prod=pS,
                     V_3way=(myV == r.label_V == pV), S_3way=(myS == coordS == pS),
                     inputs_equal=(d == r.decision_session and h == int(r.hold_sessions) and abs(S0 - r.spot) < 1e-9 and abs(inv - r.invalidation) < 1e-9 and abs(sig - r.sigma_a) < 1e-9)))
D = pd.DataFrame(rows)
D.to_csv(os.path.join(HERE, "p14_E_e1_labels.csv"), index=False)

# synthetic fixtures for REQ-WP4-01 acceptance
fx = {}
e = evaluate_outcome_path(direction="PUT", reference_price=100, future_bars=[{"high": 100.5, "low": 94.9, "close": 95}], horizon_sessions=1, target_price=95, invalidation_price=105)
fx["put_minus5pct_down_move"] = competing_event_label(e.first_passage_state).value
e = evaluate_outcome_path(direction="PUT", reference_price=100, future_bars=[{"high": 106, "low": 94, "close": 100}], horizon_sessions=1, target_price=95, invalidation_price=105)
fx["put_same_session_dual_touch"] = competing_event_label(e.first_passage_state).value
e = evaluate_outcome_path(direction="CALL", reference_price=100, future_bars=[{"high": 106, "low": 94, "close": 100}], horizon_sessions=1, target_price=105, invalidation_price=95)
fx["call_same_session_dual_touch"] = competing_event_label(e.first_passage_state).value
e = evaluate_outcome_path(direction="PUT", reference_price=100, future_bars=[{"high": 106, "low": 99, "close": 105}], horizon_sessions=1, target_price=95, invalidation_price=105)
fx["put_up_move_hits_invalidation"] = competing_event_label(e.first_passage_state).value

summ = {"n": len(D), "eligible_pool": {"CALL": len(ci), "PUT": len(pi)}}
for dname in ("CALL", "PUT"):
    X = D[D.direction == dname]
    summ[dname] = {
        "n": len(X), "inputs_equal_to_coordinator": int(X.inputs_equal.sum()),
        "V_mine_eq_coord": int((X.label_V_mine == X.label_V_coord).sum()), "V_mine_eq_prod": int((X.label_V_mine == X.label_V_prod).sum()),
        "V_coord_eq_prod": int((X.label_V_coord == X.label_V_prod).sum()), "V_3way": int(X.V_3way.sum()),
        "V_prompt_tie_rule_eq_prod": int((X.label_V_mine_prompt_tie == X.label_V_prod).sum()),
        "V_label_counts_mine": X.label_V_mine.value_counts().to_dict(),
        "S_valid": int(X.structural_valid.sum()), "S_3way_on_valid": int(X[X.structural_valid].S_3way.sum()),
        "ambiguous_V": int((X.label_V_mine == "AMBIGUOUS_TOUCH_ORDER").sum()),
        "sigma_sources": X.sigma_src.value_counts().to_dict(), "runs": sorted(X.run_id.unique().tolist()),
    }
summ["OTHER"] = "not in p32_labels.csv (directed rows only); ALG-08 / LearningStratum reject non-CALL/PUT by construction"
summ["population_ambiguous_V_in_p32"] = L.groupby("direction").label_V.apply(lambda s: int((s == "AMBIGUOUS_TOUCH_ORDER").sum())).to_dict()
summ["synthetic_fixtures_production"] = fx
json.dump({"summary": summ, "rows": rows}, open(os.path.join(HERE, "p14_E_e1_labels_out.json"), "w"), indent=1, default=str)
print(json.dumps(summ, indent=1, default=str))
print(D[["run_id", "ticker", "direction", "hold_h", "sigma_src", "label_V_mine", "label_V_coord", "label_V_prod", "label_S_mine", "label_S_coord", "label_S_prod", "inputs_equal"]].to_string())
