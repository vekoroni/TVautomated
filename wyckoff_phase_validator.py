"""
Wyckoff phase validation/adjudication layer for AVSHUNTER.

This module sits above the discovery-oriented Wyckoff engines. The existing
engines are intentionally permissive so they can surface candidates early; this
validator is intentionally stricter so downstream pipeline stages can separate
"looks like Phase C" from "structurally valid, mature Phase C".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd


PHASES = ("A", "B", "C", "D", "E")
ACCUMULATION_EVENTS = {
    "A": {"SC", "AR", "ST"},
    "B": {"TR", "ST", "ABSORPTION"},
    "C": {"SPRING", "TEST"},
    "D": {"SOS", "LPS"},
    "E": {"TREND_CONTINUATION"},
}
DISTRIBUTION_EVENTS = {
    "A": {"BC", "AR", "ST"},
    "B": {"TR", "ST", "ABSORPTION"},
    "C": {"UTAD", "UT"},
    "D": {"SOW", "LPSY"},
    "E": {"TREND_CONTINUATION"},
}
EVENT_ALIASES = {
    "ABSORPTION_UP": "ABSORPTION",
    "ABSORPTION_DOWN": "ABSORPTION",
    "UPTHRUST": "UT",
    "TEST_OF_SPRING": "TEST",
}


@dataclass(frozen=True)
class ValidationInputs:
    ticker: str
    bars: Optional[pd.DataFrame]
    wyckoff_data: Dict[str, Any]
    precor_data: Optional[Dict[str, Any]] = None


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(value)))


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _norm_phase(value: Any) -> str:
    text = str(value or "").upper().strip()
    if text.startswith("PHASE_"):
        text = text.split("PHASE_", 1)[1]
    if text[:1] in PHASES:
        return text[:1]
    return "UNKNOWN"


def _norm_event(value: Any) -> str:
    text = str(value or "").upper().strip().replace(" ", "_").replace("-", "_")
    return EVENT_ALIASES.get(text, text)


def _event_set(*values: Any) -> set[str]:
    events = {_norm_event(v) for v in values if str(v or "").strip()}
    return {e for e in events if e not in {"", "NONE", "UNKNOWN"}}


def _mode(precor_data: Optional[Dict[str, Any]], wyckoff_data: Dict[str, Any]) -> str:
    text = str((precor_data or {}).get("wyckoff_mode") or wyckoff_data.get("wyckoff_mode") or "").upper()
    if "DISTRIBUTION" in text or text in {"MARKDOWN", "SELLERS"}:
        return "DISTRIBUTION"
    if "ACCUMULATION" in text or text in {"MARKUP", "BUYERS"}:
        return "ACCUMULATION"
    control = str(wyckoff_data.get("control_state") or (precor_data or {}).get("control_state") or "").upper()
    if control == "SELLERS":
        return "DISTRIBUTION"
    return "ACCUMULATION"


def _required_events(mode: str, phase: str) -> set[str]:
    table = DISTRIBUTION_EVENTS if mode == "DISTRIBUTION" else ACCUMULATION_EVENTS
    return set(table.get(phase, set()))


def _expected_prior_events(mode: str, phase: str) -> set[str]:
    if phase not in PHASES:
        return set()
    table = DISTRIBUTION_EVENTS if mode == "DISTRIBUTION" else ACCUMULATION_EVENTS
    idx = PHASES.index(phase)
    required: set[str] = set()
    for prior in PHASES[: idx + 1]:
        required.update(table.get(prior, set()))
    return required


def _phase_from_evidence(wyckoff_data: Dict[str, Any], precor_data: Optional[Dict[str, Any]]) -> tuple[str, str, float, float]:
    wy_phase = _norm_phase(wyckoff_data.get("current_phase"))
    wy_strength = _as_float(wyckoff_data.get("phase_evidence_strength"), 0.0)
    pre_phase = _norm_phase((precor_data or {}).get("wyckoff_phase"))
    pre_strength = _as_float((precor_data or {}).get("wyckoff_phase_conf"), 0.0)

    if pre_phase != "UNKNOWN" and pre_strength > wy_strength:
        primary = pre_phase
        primary_prob = pre_strength
        alt = wy_phase
        alt_prob = wy_strength
    else:
        primary = wy_phase
        primary_prob = wy_strength
        alt = pre_phase
        alt_prob = pre_strength

    if alt == "UNKNOWN" or alt == primary:
        transition_hint = _norm_phase(
            wyckoff_data.get("transition_bias") or (precor_data or {}).get("transition_to")
        )
        alt = transition_hint if transition_hint != primary else "UNKNOWN"
        alt_prob = max(
            _as_float(wyckoff_data.get("transition_confidence"), 0.0),
            _as_float((precor_data or {}).get("transition_conf"), 0.0),
        )
    return primary, alt, _clamp(primary_prob), _clamp(alt_prob)


def _completed_events(wyckoff_data: Dict[str, Any], precor_data: Optional[Dict[str, Any]]) -> set[str]:
    events = _event_set(
        wyckoff_data.get("dominant_event"),
        (precor_data or {}).get("primary_event"),
    )
    notes = " ".join(str(x) for x in (precor_data or {}).get("notes_all", [])[:8]).upper()
    if "ABSORPTION" in notes:
        events.add("ABSORPTION")
    if "RANGE" in notes or "TRADING RANGE" in notes:
        events.add("TR")
    return events


def _event_sequence_score(mode: str, phase: str, completed: set[str]) -> tuple[float, bool, list[str], list[str]]:
    required = _required_events(mode, phase)
    prior_required = _expected_prior_events(mode, phase)
    current_ok = bool(completed & required) if required else True
    missing_current = [] if current_ok else sorted(required)

    if phase in {"A", "B"}:
        seq_valid = current_ok
        score = 65.0 if seq_valid else 45.0
    else:
        prior_hits = len(prior_required & completed)
        prior_ratio = prior_hits / max(1, len(prior_required))
        seq_valid = current_ok
        score = (60.0 if current_ok else 25.0) + prior_ratio * 40.0

    completed_sorted = sorted(completed)
    return _clamp(score), seq_valid, completed_sorted, missing_current


def _duration_score(move_age_bars: Any, phase: str) -> float:
    age = _as_float(move_age_bars, -1.0)
    if age < 0:
        return 45.0
    if phase == "A":
        return _clamp(age * 14.0)
    if phase == "B":
        return _clamp(35.0 + age * 2.0)
    if phase == "C":
        return _clamp(85.0 - age * 4.0)
    if phase == "D":
        return _clamp(35.0 + age * 3.0)
    if phase == "E":
        return _clamp(55.0 + age * 1.5)
    return 40.0


def _invalidation_level(bars: Optional[pd.DataFrame], phase: str, mode: str, wyckoff_data: Dict[str, Any]) -> Optional[float]:
    stop = wyckoff_data.get("stop_loss")
    if stop is not None:
        return round(_as_float(stop), 4)
    if bars is None or bars.empty or not {"high", "low"}.issubset(set(bars.columns)):
        return None
    recent = bars.tail(40)
    if mode == "ACCUMULATION":
        return round(float(recent["low"].min()), 4)
    if mode == "DISTRIBUTION":
        return round(float(recent["high"].max()), 4)
    return None


def _status(correctness: float, maturity: float, p10: float, invalidated: bool, ambiguous: bool) -> str:
    if invalidated:
        return "INVALIDATED"
    if ambiguous or correctness < 60:
        return "UNCERTAIN"
    if maturity >= 90:
        return "PHASE_COMPLETE"
    if maturity >= 76 and p10 >= 0.60:
        return "TRANSITION_IMMINENT"
    if maturity >= 61:
        return "LATE_ACTIVE"
    if maturity >= 31:
        return "ACTIVE"
    return "EARLY_ACTIVE"


def validate_wyckoff_phase(
    ticker: str,
    bars: Optional[pd.DataFrame],
    wyckoff_data: Dict[str, Any],
    precor_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return strict validation fields for downstream AVSHUNTER consumers."""
    precor_data = precor_data or {}
    phase, alt_phase, phase_prob, alt_prob = _phase_from_evidence(wyckoff_data, precor_data)
    mode = _mode(precor_data, wyckoff_data)
    completed = _completed_events(wyckoff_data, precor_data)
    seq_score, seq_valid, completed_events, missing_events = _event_sequence_score(mode, phase, completed)

    phase_strength = _as_float(wyckoff_data.get("phase_evidence_strength"), phase_prob)
    event_strength = _as_float(wyckoff_data.get("event_evidence_strength"), 0.0)
    truth_conf = _as_float(wyckoff_data.get("truth_confidence"), phase_prob)
    transition_conf = max(
        _as_float(wyckoff_data.get("transition_confidence"), 0.0),
        _as_float(precor_data.get("transition_conf"), 0.0),
    )
    contradictions = list(wyckoff_data.get("contradictions") or [])

    price_structure_score = _clamp(phase_strength)
    volume_spread_score = _clamp(event_strength)
    acceptance_score = _clamp(transition_conf if str(wyckoff_data.get("phase_progression", "")).lower() == "towards_next" else transition_conf * 0.75)
    context_score = _clamp(truth_conf - len(contradictions) * 8.0)

    correctness = (
        seq_score * 0.30
        + price_structure_score * 0.25
        + volume_spread_score * 0.20
        + acceptance_score * 0.15
        + context_score * 0.10
    )

    required = _required_events(mode, phase)
    required_done = 1.0 if (required and completed & required) else 0.0 if required else 1.0
    duration = _duration_score(precor_data.get("move_age_bars"), phase)
    proximity = _clamp(transition_conf)
    next_phase_evidence = _clamp(transition_conf if alt_phase != "UNKNOWN" else transition_conf * 0.5)
    exhaustion_failure = _clamp(100.0 - len(contradictions) * 18.0)
    maturity = (
        required_done * 100.0 * 0.35
        + duration * 0.20
        + proximity * 0.20
        + next_phase_evidence * 0.15
        + exhaustion_failure * 0.10
    )

    transition_hint = _norm_phase(wyckoff_data.get("transition_bias") or precor_data.get("transition_to"))
    alt_is_expected_next = alt_phase != "UNKNOWN" and alt_phase == transition_hint and seq_valid
    ambiguous = (
        alt_phase != "UNKNOWN"
        and not alt_is_expected_next
        and abs(phase_prob - alt_prob) <= 10.0
    )
    invalidated = (
        truth_conf < 25.0
        or (phase_strength < 35.0 and event_strength < 35.0)
        or (len(contradictions) >= 3 and correctness < 55.0)
    )

    p10 = _clamp((maturity * 0.55 + transition_conf * 0.45) / 100.0, 0.0, 0.95)
    p5 = _clamp(p10 * 0.60, 0.0, 0.90)
    p20 = _clamp(p10 + 0.20, 0.0, 0.98)
    if invalidated:
        p5, p10, p20 = max(p5, 0.65), max(p10, 0.80), max(p20, 0.90)

    bars_remaining_low = max(1, int(round((1.0 - p10) * 10)))
    bars_remaining_high = max(bars_remaining_low + 1, int(round((1.0 - p5) * 20)))
    next_expected_event = alt_phase if alt_phase != "UNKNOWN" else str(wyckoff_data.get("transition_bias") or precor_data.get("transition_to") or "NONE")

    return {
        "wyckoff_structure": mode,
        "wyckoff_phase": phase,
        "phase_probability": round(phase_prob / 100.0, 3),
        "alternative_phase": alt_phase,
        "alternative_phase_probability": round(alt_prob / 100.0, 3),
        "phase_correctness_score": round(_clamp(correctness), 1),
        "phase_maturity_score": round(_clamp(maturity), 1),
        "phase_status": _status(correctness, maturity, p10, invalidated, ambiguous),
        "last_confirmed_event": completed_events[-1] if completed_events else "NONE",
        "event_sequence_valid": bool(seq_valid),
        "completed_phase_events": completed_events,
        "missing_phase_events": missing_events,
        "contradicting_evidence": contradictions,
        "transition_probability_5_bars": round(p5, 3),
        "transition_probability_10_bars": round(p10, 3),
        "transition_probability_20_bars": round(p20, 3),
        "expected_bars_remaining": f"{bars_remaining_low}-{bars_remaining_high}",
        "next_expected_event": next_expected_event,
        "structural_invalidation_level": _invalidation_level(bars, phase, mode, wyckoff_data),
        "timeframe_alignment": "UNASSESSED",
        "phase_churn_warning": bool(ambiguous),
    }


def prefixed_validation_fields(validation: Dict[str, Any], prefix: str = "wyckoff_validation_") -> Dict[str, Any]:
    """Return namespaced fields for wide CSV outputs without losing schema names."""
    return {f"{prefix}{key}": value for key, value in validation.items()}
