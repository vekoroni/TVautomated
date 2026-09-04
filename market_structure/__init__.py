"""Deterministic, advisory-only Market Structure Evidence service."""

from .params import MSParams, MS_PARAMS_V1
from .profile import MarketProfile, build_market_profile, detect_double_distribution
from .service import calculate_market_structure_evidence

__all__ = ["MSParams", "MS_PARAMS_V1", "MarketProfile", "build_market_profile", "detect_double_distribution", "calculate_market_structure_evidence"]
