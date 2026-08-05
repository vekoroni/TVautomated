"""PHANTOM IV surface and entropy mechanism."""

from __future__ import annotations

import math
from statistics import median
from typing import Any, Dict, List


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def _entropy(values: List[float]) -> float:
    clean = [v for v in values if v and v > 0 and math.isfinite(v)]
    if len(clean) < 2:
        return 0.0
    total = sum(clean)
    probs = [v / total for v in clean if total > 0]
    return -sum(p * math.log(p) for p in probs if p > 0)


def compute_iv_surface(row: Dict[str, Any], db: Any) -> Dict[str, Any]:
    ticker = str(row.get("ticker") or "").upper()
    current_iv = _float(row.get("contract_iv"), _float(row.get("atm_iv"), _float(row.get("iv"), 0.0)))
    iv_rank = _float(row.get("iv_rank"), _float(row.get("iv_percentile"), 50.0))
    if iv_rank <= 1.0:
        iv_rank *= 100.0

    hist = db.historical_iv_values(ticker) if ticker else []
    hist_med = median(hist) if hist else current_iv
    hist_entropy = _entropy(hist[-250:]) if hist else 0.0

    latest_rows = db.latest_chain_rows(ticker) if ticker else []
    surface_ivs = [float(r["iv"]) for r in latest_rows if r["iv"] is not None and float(r["iv"]) > 0]
    surface_entropy = _entropy(surface_ivs)

    kl_proxy = 0.0
    if current_iv > 0 and hist_med and hist_med > 0:
        ratio = max(0.01, current_iv / hist_med)
        kl_proxy = abs(math.log(ratio))

    compression_bonus = max(0.0, 50.0 - iv_rank) * 0.8
    anomaly_bonus = min(35.0, kl_proxy * 80.0)
    entropy_bonus = 0.0
    if surface_entropy and hist_entropy:
        entropy_bonus = min(15.0, abs(surface_entropy - hist_entropy) * 6.0)

    score = max(0.0, min(100.0, 35.0 + compression_bonus + anomaly_bonus + entropy_bonus))
    quality = "DB_SURFACE" if len(surface_ivs) >= 10 and len(hist) >= 100 else ("ROW_LEVEL" if current_iv else "MISSING")

    return {
        "iv_entropy_score": round(score, 2),
        "iv_kl_divergence": round(kl_proxy, 5),
        "iv_surface_entropy": round(surface_entropy, 5),
        "iv_hist_entropy": round(hist_entropy, 5),
        "iv_hist_median": round(hist_med or 0.0, 5),
        "iv_data_quality": quality,
    }

