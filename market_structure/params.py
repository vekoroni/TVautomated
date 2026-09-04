"""Versioned MSI calibration seeds; not empirically accepted thresholds."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MSParams:
    version: str = "ms_params_v1"
    calibration_status: str = "PROPOSED_NOT_CALIBRATED"
    bin_divisor: float = 40.0
    tpo_period_minutes: int = 30
    value_area_share: float = 0.70
    region_share: float = 0.20
    peak_percentile: float = 0.60
    valley_ratio: float = 0.50
    valley_min_bins: int = 2
    separation_atr: float = 0.30
    separation_min_bins: int = 3
    chronology_share: float = 0.40
    acceptance_minutes: int = 30
    acceptance_five_minute_closes: int = 3
    acceptance_volume_share: float = 0.10
    intact_repair: float = 0.20
    failed_repair: float = 0.60


MS_PARAMS_V1 = MSParams()
