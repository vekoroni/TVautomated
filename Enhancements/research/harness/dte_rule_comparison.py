#!/usr/bin/env python
"""Research test: DTE chosen from the anticipated-move horizon versus from the 20-session window.

State: EXPLORATORY_NO_AUTHORITY. Read-only against a completed run. No pipeline imports, no databases.

Rule W (current, ACK 18 Sep decision (a)): runway floor = window 20 + monitor 3 + exit buffer 5 = 28 sessions
   -> ceil(28 * 1.4) = 40 calendar days. The book's selected contract was chosen under this rule.
Rule AM (test): runway floor = anticipated-move hold (5 or 10 by horizon bucket) + 3 + 5
   -> 13 sessions -> 19 days (1_5d); 18 sessions -> 26 days (6_10d).

For each actionable row the AM contract is picked from the run's contracts_tested record: same side, dte >= AM floor,
shortest expiry first, then strike closest to the selected contract's strike, usable two-sided quote inside the
friction domain. IV is solved from mid for both contracts so the comparison is like-for-like (ALG-04 permits
solving from mid when IV is absent). Both are valued with the merged 5+7+8 harness at the horizon hold, and the
window contract additionally under Day-10 / Day-20 exit policies that the AM contract cannot reach.
"""
from __future__ import annotations

import csv
import json
import math
import re
import statistics as st
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merged_5_7_8_scenario_harness import bsm, value_row  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
RUN = sys.argv[1] if len(sys.argv) > 1 else "20260924_085940"
RATE = 0.04
MONITOR, EXIT_BUFFER, CAL = 3, 5, 7.0 / 5.0
HOLD_BY_BUCKET = {"1_5D": 5, "6_10D": 10, "11_20D": 20}
SYM = re.compile(r"^([A-Z.]+)(\d{6})([CP])(\d{8})$")


def floor_days(hold: int) -> int:
    return math.ceil(math.ceil(hold + MONITOR + EXIT_BUFFER) * CAL)


def parse(sym: str):
    m = SYM.match(sym)
    if not m:
        return None
    return m.group(3), float(m.group(4)) / 1000.0, datetime.strptime(m.group(2), "%y%m%d").date()


def solve_iv(side: str, s: float, k: float, t: float, price: float) -> float | None:
    lo, hi = 0.01, 5.0
    if price <= max(s - k, 0.0) * (1 if side == "CALL" else 0) + max(k - s, 0.0) * (1 if side == "PUT" else 0):
        return None
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if bsm(side, s, k, t, mid, RATE) > price:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi) if 0.011 < 0.5 * (lo + hi) < 4.99 else None


