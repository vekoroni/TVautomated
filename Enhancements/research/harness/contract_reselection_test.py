#!/usr/bin/env python
"""Research test: would selecting the contract by reachable-payoff expectancy (ALG-04, net of friction)
instead of the legacy ESTIMATED_R (intrinsic at the structural target) change the contract, and by how much?

State: EXPLORATORY_NO_AUTHORITY. Read-only against a completed run. No pipeline imports, no databases.

For every actionable row: candidates = the run's contracts_tested for the ticker, same side, dte >= window floor
(40 days), two-sided quote with spread <= 30% of mid (friction domain). IV solved from mid for every candidate
including the pipeline's own selection (like-for-like). Each candidate is valued with the merged 5+7+8 harness at
the horizon hold. Selection rule under test: highest probability-free grid EV, tie-break lower spread.
Reported: how often the choice differs, the EV and asymmetry difference, and the effect on the 527 tickers that
had ESTIMATED_R_LT_1 rejections.
"""
from __future__ import annotations

import csv
import json
import statistics as st
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dte_rule_comparison import floor_days, parse, solve_iv  # noqa: E402
from merged_5_7_8_scenario_harness import value_row  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
RUN = sys.argv[1] if len(sys.argv) > 1 else "20260924_085940"
RATE = 0.04
HOLD_BY_BUCKET = {"1_5D": 5, "6_10D": 10, "11_20D": 20}
G = "ev_grid_net_return_fraction"
REACH = "payoff_favourable_reachable_base_net_return_fraction"
FLAT = "payoff_flat_base_net_return_fraction"


