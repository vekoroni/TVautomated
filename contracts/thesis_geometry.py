"""Side-aware, missingness-preserving thesis geometry helpers."""

from __future__ import annotations

import math
from typing import Any, Optional, Tuple

from contracts.governed_states import LifecycleEvaluationState


def select_directional_invalidation(
    row: Any,
    direction: str,
    entry: Any,
) -> Tuple[Optional[float], str, str]:
    """Return the first authoritative invalidation with valid side geometry.

    The governed/validated structural levels take precedence over legacy stop
    aliases. ATR fallback values are intentionally excluded because they are a
    convention rather than thesis evidence. Missing input remains ``None``.
    """
    get = row.get if hasattr(row, "get") else lambda key, default=None: default
    try:
        entry_value = float(entry)
    except (TypeError, ValueError):
        return None, LifecycleEvaluationState.MISSING_AUTHORITATIVE_STOP.value, "MISSING_ENTRY"
    if not math.isfinite(entry_value) or entry_value <= 0 or direction not in {"CALL", "PUT"}:
        return None, LifecycleEvaluationState.MISSING_AUTHORITATIVE_STOP.value, "NOT_EVALUABLE"

    legacy_source = str(get("structural_stop_source", "") or "").upper().strip()
    governed_source = str(get("governed_invalidation_source", "") or "").strip()
    candidates = [
        ("governed_invalidation_spot", governed_source or "DISCOVERY_GOVERNED_INVALIDATION"),
        ("wyckoff_validation_structural_invalidation_level", "WYCKOFF_VALIDATION"),
    ]
    if legacy_source != "ATR_FALLBACK":
        candidates.extend(
            [
                ("structural_stop", legacy_source or "structural_stop"),
                ("stop_loss", legacy_source or "stop_loss"),
            ]
        )
    candidates.append(("invalidation_price", "INVALIDATION_PRICE"))

    saw_numeric = False
    for field, source in candidates:
        raw = get(field)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value) or value <= 0:
            continue
        saw_numeric = True
        if (direction == "CALL" and value < entry_value) or (
            direction == "PUT" and value > entry_value
        ):
            return value, source, "AVAILABLE"

    return (
        None,
        LifecycleEvaluationState.MISSING_AUTHORITATIVE_STOP.value,
        LifecycleEvaluationState.DATA_DEFECT_WRONG_SIDE.value if saw_numeric else "MISSING",
    )
