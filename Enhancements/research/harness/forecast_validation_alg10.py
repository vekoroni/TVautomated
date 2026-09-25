#!/usr/bin/env python
"""C3 / ALG-10 forecast-volatility validation (AVS-VAL-001), read-only.

Inputs: every run's qomega/garch_forecasts_<run>.csv (point-in-time Layer 3 forecast per ticker), the run's
vanguard file for the as-of session (bar_data_asof) and hidden_state_label, and the canonical price DB opened
read-only (mode=ro) for realised close-to-close volatility over the next h sessions.

Method (docs/requirements/AVS-REQ-FIX-002_Annex_A ALG-10; reviewer amendment: variance QLIKE):
  RV_h      = sqrt(252/h * sum_{t=d+1..d+h} ln(C_t/C_{t-1})^2)         annualised
  ratio_h   = RV_h / sigma_f
  coverage  = 1[ |ln(C_{d+h}/C_d)| <= sigma_f * sqrt(h/252) ]           ~0.68 if unbiased and normal
  qlike     = RV^2/sigma^2 - ln(RV^2/sigma^2) - 1                        on variance, >= 0, 0 is perfect
  Partition: sessions time-ordered; train = first 70% of sessions, purge = h sessions, test = the rest.
  Multiplier m = clip(median train ratio, 0.5, 1.5); PASS on test iff median(ratio/m) in [0.90, 1.10] and
  coverage with m applied in [0.60, 0.76]. Buckets with n < minimum_n back off to overall.
  Effective sample size = number of test sessions (blocks); block bootstrap by session for the median.

Two forecast families are reported separately and never mixed:
  LEGACY_PRE_17SEP : runs before the 17 Sep Layer 3 integrity fix (no l3_forecast_state column)
  CURRENT_V2       : l3_forecast_state == FORECAST_OK, l3_forward_realised_vol_raw
A forecast for the same (ticker, session) from two runs is used once.
State: EXPLORATORY_NO_AUTHORITY. Writes only under Enhancements/research/output/forecast_validation/.
"""
from __future__ import annotations

import csv
import json
import math
import os
import random
import sqlite3
import statistics as st
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNS = ROOT / "data" / "output" / "runs"
DB = ROOT / "data" / "canonical" / "historical_prices.sqlite"
OUT = ROOT / "Enhancements" / "research" / "output" / "forecast_validation"
HORIZONS = (5, 10, 20)
MIN_N = 200
TRAIN_SHARE = 0.70
PASS_MEDIAN = (0.90, 1.10)
PASS_COVERAGE = (0.60, 0.76)
SEED = 20260925


