"""Classify legacy prediction levels without defaulting anything (pure)."""

from __future__ import annotations

import math
import re
from typing import Any

from .model import ContractState, Direction, Geometry, InvalidationState, TargetState

OCC_SYMBOL = re.compile(r"^(?P<root>[A-Z.]{1,6})(?P<expiry>\d{6})(?P<side>[CP])(?P<strike>\d{8})$")
DIRECTION_WORDS = {"CALL": Direction.BULL, "BULL": Direction.BULL, "PUT": Direction.BEAR, "BEAR": Direction.BEAR}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def parse_direction(value: Any) -> Direction | None:
    return DIRECTION_WORDS.get(str(value or "").strip().upper())


def classify(direction_value: Any, reference: Any, invalidation: Any, target: Any, contract: Any) -> Geometry:
    direction = parse_direction(direction_value)
    reference_price = _number(reference)
    if reference_price is not None and reference_price <= 0:
        reference_price = None
    invalidation_price = _number(invalidation)
    target_price = _number(target)
    sign = direction.sign if direction else 0

    if invalidation_price is None:
        inv_state = InvalidationState.MISSING
    elif invalidation_price <= 0:
        inv_state = InvalidationState.NON_POSITIVE
    elif direction is None or reference_price is None or sign * (reference_price - invalidation_price) <= 0:
        inv_state = InvalidationState.WRONG_SIDE
    else:
        inv_state = InvalidationState.VALID

    if target_price is None:
        tgt_state = TargetState.NONE
    elif target_price <= 0 or direction is None or reference_price is None or sign * (target_price - reference_price) <= 0:
        tgt_state = TargetState.INVALID_LEGACY
    else:
        tgt_state = TargetState.LEVEL

    symbol = str(contract or "").strip().upper()
    if not symbol or symbol in {"NAN", "NONE"}:
        contract_state, symbol_out = ContractState.MISSING, None
    else:
        match = OCC_SYMBOL.match(symbol)
        if not match:
            contract_state = ContractState.UNPARSEABLE
        elif direction is None or match.group("side") != ("C" if direction is Direction.BULL else "P"):
            contract_state = ContractState.SIDE_MISMATCH
        else:
            contract_state = ContractState.VALID
        symbol_out = symbol

    return Geometry(
        direction=direction,
        reference_price=reference_price,
        invalidation_price=invalidation_price,
        invalidation_state=inv_state,
        target_price=target_price,
        target_state=tgt_state,
        contract_symbol=symbol_out,
        contract_state=contract_state,
        direction_text=str(direction_value or ""),
    )
