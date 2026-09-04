"""AVS-TST-SD-001 Part A — parametrised pipeline regression suite.

Adapted from the AVS-E2E-CODE-001 measurements/ m-scripts, parametrised on run
id so the same suite runs against baseline and any candidate, and extended with
explicit OTHER-direction counts (STRANGLE / UNRESOLVED / blank / NONE).

READ-ONLY on production and run data. Writes nothing outside
audit/pipeline_map/AVS-TST-SD-001/.

Usage:
    python t_regression.py <run_id> [--baseline <run_id>] [--json out.json]

Emits one row per test: test_id, expected, actual, PASS/FAIL/BLOCKED.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RUNS = ROOT / "data" / "output" / "runs"

# Baseline reference values, established by AVS-E2E-CODE-001 (14/14 CONFIRMED).
BASELINE = {
    "discovery_rows": 1527, "vanguard_rows": 1481, "options_rows": 1248,
    "execution_rows": 1248, "eil_rows": 1248, "wbs_rows": 31,
    "eod_rows": 201, "book_rows": 201,
    "book_put": 111, "book_call": 90,
    "governed_call": 104, "governed_put": 77, "governed_strangle": 20,
    "invalidated": 442, "invalidated_put": 437, "invalidated_call": 5,
    "dte_unsuitable": 657, "blocked": 106,
    "contract_present": 191, "two_sided": 175,
    "wbs_intersection": 14, "wbs_excluded": 17,
    "trigger_quality_blank": 201, "trigger_score_55": 191,
    "horizon_1_5d": 655, "horizon_6_10d": 284, "horizon_11_20d": 0,
    "horizon_blocked": 17, "horizon_unaccounted": 292,
}

ARTEFACTS = {
    "discovery": "discovery/discovery_candidates_ultimate_{r}.csv",
    "vanguard": "vanguard/vanguard_signals.csv",
    "options": "options/options_intelligence_{r}.csv",
    "execution": "execution/execution_v3_5_{r}.csv",
    "eil": "superbrain/eil_enriched_{r}.csv",
    "wbs": "superbrain/wall_break_scores_{r}.csv",
    "eod": "morning_validation/morning_candidates_{r}.csv",
    "book": "intelligence_lab/final_opportunity_book_{r}.csv",
    "h15": "horizon/horizon_1_5d_{r}.csv",
    "h610": "horizon/horizon_6_10d_{r}.csv",
    "h1120": "horizon/horizon_11_20d_{r}.csv",
    "hblocked": "horizon/horizon_blocked_{r}.csv",
    "dropoff": "morning_validation/eod_dropoff_audit_{r}.csv",
    "mblocked": "morning_validation/morning_blocked_review_{r}.csv",
}

DIRECTIONAL = {"CALL", "PUT"}
OTHER_TOKENS = {"STRANGLE", "UNRESOLVED", "NONE", "", "NAN", "NULL"}

results: list[dict] = []


def emit(tid, ws, level, expected, actual, status, note=""):
    results.append({
        "test_id": tid, "workstream": ws, "level": level,
        "expected": str(expected), "actual": str(actual),
        "status": status, "note": note,
    })


def load(run: str, key: str):
    """Return (rows, header) or (None, None) if absent."""
    p = RUNS / run / ARTEFACTS[key].format(r=run)
    if not p.exists():
        return None, None
    with p.open(newline="", encoding="utf-8-sig", errors="replace") as f:
        rd = csv.reader(f)
        try:
            header = next(rd)
        except StopIteration:
            return [], []
        return list(rd), header


def col(header, *names):
    for n in names:
        if n in header:
            return header.index(n)
    return None


def vals(rows, header, *names):
    i = col(header, *names)
    if i is None:
        return None
    return [(r[i].strip() if i < len(r) else "") for r in rows]


def norm(v: str) -> str:
    return (v or "").strip().upper()


def dir_bucket(v: str) -> str:
    u = norm(v)
    if u in DIRECTIONAL:
        return u
    return "OTHER"


def tickers(rows, header):
    v = vals(rows, header, "ticker", "Ticker", "TICKER", "symbol")
    return [norm(x) for x in v if norm(x)] if v is not None else []


def run_suite(run: str) -> None:
    data = {k: load(run, k) for k in ARTEFACTS}

    # ---- A1: population census -------------------------------------
    census = {}
    for key in ("discovery", "vanguard", "options", "execution", "eil",
                "wbs", "eod", "book"):
        rows, header = data[key]
        if rows is None:
            emit(f"A1.census.{key}", "A1", "artefact", "artefact present",
                 "MISSING", "BLOCKED", "artefact absent from run")
            census[key] = None
            continue
        t = tickers(rows, header)
        census[key] = (len(rows), len(set(t)), len(t) - len(set(t)))
        exp = BASELINE.get(f"{key}_rows")
        emit(f"A1.census.{key}", "A1", "artefact",
             f"{exp} rows (baseline)", f"{len(rows)} rows",
             "PASS" if exp is None or len(rows) == exp else "FAIL")
        emit(f"A1.dupes.{key}", "A1", "artefact", "0 duplicate tickers",
             census[key][2], "PASS" if census[key][2] == 0 else "FAIL")

    # ---- A1: no downstream arrivals --------------------------------
    chain = [("discovery", "vanguard"), ("vanguard", "options"),
             ("options", "eil"), ("eil", "execution"),
             ("execution", "eod"), ("eod", "book")]
    for a, b in chain:
        ra, ha = data[a]
        rb, hb = data[b]
        if ra is None or rb is None:
            emit(f"A1.arrivals.{a}->{b}", "A1", "artefact", "0 arrivals",
                 "BLOCKED", "BLOCKED", "artefact missing")
            continue
        ta, tb = set(tickers(ra, ha)), set(tickers(rb, hb))
        gained = tb - ta
        emit(f"A1.arrivals.{a}->{b}", "A1", "artefact",
             "0 tickers appearing that were absent upstream", len(gained),
             "PASS" if not gained else "FAIL",
             ",".join(sorted(gained)[:6]))

    # ---- A1: contract + quote coverage -----------------------------
    rows, header = data["book"]
    if rows is not None:
        cs = vals(rows, header, "contract_symbol", "selected_contract_symbol",
                  "recommended_contract")
        n_contract = sum(1 for x in (cs or []) if norm(x)) if cs else 0
        emit("A1.contract_coverage", "A1", "artefact",
             f"{BASELINE['contract_present']}/{BASELINE['book_rows']} (baseline)",
             f"{n_contract}/{len(rows)}",
             "PASS" if n_contract == BASELINE["contract_present"] else "FAIL")

        bid = vals(rows, header, "contract_bid", "live_contract_bid")
        ask = vals(rows, header, "contract_ask", "live_contract_ask")
        if bid and ask:
            def pos(x):
                try:
                    return float(x) > 0
                except Exception:
                    return False
            n2 = sum(1 for b, a in zip(bid, ask) if pos(b) and pos(a))
            emit("A1.two_sided_quotes", "A1", "artefact",
                 f"{BASELINE['two_sided']}/{BASELINE['book_rows']} (baseline)",
                 f"{n2}/{len(rows)}",
                 "PASS" if n2 == BASELINE["two_sided"] else "FAIL")
        else:
            emit("A1.two_sided_quotes", "A1", "artefact",
                 f"{BASELINE['two_sided']}/{BASELINE['book_rows']}",
                 "bid/ask columns not found", "BLOCKED")

    # ---- A1: WBS intersection --------------------------------------
    rw, hw = data["wbs"]
    rb2, hb2 = data["book"]
    if rw is not None and rb2 is not None:
        tw, tb2 = set(tickers(rw, hw)), set(tickers(rb2, hb2))
        inter, excl = tw & tb2, tw - tb2
        emit("A1.wbs_scored", "A1", "artefact",
             f"{BASELINE['wbs_rows']} (baseline)", len(tw),
             "PASS" if len(tw) == BASELINE["wbs_rows"] else "FAIL")
        emit("A1.wbs_intersection", "A1", "artefact",
             f"{BASELINE['wbs_intersection']} (baseline)", len(inter),
             "PASS" if len(inter) == BASELINE["wbs_intersection"] else "FAIL")
        emit("A1.wbs_excluded", "A1", "artefact",
             f"{BASELINE['wbs_excluded']} (baseline)", len(excl),
             "PASS" if len(excl) == BASELINE["wbs_excluded"] else "FAIL",
             ",".join(sorted(excl)[:20]))

    # ---- A1/A3: direction split, THREE-DIRECTION -------------------
    if rb2 is not None:
        for cname in ("canonical_direction", "final_direction", "direction",
                      "governed_direction"):
            v = vals(rb2, hb2, cname)
            if v is None:
                emit(f"A1.direction.{cname}", "A1", "artefact",
                     "column present", "ABSENT", "BLOCKED")
                continue
            buckets = {"CALL": 0, "PUT": 0, "OTHER": 0}
            other_detail: dict[str, int] = {}
            for x in v:
                b = dir_bucket(x)
                buckets[b] += 1
                if b == "OTHER":
                    other_detail[norm(x) or "<blank>"] = \
                        other_detail.get(norm(x) or "<blank>", 0) + 1
            emit(f"A1.direction.{cname}", "A1", "artefact",
                 "CALL/PUT/OTHER all reported",
                 f"CALL={buckets['CALL']} PUT={buckets['PUT']} "
                 f"OTHER={buckets['OTHER']} {other_detail}",
                 "PASS", "three-direction census")

    # ---- A3: unchanged-by-design defects (pre-fix reproduction) -----
    ro, ho = data["options"]
    if ro is not None:
        rr = vals(ro, ho, "remaining_runway_state")
        dirn = vals(ro, ho, "options_direction", "direction",
                    "canonical_direction")
        if rr is not None:
            inval = [i for i, x in enumerate(rr) if norm(x) == "THESIS_INVALIDATED"]
            emit("A3.invalidated_total", "WS1", "artefact",
                 f"{BASELINE['invalidated']} (baseline defect reproduces)",
                 len(inval),
                 "PASS" if len(inval) == BASELINE["invalidated"] else "FAIL",
                 "pre-WS1 expectation; post-WS1 expectation is 0")
            if dirn is not None:
                b = {"CALL": 0, "PUT": 0, "OTHER": 0}
                for i in inval:
                    b[dir_bucket(dirn[i])] += 1
                emit("A3.invalidated_by_direction", "WS1", "artefact",
                     f"PUT={BASELINE['invalidated_put']} "
                     f"CALL={BASELINE['invalidated_call']} OTHER=0",
                     f"PUT={b['PUT']} CALL={b['CALL']} OTHER={b['OTHER']}",
                     "PASS" if (b["PUT"] == BASELINE["invalidated_put"]
                                and b["CALL"] == BASELINE["invalidated_call"])
                     else "FAIL")
        liq = vals(ro, ho, "liquidity_state")
        if liq is not None:
            n = sum(1 for x in liq if norm(x) == "DTE_UNSUITABLE")
            emit("A3.dte_unsuitable", "WS1", "artefact",
                 f"{BASELINE['dte_unsuitable']} (baseline defect reproduces)", n,
                 "PASS" if n == BASELINE["dte_unsuitable"] else "FAIL",
                 "post-WS1 expectation is <= 32 + reported-unrouted")
        hold = vals(ro, ho, "remaining_hold_sessions")
        if hold is not None:
            def f(x):
                try:
                    return float(x)
                except Exception:
                    return None
            hv = [f(x) for x in hold]
            routed = sum(1 for x in hv if x in (5.0, 10.0, 20.0))
            emit("A3.hold_domain", "WS1", "artefact",
                 "post-WS1: 100% in {5,10,20}",
                 f"{routed}/{len(hv)} in routed set",
                 "PASS", "pre-WS1 census only; not a gate before WS1")

    # ---- A3: trigger fields in the book -----------------------------
    if rb2 is not None:
        tq = vals(rb2, hb2, "trigger_quality")
        ts = vals(rb2, hb2, "trigger_score")
        # WS2 must be tested on TYPE and EIL-equality, not populated-ness.
        # Baseline defect: the book's trigger_quality is NOT blank, it carries
        # trigger_score's numeric value ('55.0'/'0.0'). A naive
        # "is it populated?" test passes the defect. Test the domain instead.
        CATEG = {"STRONG", "SINGLE", "NONE"}

        def is_num(x: str) -> bool:
            try:
                float(x)
                return True
            except Exception:
                return False

        if tq is not None:
            blank = sum(1 for x in tq if not norm(x))
            numeric = sum(1 for x in tq if norm(x) and is_num(x))
            categ = sum(1 for x in tq if norm(x) in CATEG)
            emit("A3.trigger_quality_domain", "WS2", "artefact",
                 f"baseline defect: numeric-poisoned; post-WS2: "
                 f"{len(tq)}/{len(tq)} in {sorted(CATEG)}",
                 f"blank={blank} numeric={numeric} categorical={categ} "
                 f"of {len(tq)}",
                 "PASS" if numeric == BASELINE["trigger_score_55"] + 10
                 else "FAIL",
                 "TRAP: a populated-ness test passes this defect; "
                 "the column is type-poisoned, not empty")

            # ticker-wise equality with EIL (the actual WS2 gate)
            re_, he_ = data["eil"]
            if re_ is not None:
                et = tickers(re_, he_)
                eq = vals(re_, he_, "trigger_quality")
                emap = {t: norm(q) for t, q in zip(et, eq or [])}
                bt = tickers(rb2, hb2)
                pairs = [(t, norm(q), emap.get(t)) for t, q in zip(bt, tq)
                         if t in emap]
                agree = sum(1 for _, b, e in pairs if b == e)
                emit("A3.trigger_quality_eq_eil", "WS2", "artefact",
                     f"post-WS2: {len(pairs)}/{len(pairs)} equal to EIL",
                     f"{agree}/{len(pairs)} equal",
                     "PASS" if agree == 0 else "FAIL",
                     "baseline expectation is 0 agreement "
                     "(book numeric vs EIL categorical)")

        tp = vals(rb2, hb2, "trigger_primary")
        if tp is not None:
            blank = sum(1 for x in tp if not norm(x))
            emit("A3.trigger_primary_blank", "WS2", "artefact",
                 "baseline: 48/201 blank in the BOOK "
                 "(201/201 blank in morning_candidates)",
                 f"{blank}/{len(tp)}",
                 "PASS" if blank == 48 else "FAIL",
                 "post-WS2 expectation is 0 blank")

    # ---- A3: the EOD-candidate boundary, where the loss occurs ------
    rc, hc = data["eod"]
    if rc is not None:
        for cname, exp in (("trigger_quality", 201), ("trigger_primary", 201),
                           ("trigger_codes", 201)):
            v = vals(rc, hc, cname)
            if v is None:
                emit(f"A3.eod_{cname}", "WS2", "artefact", "column present",
                     "ABSENT", "BLOCKED")
                continue
            blank = sum(1 for x in v if not norm(x))
            emit(f"A3.eod_{cname}_blank", "WS2", "artefact",
                 f"{exp}/{exp} blank (baseline defect reproduces)",
                 f"{blank}/{len(v)}",
                 "PASS" if blank == exp else "FAIL",
                 "post-WS2 expectation is 0 blank")
        if ts is not None:
            n55 = sum(1 for x in ts if norm(x) in ("55.0", "55"))
            emit("A3.trigger_score_55", "WS2", "artefact",
                 f"{BASELINE['trigger_score_55']} (baseline)", n55,
                 "PASS" if n55 == BASELINE["trigger_score_55"] else "FAIL")
        qt = vals(rb2, hb2, "selected_quote_timestamp_utc")
        if qt is not None:
            blank = sum(1 for x in qt if not norm(x))
            emit("A3.quote_timestamp_blank", "WS6", "artefact",
                 f"{BASELINE['book_rows']}/{BASELINE['book_rows']} blank "
                 "(baseline defect reproduces)", f"{blank}/{len(qt)}",
                 "PASS" if blank == len(qt) else "FAIL",
                 "post-WS6 expectation is 0 blank")

    # ---- A3: horizon reconciliation --------------------------------
    hz = 0
    ok = True
    for k in ("h15", "h610", "h1120", "hblocked"):
        r, _ = data[k]
        if r is None:
            ok = False
            break
        hz += len(r)
    if ok and data["options"][0] is not None:
        oi = len(data["options"][0])
        emit("A3.horizon_reconciliation", "WS3", "artefact",
             f"input {oi} = routed + blocked; baseline unaccounted "
             f"{BASELINE['horizon_unaccounted']}",
             f"routed+blocked={hz}, unaccounted={oi - hz}",
             "PASS" if (oi - hz) == BASELINE["horizon_unaccounted"] else "FAIL",
             "post-WS3 expectation is 0 unaccounted")

    # ---- A2: closure marker ----------------------------------------
    rm = RUNS / run / "run_meta.json"
    emit("A2.run_closed", "A2", "artefact", "run_meta.json present",
         "present" if rm.exists() else "ABSENT",
         "PASS" if rm.exists() else "FAIL")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    if not (RUNS / a.run_id).exists():
        print(f"BLOCKED: run {a.run_id} does not exist under {RUNS}")
        sys.exit(2)

    run_suite(a.run_id)

    w = max(len(r["test_id"]) for r in results) + 1
    print(f"\n=== AVS-TST-SD-001 Part A regression :: run {a.run_id} ===\n")
    for r in results:
        print(f"  {r['status']:<8} {r['test_id']:<{w}} "
              f"expected={r['expected']!r:<48} actual={r['actual']!r}")
        if r["note"]:
            print(f"           {'':<{w}} note: {r['note'][:110]}")
    tally: dict[str, int] = {}
    for r in results:
        tally[r["status"]] = tally.get(r["status"], 0) + 1
    print(f"\n  TALLY: {tally}")

    out = Path(__file__).resolve().parent.parent / (
        a.json or f"TST_partA_{a.run_id}.csv")
    with out.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        wr.writeheader()
        wr.writerows(results)
    print(f"  wrote {out.name}")


if __name__ == "__main__":
    main()
