"""BEH-001 duration evidence (C-04, C-05, RQ-3): remaining time to activation and to outcome.

Rules fixed before results are read:
- Input: stage-A candidates (beh001_eval_candidates.py). Own-timeframe forward bars, C12
  passage rules, and research limits as in beh001_eval_v2.py.
- ACTIVATION: DETECTED candidates, trigger touched before invalidation.
  OUTCOME: ACTIVATED candidates, Outcome_Level touched before invalidation.
  OUTCOME_FROM_DETECTION (added 3 Oct 2026, anticipated-move step 4a): DETECTED candidates with an
  Outcome_Level, that level touched before invalidation, timed from detection. Many detected types
  never become ACTIVATED themselves (they hand over to successor candidates), so the time to the
  anticipated level must be measured from detection, never summed from stages that do not exist.
  Time is counted in own-timeframe bars from the candidate's as-of bar, so it is the
  REMAINING time at the candidate's current age (RQ-3).
- Groups: timeframe x scope x signal type x direction x test, by age bucket and pooled
  over age. Estimator: Aalen-Johansen cumulative incidence (C12); censoring is never success
  or failure.
- Published per group: n, censored, P(event by h) and P(invalidation by h) at the
  own-timeframe horizons; remaining-time quantiles q50/q80 = first bar at which the event
  incidence reaches 50% / 80% of its value at the research limit (censoring-corrected);
  unresolved share at the limit.
- A group with fewer than `min_n` cases is published as INSUFFICIENT_SAMPLE.
  Status of all estimates: IN_SAMPLE_REPLAY_NOT_VALIDATED. Display and measurement only;
  never a gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from avshunter.c12_outcome.estimators import _curves  # noqa: E402
from avshunter.c12_outcome.geometry import classify  # noqa: E402
from avshunter.c12_outcome.model import Bar, OutcomeState  # noqa: E402
from avshunter.c12_outcome.passage import evaluate_passage  # noqa: E402
from beh001_eval_v2 import HORIZONS, WINDOW, load_wide, own_tf_bars  # noqa: E402
from dir002_replay import select_tickers  # noqa: E402
from domain.structure_behaviour.policy import load_policy  # noqa: E402

T, S, C = 0, 1, 2


def age_bucket(age: int, edges) -> str:
    label = f"{edges[-1]}+"
    for lo, hi in zip(edges, edges[1:]):
        if lo <= age < hi:
            label = f"{lo}-{hi - 1}"
            break
    return label


def summarise(counts: np.ndarray, tf: str, min_n: int) -> dict:
    n = int(counts.sum())
    out = {"n": n, "censored": int(counts[C].sum())}
    if n < min_n:
        out["status"] = "INSUFFICIENT_SAMPLE"
        return out
    target, stop, survival = _curves(counts)
    final = float(target[-1])
    out.update({"status": "IN_SAMPLE_REPLAY_NOT_VALIDATED", "p_event_at_limit": round(final, 4),
                "p_invalidation_at_limit": round(float(stop[-1]), 4),
                "unresolved_at_limit": round(float(survival[-1]), 4)})
    for q in (0.5, 0.8):
        hit = np.nonzero(target >= q * final)[0] if final > 0 else []
        out[f"remaining_bars_q{int(q * 100)}"] = int(hit[0]) + 1 if len(hit) else None
    out["by_horizon"] = {str(h): {"p_event": round(float(target[h - 1]), 4), "p_invalidation": round(float(stop[h - 1]), 4)}
                         for h in HORIZONS[tf] if h <= WINDOW[tf]}
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--candidates", required=True)
    p.add_argument("--tickers", type=int, default=500)
    p.add_argument("--offset", type=int, default=0, help="skip the first N panel tickers (holdout panel)")
    p.add_argument("--records", default=None, help="also write one line per scored candidate (calibration)")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    policy = load_policy()
    cfg = policy["duration"]
    edges, min_n = list(cfg["age_bucket_edges"]), int(cfg["min_n"])
    rows = [json.loads(l) for l in open(a.candidates, encoding="utf-8")]
    cand = pd.DataFrame([r for r in rows if "engine_error" not in r])
    tickers, wide = load_wide(select_tickers(a.offset + a.tickers)[a.offset:])
    records = open(a.records, "w", encoding="utf-8") if a.records else None
    col = {t: i for i, t in enumerate(tickers)}
    dates = wide["close"].index
    pos = {d.strftime("%Y-%m-%d"): i for i, d in enumerate(dates)}
    counts = defaultdict(lambda: None)

    def add(key, tf, cause, time):
        if counts[key] is None:
            counts[key] = np.zeros((3, WINDOW[tf] + 1))
        counts[key][cause, min(max(time, 0), WINDOW[tf])] += 1

    for cut in sorted(cand["cut"].unique()):
        cp = pos[cut]
        for tf in WINDOW:
            sub = cand[(cand["cut"] == cut) & (cand["tf"] == tf)]
            if sub.empty:
                continue
            labels, fo, fh, fl, fc = own_tf_bars(wide, dates[cp + 1:], tf)
            n = min(len(labels), WINDOW[tf])
            sessions = [pd.Timestamp(x).date() for x in labels[:n]]
            for r in sub.itertuples(index=False):
                j = col.get(r.ticker)
                if j is None:
                    continue
                tests = []
                has_outcome = r.outcome is not None and np.isfinite(r.outcome)
                if r.state == "DETECTED":
                    tests.append(("ACTIVATION", r.trigger))
                    if has_outcome:
                        tests.append(("OUTCOME_FROM_DETECTION", r.outcome))
                elif r.state == "ACTIVATED" and has_outcome:
                    tests.append(("OUTCOME", r.outcome))
                bars = {s: Bar(s, float(fo[k, j]), float(fh[k, j]), float(fl[k, j]), float(fc[k, j]))
                        for k, s in enumerate(sessions) if np.isfinite(fh[k, j]) and np.isfinite(fl[k, j])}
                for test, target in tests:
                    geometry = classify(r.dir, r.close, r.invalidation, target, None)
                    if not geometry.scorable or geometry.target_state.value != "LEVEL":
                        continue
                    res = evaluate_passage(geometry, sessions, bars, WINDOW[tf])
                    if res.state is OutcomeState.TARGET_FIRST:
                        cause, time = T, res.resolution_session
                    elif res.state in (OutcomeState.STOP_FIRST, OutcomeState.AMBIGUOUS):
                        cause, time = S, res.resolution_session
                    else:
                        cause, time = C, res.sessions_observed
                    base = (tf, r.scope, r.type, r.dir, test)
                    if records is not None:
                        records.write(json.dumps({"ticker": r.ticker, "cut": cut, "timeframe": tf, "scope": r.scope,
                                                  "signal_type": r.type, "direction": r.dir, "test": test,
                                                  "age_bucket": age_bucket(int(r.age_bars), edges),
                                                  "cause": ["EVENT", "INVALIDATION", "CENSORED"][cause],
                                                  "time_bars": int(time)}) + chr(10))
                    add(base + ("ALL",), tf, cause, time)
                    add(base + (age_bucket(int(r.age_bars), edges),), tf, cause, time)
        print(f"cut {cut} done", flush=True)

    groups = []
    for (tf, scope, kind, direction, test, age), c in sorted(counts.items()):
        groups.append({"timeframe": tf, "scope": scope, "signal_type": kind, "direction": direction,
                       "test": test, "age_bucket": age, **summarise(c, tf, min_n)})
    source = Path(a.candidates)
    evidence = {
        "version": "beh001_duration_evidence_v3",
        "authority_state": "DISPLAY_AND_MEASUREMENT_ONLY",
        "method": __doc__.strip(),
        "source_candidates": str(source.as_posix()),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "first_cut": str(cand["cut"].min()), "last_cut": str(cand["cut"].max()),
        "data_end": str(dates[-1].date()),
        "windows_bars": WINDOW, "age_bucket_edges": edges, "min_n": min_n,
        "groups": groups,
    }
    Path(a.out).write_text(json.dumps(evidence, indent=1) + "\n", encoding="utf-8")
    print(f"groups {len(groups)}; published {sum(g['status'] != 'INSUFFICIENT_SAMPLE' for g in groups)}")


if __name__ == "__main__":
    main()
