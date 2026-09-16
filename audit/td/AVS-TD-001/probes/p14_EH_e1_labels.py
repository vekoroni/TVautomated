"""p14_EH_e1_labels: Track E1. Sample 30 presented (ticker, session, direction) rows
(15 CALL / 15 PUT, holds 5/10/20) from probes/p31_presented_candidates.csv whose full
hold window is inside the price-store copy; join the point-in-time annualised forecast
sigma_a from qomega/garch_forecasts_<run>.csv (l3_forward_realised_vol); read daily OHLC
read-only from db_copies/historical_prices.sqlite; recompute the ALG-08 label
independently (target = S_d x (1 +/- 1.5 sigma_a sqrt(h/252)), invalidation = row's
governed invalidation, sessions d+1..d+h, same-session dual touch = AMBIGUOUS_TOUCH_ORDER);
also the prompt's variant (tie -> INVALIDATION_FIRST) and the label using the row's
structural target; then call the production label function
domain.decision_outcome.evaluate_outcome_path + domain.outcome_learning.competing_event_label
on the same inputs. Output: p14_EH_e1_labels.csv, p14_EH_e1_labels_out.json
"""
import os, sys, json, csv, math, sqlite3, random
import pandas as pd
ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(ROOT, "..", "..", "..", ".."))
sys.path.insert(0, REPO)
from domain.decision_outcome import evaluate_outcome_path
from domain.outcome_learning import competing_event_label, CompetingEventLabel
K = 1.5
DB = os.path.abspath(os.path.join(ROOT, "..", "db_copies", "historical_prices.sqlite"))
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

p = pd.read_csv(os.path.join(ROOT, "p31_presented_candidates.csv"), low_memory=False)
f = p[(p.reconstructable == "FULL_WINDOW_AVAILABLE") & (p.invalidation > 0) & (p.spot > 0) & p.hold_sessions.notna()].copy()
f["hold_sessions"] = f["hold_sessions"].astype(int)
f = f.drop_duplicates(["ticker", "direction", "decision_session"])
vol_cache = {}
def sigma_for(run, ticker):
    if run not in vol_cache:
        fp = os.path.join(REPO, "data", "output", "runs", run, "qomega", f"garch_forecasts_{run}.csv")
        vol_cache[run] = pd.read_csv(fp, usecols=["ticker", "l3_forward_realised_vol"]).set_index("ticker")["l3_forward_realised_vol"].to_dict() if os.path.exists(fp) else {}
    v = vol_cache[run].get(ticker)
    return float(v) if v is not None and not (isinstance(v, float) and math.isnan(v)) and v > 0 else None
rnd = random.Random(20260913)
sample = []
quota = {("CALL", 5): 6, ("CALL", 10): 6, ("CALL", 20): 3, ("PUT", 5): 6, ("PUT", 10): 6, ("PUT", 20): 3}
for (d, h), n in quota.items():
    pool = f[(f.direction == d) & (f.hold_sessions == h)].sample(frac=1, random_state=rnd.randint(0, 10**6)) if len(f[(f.direction == d) & (f.hold_sessions == h)]) else f.iloc[0:0]
    taken = 0
    for _, r in pool.iterrows():
        s = sigma_for(r.run_id, r.ticker)
        if s is None: continue
        sample.append((r, s)); taken += 1
        if taken >= n: break
# top up to 30 from holds 5/10 if 20s are short
while len(sample) < 30:
    d = "CALL" if sum(r.direction == "CALL" for r, _ in sample) < 15 else "PUT"
    pool = f[(f.direction == d) & (f.hold_sessions.isin([5, 10]))].sample(frac=1, random_state=rnd.randint(0, 10**6))
    for _, r in pool.iterrows():
        if any(r.ticker == x.ticker and r.decision_session == x.decision_session and r.direction == x.direction for x, _ in sample): continue
        s = sigma_for(r.run_id, r.ticker)
        if s is None: continue
        sample.append((r, s)); break

def bars_after(ticker, session, n):
    rows = con.execute("SELECT trading_date, open, high, low, close FROM ohlcv_daily WHERE ticker=? AND adjustment_convention='POLYGON_SPLIT_ADJUSTED' AND bar_status='COMPLETE' AND trading_date>? ORDER BY trading_date LIMIT ?", (ticker, session, n)).fetchall()
    return [{"date": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4]} for r in rows]

def my_label(direction, bars, target, inval, tie="AMBIGUOUS"):
    hit_t = hit_s = None
    for t, b in enumerate(bars, 1):
        ht = (b["high"] >= target) if direction == "CALL" else (b["low"] <= target)
        hs = (b["low"] <= inval) if direction == "CALL" else (b["high"] >= inval)
        if ht and hs:
            return ("AMBIGUOUS_TOUCH_ORDER" if tie == "AMBIGUOUS" else "INVALIDATION_FIRST"), t
        if ht: return "TARGET_FIRST", t
        if hs: return "INVALIDATION_FIRST", t
    return "TIMEOUT", None

