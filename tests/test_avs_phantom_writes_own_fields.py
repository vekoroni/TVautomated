"""Phantom (ACK 7 Oct 2026, "8 = follow recommendation"): Phantom writes only its own fields.

Phantom runs in production (PHASE 7.5 inside evening_workflow) and its CSV replaces the Options Intelligence CSV
downstream. Its apply_payload overwrote options_score (when its OIS adjustment was positive) and rewrote
options_route_verdict / positive_factors on a promotion - authority without G1-G4 (CLAUDE.md rule 5). It had no
effect on run 20261006 (0 adjustments, 0 promotions) but could at any time. run_phantom_layer (and its PHANTOM_RUNNER
wrapper scripts/run_phantom.py) was defined and never called - a dead duplicate of PHASE 7.5.
Business rules:
- apply_payload adds Phantom's evidence fields and never changes options_score, options_route_verdict or
  positive_factors.
- The dead launcher and its wrapper are removed (tidy, ACK 6 Oct 2026).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from phantom_engine import apply_payload  # noqa: E402


def test_phantom_never_rewrites_the_options_score_route_or_factors():
    row = {"ticker": "AAA", "options_score": 62.0, "options_route_verdict": "OPTIONS_GO_REVIEW",
           "options_verdict": "WATCH", "positive_factors": "TREND"}
    payload = {"phantom_score": 81.0, "phantom_ois_adjustment": 6.0, "options_score_phantom_adjusted": 68.0,
               "phantom_promoted_verdict": "EXECUTE", "phantom_promotion_reason": "PHANTOM HIGH",
               "phantom_hard_veto_respected": False}
    out = apply_payload(row, payload)
    assert out["options_score"] == 62.0
    assert out["options_route_verdict"] == "OPTIONS_GO_REVIEW"
    assert out["positive_factors"] == "TREND"
    assert out["phantom_score"] == 81.0 and out["options_score_phantom_adjusted"] == 68.0
    assert out["phantom_promoted_verdict"] == "EXECUTE"
    assert out["phantom_execution_authority"] == "EVIDENCE_ONLY"


def test_the_dead_phantom_launcher_is_removed():
    src = (ROOT / "intelligent_orchestrator.py").read_text(encoding="utf-8")
    assert "def run_phantom_layer" not in src and "PHANTOM_RUNNER" not in src
    assert not (ROOT / "scripts" / "run_phantom.py").exists()
