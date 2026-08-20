"""
AVSHUNTER ML Confidence Layer
XGBoost + LSTM Post-VANGUARD Intelligence Module
"""

from .ml_confidence_engine import (
    MLConfidenceEngine,
    VanguardInput,
    MLConfidenceResult,
    BASE_CAPITAL,
    RISK_PCT_PER_TRADE,
)

from .compounding_tracker import CompoundingTracker

__all__ = [
    "MLConfidenceEngine",
    "VanguardInput",
    "MLConfidenceResult",
    "CompoundingTracker",
    "BASE_CAPITAL",
    "RISK_PCT_PER_TRADE",
]

__version__ = "1.0.0"
