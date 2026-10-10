"""Per-setup rates and calibration from the replay panels (output-trust item 10, part 10.1; C-1).

Design: Enhancements/phase7/ITEM10_CALIBRATION_AND_STATIONS_DESIGN_20261010.md. Replaces pooled, unshrunk, uncalibrated
rates as the trader's evidence (display and report first; the lane table and geometry switch is ACK's decision).

Event, stated exactly: the setup's outcome level reached before its invalidation within the planned hold. The planned
hold is the setup's own q80 time to the outcome on the ORIGINAL panel (the governed runway); the held-out panel is
scored against that same hold, never re-fitted. Censored, invalidated or later = not reached.
Rates per setup (timeframe x state x type x side): n, hits, Wilson interval, both panels; beta-binomial shrinkage
toward the parent (timeframe x state x side) with a method-of-moments prior strength.
Calibration: the shrunk original-panel rate predicts; the held-out panel is reality. Slope and intercept from a
binomial logistic fit of held-out outcomes on logit(prediction) (perfect = 1 and 0), ECE (n-weighted) and Brier.
"""
from __future__ import annotations

import math
from collections import defaultdict
from statistics import NormalDist
from typing import Any, Dict, Iterable, List, Mapping, Tuple

EVENT_TEXT = ("outcome level before invalidation within the planned hold (the setup's q80 time on the original panel); "
              "censored, invalidated or later = not reached")
_STATE = {"OUTCOME": "ACTIVATED", "OUTCOME_FROM_DETECTION": "DETECTED"}


def event_within_hold(record: Mapping[str, Any], *, hold_bars: float) -> bool:
    return record.get("cause") == "EVENT" and float(record.get("time_bars") or 0) <= hold_bars


def wilson(hits: int, n: int, confidence: float = 0.95) -> Tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    z = NormalDist().inv_cdf(0.5 + confidence / 2)
    p = hits / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (round(centre - half, 4), round(centre + half, 4))


def shrink_to_parent(*, hits: int, n: int, parent_rate: float, prior_strength: float) -> float:
    return (hits + prior_strength * parent_rate) / (n + prior_strength)


def _q80(values: List[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return float(ordered[min(len(ordered) - 1, int(math.ceil(0.8 * len(ordered))) - 1)])


def _key(r: Mapping[str, Any]) -> Tuple[str, str, str, str] | None:
    state = _STATE.get(str(r.get("test")))
    if not state:
        return None
    return (str(r.get("timeframe")), state, str(r.get("signal_type")), str(r.get("direction")))


def _prior_strength(rates: List[Tuple[float, int]], mean: float) -> float:
    """Method of moments: between-setup variance net of binomial noise -> beta prior strength (clamped)."""
    if len(rates) < 2 or not 0 < mean < 1:
        return 50.0
    total = sum(n for _, n in rates)
    observed = sum(n * (r - mean) ** 2 for r, n in rates) / total
    noise = sum(mean * (1 - mean) for _, n in rates) / len(rates) / (total / len(rates))
    between = max(observed - noise, 1e-6)
    return float(min(500.0, max(2.0, mean * (1 - mean) / between - 1)))


def build_setup_rates(original: Iterable[Mapping[str, Any]], holdout: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    panels = {"original": defaultdict(list), "holdout": defaultdict(list)}
    for name, records in (("original", original), ("holdout", holdout)):
        for r in records:
            k = _key(r)
            if k:
                panels[name][k].append(r)
    setups: List[Dict[str, Any]] = []
    for k, recs in panels["original"].items():
        hold = _q80([float(r.get("time_bars") or 0) for r in recs if r.get("cause") == "EVENT"])
        row: Dict[str, Any] = {"timeframe": k[0], "state": k[1], "signal_type": k[2], "direction": k[3], "hold_bars": hold}
        for name in ("original", "holdout"):
            group = panels[name].get(k, [])
            hits = sum(event_within_hold(r, hold_bars=hold) for r in group)
            row.update({f"n_{name}": len(group), f"hits_{name}": hits,
                        f"rate_{name}": round(hits / len(group), 4) if group else None,
                        f"ci_{name}": wilson(hits, len(group)) if group else None,
                        f"tickers_{name}": len({r.get("ticker") for r in group})})
        setups.append(row)
    parents: Dict[str, Dict[str, Any]] = {}
    by_parent: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for s in setups:
        by_parent[f"{s['timeframe']}|{s['state']}|{s['direction']}"].append(s)
    for pkey, members in by_parent.items():
        n = sum(m["n_original"] for m in members)
        hits = sum(m["hits_original"] for m in members)
        rate = hits / n if n else 0.0
        strength = _prior_strength([(m["rate_original"] or 0.0, m["n_original"]) for m in members if m["n_original"]], rate)
        parents[pkey] = {"rate": round(rate, 4), "n": n, "prior_strength": round(strength, 2), "setups": len(members)}
        for m in members:
            m["rate_shrunk"] = round(shrink_to_parent(hits=m["hits_original"], n=m["n_original"], parent_rate=rate,
                                                      prior_strength=strength), 4)
    groups = [{"predicted": s["rate_shrunk"], "n": s["n_holdout"], "hits": s["hits_holdout"]}
              for s in setups if s["n_holdout"]]
    return {"event": EVENT_TEXT, "setups": sorted(setups, key=lambda s: (s["timeframe"], s["state"], s["signal_type"],
                                                                            s["direction"])),
            "parents": parents, "calibration": calibration_summary(groups)}


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def calibration_summary(groups: List[Mapping[str, Any]]) -> Dict[str, Any]:
    """Binomial logistic fit hits/n ~ a + b * logit(predicted) by IRLS; ECE (n-weighted) and Brier."""
    data = [(float(g["predicted"]), int(g["n"]), int(g["hits"])) for g in groups if int(g["n"]) > 0]
    total = sum(n for _, n, _ in data)
    if total == 0:
        return {"slope": None, "intercept": None, "ece": None, "brier": None, "n": 0, "groups": 0}
    a, b = 0.0, 1.0
    for _ in range(50):
        g0 = g1 = h00 = h01 = h11 = 0.0
        for p, n, k in data:
            x = _logit(p)
            mu = 1 / (1 + math.exp(-(a + b * x)))
            w = n * mu * (1 - mu)
            r = k - n * mu
            g0, g1 = g0 + r, g1 + r * x
            h00, h01, h11 = h00 + w, h01 + w * x, h11 + w * x * x
        det = h00 * h11 - h01 * h01
        if abs(det) < 1e-12:
            break
        da, db = (h11 * g0 - h01 * g1) / det, (h00 * g1 - h01 * g0) / det
        a, b = a + da, b + db
        if abs(da) < 1e-9 and abs(db) < 1e-9:
            break
    ece = sum(n * abs(k / n - p) for p, n, k in data) / total
    brier = sum(k * (1 - p) ** 2 + (n - k) * p ** 2 for p, n, k in data) / total
    return {"slope": round(b, 4), "intercept": round(a, 4), "ece": round(ece, 4), "brier": round(brier, 4),
            "n": total, "groups": len(data)}
