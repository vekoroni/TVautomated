"""Canonical quote and spread units; legacy values are never guessed."""
from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Any, Mapping

QUOTE_UNITS_VERSION = "quote_units_v1"

def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None

@dataclass(frozen=True, slots=True)
class SpreadObservation:
    spread_fraction_mid: float | None
    spread_pct_of_mid: float | None
    quality_state: str
    source: str
    calculation_version: str = QUOTE_UNITS_VERSION

    def to_dict(self) -> dict:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

def resolve_spread(row: Mapping[str, Any]) -> SpreadObservation:
    bid, ask = _number(row.get("bid")), _number(row.get("ask"))
    if bid is not None and ask is not None:
        if bid < 0 or ask < 0 or bid >= ask:
            return SpreadObservation(None, None, "DATA_DEFECT", "BID_ASK")
        midpoint = (bid + ask) / 2.0
        fraction = (ask - bid) / midpoint
        return SpreadObservation(fraction, fraction * 100.0, "PASS", "BID_ASK")
    explicit = _number(row.get("spread_fraction_mid"))
    if explicit is not None:
        if not 0 <= explicit <= 2:
            return SpreadObservation(None, None, "DATA_DEFECT", "SPREAD_FRACTION_MID")
        return SpreadObservation(explicit, explicit * 100.0, "PASS", "SPREAD_FRACTION_MID")
    display = _number(row.get("spread_pct_of_mid"))
    if display is not None:
        if not 0 <= display <= 200:
            return SpreadObservation(None, None, "DATA_DEFECT", "SPREAD_PCT_OF_MID")
        return SpreadObservation(display / 100.0, display, "PASS", "SPREAD_PCT_OF_MID")
    legacy = _number(row.get("spread_pct") if "spread_pct" in row else row.get("contract_spread_pct"))
    unit = str(row.get("spread_unit") or "").strip().upper()
    if legacy is not None and unit in {"FRACTION", "FRACTION_OF_MID"}:
        return SpreadObservation(legacy, legacy * 100.0, "PASS_LEGACY_ADAPTED", "LEGACY_FRACTION")
    if legacy is not None and unit in {"PERCENT", "PCT_OF_MID"}:
        return SpreadObservation(legacy / 100.0, legacy, "PASS_LEGACY_ADAPTED", "LEGACY_PERCENT")
    return SpreadObservation(None, None, "NOT_EVALUATED_UNIT_AMBIGUOUS" if legacy is not None else "NOT_EVALUATED_DATA_MISSING", "NONE")
