#!/usr/bin/env python3
"""
AVS-VERIFY-001 v1.1 — deterministic run verifier for AVSHUNTER.

Read-only and advisory. It never imports pipeline code and never writes into the run folder.
It reads one run's book and the final_run_manifest.json, applies invariant rules,
and writes its report under audit/verify/<run_id>/<phase>/.

  C:\\Python314\\python.exe tools\\avs_verify\\avs_verify.py --run-id 20260927_205123 --phase morning
  C:\\Python314\\python.exe tools\\avs_verify\\avs_verify.py --run-id 20260927_205123 --phase evening

Scope: book-level rules cover the whole book. Row-level rules cover only TRADEABLE rows
(the rows a trader could act on), because UNRESOLVED/BLOCK rows are expected to have gaps.

Exit codes: 0 TRUST, 1 TRUST_WITH_CAVEATS, 2 DO_NOT_TRADE, 3 UNVERIFIED, 4 error.  Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

VERSION = "avs_verify_v1_2"
SEV = {"P0": 0, "P1": 1, "P2": 2}
csv.field_size_limit(2**31 - 1)


# ------------------------------------------------------------------ helpers
def et_offset(u: dt.datetime) -> dt.timedelta:
    try:
        from zoneinfo import ZoneInfo
        return u.astimezone(ZoneInfo("America/New_York")).utcoffset()
    except Exception:  # Windows without tzdata: US DST rule
        y = u.year
        m1 = dt.datetime(y, 3, 1, tzinfo=dt.timezone.utc)
        start = m1 + dt.timedelta(days=(6 - m1.weekday()) % 7 + 7, hours=7)
        n1 = dt.datetime(y, 11, 1, tzinfo=dt.timezone.utc)
        end = n1 + dt.timedelta(days=(6 - n1.weekday()) % 7, hours=6)
        return dt.timedelta(hours=-4 if start <= u < end else -5)


def to_et(u: dt.datetime) -> dt.datetime:
    u = u.astimezone(dt.timezone.utc)
    return (u + et_offset(u)).replace(tzinfo=None)


def parse_ts(s) -> dt.datetime | None:
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def hhmm(s: str) -> dt.time:
    h, m = s.split(":")
    return dt.time(int(h), int(m))


def num(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s == "" or s.lower() in ("nan", "none", "null", "na", "n/a"):
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def blank(v) -> bool:
    return v is None or str(v).strip().lower() in ("", "nan", "none", "null", "na", "n/a")


def dig(d: dict, path: str):
    for p in path.split("."):
        if not isinstance(d, dict) or p not in d:
            return None
        d = d[p]
    return d


class F:
    def __init__(self, known: dict):
        self.book, self.row, self.known = [], {}, known

    def b(self, rule, sev, status, msg, ev=None):
        note = None
        if sev == "P0" and status == "FAIL" and rule in self.known:
            sev, note = "P1", f"known defect: {self.known[rule]}"
        self.book.append({"rule": rule, "severity": sev, "status": status, "message": msg,
                          "known_defect": note, "evidence": ev or {}})

    def r(self, i, rule, sev, msg):
        self.row.setdefault(i, []).append((rule, sev, msg))


# ------------------------------------------------------------------ rules
def r_self_report(man, cfg, phase, nrows, f: F):
    if not man:
        f.b("R00_PIPELINE_SELF_REPORT", "P1", "SKIPPED", "No final_run_manifest.json found.")
        return
    sr = cfg["manifest_self_report"]
    fails, warns = [], []
    for k, bad in sr["fail_if"].items():
        if k in man and man[k] in bad:
            fails.append(f"{k}={man[k]}")
    for k in sr["fail_if_nonempty"]:
        if man.get(k):
            fails.append(f"{k}={man[k]}")
    for k, bad in sr["warn_if"].items():
        if k in man and man[k] in bad:
            warns.append(f"{k}={man[k]}")
    for k in sr["warn_if_nonempty"]:
        if man.get(k):
            warns.append(f"{k}={man[k]}")
    if fails:
        f.b("R00_PIPELINE_SELF_REPORT", "P0", "FAIL",
            "The pipeline itself marked this run not tradeable: " + "; ".join(fails), {"fails": fails, "warns": warns})
    else:
        f.b("R00_PIPELINE_SELF_REPORT", "P0", "PASS", "Pipeline self-report clean.", {"warns": warns})
    if warns:
        f.b("R00_PIPELINE_HEALTH", "P1", "WARN", "; ".join(warns))
    rc = dig(man, sr["row_count_key"][phase])
    if isinstance(rc, (int, float)):
        f.b("R24_MANIFEST_RECONCILE", "P0", "PASS" if int(rc) == nrows else "FAIL",
            f"manifest {sr['row_count_key'][phase]}={rc} vs book rows={nrows}")


def r_timing(run_id, phase, man, cfg, f: F):
    t, src = None, cfg["phases"][phase]["run_time_source"]
    if src.startswith("manifest.") and man:
        t = parse_ts(dig(man, src.split(".", 1)[1]))
    if t is None:
        m = re.match(r"(\d{8}_\d{6})", run_id)
        if m:
            t = dt.datetime.strptime(m.group(1), "%Y%m%d_%H%M%S").replace(tzinfo=dt.timezone.utc) \
                - dt.timedelta(hours=cfg["timing"]["run_id_utc_offset_hours"])
            src = "run_id"
    if t is None:
        f.b("R01_RUN_TIMING", "P1", "SKIPPED", "Run time unknown.")
        return None
    et, T = to_et(t), cfg["timing"]
    wk = et.weekday() < 5
    rth = wk and hhmm(T["rth_open_et"]) <= et.time() < hhmm(T["evening_earliest_et"])
    ev = {"utc": t.isoformat(), "et": et.strftime("%a %Y-%m-%d %H:%M ET"), "source": src}
    if phase == "evening":
        f.b("R01_RUN_TIMING", "P0", "FAIL" if rth else "PASS",
            f"Evening run at {ev['et']} — " + ("INSIDE the trading session; session anchor and quotes are the prior day's."
                                               if rth else "outside the regular session."), ev)
    else:
        lo, hi = (hhmm(x) for x in T["morning_quote_window_et"])
        if wk and lo <= et.time() <= hi:
            f.b("R01_RUN_TIMING", "P1", "PASS", f"Morning validation at {ev['et']} — inside quote window.", ev)
        else:
            f.b("R01_RUN_TIMING", "P1", "WARN",
                f"Morning validation at {ev['et']} — outside the {lo:%H:%M}–{hi:%H:%M} ET quote window.", ev)
    return t


def r_structure(header, rows, raw_rows, cm, cfg, trade_idx, f: F):
    cnt = Counter(header)
    dups = [h for h, n in cnt.items() if n > 1]
    differ = []
    for h in dups:
        idx = [i for i, c in enumerate(header) if c == h]
        if any(len({rr[i] if i < len(rr) else "" for i in idx}) > 1 for rr in raw_rows):
            differ.append(h)
    if differ:
        f.b("R02_DUPLICATE_HEADERS", "P0", "FAIL", f"Duplicate headers with CONFLICTING values: {differ}", {"all": dups})
    elif dups:
        f.b("R02_DUPLICATE_HEADERS", "P1", "WARN",
            f"{len(dups)} duplicated headers (values identical today, but any reader picks one copy arbitrarily): {dups}")
    else:
        f.b("R02_DUPLICATE_HEADERS", "P0", "PASS", "No duplicate headers.")

    f.b("R02_TRADEABLE_SET", "P2", "INFO", f"{len(trade_idx)} tradeable rows of {len(rows)}.")
    miss = [k for k, c in cfg["columns"].items() if c.get("critical") and not cm.get(k)]
    f.b("R03_CRITICAL_COLUMNS", "P0", "FAIL" if miss else "PASS",
        f"Critical columns not found: {miss}" if miss else "All critical columns resolved.")
    thr, nulls = cfg["thresholds"]["critical_null_rate_fail"], {}
    if trade_idx:
        for k, c in cfg["columns"].items():
            col = cm.get(k)
            if c.get("critical") and col:
                rate = sum(blank(rows[i].get(col)) for i in trade_idx) / len(trade_idx)
                if rate > thr:
                    nulls[k] = round(rate, 3)
    f.b("R03_CRITICAL_NULLS", "P0", "FAIL" if nulls else "PASS",
        f"Tradeable rows with critical fields null above {thr:.0%}: {nulls}" if nulls
        else "Critical fields populated on tradeable rows.", nulls)

    tk, ct = cm.get("ticker"), cm.get("contract")
    if tk and trade_idx:
        keys = Counter((rows[i].get(tk), rows[i].get(ct) if ct else "") for i in trade_idx)
        d = [list(k) for k, n in keys.items() if n > 1]
        f.b("R04_DUPLICATE_ROWS", "P1", "FAIL" if d else "PASS",
            f"{len(d)} duplicated ticker/contract among tradeable rows." if d else "No duplicate tradeable rows.",
            {"examples": d[:10]})


def r_contradictions(rows, header, cfg, f: F):
    hs = set(header)
    for c in cfg["contradictions"]:
        if c["a"] in hs and c["b"] in hs:
            n = sum(1 for r in rows if r.get(c["a"]) in c["a_in"] and r.get(c["b"]) in c["b_in"])
            base = sum(1 for r in rows if r.get(c["a"]) in c["a_in"])
            if n:
                sev = "P0" if base and n / base >= cfg["thresholds"]["systemic_rate"] else "P1"
                f.b(f"R20_{c['id']}", sev, "FAIL",
                    f"{n}/{base} rows with {c['a']}∈{c['a_in']} also have {c['b']}∈{c['b_in']} — "
                    "two authorities disagree on whether the row is tradeable.")
            else:
                f.b(f"R20_{c['id']}", "P1", "PASS", f"No {c['a']}/{c['b']} contradiction.")


def r_rows(rows, trade_idx, cm, cfg, phase, run_ts, f: F):
    th, c = cfg["thresholds"], cm
    uv = cfg["spread_unit_values"]
    g = lambda r, k: r.get(c[k]) if c.get(k) else None
    agg = Counter()
    for i in trade_idx:
        r = rows[i]
        d = (g(r, "direction") or "").strip().upper()
        if d not in ("CALL", "PUT"):
            f.r(i, "R10_DIRECTION", "P0", f"tradeable row with direction '{d or 'blank'}'")
            d = None
        ref, live, tgt, stp = (num(g(r, k)) for k in ("ref_spot", "live_spot", "target", "stop"))
        for k, v in (("ref_spot", ref), ("target", tgt), ("stop", stp)):
            if v is None or v <= 0:
                f.r(i, "R11_LEVELS_PRESENT", "P0", f"{k} missing/≤0")
        if d and ref and tgt and stp:
            if not ((tgt > ref > stp) if d == "CALL" else (tgt < ref < stp)):
                f.r(i, "R12_LEVEL_SIDES", "P0", f"{d}: target {tgt} / ref {ref} / stop {stp} wrong side")
        if phase == "morning" and d and live and stp:
            if (live <= stp) if d == "CALL" else (live >= stp):
                f.r(i, "R12_LIVE_THROUGH_STOP", "P0", f"{d}: live {live} already through invalidation {stp}")
        if phase == "morning" and d and live and tgt:
            if (live >= tgt) if d == "CALL" else (live <= tgt):
                f.r(i, "R12_LIVE_PAST_TARGET", "P1", f"{d}: live {live} already past target {tgt}")

        sym = (g(r, "contract") or "").strip()
        m = re.search(r"\d{6}([CP])\d{8}$", sym)
        if d and m and m.group(1) != d[0]:
            f.r(i, "R14_CONTRACT_TYPE", "P0", f"{d} thesis but contract {sym} is a {m.group(1)}")
        bid, ask, mid = (num(g(r, k)) for k in ("bid", "ask", "mid"))
        if bid is not None and ask is not None:
            if ask <= 0 or bid < 0 or bid > ask:
                f.r(i, "R13_QUOTE_SANITY", "P0", f"bid {bid} / ask {ask} invalid")
            elif bid == 0:
                f.r(i, "R13_QUOTE_SANITY", "P1", "zero bid — no exit liquidity")
            elif mid is not None and not (bid - 1e-9 <= mid <= ask + 1e-9):
                f.r(i, "R13_QUOTE_SANITY", "P1", f"mid {mid} outside {bid}/{ask}")
        de = num(g(r, "delta"))
        if d and de is not None:
            if (d == "CALL" and de <= 0) or (d == "PUT" and de >= 0):
                f.r(i, "R14_DELTA_SIGN", "P0", f"{d} with delta {de}")
            elif not th["delta_abs_min"] <= abs(de) <= th["delta_abs_max"]:
                f.r(i, "R14_DELTA_RANGE", "P1", f"|delta| {abs(de):.2f} outside band")

        dte, hold = num(g(r, "dte")), num(g(r, "hold"))
        hold_cal = hold * th["session_to_calendar"] if hold else None
        if dte is not None and dte <= 0:
            f.r(i, "R15_DTE", "P0", f"DTE {dte}")
        if dte is not None and hold_cal and dte < hold_cal:
            f.r(i, "R15_DTE_VS_HOLD", "P0", f"DTE {dte:.0f} < hold {hold:.0f} sessions (~{hold_cal:.0f} cal days)")
        agg.setdefault("_holds", Counter())[hold] += 1
        src = (r.get(cfg["hold_derivation"]["source_column"]) or "").strip()
        agg.setdefault("_hold_src", Counter())[src or "<blank>"] += 1

        sp, unit = num(g(r, "spread")), uv.get((g(r, "spread_unit") or "").strip())
        if sp is not None:
            if unit is None:
                agg["spread_unit_missing"] += 1
            else:
                frac = sp / 100 if unit == "percent" else sp
                agg["spread_n"] += 1
                if (unit == "fraction" and sp > 5) or (unit == "percent" and 0 < sp < 0.05 and sp != 0):
                    agg["spread_unit_suspect"] += 1
                if frac >= th["spread_fail_fraction"]:
                    f.r(i, "R16_SPREAD", "P1", f"spread {frac:.0%} of mid")
                    agg["spread_fail"] += 1
                elif frac >= th["spread_warn_fraction"]:
                    agg["spread_warn"] += 1

        gg = [num(g(r, k)) for k in ("garch_1_5", "garch_6_10", "garch_11_20")]
        if all(x is not None for x in gg):
            agg["garch_n"] += 1
            if not gg[0] <= gg[1] <= gg[2]:
                agg["garch_bad"] += 1
        em = None
        if hold:
            em = num(g(r, "em_5d")) if hold <= 7 else num(g(r, "em_10d")) if hold <= 14 else num(g(r, "em_20d"))
        if ref and tgt and em and em > 0:
            ratio = abs(tgt - ref) / ref / em
            agg["reach_n"] += 1
            if ratio > th["target_vs_move_fail"]:
                agg["reach_fail"] += 1
                f.r(i, "R18_TARGET_REACHABLE", "P1", f"target needs {ratio:.1f}× expected move over hold")
            elif ratio > th["target_vs_move_warn"]:
                agg["reach_warn"] += 1

        if phase == "morning":
            # independent age: quote timestamp vs the time the verdict was stamped (manifest)
            q = parse_ts(g(r, "quote_ts"))
            own = (run_ts - q).total_seconds() / 60 if (q and run_ts) else None
            rep = num(g(r, "quote_age_s"))
            rep_m = rep / 60 if rep is not None else None
            lim = cfg["timing"]["quote_max_age_minutes"]
            agg["quote_n"] += 1
            if own is None and rep_m is None:
                agg["quote_unknown"] += 1
            else:
                if own is not None:
                    agg.setdefault("_own", []).append(own)
                stale_own = own is not None and own > lim
                stale_rep = rep_m is not None and rep_m > lim
                if stale_own or stale_rep:
                    agg["quote_stale"] += 1
                    if stale_rep:
                        agg["quote_stale_both"] += 1
                    f.r(i, "R19_QUOTE_FRESH", "P0" if stale_rep else "P1",
                        f"quote {own:.0f} min old at verdict time" + (f" (pipeline reports {rep_m:.0f} min)" if rep_m is not None else "")
                        if own is not None else f"pipeline reports quote {rep_m:.0f} min old")

        wp = num(g(r, "win_prob"))
        if wp is not None and not 0 <= wp <= 1:
            f.r(i, "R21_PROB_RANGE", "P0", f"win_prob {wp}")
        if "UNMAPPED" in (g(r, "macro_align") or "").upper():
            agg["unmapped"] += 1

    n = len(trade_idx) or 1
    sys_rate = th["systemic_rate"]
    if agg["spread_n"] or agg["spread_unit_missing"]:
        bad = agg["spread_unit_suspect"] + agg["spread_unit_missing"]
        f.b("R16_SPREAD_UNITS", "P0", "FAIL" if bad else "PASS",
            f"{bad} rows with missing or implausible spread unit." if bad else "Per-row spread units consistent.")
        f.b("R16_SPREAD_LEVEL", "P1", "WARN" if agg["spread_fail"] or agg["spread_warn"] else "PASS",
            f"Tradeable spreads: {agg['spread_fail']} ≥{th['spread_fail_fraction']:.0%}, "
            f"{agg['spread_warn']} in {th['spread_warn_fraction']:.0%}–{th['spread_fail_fraction']:.0%} of mid (n={agg['spread_n']}).")
    if agg["garch_n"]:
        rate = agg["garch_bad"] / agg["garch_n"]
        f.b("R17_GARCH_MONOTONIC", "P0" if rate >= sys_rate else "P1", "FAIL" if agg["garch_bad"] else "PASS",
            f"{agg['garch_bad']}/{agg['garch_n']} tradeable rows have non-cumulative GARCH windows ({rate:.0%}).")
    if agg["reach_n"]:
        f.b("R18_TARGET_REACHABLE", "P1", "WARN" if agg["reach_fail"] else "PASS",
            f"{agg['reach_fail']} tradeable targets need >{th['target_vs_move_fail']}× the expected move over the hold; "
            f"{agg['reach_warn']} more need {th['target_vs_move_warn']}–{th['target_vs_move_fail']}× (n={agg['reach_n']}).")
    # Hold must be an analysis output per trade (ACK 28 Sep): no cap, no constant.
    holds, srcs = agg.get("_holds", Counter()), agg.get("_hold_src", Counter())
    hd = cfg["hold_derivation"]
    known_holds = {k: v for k, v in holds.items() if k is not None}
    if not trade_idx:
        pass
    elif not known_holds:
        f.b("R15_HOLD_DERIVED", "P0", "UNCERTAIN", "No hold value on any tradeable row — hold derivation cannot be verified.")
    else:
        constant_src = [s for s in srcs if s in hd["constant_sources"]]
        single = len(known_holds) == 1 and len(trade_idx) >= hd["min_rows_for_constant_test"]
        if single or constant_src:
            f.b("R15_HOLD_DERIVED", "P0", "FAIL",
                f"Hold is not derived per trade: {len(known_holds)} distinct value(s) {sorted(known_holds)[:5]} across "
                f"{len(trade_idx)} tradeable rows; source {dict(srcs.most_common(3))}.",
                {"distinct_holds": {str(k): v for k, v in holds.most_common(10)}, "sources": dict(srcs)})
        else:
            f.b("R15_HOLD_DERIVED", "P0", "PASS",
                f"{len(known_holds)} distinct holds across {len(trade_idx)} tradeable rows; sources {dict(srcs.most_common(3))}.")
    if phase == "morning" and agg["quote_n"]:
        rate_both = agg["quote_stale_both"] / agg["quote_n"]
        own = sorted(agg.get("_own", []))
        rng = f" Independent age at verdict time: {own[0]:.0f}–{own[-1]:.0f} min (median {own[len(own)//2]:.0f})." if own else ""
        sev = "P0" if rate_both >= sys_rate else "P1"
        f.b("R19_QUOTE_FRESH", sev, "FAIL" if agg["quote_stale"] else "PASS",
            f"{agg['quote_stale']}/{agg['quote_n']} tradeable rows on quotes >{cfg['timing']['quote_max_age_minutes']} min old "
            f"({agg['quote_stale_both']} also stale by the pipeline's own quote_age_seconds); "
            f"{agg['quote_unknown']} unknown.{rng} Re-quote before entry.")
    if c.get("macro_align"):
        rate = agg["unmapped"] / n
        f.b("R22_MACRO_JOIN", "P0" if rate >= 0.95 else "P1",
            "FAIL" if rate >= th["macro_unmapped_rate_warn"] else "PASS",
            f"{agg['unmapped']}/{len(trade_idx)} tradeable rows USMI-UNMAPPED ({rate:.0%}) — macro context not reaching trades.")


def r_constant(header, rows, cfg, f: F):
    for col in cfg["thresholds"]["constant_columns"]:
        if col in header and len(rows) > 20:
            vals = {r.get(col) for r in rows if not blank(r.get(col))}
            if len(vals) == 1:
                f.b("R23_PLACEHOLDER_COLUMN", "P1", "WARN", f"{col} constant ({vals.pop()}) on every row.")


# ------------------------------------------------------------------ verdict
def decide(f: F, trade_idx):
    p0 = [b for b in f.book if b["severity"] == "P0" and b["status"] == "FAIL"]
    if any(b["rule"] == "R03_CRITICAL_COLUMNS" and b["status"] == "FAIL" for b in f.book):
        return "UNVERIFIED", [], "Critical columns missing — fix the column map."
    clean = [i for i in trade_idx if not any(s == "P0" for _, s, _ in f.row.get(i, []))]
    p1 = [b for b in f.book if b["severity"] == "P1" and b["status"] in ("FAIL", "WARN")]
    if p0:
        return "DO_NOT_TRADE", clean, f"{len(p0)} book-level P0: " + ", ".join(b["rule"] for b in p0)
    p0_unc = [b for b in f.book if b["severity"] == "P0" and b["status"] == "UNCERTAIN"]
    if p0_unc:  # missing evidence is never a pass
        return "UNVERIFIED", clean, "P0 evidence missing: " + ", ".join(b["rule"] for b in p0_unc)
    if not trade_idx:
        return "DO_NOT_TRADE", clean, "No tradeable rows."
    if not clean:
        return "DO_NOT_TRADE", clean, "Every tradeable row has a row-level P0."
    if p1 or len(clean) < len(trade_idx):
        return "TRUST_WITH_CAVEATS", clean, f"{len(clean)}/{len(trade_idx)} tradeable rows clean; {len(p1)} caveat(s)."
    return "TRUST", clean, "All rules passed."


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id")
    ap.add_argument("--run-dir")
    ap.add_argument("--runs-root", default=str(Path("data") / "output" / "runs"))
    ap.add_argument("--phase", choices=["evening", "morning"], required=True)
    ap.add_argument("--book")
    ap.add_argument("--rules", default=str(Path(__file__).with_name("avs_verify_rules.json")))
    ap.add_argument("--out-root", default=str(Path("audit") / "verify"))
    a = ap.parse_args()

    cfg = json.loads(Path(a.rules).read_text(encoding="utf-8"))
    run_dir = Path(a.run_dir) if a.run_dir else Path(a.runs_root) / (a.run_id or "")
    run_id = a.run_id or run_dir.name
    if not run_dir.is_dir():
        print(f"ERROR run folder not found: {run_dir}", file=sys.stderr)
        return 4
    ph = cfg["phases"][a.phase]
    book = Path(a.book) if a.book else next(
        (run_dir / p.format(run_id=run_id) for p in ph["book_files"] if (run_dir / p.format(run_id=run_id)).is_file()), None)
    if not book or not book.is_file():
        print(f"ERROR no {a.phase} book under {run_dir}", file=sys.stderr)
        return 4
    man = None
    for p in cfg["manifest_files"]:
        if (run_dir / p).is_file():
            man = json.loads((run_dir / p).read_text(encoding="utf-8"))
            break

    h = hashlib.sha256()
    with book.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    with book.open(newline="", encoding="utf-8-sig") as fh:
        rdr = csv.reader(fh)
        header = next(rdr, [])
        raw = list(rdr)
    first = {}
    for i, col in enumerate(header):
        first.setdefault(col, i)
    rows = [{col: (rr[i] if i < len(rr) else "") for col, i in first.items()} for rr in raw]

    lower = {x.lower(): x for x in header}
    cm = {k: next((lower[n.lower()] for n in c["names"] if n.lower() in lower), None) for k, c in cfg["columns"].items()}
    tcol, tvals = ph["tradeable"]["column"], set(ph["tradeable"]["values"])
    trade_idx = [i for i, r in enumerate(rows) if r.get(tcol) in tvals] if tcol in first else list(range(len(rows)))

    f = F(cfg.get("known_defects", {}))
    if tcol not in first:
        f.b("R02_TRADEABLE_COLUMN", "P1", "WARN", f"Tradeable column '{tcol}' missing — checking every row.")
    r_self_report(man, cfg, a.phase, len(rows), f)
    run_ts = r_timing(run_id, a.phase, man, cfg, f)
    r_structure(header, rows, raw, cm, cfg, trade_idx, f)
    r_contradictions(rows, header, cfg, f)
    r_rows(rows, trade_idx, cm, cfg, a.phase, run_ts, f)
    r_constant(header, rows, cfg, f)
    verdict, clean, why = decide(f, trade_idx)

    out = Path(a.out_root) / run_id / a.phase
    out.mkdir(parents=True, exist_ok=True)
    counts = Counter(rule for fl in f.row.values() for rule, _, _ in fl)
    checks = sorted(f.book, key=lambda b: (SEV.get(b["severity"], 3), b["status"] == "PASS", b["rule"]))
    rep = {"verifier": VERSION, "run_id": run_id, "phase": a.phase, "verdict": verdict, "reason": why,
           "book_file": str(book), "book_sha256": h.hexdigest(),
           "rules_sha256": hashlib.sha256(Path(a.rules).read_bytes()).hexdigest(),
           "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "rows": len(rows), "tradeable_rows": len(trade_idx), "clean_tradeable_rows": len(clean),
           "column_map": cm, "book_checks": checks, "row_failure_counts": dict(counts.most_common())}
    (out / "verify_report.json").write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")

    tk, dc = cm.get("ticker"), cm.get("direction")
    cset = set(clean)
    with (out / "row_flags.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["row", "ticker", "direction", "contract", "clean", "p0", "p1", "issues"])
        for i in trade_idx:
            r, fl = rows[i], f.row.get(i, [])
            w.writerow([i, r.get(tk, ""), r.get(dc, ""), r.get(cm.get("contract") or "", ""), i in cset,
                        sum(s == "P0" for _, s, _ in fl), sum(s == "P1" for _, s, _ in fl),
                        " | ".join(f"{a_}: {m}" for a_, _, m in fl)])

    L = [f"# AVS-VERIFY — {run_id} · {a.phase}", "", f"**Verdict: {verdict}** — {why}", "",
         f"`{book.name}` · {len(rows)} rows · {len(trade_idx)} tradeable · {len(clean)} clean · "
         f"sha256 `{rep['book_sha256'][:12]}` · {VERSION}", "",
         "## Book-level checks", "", "| Sev | Rule | Status | Detail |", "|---|---|---|---|"]
    for b in checks:
        det = b["message"] + (f" _({b['known_defect']})_" if b.get("known_defect") else "")
        L.append(f"| {b['severity']} | {b['rule']} | {b['status']} | {det.replace('|', '/')} |")
    L += ["", "## Row-level findings on tradeable rows", ""]
    L += [f"- {k}: {v}" for k, v in counts.most_common()] or ["- none"]
    L += ["", "## Column map", ""] + [f"- {k} → `{v}`" if v else f"- {k} → **NOT FOUND**" for k, v in cm.items()]
    (out / "verify_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"{verdict}: {why}\nReport: {out / 'verify_report.md'}")
    return {"TRUST": 0, "TRUST_WITH_CAVEATS": 1, "DO_NOT_TRADE": 2, "UNVERIFIED": 3}[verdict]


if __name__ == "__main__":
    sys.exit(main())