def main() -> int:
    book = ROOT / "data/output/runs" / RUN / "intelligence_lab" / f"final_opportunity_book_{RUN}.json"
    tested = ROOT / "data/output/runs" / RUN / "options" / f"contracts_tested_{RUN}.jsonl"
    d = json.loads(book.read_text(encoding="utf-8"))
    rows = d if isinstance(d, list) else (d.get("rows") or d.get("opportunities") or d.get("items") or d.get("book"))
    go = [r for r in rows if str(r.get("lab_verdict") or "").upper() in ("GO", "GO_LIMIT")]
    by = {}
    for line in tested.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            by[rec["ticker"]] = rec

    out, reasons = [], Counter()
    for r in go:
        t = r["ticker"]
        side = str(r.get("options_direction") or r.get("final_direction") or r.get("direction") or "").upper()
        bucket = str(r.get("time_horizon") or "").upper()
        hold = HOLD_BY_BUCKET.get(bucket)
        spot = float(r["underlying_price"])
        sel = parse(str(r.get("selected_contract_symbol") or ""))
        if not (side in ("CALL", "PUT") and hold and sel):
            reasons["ROW_UNUSABLE"] += 1
            continue
        _, sel_strike, _ = sel
        am_floor, w_floor = floor_days(hold), floor_days(20)
        cands = []
        for c in by.get(t, {}).get("contracts_tested", []):
            p = parse(c["symbol"])
            if not p or p[0] != side[0] or c["dte"] < am_floor or c["dte"] >= w_floor:
                continue
            mid, sp = float(c.get("mid") or 0), float(c.get("spread_pct") or 0)
            if mid <= 0 or sp <= 0 or sp > 0.30:
                continue
            cands.append((c["dte"], abs(p[1] - sel_strike), p[1], mid, sp, c["symbol"]))
        if not cands:
            reasons["NO_AM_CONTRACT_IN_BAND_WITH_USABLE_QUOTE"] += 1
            continue
        cands.sort()
        dte_am, _, k_am, mid_am, sp_am, sym_am = cands[0]
        bid_am, ask_am = mid_am * (1 - sp_am / 2), mid_am * (1 + sp_am / 2)
        iv_am = solve_iv(side, spot, k_am, dte_am / 365.0, mid_am)
        # like-for-like: solve the window contract's IV from its book mid as well
        bid_w, ask_w = float(r["contract_bid"]), float(r["contract_ask"])
        dte_w = float(r.get("contract_dte") or r.get("dte"))
        iv_w_book = float(r["contract_iv"])
        iv_w = solve_iv(side, spot, sel_strike, dte_w / 365.0, 0.5 * (bid_w + ask_w))
        if iv_am is None or iv_w is None:
            reasons["IV_UNSOLVABLE"] += 1
            continue

        def val(strike, dte, iv, bid, ask, h):
            rr = dict(r)
            rr.update(strike=strike, contract_dte=dte, dte=dte, contract_iv=iv, contract_bid=bid, contract_ask=ask,
                      planned_hold_sessions=h, time_horizon={5: "1_5D", 10: "6_10D", 20: "11_20D"}[h])
            return value_row(rr, RATE, "horizon")

        vw = val(sel_strike, dte_w, iv_w, bid_w, ask_w, hold)
        vam = val(k_am, dte_am, iv_am, bid_am, ask_am, hold)
        vw20 = val(sel_strike, dte_w, iv_w, bid_w, ask_w, 20)
        vw10 = val(sel_strike, dte_w, iv_w, bid_w, ask_w, 10) if hold == 5 else vw20
        if vw["applicability"] != "OK" or vam["applicability"] != "OK":
            reasons["VALUATION_INDETERMINATE:" + (vw["reason"] or vam["reason"])] += 1
            continue
        g = "ev_grid_net_return_fraction"
        out.append({
            "ticker": t, "direction": side, "bucket": bucket, "hold": hold, "am_floor_days": am_floor,
            "w_symbol": r["selected_contract_symbol"], "w_dte": dte_w, "w_strike": sel_strike, "w_ask": ask_w,
            "w_spread": round((ask_w - bid_w) / (0.5 * (ask_w + bid_w)), 4), "w_iv_book": iv_w_book, "w_iv_solved": round(iv_w, 4),
            "am_symbol": sym_am, "am_dte": dte_am, "am_strike": k_am, "am_ask": round(ask_am, 4), "am_spread": round(sp_am, 4),
            "am_iv_solved": round(iv_am, 4), "same_strike": k_am == sel_strike,
            "premium_saving_fraction": round((ask_w - ask_am) / ask_w, 4),
            "w_flat": vw["payoff_flat_base_net_return_fraction"], "am_flat": vam["payoff_flat_base_net_return_fraction"],
            "w_reach": vw["payoff_favourable_reachable_base_net_return_fraction"], "am_reach": vam["payoff_favourable_reachable_base_net_return_fraction"],
            "w_inval": vw["payoff_adverse_invalidation_base_net_return_fraction"], "am_inval": vam["payoff_adverse_invalidation_base_net_return_fraction"],
            "w_ev_grid": vw[g], "am_ev_grid": vam[g], "ev_delta_am_minus_w": round(vam[g] - vw[g], 4),
            "w_ppos": vw["p_positive_net_exit_grid"], "am_ppos": vam["p_positive_net_exit_grid"],
            "w_ev_grid_day10": vw10[g] if vw10["applicability"] == "OK" else None,
            "w_ev_grid_day20": vw20[g] if vw20["applicability"] == "OK" else None,
            "w_best_policy_ev": max(x for x in (vw[g], vw10[g] if vw10["applicability"] == "OK" else -9, vw20[g] if vw20["applicability"] == "OK" else -9)),
        })

    od = ROOT / "Enhancements/research/output" / RUN
    od.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = od / f"dte_rule_comparison_{stamp}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    med = lambda k: round(st.median([o[k] for o in out if o[k] is not None]), 4)
    summ = {
        "run_id": RUN, "state": "EXPLORATORY_NO_AUTHORITY", "rows_actionable": len(go), "rows_compared": len(out),
        "excluded": dict(reasons), "floors_days": {"1_5d": floor_days(5), "6_10d": floor_days(10), "window": floor_days(20)},
        "same_strike_share": round(sum(1 for o in out if o["same_strike"]) / len(out), 3),
        "medians": {k: med(k) for k in ("w_dte", "am_dte", "premium_saving_fraction", "w_spread", "am_spread", "w_iv_solved", "am_iv_solved",
                                       "w_flat", "am_flat", "w_reach", "am_reach", "w_inval", "am_inval", "w_ev_grid", "am_ev_grid",
                                       "ev_delta_am_minus_w", "w_ppos", "am_ppos", "w_best_policy_ev")},
        "iv_solved_vs_book_median_abs_gap": round(st.median([abs(o["w_iv_solved"] - o["w_iv_book"]) for o in out]), 4),
        "count_am_better_at_horizon": sum(1 for o in out if o["am_ev_grid"] > o["w_ev_grid"]),
        "count_am_positive": sum(1 for o in out if o["am_ev_grid"] > 0), "count_w_positive": sum(1 for o in out if o["w_ev_grid"] > 0),
        "count_w_best_policy_positive": sum(1 for o in out if o["w_best_policy_ev"] > 0),
        "count_am_better_than_w_best_policy": sum(1 for o in out if o["am_ev_grid"] > o["w_best_policy_ev"]),
        "output_csv": str(path),
    }
    (od / f"dte_rule_comparison_{stamp}_summary.json").write_text(json.dumps(summ, indent=2), encoding="utf-8")
    print(json.dumps(summ, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
