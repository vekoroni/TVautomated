"""p14_E_e2_point_in_time: Track E2 (read-only).
Part A (retrospective labels): take 10 rows of the E1 sample (first 5 CALL, first 5 PUT of p14_E_e1_labels.csv).
  For each, the label inputs (sigma_a, invalidation, spot) were read from the archived artefacts of the
  decision run. Confirm: (i) the archived qomega / book file values equal the values used in the label;
  (ii) the first label bar is strictly after the decision session and the decision session is before the run date;
  (iii) compare with the CURRENT values for the same ticker/direction in the latest run 20260911_115904
  (book + qomega) to show whether using current values would have changed the inputs and the label.
Part B (production path): reuse probes/p14_EH_e2_point_in_time_out.json (earlier worker, 10 ledger
  CANDIDATE_DECISION events vs same-run book) and restate which target production maturation passes to the label.
Outputs: p14_E_e2_point_in_time.csv, p14_E_e2_point_in_time_out.json
"""
import os, sys, json, math, glob, sqlite3
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, REPO)
from domain.decision_outcome import evaluate_outcome_path
from domain.outcome_learning import competing_event_label

RUNS = os.path.join(REPO, "data", "output", "runs")
CUR = "20260911_115904"
K = 1.5
E1 = pd.read_csv(os.path.join(HERE, "p14_E_e1_labels.csv"))
samp = pd.concat([E1[E1.direction == "CALL"].head(5), E1[E1.direction == "PUT"].head(5)])
con = sqlite3.connect("file:" + os.path.join(HERE, "..", "db_copies", "historical_prices.sqlite") + "?mode=ro", uri=True)

cur_book = pd.read_csv(glob.glob(os.path.join(RUNS, CUR, "intelligence_lab", "final_opportunity_book_*.csv"))[0], low_memory=False)
cur_q = pd.read_csv(glob.glob(os.path.join(RUNS, CUR, "qomega", "garch_forecasts_*.csv"))[0], usecols=["ticker", "l3_forward_realised_vol"]).drop_duplicates("ticker").set_index("ticker")["l3_forward_realised_vol"]


def q_of(run, t):
    f = glob.glob(os.path.join(RUNS, run, "qomega", "garch_forecasts_*.csv"))
    g = pd.read_csv(f[0], usecols=["ticker", "l3_forward_realised_vol"]).drop_duplicates("ticker").set_index("ticker")["l3_forward_realised_vol"]
    return (float(g[t]) if t in g.index else None), f[0]


def bars(t, d, h):
    r = con.execute("select trading_date, high, low, close from ohlcv_daily where ticker=? and bar_status='COMPLETE' and trading_date > ? order by trading_date limit ?", (t, d, h)).fetchall()
    return [dict(date=x[0], high=x[1], low=x[2], close=x[3]) for x in r]


