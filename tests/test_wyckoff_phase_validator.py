from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wyckoff_phase_validator import validate_wyckoff_phase


def _bars() -> pd.DataFrame:
    rows = []
    price = 100.0
    for i in range(60):
        price += 0.15 if i > 35 else -0.05
        rows.append(
            {
                "open": price * 0.995,
                "high": price * 1.01,
                "low": price * 0.99,
                "close": price,
                "volume": 1_000_000 + i * 1000,
            }
        )
    return pd.DataFrame(rows)


def test_phase_c_spring_is_confirmed_active_or_late():
    wyckoff = {
        "current_phase": "C",
        "phase_evidence_strength": 82,
        "dominant_event": "Spring",
        "event_evidence_strength": 86,
        "truth_confidence": 84,
        "transition_bias": "D",
        "transition_confidence": 78,
        "phase_progression": "towards_next",
        "stop_loss": 94.5,
        "contradictions": [],
    }
    precor = {
        "wyckoff_phase": "C",
        "wyckoff_phase_conf": 80,
        "wyckoff_mode": "ACCUMULATION",
        "primary_event": "Spring",
        "transition_to": "D",
        "transition_conf": 76,
        "move_age_bars": 2,
        "notes_all": ["Spring detected", "Reclaim within 2 bars"],
    }

    out = validate_wyckoff_phase("TEST", _bars(), wyckoff, precor)

    assert out["wyckoff_structure"] == "ACCUMULATION"
    assert out["wyckoff_phase"] == "C"
    assert out["event_sequence_valid"] is True
    assert out["phase_correctness_score"] >= 75
    assert out["phase_status"] in {"LATE_ACTIVE", "TRANSITION_IMMINENT", "PHASE_COMPLETE"}
    assert out["structural_invalidation_level"] == 94.5


def test_phase_d_without_sos_or_sow_is_uncertain():
    wyckoff = {
        "current_phase": "D",
        "phase_evidence_strength": 68,
        "dominant_event": "TR",
        "event_evidence_strength": 42,
        "truth_confidence": 58,
        "transition_bias": "E",
        "transition_confidence": 50,
        "phase_progression": "stable",
        "contradictions": ["Phase D closely contested by Phase C"],
    }
    precor = {
        "wyckoff_phase": "D",
        "wyckoff_phase_conf": 65,
        "wyckoff_mode": "ACCUMULATION",
        "primary_event": "NONE",
        "transition_to": "E",
        "transition_conf": 50,
        "move_age_bars": 9,
        "notes_all": [],
    }

    out = validate_wyckoff_phase("TEST", _bars(), wyckoff, precor)

    assert out["event_sequence_valid"] is False
    assert "SOS" in out["missing_phase_events"]
    assert out["phase_status"] == "UNCERTAIN"
    assert out["phase_correctness_score"] < 70


def test_weak_conflicted_phase_is_invalidated():
    wyckoff = {
        "current_phase": "B",
        "phase_evidence_strength": 22,
        "dominant_event": "TR",
        "event_evidence_strength": 20,
        "truth_confidence": 18,
        "transition_bias": "C",
        "transition_confidence": 20,
        "phase_progression": "ambiguous",
        "contradictions": ["low phase evidence", "weak event evidence", "control shifting"],
    }

    out = validate_wyckoff_phase("TEST", _bars(), wyckoff, None)

    assert out["phase_status"] == "INVALIDATED"
    assert out["transition_probability_10_bars"] >= 0.8


def test_mature_phase_c_reports_transition_imminent():
    wyckoff = {
        "current_phase": "C",
        "phase_evidence_strength": 88,
        "dominant_event": "Spring",
        "event_evidence_strength": 90,
        "truth_confidence": 89,
        "transition_bias": "D",
        "transition_confidence": 92,
        "phase_progression": "towards_next",
        "contradictions": [],
    }
    precor = {
        "wyckoff_phase": "C",
        "wyckoff_phase_conf": 86,
        "wyckoff_mode": "ACCUMULATION",
        "primary_event": "Spring",
        "transition_to": "D",
        "transition_conf": 92,
        "move_age_bars": 1,
        "notes_all": ["Spring detected", "Range reclaim"],
    }

    out = validate_wyckoff_phase("TEST", _bars(), wyckoff, precor)

    assert out["phase_maturity_score"] >= 76
    assert out["transition_probability_10_bars"] >= 0.60
    assert out["phase_status"] in {"TRANSITION_IMMINENT", "PHASE_COMPLETE"}
