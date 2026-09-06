"""Per-contract rejection taxonomy for long-option selection.

AVS-FIX-001 W3.3 (THS-001 §3.1, RCA-003 §2).

`select_best_contract` filters a chain down through DTE, delta, quote-validity
and spread gates, returning `None` the moment a stage empties. That answers
"was a contract selected?" and nothing else. RCA-003 had to reconstruct the
funnel from stored chains to establish that the median blocked ticker had
*exactly one* contract inside its delta band — selection was not choosing
badly, it was being handed a single candidate. Nothing in the artefact said so.

This module classifies every contract in the chain against the same gates and
returns the whole funnel, so the next investigation reads it off the row.

It is INSTRUMENTATION. It selects nothing, changes no gate, and grants no
permission — `classify_chain` is a pure function of a chain and its bands.

The reason codes live here rather than inline in the selector so the Options
row, the repair search and any future ranker name the same failure the same
way.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

#: Reason codes. The first four extend the existing contract-rejection
#: vocabulary (CHAIN_FETCH_FAILED, NO_OPTIONS_CHAIN_DATA) rather than replacing
#: it; REJECT_NO_CHAIN is the per-ticker form of the latter.
REJECT_NO_CHAIN = "REJECT_NO_CHAIN"
REJECT_WRONG_SIDE = "REJECT_WRONG_SIDE"
REJECT_DTE_BAND = "REJECT_DTE_BAND"
REJECT_DELTA_BAND = "REJECT_DELTA_BAND"
REJECT_STALE_QUOTE = "REJECT_STALE_QUOTE"
REJECT_SPREAD = "REJECT_SPREAD"
ACCEPTED = "ACCEPTED"

#: The gate order. A contract is attributed to the FIRST gate it fails, so the
#: counts form a funnel that sums to the chain size and never double-counts.
GATE_ORDER: tuple[str, ...] = (
    REJECT_WRONG_SIDE,
    REJECT_DTE_BAND,
    REJECT_DELTA_BAND,
    REJECT_STALE_QUOTE,
    REJECT_SPREAD,
)

TAXONOMY_VERSION = "contract-rejection-taxonomy-v1"


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        result = float(value)
        return None if math.isnan(result) or math.isinf(result) else result
    except (TypeError, ValueError):
        return None


def _side_of(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text.startswith("C"):
        return "CALL"
    if text.startswith("P"):
        return "PUT"
    return ""


def _quote_is_stale(row: Mapping[str, Any]) -> bool:
    """A quote that cannot be executed against or priced from.

    Mirrors the selector's own invalid-quote rule: an INVALID quality label, a
    crossed or negative quote flag, a negative side, a crossed book, or no
    positive mark to compute economics from.
    """
    quality = str(row.get("quote_quality") or "INCOMPLETE").upper()
    if quality == "INVALID":
        return True
    flags = row.get("quality_flags") or ()
    if isinstance(flags, str):
        flags = [part.strip() for part in flags.replace(";", ",").split(",")]
    if {"CROSSED_QUOTE", "NEGATIVE_QUOTE"} & {str(f).upper() for f in flags}:
        return True
    bid = _number(row.get("bid"))
    ask = _number(row.get("ask"))
    if bid is not None and bid < 0:
        return True
    if ask is not None and ask < 0:
        return True
    if bid is not None and ask is not None and bid > ask:
        return True
    mark = _number(row.get("mark"))
    if mark is None:
        mark = _number(row.get("mid"))
    return not (mark and mark > 0)


def classify_contract(
    row: Mapping[str, Any],
    *,
    direction: str,
    dte_min: float,
    dte_max: float,
    delta_min: float,
    delta_max: float,
    spread_limit: float,
) -> dict[str, Any]:
    """Classify one contract. Returns its evidence plus the first gate it fails."""

    dte = _number(row.get("dte"))
    delta = _number(row.get("delta"))
    spread = _number(row.get("spread_pct"))
    mid = _number(row.get("mid"))
    if mid is None:
        mid = _number(row.get("mark"))

    if _side_of(row.get("right")) != str(direction or "").upper():
        gate = REJECT_WRONG_SIDE
    elif dte is None or not (dte_min <= dte <= dte_max):
        gate = REJECT_DTE_BAND
    elif delta is None or not (delta_min <= abs(delta) <= delta_max):
        gate = REJECT_DELTA_BAND
    elif _quote_is_stale(row):
        gate = REJECT_STALE_QUOTE
    elif spread is None or spread > spread_limit:
        gate = REJECT_SPREAD
    else:
        gate = ACCEPTED

    return {
        "symbol": str(row.get("symbol") or ""),
        "dte": dte,
        "delta": delta,
        "spread_pct": spread,
        "mid": mid,
        "gate_failed": None if gate == ACCEPTED else gate,
    }


def classify_chain(
    chain: Iterable[Mapping[str, Any]],
    *,
    direction: str,
    dte_min: float,
    dte_max: float,
    delta_min: float,
    delta_max: float,
    spread_limit: float,
    max_recorded: int = 400,
) -> dict[str, Any]:
    """Classify a whole chain and summarise the funnel.

    `primary_rejection_reason` is the gate at which the funnel first reached
    zero — the binding constraint, the thing that would have to change for this
    ticker to produce a contract. `secondary_rejection_reason` is the gate that
    eliminated the most contracts other than the primary: the next thing to
    look at, and often not the same gate.

    `best_alternative_*` names the contract that came closest — the one that
    cleared DTE, delta and quote validity and failed only on spread, with the
    tightest spread of those. That is the row an operator wants to see beside
    `EQUITY_VALID_OPTIONS_NOT_MONETISABLE`.

    Non-directional rows are not classified: an OTHER-direction row stands down
    and never selects a contract (RG-07). It returns `REJECT_NO_CHAIN`-free,
    zero-count evidence with the reason named.
    """

    rows = list(chain)
    direction = str(direction or "").upper()

    empty = {
        "contracts_tested": [],
        "contracts_tested_count": 0,
        "contracts_side_correct_count": 0,
        "gate_counts": {gate: 0 for gate in (*GATE_ORDER, ACCEPTED)},
        "funnel": {},
        "primary_rejection_reason": "",
        "secondary_rejection_reason": "",
        "best_alternative_symbol": "",
        "best_alternative_spread_pct": None,
        "repair_attempted": False,
        "repair_result": "",
        "taxonomy_version": TAXONOMY_VERSION,
    }

    if direction not in ("CALL", "PUT"):
        # RG-07: OTHER rows stand down. Recorded, never "rejected".
        return {**empty, "primary_rejection_reason": "NOT_APPLICABLE_NON_DIRECTIONAL"}
    if not rows:
        return {**empty, "primary_rejection_reason": REJECT_NO_CHAIN}

    classified = [
        classify_contract(
            row, direction=direction, dte_min=dte_min, dte_max=dte_max,
            delta_min=delta_min, delta_max=delta_max, spread_limit=spread_limit,
        )
        for row in rows
    ]

    counts = {gate: 0 for gate in (*GATE_ORDER, ACCEPTED)}
    for entry in classified:
        counts[entry["gate_failed"] or ACCEPTED] += 1

    side_correct = len(classified) - counts[REJECT_WRONG_SIDE]

    # Survivors after each gate, in order. The funnel a reader wants.
    funnel = {
        "chain_rows": len(classified),
        "side_correct": side_correct,
        "in_dte_band": side_correct - counts[REJECT_DTE_BAND],
        "in_delta_band": side_correct - counts[REJECT_DTE_BAND] - counts[REJECT_DELTA_BAND],
        "quote_usable": (
            side_correct - counts[REJECT_DTE_BAND] - counts[REJECT_DELTA_BAND]
            - counts[REJECT_STALE_QUOTE]
        ),
        "passing_spread": counts[ACCEPTED],
    }

    stages: Sequence[tuple[str, str]] = (
        ("side_correct", REJECT_WRONG_SIDE),
        ("in_dte_band", REJECT_DTE_BAND),
        ("in_delta_band", REJECT_DELTA_BAND),
        ("quote_usable", REJECT_STALE_QUOTE),
        ("passing_spread", REJECT_SPREAD),
    )
    primary = ""
    for key, gate in stages:
        if funnel[key] == 0:
            primary = gate
            break

    eliminated = {gate: counts[gate] for gate in GATE_ORDER if gate != primary}
    secondary = ""
    if eliminated:
        candidate = max(eliminated, key=lambda gate: eliminated[gate])
        if eliminated[candidate] > 0:
            secondary = candidate

    # The near miss: cleared everything but spread, tightest spread first.
    near_misses = [
        entry for entry in classified
        if entry["gate_failed"] == REJECT_SPREAD and entry["spread_pct"] is not None
    ]
    near_misses.sort(key=lambda entry: entry["spread_pct"])
    best_alternative = near_misses[0] if near_misses else None

    # Only side-correct contracts are worth recording; a chain is mostly the
    # other side and recording it would bury the evidence in noise.
    recorded = [entry for entry in classified if entry["gate_failed"] != REJECT_WRONG_SIDE]
    truncated = len(recorded) > max_recorded

    return {
        "contracts_tested": recorded[:max_recorded],
        "contracts_tested_count": len(recorded),
        "contracts_tested_truncated": truncated,
        "contracts_side_correct_count": side_correct,
        "gate_counts": counts,
        "funnel": funnel,
        "primary_rejection_reason": primary,
        "secondary_rejection_reason": secondary,
        "best_alternative_symbol": (best_alternative or {}).get("symbol", ""),
        "best_alternative_spread_pct": (best_alternative or {}).get("spread_pct"),
        "best_alternative_dte": (best_alternative or {}).get("dte"),
        "best_alternative_delta": (best_alternative or {}).get("delta"),
        "repair_attempted": False,
        "repair_result": "",
        "taxonomy_version": TAXONOMY_VERSION,
    }
