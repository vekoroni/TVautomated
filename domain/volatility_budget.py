"""Canonical volatility-budget arithmetic for AVS-FIX-002 Stage 2.

All horizons are XNYS trading sessions.  The result is a fraction (0.10 is
10%), never a display percentage, and carries the forecast validation truth.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

VOLATILITY_BUDGET_VERSION = "vol_budget_v2"


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
