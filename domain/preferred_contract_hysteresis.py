"""Governed hysteresis decision for preferred DOI contracts."""
from __future__ import annotations
from dataclasses import dataclass

HYSTERESIS_VERSION = "hysteresis_v1"
TERMINAL = {"EXPIRED":"EXPIRED", "MALFORMED":"MALFORMED", "DATA_DEFECT":"DEFECT"}

@dataclass(frozen=True, slots=True)
class HysteresisDecision:
    switch: bool
    threshold: float
    score_improvement: float
    reason: str
    calculation_version: str = HYSTERESIS_VERSION

def decide_preferred_contract(*, incumbent_utility: float, challenger_utility: float,
                              challenger_quality: str, incumbent_state: str = "ACTIVE",
                              margin_abs: float = .05, margin_rel: float = .10) -> HysteresisDecision:
    state = str(incumbent_state).upper()
    improvement = float(challenger_utility) - float(incumbent_utility)
    threshold = max(float(margin_abs), float(margin_rel) * abs(float(incumbent_utility)))
    if state in TERMINAL:
        return HysteresisDecision(True, threshold, improvement, TERMINAL[state])
    if str(challenger_quality).upper() not in {"PASS", "TWO_SIDED", "CONTRACT_LIMIT_PRICE_REQUIRED"}:
        return HysteresisDecision(False, threshold, improvement, "CHALLENGER_QUALITY_NOT_PASS")
    return HysteresisDecision(improvement >= threshold, threshold, improvement,
                              "MARGIN_EXCEEDED" if improvement >= threshold else "MARGIN_NOT_EXCEEDED")
