"""B7 (invented-values inventory, ACK 3 Oct 2026 "go ahead with B7"): Wyckoff heuristic scores are not probabilities.

wyckoff_phase_validator publishes phase/alternative/transition "probabilities" built from weighted heuristic scores
with fixed transforms (p5 = 0.6 x p10, p20 = p10 + 0.20, invalidated forced >= 0.80) - round constants on 1 Oct
(0.9 on 357 rows, 0.82 on 348, 1.0 on 281). Nothing gates on them (display and Interpreter evidence only).
Business rules:
- The published fields carry a basis saying they are heuristic scores, not calibrated probabilities, and that the
  expected-bars range is derived from them.
- The book carries that basis beside the values.
- The Interpreter evidence does not hand the model these numbers as probabilities.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))


def test_validator_labels_its_scores():
    from test_wyckoff_phase_validator import _bars
    from wyckoff_phase_validator import prefixed_validation_fields, validate_wyckoff_phase
    out = validate_wyckoff_phase("TEST", _bars(), {"current_phase": "D"}, None)
    assert out["probability_fields_basis"] == "HEURISTIC_SCORES_NOT_CALIBRATED_PROBABILITIES"
    assert out["expected_bars_remaining_basis"] == "DERIVED_FROM_HEURISTIC_SCORES"
    assert "wyckoff_validation_probability_fields_basis" in prefixed_validation_fields(out)


def test_book_carries_the_basis():
    from contracts.lab_control import FINAL_BOOK_FIELDS
    assert "wyckoff_validation_probability_fields_basis" in FINAL_BOOK_FIELDS


def test_interpreter_evidence_does_not_offer_them_as_probabilities():
    src = (ROOT / "pipeline_interpreter" / "pipeline_interpreter_engine.py").read_text(encoding="utf-8")
    group = src[src.index('("Wyckoff and chart state", ['):src.index('("Volatility, volume, and liquidity", [')]
    assert "transition_probability" not in group
