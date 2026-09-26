"""Canonical volatility-budget arithmetic for AVS-FIX-002 Stage 2.

All horizons are XNYS trading sessions.  The result is a fraction (0.10 is
10%), never a display percentage, and carries the forecast validation truth.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

VOLATILITY_BUDGET_VERSION = "vol_budget_v2"
CANONICAL_VOL_BUDGET_FIELDS = (
    "volatility_budget_version", "expected_move_5d_fraction",
    "expected_move_10d_fraction", "expected_move_20d_fraction",
    "horizon_convention", "forecast_horizon_basis", "vol_validation_state",
    "bias_multiplier", "bias_multiplier_applied", "validation_report_id",
    "held_out_validation_passed",
)


def cumulative_expected_move_pct(row: Mapping[str, Any], horizon: str) -> float | None:
    """Hold-window one-sigma stock move in percent, never a band increment.

    Canonical budgets are fractions; legacy Layer 3 fields are incremental
    display percentages for 1-5, 6-10, and 11-20 sessions respectively.
    Missing or invalid components cannot be replaced by a shorter horizon.
    """
    selected = {
        "1_5D": ("expected_move_5d_fraction", 1),
        "6_10D": ("expected_move_10d_fraction", 2),
        "11_20D": ("expected_move_20d_fraction", 3),
    }.get(str(horizon or "").strip().upper())
    if selected is None:
        return None
    canonical_field, count = selected
    convention = str(row.get("horizon_convention") or "").strip().upper()
    if convention and convention != "CUMULATIVE_1SIGMA":
        return None

    def positive(value: Any) -> float | None:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        return result if math.isfinite(result) and result > 0 else None

    raw = row.get(canonical_field)
    if raw is not None and str(raw).strip() != "":
        fraction = positive(raw)
        return fraction * 100.0 if fraction is not None and fraction <= 3.0 else None
    fields = (
        "l3_expected_move_1_5d",
        "l3_expected_move_6_10d",
        "l3_expected_move_11_20d",
    )[:count]
    increments = []
    for name in fields:
        raw = row.get("garch_expected_move_" + name.removeprefix("l3_expected_move_"))
        if raw is None or str(raw).strip() == "":
            raw = row.get(name)
        value = positive(raw)
        if value is None:
            return None
        increments.append(value)
    return sum(increments)


@dataclass(frozen=True, slots=True)
class VolatilityBudget:
    annual_vol_fraction: float | None
    hold_sessions: int
    expected_move_fraction: float | None
    validation_state: str
    bias_multiplier: float = 1.0
    bias_multiplier_applied: bool = False
    validation_report_id: str | None = None
    held_out_validation_passed: bool = False
    quality_state: str = "PASS"
    horizon_convention: str = "CUMULATIVE_1SIGMA"
    forecast_horizon_basis: str = "SCALED_CURRENT_ANNUAL_FORECAST"
    calculation_version: str = VOLATILITY_BUDGET_VERSION

    def to_dict(self) -> dict:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def calculate_volatility_budget(
    annual_vol_fraction: float | None,
    hold_sessions: int,
    *,
    bias_multiplier: float = 1.0,
    validation_state: str = "UNVALIDATED",
    multiplier_approved: bool = False,
    validation_report_id: str | None = None,
    held_out_validation_passed: bool = False,
) -> VolatilityBudget:
    hold = int(hold_sessions)
    if hold != hold_sessions or not 1 <= hold <= 20:
        raise ValueError("hold_sessions must be an integer between 1 and 20")
    if annual_vol_fraction is None:
        return VolatilityBudget(None, hold, None, validation_state, quality_state="NOT_EVALUATED_DATA_MISSING")
    vol = float(annual_vol_fraction)
    if not math.isfinite(vol) or vol <= 0 or vol > 3.0:
        return VolatilityBudget(vol, hold, None, validation_state, quality_state="DATA_DEFECT")
    multiplier = float(bias_multiplier)
    if not math.isfinite(multiplier) or multiplier <= 0:
        raise ValueError("bias_multiplier must be finite and positive")
    report_id = str(validation_report_id or "").strip() or None
    applied = bool(
        multiplier_approved
        and validation_state == "VALIDATED"
        and held_out_validation_passed
        and report_id
    )
    effective = multiplier if applied else 1.0
    move = vol * effective * math.sqrt(hold / 252.0)
    return VolatilityBudget(
        vol, hold, move, validation_state, effective, applied,
        report_id, bool(held_out_validation_passed),
    )


def checkpoint_fields(annual_vol_fraction: float | None) -> dict:
    budgets = {h: calculate_volatility_budget(annual_vol_fraction, h) for h in (5, 10, 20)}
    return {
        "volatility_budget_version": VOLATILITY_BUDGET_VERSION,
        "expected_move_5d_fraction": budgets[5].expected_move_fraction,
        "expected_move_10d_fraction": budgets[10].expected_move_fraction,
        "expected_move_20d_fraction": budgets[20].expected_move_fraction,
        "horizon_convention": "CUMULATIVE_1SIGMA",
        "forecast_horizon_basis": "SCALED_CURRENT_ANNUAL_FORECAST",
        "vol_validation_state": "UNVALIDATED",
        "bias_multiplier": 1.0,
        "bias_multiplier_applied": False,
        "validation_report_id": None,
        "held_out_validation_passed": False,
    }
