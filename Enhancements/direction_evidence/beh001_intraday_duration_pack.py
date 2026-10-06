"""BEH-001 step 4b (ACK 5 Oct 2026): intraday duration evidence in the daily evidence format.

Rules fixed before results are read:
- Input: records.jsonl from beh001_intraday_evidence.py (one line per scored test).
- Evidence: ORIGINAL panel only, grouped by timeframe x signal type x direction x test x age bucket (and pooled over
  age), with the daily estimator: C12 Aalen-Johansen cumulative incidence (censoring never success or failure), the
  same q50/q80 rule and the same minimum sample (policy duration.min_n). Groups below it are INSUFFICIENT_SAMPLE.
- Scope: the intraday records do not carry the setup's scope, so each group is pooled over scope and published under
  both LOCAL and CAMPAIGN with scope_basis POOLED_OVER_SCOPE - stated, never presented as scope-specific.
- Calibration: HOLDOUT panel events, share at or before the original group's q50 / q80; pass bands as daily
  (q50 share in [0.40, 0.60], q80 share in [0.70, 0.90]), per timeframe.
- Output: a proposal file; it changes no configuration. Display and measurement only; never a gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from avshunter.c12_outcome.estimators import _curves  # noqa: E402
from beh001_intraday_evidence import WINDOW  # noqa: E402
from domain.structure_behaviour.policy import load_policy  # noqa: E402

CAUSE = {"EVENT": 0, "INVALIDATION": 1, "CENSORED": 2}
HORIZONS = {"60m": (7, 14, 33), "15m": (13, 26, 52), "5m": (12, 39, 78)}


def age_bucket(age, edges) -> str:
    age = int(age or 0)
    label = f"{edges[-1]}+"
    for lo, hi in zip(edges, edges[1:]):
        if lo <= age < hi:
            label = f"{lo}-{hi - 1}"
            break
    return label


def summarise(counts: np.ndarray, tf: str, min_n: int) -> dict:
    n = int(counts.sum())
    out = {"n": n, "censored": int(counts[2].sum())}
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


def build(records: list[dict], edges: list[int], min_n: int) -> dict:
    counts: dict = defaultdict(lambda: None)
    for r in records:
        if r.get("panel") != "original" or r.get("cause") not in CAUSE:
            continue
        tf = r["timeframe"]
        base = (tf, r["signal_type"], r["direction"], r["test"])
        for age in (age_bucket(r.get("age_bars"), edges), "ALL"):
            key = base + (age,)
            if counts[key] is None:
                counts[key] = np.zeros((3, WINDOW[tf] + 1))
            counts[key][CAUSE[r["cause"]], min(max(int(r["time_bars"]), 0), WINDOW[tf])] += 1
    groups = []
    for (tf, kind, direction, test, age), c in sorted(counts.items()):
        summary = summarise(c, tf, min_n)
        for scope in ("LOCAL", "CAMPAIGN"):
            groups.append({"timeframe": tf, "scope": scope, "scope_basis": "POOLED_OVER_SCOPE", "signal_type": kind,
                           "direction": direction, "test": test, "age_bucket": age, **summary})
    return {"groups": groups}


def calibrate(records: list[dict], groups: list[dict]) -> dict:
    index = {(g["timeframe"], g["signal_type"], g["direction"], g["test"]): g for g in groups
             if g["age_bucket"] == "ALL" and g["scope"] == "LOCAL" and g.get("status") != "INSUFFICIENT_SAMPLE"}
    shares: dict = defaultdict(lambda: [0, 0, 0])
    for r in records:
        if r.get("panel") != "holdout" or r.get("cause") != "EVENT":
            continue
        g = index.get((r["timeframe"], r["signal_type"], r["direction"], r["test"]))
        if g is None or g.get("remaining_bars_q50") is None or g.get("remaining_bars_q80") is None:
            continue
        s = shares[r["timeframe"]]
        s[0] += 1
        s[1] += int(r["time_bars"]) <= g["remaining_bars_q50"]
        s[2] += int(r["time_bars"]) <= g["remaining_bars_q80"]
    out = {}
    for tf, (n, le50, le80) in shares.items():
        q50, q80 = le50 / n, le80 / n
        out[tf] = {"events": n, "share_le_q50": round(q50, 4), "share_le_q80": round(q80, 4),
                   "pass_timing": bool(0.40 <= q50 <= 0.60 and 0.70 <= q80 <= 0.90)}
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--records", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    policy = load_policy()
    edges, min_n = list(policy["duration"]["age_bucket_edges"]), int(policy["duration"]["min_n"])
    records = [json.loads(line) for line in open(a.records, encoding="utf-8")]
    records = [r for r in records if "cause" in r]
    built = build(records, edges, min_n)
    cuts = sorted({r["cut"] for r in records})
    proposal = {"version": "beh001_duration_evidence_intraday_v1_PROPOSAL", "authority_state": "DISPLAY_AND_MEASUREMENT_ONLY",
                "method": __doc__.strip(), "source_records": str(Path(a.records).as_posix()),
                "first_cut": cuts[0] if cuts else None, "last_cut": cuts[-1] if cuts else None,
                "data_end": "2026-10-02", "windows_bars": WINDOW, "age_bucket_edges": edges, "min_n": min_n,
                "groups": built["groups"], "holdout_calibration": calibrate(records, built["groups"])}
    Path(a.out).write_text(json.dumps(proposal, indent=1) + "\n", encoding="utf-8")
    published = sum(g.get("status") != "INSUFFICIENT_SAMPLE" for g in built["groups"]) // 2
    print(json.dumps({"groups": len(built["groups"]) // 2, "published": published,
                      "calibration": proposal["holdout_calibration"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
