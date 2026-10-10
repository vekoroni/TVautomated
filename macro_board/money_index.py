"""The US Money Index risk-off score, measured locally (ACK 10 Oct 2026).

The ChatGPT Money Index scores risk-off transmission on nine weighted components. Seven are measurable
from data AVSHUNTER holds - oil, 10Y, credit, VIX, breadth, small caps, AI/semis - so the board scores
them itself:

- each component against its own trailing window as a percentile, oriented to risk-off (no fixed
  threshold to go stale); points = weight x how far the percentile sits between the median and the
  95th percentile;
- the published ladder's weights, so local and published compare component by component;
  geopolitics and Hormuz stay LLM-only and are labelled so;
- the score's history, point-in-time, measured against what followed for every ETF with the board's
  evidence rules, plus each ETF's beta and correlation to SPY and QQQ and its information
  coefficient against the score (ACK: the plan works per ETF with its correlation).

Display only: never a gate, score or rank for the pipeline. Settings in config["money_index"].
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from macro_board import evidence as ev


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def component_scores(raw: pd.DataFrame, components: Sequence[Mapping], cfg: Mapping) -> pd.DataFrame:
    """Points per component per session from the trailing-window percentile (today included)."""
    window, min_n = int(cfg["window_sessions"]), int(cfg["min_sessions"])
    floor, full = float(cfg["score_floor_pct"]), float(cfg["score_full_pct"])
    out = pd.DataFrame(index=raw.index)
    for c in components:
        s = raw[c["key"]] if c["key"] in raw.columns else pd.Series(np.nan, index=raw.index)
        pct = s.rolling(window, min_periods=min_n).rank(pct=True)
        pct = pct.where(s.notna())
        if c["risk_off"] == "LOW":
            n = s.rolling(window, min_periods=min_n).count()
            pct = (n - pct * n + 1) / n                   # rank from the other end: the lowest value -> 1.0
        frac = ((pct - floor) / (full - floor)).clip(lower=0.0, upper=1.0)
        out[c["key"]] = frac * float(c["weight"])
    return out


def total_score(scores: pd.DataFrame, components: Sequence[Mapping]) -> pd.Series:
    """0-100 over the measured weights; a session with any component missing has no total."""
    weight = sum(float(c["weight"]) for c in components)
    keys = [c["key"] for c in components]
    total = scores[keys].sum(axis=1, min_count=len(keys)) / weight * 100.0
    return total.where(scores[keys].notna().all(axis=1))


def band(score, bands: Mapping) -> str:
    score = _num(score)
    if score is None:
        return "MISSING"
    if score < float(bands["calm_below"]):
        return "CALM"
    return "RISK_OFF" if score >= float(bands["risk_off_from"]) else "TRANSITION"


def current_reading(raw: pd.DataFrame, scores: pd.DataFrame, components: Sequence[Mapping], cfg: Mapping) -> dict:
    window, min_n = int(cfg["window_sessions"]), int(cfg["min_sessions"])
    rows, missing = [], []
    for c in components:
        s = raw[c["key"]] if c["key"] in raw.columns else pd.Series(np.nan, index=raw.index)
        value = _num(s.iloc[-1]) if len(s) else None
        pct = None
        if value is not None:
            tail = s.iloc[-window:].dropna()
            if len(tail) >= min_n:
                pct = float((tail <= value).mean()) if c["risk_off"] == "HIGH" else float((tail >= value).mean())
        points = _num(scores[c["key"]].iloc[-1]) if c["key"] in scores.columns and len(scores) else None
        if value is None or points is None:
            missing.append(c["key"])
        rows.append({"key": c["key"], "label": c["label"], "unit": c.get("unit"), "risk_off": c["risk_off"],
                     "weight": float(c["weight"]), "value": value, "percentile": pct,
                     "points": None if points is None else round(points, 2), "published_key": c.get("published_key")})
    total = total_score(scores, components)
    score = _num(total.iloc[-1]) if len(total) else None
    return {"session": str(raw.index[-1].date()) if len(raw.index) else None,
            "score": None if score is None else round(score, 1), "band": band(score, cfg["bands"]),
            "components": rows, "missing": missing,
            "measured_weight": int(sum(float(c["weight"]) for c in components))}


def beta_corr(etf: pd.Series, bench: pd.Series, *, window: int) -> dict:
    r = np.log(pd.concat([etf, bench], axis=1).dropna()).diff().dropna().iloc[-window:]
    if len(r) < max(10, window // 2) or r.iloc[:, 1].std() == 0:
        return {"beta": None, "corr": None, "n": int(len(r))}
    cov = np.cov(r.iloc[:, 0], r.iloc[:, 1], ddof=1)
    return {"beta": round(float(cov[0, 1] / cov[1, 1]), 4), "corr": round(float(np.corrcoef(r.iloc[:, 0], r.iloc[:, 1])[0, 1]), 4),
            "n": int(len(r))}


def information_coefficient(score: pd.Series, fwd: pd.Series, *, step: int) -> dict:
    """Rank correlation of the score with the forward return, on every ``step``-th session (no overlap)."""
    both = pd.concat([score, fwd], axis=1).dropna()
    thin = both.iloc[::max(1, int(step))]
    if len(thin) < 10 or thin.iloc[:, 0].nunique() < 2 or thin.iloc[:, 1].nunique() < 2:
        return {"ic": None, "n": int(len(thin))}
    return {"ic": round(float(thin.iloc[:, 0].rank().corr(thin.iloc[:, 1].rank())), 4), "n": int(len(thin))}


def band_evidence(fwd: pd.Series, bands: pd.Series, current_band: str, horizon: int, settings: Mapping) -> dict:
    """What followed sessions in today's band, with the board's evidence rules (independent windows,
    train lean, held-out check)."""
    mask = (bands.reindex(fwd.index) == current_band)
    return ev.ticker_evidence(fwd, mask, horizon, settings)


def compare(reading: Mapping, published: Mapping | None, cfg: Mapping) -> dict:
    """Local measured points beside the published (LLM) points, component by component."""
    pub = (published or {}).get("components") or {}
    rows = []
    for r in reading["components"]:
        p = pub.get(r.get("published_key")) or {}
        rows.append({"key": r["key"], "label": r["label"], "basis": "MEASURED", "weight": r["weight"],
                     "local_points": r["points"], "published_points": _num(p.get("score")),
                     "published_weight": _num(p.get("weight")), "published_status": p.get("status")})
    llm_points = []
    for c in cfg.get("published_only") or []:
        p = pub.get(c["key"]) or {}
        pts = _num(p.get("score"))
        llm_points.append(pts)
        rows.append({"key": c["key"], "label": c["label"], "basis": "LLM_ONLY", "weight": float(c["weight"]),
                     "local_points": None, "published_points": pts, "published_weight": _num(p.get("weight")),
                     "published_status": p.get("status")})
    measured = [r["points"] for r in reading["components"]]
    llm_weight = sum(float(c["weight"]) for c in cfg.get("published_only") or [])
    comparable = None
    if all(x is not None for x in measured + llm_points):
        comparable = round((sum(measured) + sum(llm_points)) / (reading["measured_weight"] + llm_weight) * 100.0, 4)
    return {"rows": rows, "published_score": _num((published or {}).get("score")),
            "local_score": reading["score"], "comparable_total": comparable,
            "note": ("Comparable total = local measured points + the published geopolitics/Hormuz points, over all nine "
                     "weights; none when any part is missing (missing is never zero).")}


def build(*, raw: pd.DataFrame, opens: pd.DataFrame, closes: pd.DataFrame, tickers: Sequence[str],
          published: Mapping | None, cfg: Mapping, evidence_settings: Mapping, spark_sessions: int) -> dict:
    components = cfg["components"]
    scores = component_scores(raw, components, cfg)
    total = total_score(scores, components)
    bands = total.map(lambda x: band(x, cfg["bands"]))
    reading = current_reading(raw, scores, components, cfg)
    horizons = [int(h) for h in cfg["horizons"]]
    fwd = {h: ev.forward_returns(opens, closes, h) for h in horizons}
    ic_h = int(cfg["ic_horizon"])
    fwd_ic = fwd.get(ic_h) if ic_h in fwd else ev.forward_returns(opens, closes, ic_h)
    window = int(cfg["corr_window_sessions"])
    per_etf = {}
    for t in tickers:
        if t not in closes.columns:
            continue
        row = {"spy": beta_corr(closes[t], closes["SPY"], window=window) if "SPY" in closes else None,
               "qqq": beta_corr(closes[t], closes["QQQ"], window=window) if "QQQ" in closes else None,
               "ic": information_coefficient(total, fwd_ic[t], step=ic_h),
               "band_evidence": {}}
        if reading["band"] != "MISSING":
            for h in horizons:
                e = band_evidence(fwd[h][t], bands, reading["band"], h, evidence_settings)
                row["band_evidence"][str(h)] = {k: e.get(k) for k in ("lean", "holdout", "history_sessions")} | {
                    "analog": e.get("analog"), "base": e.get("base"), "excess_vs_base_pct": e.get("excess_vs_base_pct")}
        per_etf[t] = row
    hist = total.iloc[-int(spark_sessions):]
    band_counts = bands[total.notna()].value_counts().to_dict()
    return {"reading": reading, "comparison": compare(reading, published, cfg),
            "history": {"sessions": [str(d.date()) for d in hist.index], "score": [None if pd.isna(x) else round(float(x), 1) for x in hist]},
            "history_sessions": int(total.notna().sum()), "band_counts": {k: int(v) for k, v in band_counts.items()},
            "per_etf": per_etf, "settings": {k: v for k, v in cfg.items() if k != "rationale"},
            "authority": "DISPLAY_ONLY: measured description of conditions; never a gate, score or rank."}