out = []
for r in samp.itertuples():
    q_arch, qfile = q_of(r.run_id, r.ticker)
    run_date = f"{r.run_id[:4]}-{r.run_id[4:6]}-{r.run_id[6:8]}"
    cb = cur_book[(cur_book.ticker.astype(str) == r.ticker)]
    cdir = "governed_direction" if "governed_direction" in cur_book.columns else "direction"
    cbd = cb[cb[cdir] == r.direction]
    def fnum(v):
        try:
            v = float(v)
            return v if math.isfinite(v) else None
        except (TypeError, ValueError):
            return None
    cur_inv = fnum(cbd.iloc[0]["invalidation_price"]) if len(cbd) else None
    cur_spot = fnum(cbd.iloc[0]["underlying_price"]) if len(cbd) else None
    cur_sig = fnum(cur_q[r.ticker]) if r.ticker in cur_q.index else None
    # label with current sigma/invalidation (keeping archived S_d) -> would the label change?
    alt = None
    if cur_sig is not None or cur_inv is not None:
        sig = cur_sig if cur_sig is not None else r.sigma_mine
        inv = cur_inv if cur_inv is not None else r.invalidation_mine
        bs = bars(r.ticker, r.decision_session_mine, int(r.hold_h))
        sgn = 1 if r.direction == "CALL" else -1
        tv = r.spot_mine * (1 + sgn * K * sig * math.sqrt(r.hold_h / 252))
        ok_geom = (inv < r.spot_mine) if r.direction == "CALL" else (inv > r.spot_mine)
        if ok_geom:
            ev = evaluate_outcome_path(direction=r.direction, reference_price=r.spot_mine, future_bars=bs, horizon_sessions=int(r.hold_h), target_price=tv, invalidation_price=inv)
            alt = competing_event_label(ev.first_passage_state).value
        else:
            alt = "CURRENT_INVALIDATION_WRONG_SIDE_OF_ARCHIVED_SPOT"
    out.append(dict(run_id=r.run_id, run_date=run_date, ticker=r.ticker, direction=r.direction, decision_session=r.decision_session_mine,
                    first_label_bar=r.first_bar, hold_h=r.hold_h, sigma_used=r.sigma_mine, sigma_src=r.sigma_src, sigma_archived_qomega=q_arch,
                    sigma_used_eq_archived=(r.sigma_src != "qomega.l3_forward_realised_vol") or (q_arch is not None and abs(q_arch - r.sigma_mine) < 1e-12),
                    invalidation_used=r.invalidation_mine, spot_used=r.spot_mine,
                    session_before_run=r.decision_session_mine < run_date, first_bar_after_session=str(r.first_bar) > r.decision_session_mine,
                    current_run=CUR, current_sigma=cur_sig, current_invalidation=cur_inv, current_spot=cur_spot,
                    sigma_changed_vs_current=(cur_sig is not None and abs(cur_sig - r.sigma_mine) > 1e-9),
                    invalidation_changed_vs_current=(cur_inv is not None and abs(cur_inv - r.invalidation_mine) > 1e-9),
                    label_point_in_time=r.label_V_mine, label_if_current_values=alt,
                    label_would_change=(alt is not None and alt != r.label_V_mine)))
D = pd.DataFrame(out)
D.to_csv(os.path.join(HERE, "p14_E_e2_point_in_time.csv"), index=False)
prior = json.load(open(os.path.join(HERE, "p14_EH_e2_point_in_time_out.json")))["summary"]
summ = {}
for d in ("CALL", "PUT"):
    X = D[D.direction == d]
    summ[d] = {"n": len(X), "sigma_used_eq_archived": int(X.sigma_used_eq_archived.sum()), "session_before_run": int(X.session_before_run.sum()),
               "first_bar_after_session": int(X.first_bar_after_session.sum()), "present_in_current_run": int(X.current_invalidation.notna().sum()),
               "sigma_changed_vs_current": int(X.sigma_changed_vs_current.sum()), "invalidation_changed_vs_current": int(X.invalidation_changed_vs_current.sum()),
               "label_would_change_with_current_values": int(X.label_would_change.sum())}
summ["partB_production_ledger_vs_book_prior_probe"] = prior
summ["partB_note"] = ("canonical_data/outcome_maturation.py:111-113 reads reference/target/invalidation from the CANDIDATE_DECISION payload and "
                      ":162-169 passes them to evaluate_outcome_path; payload target_price == book structural_target on 10/10 and == ALG-08 budget "
                      "target on 0/10, so production labels are structural-target labels, not k x e_h labels; no budget e_h is recorded on the payload.")
json.dump({"summary": summ, "rows": out}, open(os.path.join(HERE, "p14_E_e2_point_in_time_out.json"), "w"), indent=1, default=str)
print(json.dumps(summ, indent=1, default=str))
print(D[["run_id", "ticker", "direction", "decision_session", "first_label_bar", "sigma_used", "current_sigma", "invalidation_used", "current_invalidation", "label_point_in_time", "label_if_current_values"]].to_string())
