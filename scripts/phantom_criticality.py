"""PHANTOM phase-transition / criticality mechanism."""

from __future__ import annotations

import math
from typing import Any, Dict


def _float(row: Dict[str, Any], *names: str, default: float = 0.0) -> float:
    for name in names:
        try:
            value = row.get(name)
            if value is None or value == "":
                continue
            out = float(value)
            if math.isfinite(out):
                return out
        except Exception:
            continue
    return default


def compute_criticality(row: Dict[str, Any]) -> Dict[str, Any]:
    phase_transition = _float(row, "phase_transition_probability", default=0.0)
    if phase_transition > 1.0:
        phase_transition /= 100.0
    instability = _float(row, "regime_instability_score", default=0.0)
    if instability > 1.0:
        instability /= 100.0
    compression = _float(row, "compression_score", "vol_compression_score", default=0.0)
    if compression > 1.0:
        compression /= 100.0
    iv_accel = str(row.get("iv_accel_detected") or "").upper() in {"1", "TRUE", "YES"}
    phase = str(row.get("phase") or row.get("phase_best") or row.get("layer2__phase_v2") or "").upper()

    phase_bonus = 0.12 if any(x in phase for x in ["PHASE_C", "PHASE C", "SPRING", "ACCUMULATION"]) else 0.0
    accel_bonus = 0.10 if iv_accel else 0.0
    criticality = max(0.0, min(1.0, 0.45 * phase_transition + 0.25 * instability + 0.20 * compression + phase_bonus + accel_bonus))
    score = criticality * 100.0
    return {
        "criticality_score": round(score, 2),
        "criticality_order_parameter": round(criticality, 4),
    }