def main() -> int:
    base = ROOT / "data/output/runs" / RUN
    d = json.loads((base / "intelligence_lab" / f"final_opportunity_book_{RUN}.json").read_text(encoding="utf-8"))
    rows = d if isinstance(d, list) else (d.get("rows") or d.get("opportunities") or d.get("items") or d.get("book"))
    go = [r for r in rows if str(r.get("lab_verdict") or "").upper() in ("GO", "GO_LIMIT")]
    tested = {}
    for line in (base / "options" / f"contracts_tested_{RUN}.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            tested[rec["ticker"]] = rec
    rlt1 = set()
    with (base / "options" / f"contract_rejection_log_{RUN}.csv").open(encoding="utf-8") as f:
        for c in csv.DictReader(f):
            if "ESTIMATED_R_LT_1" in c["rejection_reason"]:
                rlt1.add(c["ticker"])

    out, reasons = [], Counter()
    for r in go:
        t = r["ticker"]
        side = str(r.get("options_direction") or r.get("final_direction") or r.get("direction") or "").upper()
        hold = HOLD_BY_BUCKET.get(str(r.get("time_horizon") or "").upper())
        spot = float(r["underlying_price"])
        sel_sym = str(r.get("selected_contract_symbol") or "")
        sel = parse(sel_sym)
        if not (side in ("CALL", "PUT") and hold and sel):
            reasons["ROW_UNUSABLE"] += 1
            continue
        w_floor = floor_days(20)

        def value(strike, dte, bid, ask):
            iv = solve_iv(side, spot, strike, dte / 365.0, 0.5 * (bid + ask))
            if iv is None:
                return None
            rr = dict(r)
            rr.update(strike=strike, contract_dte=dte, dte=dte, contract_iv=iv, contract_bid=bid, contract_ask=ask,
                      planned_hold_sessions=hold, time_horizon={5: "1_5D", 10: "6_10D", 20: "11_20D"}[hold])
            v = value_row(rr, RATE, "horizon")
            return v if v["applicability"] == "OK" else None

        # pipeline's own selection, like-for-like
        vsel = value(sel[1], float(r.get("contract_dte") or r.get("dte")), float(r["contract_bid"]), float(r["contract_ask"]))
        if vsel is None:
            reasons["SELECTED_UNVALUABLE"] += 1
            continue
        cands = []
        for c in tested.get(t, {}).get("contracts_tested", []):
            p = parse(c["symbol"])
            if not p or p[0] != side[0] or c["dte"] < w_floor:
                continue
            mid, sp = float(c.get("mid") or 0), float(c.get("spread_pct") or 0)
            if mid <= 0 or sp <= 0 or sp > 0.30:
                continue
            v = value(p[1], float(c["dte"]), mid * (1 - sp / 2), mid * (1 + sp / 2))
            if v is not None:
                cands.append((v[G], -sp, c["symbol"], p[1], float(c["dte"]), sp, v, c.get("gate_failed", "")))
        if not cands:
            reasons["NO_VALUABLE_CANDIDATE"] += 1
            continue
        cands.sort(reverse=True)
        best = cands[0]
        v_b = best[6]
        out.append({
            "ticker": t, "direction": side, "hold": hold, "had_r_lt1_rejection": t in rlt1,
            "sel_symbol": sel_sym, "sel_strike": sel[1], "sel_dte": float(r.get("contract_dte") or r.get("dte")),
            "sel_spread": vsel["spread_fraction_mid"], "sel_ev": vsel[G], "sel_reach": vsel[REACH], "sel_flat": vsel[FLAT],
            "sel_asym": round(vsel[REACH] / abs(vsel[FLAT]), 3) if vsel[FLAT] else None,
            "best_symbol": best[2], "best_strike": best[3], "best_dte": best[4], "best_spread": round(best[5], 4),
            "best_ev": v_b[G], "best_reach": v_b[REACH], "best_flat": v_b[FLAT],
            "best_asym": round(v_b[REACH] / abs(v_b[FLAT]), 3) if v_b[FLAT] else None,
            "best_gate_in_pipeline": best[7], "changed": best[2] != sel_sym,
            "ev_gain": round(v_b[G] - vsel[G], 4), "n_candidates": len(cands),
            "moneyness_sel": round(sel[1] / spot - 1, 4), "moneyness_best": round(best[3] / spot - 1, 4),
        })

    od = ROOT / "Enhancements/research/output" / RUN
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = od / f"contract_reselection_{stamp}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    ch = [o for o in out if o["changed"]]
    med = lambda xs: round(st.median(xs), 4) if xs else None
    summ = {
        "run_id": RUN, "state": "EXPLORATORY_NO_AUTHORITY", "rows_actionable": len(go), "rows_compared": len(out), "excluded": dict(reasons),
        "contract_changed": len(ch), "changed_share": round(len(ch) / len(out), 3),
        "median_ev_gain_all": med([o["ev_gain"] for o in out]), "median_ev_gain_changed": med([o["ev_gain"] for o in ch]),
        "sel_positive": sum(1 for o in out if o["sel_ev"] > 0), "best_positive": sum(1 for o in out if o["best_ev"] > 0),
        "sel_asym_ge2_spread_le15": sum(1 for o in out if o["sel_asym"] and o["sel_asym"] >= 2 and o["sel_spread"] <= 0.15),
        "best_asym_ge2_spread_le15": sum(1 for o in out if o["best_asym"] and o["best_asym"] >= 2 and o["best_spread"] <= 0.15),
        "median_sel": {"spread": med([o["sel_spread"] for o in out]), "dte": med([o["sel_dte"] for o in out]), "moneyness": med([o["moneyness_sel"] for o in out]), "ev": med([o["sel_ev"] for o in out]), "asym": med([o["sel_asym"] for o in out if o["sel_asym"]])},
        "median_best": {"spread": med([o["best_spread"] for o in out]), "dte": med([o["best_dte"] for o in out]), "moneyness": med([o["moneyness_best"] for o in out]), "ev": med([o["best_ev"] for o in out]), "asym": med([o["best_asym"] for o in out if o["best_asym"]])},
        "best_contract_pipeline_gate": dict(Counter(o["best_gate_in_pipeline"] for o in ch)),
        "r_lt1_tickers": {"n": sum(1 for o in out if o["had_r_lt1_rejection"]), "changed": sum(1 for o in ch if o["had_r_lt1_rejection"]),
                          "median_ev_gain": med([o["ev_gain"] for o in out if o["had_r_lt1_rejection"]]),
                          "sel_positive": sum(1 for o in out if o["had_r_lt1_rejection"] and o["sel_ev"] > 0),
                          "best_positive": sum(1 for o in out if o["had_r_lt1_rejection"] and o["best_ev"] > 0)},
        "output_csv": str(path),
    }
    (od / f"contract_reselection_{stamp}_summary.json").write_text(json.dumps(summ, indent=2), encoding="utf-8")
    print(json.dumps(summ, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
