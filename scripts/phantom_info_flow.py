"""PHANTOM information-flow mechanism."""

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


def compute_info_flow(row: Dict[str, Any]) -> Dict[str, Any]:
    """Compute transfer-entropy proxy.

    pyinform is intentionally optional. Until installed and wired to timeseries,
    this deterministic proxy scores asymmetric options participation using PCR,
    volume/OI, crowd arrival, and directional arbitration fields.
    """
    pcr_oi = _float(row, "pcr_oi", default=1.0)
    volume = _float(row, "contract_volume", "volume", default=0.0)
    oi = _float(row, "contract_oi", "open_interest", default=0.0)
    flow_ratio = volume / max(1.0, oi)
    crowd = str(row.get("crowd_arrival_state") or row.get("crowd_arrival_label") or "").upper()
    arb = str(row.get("direction_arbitration_status") or "").upper()

    pcr_score = min(25.0, abs(math.log(max(0.05, pcr_oi))) * 18.0)
    flow_score = min(35.0, flow_ratio * 100.0)
    crowd_score = 15.0 if "ARRIVING" in crowd else (8.0 if "HINT" in crowd else 0.0)
    arbitration_score = 15.0 if "ALIGNED" in arb or "RESOLVED" in arb else 0.0
    score = max(0.0, min(100.0, 30.0 + pcr_score + flow_score + crowd_score + arbitration_score))
    return {
        "info_flow_score": round(score, 2),
        "info_flow_source": "proxy_options_participation",
        "info_flow_ratio": round(flow_ratio, 4),
    }

