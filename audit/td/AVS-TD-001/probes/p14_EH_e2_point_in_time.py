"""p14_EH_e2_point_in_time: Track E2. For 10 sampled EOD_THESIS CANDIDATE_DECISION
events (5 CALL / 5 PUT, runs 20260911_115904 and 20260910_150045) compare the ledger
payload target_price / invalidation_price / reference_price with the run's stored
final_opportunity_book columns for the same ticker (structural_target, target_price,
invalidation_price, underlying_price, signal_price) and with the ALG-08 budget target
S x (1 +/- 1.5 sigma sqrt(h/252)) built from the book's garch_forecast_vol and hold bucket.
Read-only. Output: p14_EH_e2_point_in_time_out.json / .csv
"""
import sqlite3, json, os, csv, math, random
import pandas as pd
ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(ROOT, "..", "..", "..", ".."))
DB = os.path.abspath(os.path.join(ROOT, "..", "db_copies", "decision_outcome_ledger.sqlite"))
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
HOLD = {"1_5d": 5, "6_10d": 10, "11_20d": 20}
rows_out = []
for run in ("20260911_115904", "20260910_150045"):
    book = pd.read_csv(os.path.join(REPO, "data", "output", "runs", run, "intelligence_lab", f"final_opportunity_book_{run}.csv"), low_memory=False)
    book["ticker"] = book["ticker"].astype(str).str.upper()
    ev = con.execute("SELECT event_id,ticker,occurred_at_utc,payload_json FROM ledger_events WHERE run_id=? AND event_type='CANDIDATE_DECISION'", (run,)).fetchall()
    ev = [(e, t, o, json.loads(p)) for e, t, o, p in ev]
    ev = [x for x in ev if x[3].get("decision_stage") == "EOD_THESIS" and x[3].get("direction") in ("CALL", "PUT") and x[3].get("target_price") not in ("", None, 0)]
    rnd = random.Random(2026)
    for d in ("CALL", "PUT"):
        pool = [x for x in ev if x[3]["direction"] == d]
        rnd.shuffle(pool)
        for e, t, o, p in pool[: (3 if run == "20260911_115904" else 2)]:
            b = book[book["ticker"] == t]
            b = b.iloc[0] if len(b) else None
            def g(c):
                try: return float(b[c]) if b is not None and c in b and pd.notna(b[c]) else None
                except (TypeError, ValueError): return None
            s = g("underlying_price"); sig = g("garch_forecast_vol"); hb = str(b["hold_period"]) if b is not None and "hold_period" in b else None
            h = HOLD.get(hb)
            budget_target = None
            if s and sig and h:
                budget_target = s * (1 + (1.5 * sig * math.sqrt(h / 252)) * (1 if d == "CALL" else -1))
            lt, li, lr = (float(p["target_price"]) if p.get("target_price") not in ("", None) else None,
                          float(p["invalidation_price"]) if p.get("invalidation_price") not in ("", None) else None,
                          float(p["reference_price"]) if p.get("reference_price") not in ("", None) else None)
            def eq(a, c): return (a is not None and c is not None and abs(a - c) <= 1e-6 * max(1, abs(c)))
            rows_out.append({
                "run_id": run, "event_id": e[:16], "ticker": t, "direction": d, "occurred_at_utc": o,
                "ledger_target": lt, "ledger_invalidation": li, "ledger_reference": lr,
                "ledger_completed_session": p.get("completed_session"), "ledger_planned_hold": p.get("planned_hold_sessions"),
                "book_structural_target": g("structural_target"), "book_target_price": g("target_price"), "book_invalidation_price": g("invalidation_price"),
                "book_underlying_price": s, "book_signal_price": g("signal_price"), "book_garch_forecast_vol": sig, "book_hold_period": hb,
                "alg08_budget_target_from_book": budget_target,
                "target_eq_book_target_price": eq(lt, g("target_price")), "target_eq_book_structural_target": eq(lt, g("structural_target")),
                "target_eq_alg08_budget": eq(lt, budget_target), "invalidation_eq_book": eq(li, g("invalidation_price")),
                "reference_eq_book_underlying": eq(lr, s), "reference_eq_book_signal": eq(lr, g("signal_price")),
            })
with open(os.path.join(ROOT, "p14_EH_e2_point_in_time.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows_out[0])); w.writeheader(); w.writerows(rows_out)
summary = {k: sum(bool(r[k]) for r in rows_out) for k in ("target_eq_book_target_price", "target_eq_book_structural_target", "target_eq_alg08_budget", "invalidation_eq_book", "reference_eq_book_underlying", "reference_eq_book_signal")}
summary["n"] = len(rows_out); summary["by_direction"] = {d: sum(r["direction"] == d for r in rows_out) for d in ("CALL", "PUT")}
summary["completed_session_present"] = sum(r["ledger_completed_session"] not in (None, "") for r in rows_out)
summary["planned_hold_present"] = sum(r["ledger_planned_hold"] not in (None, "") for r in rows_out)
summary["production_reads_payload_only"] = "canonical_data/outcome_maturation.py:111-113 reference/target/invalidation from candidate.payload; :162-169 passed verbatim to evaluate_outcome_path; future_bars are the only later data"
json.dump({"summary": summary, "rows": rows_out}, open(os.path.join(ROOT, "p14_EH_e2_point_in_time_out.json"), "w"), indent=1, default=str)
print(json.dumps(summary, indent=1)); print(pd.DataFrame(rows_out)[["run_id","ticker","direction","ledger_target","book_target_price","book_structural_target","alg08_budget_target_from_book","ledger_invalidation","book_invalidation_price","ledger_reference","book_underlying_price"]].to_string())