def _f(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def load_forecasts():
    """(family, ticker, session, sigma_f, hidden_state) with one row per (family, ticker, session)."""
    seen = {}
    runs_used = []
    for run in sorted(os.listdir(RUNS)):
        gp = RUNS / run / "qomega" / f"garch_forecasts_{run}.csv"
        vp = RUNS / run / "options" / f"vanguard_signals_enriched_{run}.csv"
        if not gp.exists() or not vp.exists():
            continue
        vrows = {}
        with vp.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                t = str(r.get("ticker") or "").upper()
                if t:
                    vrows[t] = (str(r.get("bar_data_asof") or "")[:10], str(r.get("hidden_state_label") or "UNAVAILABLE"))
        with gp.open(encoding="utf-8") as f:
            rd = csv.DictReader(f)
            has_state = "l3_forecast_state" in (rd.fieldnames or [])
            n = 0
            for r in rd:
                t = str(r.get("ticker") or "").upper()
                if t not in vrows:
                    continue
                session, state_label = vrows[t]
                if not session:
                    continue
                if has_state:
                    if not str(r.get("l3_forecast_state") or "").startswith("FORECAST_OK"):
                        continue
                    sigma, family = _f(r.get("l3_forward_realised_vol_raw")), "CURRENT_V2"
                else:
                    sigma, family = _f(r.get("l3_forward_realised_vol")), "LEGACY_PRE_17SEP"
                if sigma is None or sigma <= 0:
                    continue
                key = (family, t, session)
                if key not in seen:
                    seen[key] = (sigma, state_label, run)
                    n += 1
        runs_used.append((run, "CURRENT_V2" if has_state else "LEGACY_PRE_17SEP", n))
    return seen, runs_used


def load_closes(tickers):
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    closes = defaultdict(list)
    q = "SELECT ticker, trading_date, close FROM ohlcv_daily WHERE close IS NOT NULL AND close > 0 ORDER BY ticker, trading_date"
    for t, d, c in con.execute(q):
        if t in tickers:
            closes[t].append((d, float(c)))
    con.close()
    return closes


def realised(closes_t, session, h):
    """(RV_h, |ln(C_{d+h}/C_d)|) or None if the window is not complete in the store."""
    dates = [d for d, _ in closes_t]
    # index of the session close (exact match required: the forecast is as of that close)
    try:
        i = dates.index(session)
    except ValueError:
        return None
    if i + h >= len(closes_t):
        return None
    seg = [c for _, c in closes_t[i:i + h + 1]]
    rets = [math.log(seg[k + 1] / seg[k]) for k in range(h)]
    rv = math.sqrt(252.0 / h * sum(r * r for r in rets))
    return rv, abs(math.log(seg[-1] / seg[0]))


def summarise(rows, h, multiplier=1.0):
    ratios = sorted(r["ratio"] / multiplier for r in rows)
    if not ratios:
        return None
    cov = sum(1 for r in rows if r["abs_move"] <= r["sigma"] * multiplier * math.sqrt(h / 252.0)) / len(rows)
    qlike = [(r["rv"] ** 2) / ((r["sigma"] * multiplier) ** 2) - math.log((r["rv"] ** 2) / ((r["sigma"] * multiplier) ** 2)) - 1 for r in rows]
    return {
        "n": len(rows), "sessions": len({r["session"] for r in rows}),
        "median_realised_to_forecast": round(st.median(ratios), 4),
        "iqr": [round(st.quantiles(ratios, n=4)[0], 4), round(st.quantiles(ratios, n=4)[2], 4)] if len(ratios) > 3 else None,
        "mean_log_ratio": round(sum(math.log(x) for x in ratios) / len(ratios), 4),
        "coverage_1sigma": round(cov, 4), "qlike_variance_mean": round(sum(qlike) / len(qlike), 4),
    }


def block_bootstrap_median(rows, resamples=1000):
    by_session = defaultdict(list)
    for r in rows:
        by_session[r["session"]].append(r["ratio"])
    sessions = sorted(by_session)
    if len(sessions) < 2:
        return None
    rng = random.Random(SEED)
    meds = []
    for _ in range(resamples):
        sample = []
        for _ in sessions:
            sample.extend(by_session[rng.choice(sessions)])
        meds.append(st.median(sample))
    meds.sort()
    return [round(meds[int(0.025 * len(meds))], 4), round(meds[int(0.975 * len(meds)) - 1], 4)]


def validate(family_rows, h):
    rows = [r for r in family_rows if r["h"] == h]
    if not rows:
        return {"h": h, "state": "NO_MATURED_WINDOWS"}
    sessions = sorted({r["session"] for r in rows})
    n_train = int(math.floor(len(sessions) * TRAIN_SHARE))
    train_sessions = set(sessions[:n_train])
    purge_end = n_train + h
    test_sessions = set(sessions[purge_end:])
    train = [r for r in rows if r["session"] in train_sessions]
    test = [r for r in rows if r["session"] in test_sessions]
    out = {"h": h, "sessions_total": len(sessions), "first_session": sessions[0], "last_session": sessions[-1],
           "train_sessions": len(train_sessions), "purged_sessions": min(h, max(0, len(sessions) - n_train)),
           "test_sessions": len(test_sessions), "all": summarise(rows, h),
           "all_median_ci95_block_bootstrap_by_session": block_bootstrap_median(rows)}
    if not train or not test:
        out["state"] = "INSUFFICIENT_SESSIONS_FOR_TIME_ORDERED_TEST"
        return out
    train_med = st.median(r["ratio"] for r in train)
    m = max(0.5, min(1.5, train_med))
    test_raw, test_adj = summarise(test, h), summarise(test, h, m)
    passed = (PASS_MEDIAN[0] <= test_adj["median_realised_to_forecast"] <= PASS_MEDIAN[1]
              and PASS_COVERAGE[0] <= test_adj["coverage_1sigma"] <= PASS_COVERAGE[1])
    buckets = {}
    for label in sorted({r["hidden_state_label"] for r in train}):
        btrain = [r for r in train if r["hidden_state_label"] == label]
        btest = [r for r in test if r["hidden_state_label"] == label]
        if len(btrain) < MIN_N:
            buckets[label] = {"n_train": len(btrain), "state": "BELOW_MINIMUM_N_BACKOFF_TO_OVERALL"}
            continue
        bm = max(0.5, min(1.5, st.median(r["ratio"] for r in btrain)))
        badj = summarise(btest, h, bm) if btest else None
        buckets[label] = {"n_train": len(btrain), "n_test": len(btest), "candidate_multiplier": round(bm, 4),
                          "test_with_multiplier": badj,
                          "pass": bool(badj and PASS_MEDIAN[0] <= badj["median_realised_to_forecast"] <= PASS_MEDIAN[1]
                                       and PASS_COVERAGE[0] <= badj["coverage_1sigma"] <= PASS_COVERAGE[1])}
    out.update({"state": "TESTED", "train": summarise(train, h), "candidate_multiplier": round(m, 4),
                "test_raw": test_raw, "test_with_multiplier": test_adj, "pass_bands": {"median": PASS_MEDIAN, "coverage": PASS_COVERAGE},
                "pass": bool(passed), "buckets": buckets})
    return out


def main():
    forecasts, runs_used = load_forecasts()
    tickers = {t for (_, t, _) in forecasts}
    closes = load_closes(tickers)
    rows = []
    unmatched_session = 0
    for (family, t, session), (sigma, label, run) in forecasts.items():
        ct = closes.get(t)
        if not ct:
            continue
        for h in HORIZONS:
            r = realised(ct, session, h)
            if r is None:
                if h == 5 and session not in [d for d, _ in ct]:
                    unmatched_session += 1
                continue
            rv, move = r
            rows.append({"family": family, "ticker": t, "session": session, "h": h, "sigma": sigma, "rv": rv,
                         "ratio": rv / sigma, "abs_move": move, "hidden_state_label": label, "run": run})
    report = {"report_version": "alg10_research_v1", "state": "EXPLORATORY_NO_AUTHORITY", "generated_utc": datetime.now(timezone.utc).isoformat(),
              "price_store_last_session": max(d for c in closes.values() for d, _ in c) if closes else None,
              "forecast_rows_loaded": len(forecasts), "runs_used": runs_used,
              "forecasts_whose_session_has_no_close_in_store": unmatched_session,
              "families": {}}
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with (OUT / f"alg10_rows_{stamp}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    for family in ("LEGACY_PRE_17SEP", "CURRENT_V2"):
        fam = [r for r in rows if r["family"] == family]
        report["families"][family] = {"matured_rows": len(fam), "by_horizon": {str(h): validate(fam, h) for h in HORIZONS}}
    # continuity check between the two families on adjacent sessions (same ticker): does the 17 Sep fix change the level?
    leg = {(t, s): sig for (fam, t, s), (sig, _, _) in forecasts.items() if fam == "LEGACY_PRE_17SEP"}
    cur = {(t, s): sig for (fam, t, s), (sig, _, _) in forecasts.items() if fam == "CURRENT_V2"}
    leg_last = {}
    for (t, s), sig in leg.items():
        if t not in leg_last or s > leg_last[t][0]:
            leg_last[t] = (s, sig)
    cur_first = {}
    for (t, s), sig in cur.items():
        if t not in cur_first or s < cur_first[t][0]:
            cur_first[t] = (s, sig)
    pairs = [cur_first[t][1] / leg_last[t][1] for t in cur_first if t in leg_last and leg_last[t][1] > 0]
    report["family_continuity_current_over_legacy_adjacent_sessions"] = (
        {"n": len(pairs), "median_ratio": round(st.median(pairs), 4), "p10": round(st.quantiles(pairs, n=10)[0], 4), "p90": round(st.quantiles(pairs, n=10)[8], 4)} if len(pairs) > 10 else None)
    (OUT / f"alg10_report_{stamp}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("price_store_last_session", "forecast_rows_loaded", "forecasts_whose_session_has_no_close_in_store", "family_continuity_current_over_legacy_adjacent_sessions")}, indent=1))
    for family, fr in report["families"].items():
        print(f"\n== {family}: matured rows {fr['matured_rows']}")
        for h, v in fr["by_horizon"].items():
            if v.get("state") == "TESTED":
                print(f"  h={h}: sessions {v['sessions_total']} (train {v['train_sessions']}, purge {v['purged_sessions']}, test {v['test_sessions']}) | all median {v['all']['median_realised_to_forecast']} CI {v['all_median_ci95_block_bootstrap_by_session']} cov {v['all']['coverage_1sigma']} qlike {v['all']['qlike_variance_mean']} | m={v['candidate_multiplier']} | test raw median {v['test_raw']['median_realised_to_forecast']} cov {v['test_raw']['coverage_1sigma']} -> with m: median {v['test_with_multiplier']['median_realised_to_forecast']} cov {v['test_with_multiplier']['coverage_1sigma']} | PASS={v['pass']}")
            else:
                print(f"  h={h}: {v.get('state')} " + (f"sessions {v.get('sessions_total')} all median {v['all']['median_realised_to_forecast'] if v.get('all') else None} cov {v['all']['coverage_1sigma'] if v.get('all') else None}" if v.get('all') else ""))
    print("\nreport:", OUT / f"alg10_report_{stamp}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