out_rows = []; agree = 0; agree_prompt = 0; ties = 0; agree_struct_vs_budget = 0
for r, sig in sample:
    d, h, S, I = r.direction, int(r.hold_sessions), float(r.spot), float(r.invalidation)
    T = S * (1 + K * sig * math.sqrt(h / 252) * (1 if d == "CALL" else -1))
    bars = bars_after(r.ticker, r.decision_session, h)
    mine, t_mine = my_label(d, bars, T, I)
    mine_prompt, _ = my_label(d, bars, T, I, tie="PROMPT")
    ev = evaluate_outcome_path(direction=d, reference_price=S, future_bars=bars, horizon_sessions=h, target_price=T, invalidation_price=I)
    prod = competing_event_label(ev.first_passage_state).value if ev.data_status == "OBSERVED_COMPLETED_SESSIONS" else ev.data_status
    struct_T = float(r.target) if pd.notna(r.target) and float(r.target) > 0 else None
    mine_struct = my_label(d, bars, struct_T, I)[0] if struct_T else "NO_STRUCTURAL_TARGET"
    agree += (mine == prod); agree_prompt += (mine_prompt == prod); ties += (mine == "AMBIGUOUS_TOUCH_ORDER"); agree_struct_vs_budget += (mine_struct == mine)
    out_rows.append({"run_id": r.run_id, "decision_session": r.decision_session, "ticker": r.ticker, "direction": d, "hold_h": h, "spot_S_d": S,
                     "sigma_a": sig, "budget_target_T": round(T, 4), "invalidation_I": I, "structural_target": struct_T, "bars_found": len(bars),
                     "first_bar": bars[0]["date"] if bars else None, "last_bar": bars[-1]["date"] if bars else None,
                     "my_label_annex": mine, "my_sessions_to_event": t_mine, "my_label_prompt_tie_rule": mine_prompt,
                     "production_first_passage_state": ev.first_passage_state, "production_label": prod,
                     "production_target_hit_session": ev.target_first_hit_session, "production_stop_hit_session": ev.stop_first_hit_session,
                     "production_mfe": ev.mfe, "production_mae": ev.mae, "agree": mine == prod, "my_label_structural_target": mine_struct})
with open(os.path.join(ROOT, "p14_EH_e1_labels.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(out_rows[0])); w.writeheader(); w.writerows(out_rows)
# synthetic same-session dual-touch check of the production function
syn_call = evaluate_outcome_path(direction="CALL", reference_price=100.0, future_bars=[{"high": 101, "low": 99, "close": 100}, {"high": 110, "low": 90, "close": 100}], horizon_sessions=2, target_price=105.0, invalidation_price=95.0)
syn_put = evaluate_outcome_path(direction="PUT", reference_price=100.0, future_bars=[{"high": 101, "low": 99, "close": 100}, {"high": 110, "low": 90, "close": 100}], horizon_sessions=2, target_price=95.0, invalidation_price=105.0)
syn_put_down = evaluate_outcome_path(direction="PUT", reference_price=100.0, future_bars=[{"high": 100.5, "low": 94.0, "close": 95.0}], horizon_sessions=1, target_price=95.0, invalidation_price=105.0)
syn_short = evaluate_outcome_path(direction="CALL", reference_price=100.0, future_bars=[{"high": 106, "low": 99, "close": 105}], horizon_sessions=5, target_price=105.0, invalidation_price=95.0)
by_dir = {d: {"n": sum(r["direction"] == d for r in out_rows), "agree": sum(r["agree"] for r in out_rows if r["direction"] == d),
              "labels": {l: sum(r["my_label_annex"] == l for r in out_rows if r["direction"] == d) for l in ("TARGET_FIRST", "INVALIDATION_FIRST", "TIMEOUT", "AMBIGUOUS_TOUCH_ORDER")}} for d in ("CALL", "PUT")}
summary = {"n": len(out_rows), "agree_annex_rule": agree, "agree_prompt_tie_rule": agree_prompt, "same_session_ties_in_sample": ties,
           "structural_target_label_equals_budget_label": agree_struct_vs_budget, "by_direction": by_dir,
           "holds": {h: sum(r["hold_h"] == h for r in out_rows) for h in (5, 10, 20)},
           "runs_used": sorted({r["run_id"] for r in out_rows}),
           "synthetic": {"call_same_session_dual_touch": syn_call.first_passage_state + " -> " + competing_event_label(syn_call.first_passage_state).value,
                         "put_same_session_dual_touch": syn_put.first_passage_state + " -> " + competing_event_label(syn_put.first_passage_state).value,
                         "put_downside_touch_only": syn_put_down.first_passage_state + " -> " + competing_event_label(syn_put_down.first_passage_state).value + f" (mfe={syn_put_down.mfe:.4f})",
                         "target_hit_but_window_incomplete": syn_short.data_status + " / " + syn_short.first_passage_state},
           "put_downside_code_quote": "domain/decision_outcome.py: favourable = highs if side == 'CALL' else lows; PUT target: low <= target_value; PUT stop: high >= stop_value; sign = -1.0 for PUT"}
json.dump({"summary": summary, "rows": out_rows}, open(os.path.join(ROOT, "p14_EH_e1_labels_out.json"), "w"), indent=1, default=str)
print(json.dumps(summary, indent=1, default=str)); print(pd.DataFrame(out_rows)[["run_id","ticker","direction","hold_h","budget_target_T","invalidation_I","my_label_annex","production_label","agree","my_label_structural_target"]].to_string())
