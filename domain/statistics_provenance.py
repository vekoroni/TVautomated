"""Statistics say what they are (invented-values inventory family B; ACK 3 Oct 2026).

One owner for how outcome statistics are labelled: a statistic carries its match method, and anything not measured
is NOT_ESTIMABLE - never a default number and never a bare "ACTUARIAL".
"""
from __future__ import annotations

import math
from typing import Any, Mapping

NOT_ESTIMABLE = "NOT_ESTIMABLE"
_WIN_RATE_FIELDS = ("win_rate_5d", "win_rate_10d", "win_rate_20d", "layer2__win_rate_10d")
_METHOD_FIELDS = ("layer2__state_match_method", "actuarial_match_method", "actuarial_match_type", "state_match_method")


def _positive(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def match_method(row: Mapping[str, Any]) -> str:
    for field in _METHOD_FIELDS:
        text = str(row.get(field) or "").strip().upper()
        if text and text not in {"NAN", "NONE", "UNKNOWN"}:
            return text
    return "METHOD_UNKNOWN"


def win_rate_source_label(row: Mapping[str, Any]) -> str:
    """ACTUARIAL_<METHOD> when measured actuarial win rates exist; otherwise NOT_ESTIMABLE (B2)."""
    measured = any(_positive(row.get(field)) for field in _WIN_RATE_FIELDS) or (
        _positive(row.get("win_prob_predicted")) and _positive(row.get("actuarial_sample_size")))
    if measured:
        return f"ACTUARIAL_{match_method(row)}"
    return NOT_ESTIMABLE
