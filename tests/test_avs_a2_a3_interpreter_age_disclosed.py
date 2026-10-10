"""A2/A3 (ACK 7 Oct 2026, "6 = follow recommendation"): the Interpreter discloses evidence age and never blocks on it.

The Interpreter treated an option quote older than 60 s, an underlying older than 30 s or structure older than 120 s
as STALE, raised EVIDENCE_REFRESH_REQUIRED for executable-session use ("MSI BLOCKED") and rejected the assessment as
REJECTED_STALE_BUNDLE - on a 15-minute delayed feed, essentially every ticker. Standing ACK rule: quote age is
disclosed, never a gate; missing or invalid evidence is a different thing and may still stop an assessment.
Business rules:
- Aged (STALE) evidence: resolution succeeds; the age is disclosed (aged_domains, disposition AGE_DISCLOSED).
- Missing or invalid evidence: still blocks (EVIDENCE_REFRESH_REQUIRED) - it cannot be assessed.
- An assessment on aged evidence is not rejected; its findings disclose the aged domains. Missing/invalid evidence
  still rejects it, with a reason that says so.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from pipeline_interpreter.assessment_contract import build_assessment  # noqa: E402
from pipeline_interpreter.evidence_resolver import EvidenceResolutionError, resolve_interpreter_evidence  # noqa: E402
from test_msi_interpreter_handoff import TICKER, _fixture  # noqa: E402

MODEL = {"strengthening_weakening": "STRENGTHENING", "agreement_conflict": "ALIGNED", "manual_checks": [],
         "data_gaps": [], "plain_language_reason": "Evidence is strengthening; human review remains required."}


def test_aged_evidence_is_disclosed_and_never_blocks(tmp_path: Path) -> None:
    manifest, _, _ = _fixture(tmp_path, freshness="STALE")
    evidence = resolve_interpreter_evidence(TICKER, manifest_path=manifest)        # no raise
    assert evidence.refresh_required["disposition"] == "AGE_DISCLOSED"
    assert evidence.refresh_required["blocking_domains"] == []
    assert {"exact_option_quote", "underlying_quote"} <= set(evidence.refresh_required["aged_domains"])


def test_missing_evidence_still_blocks(tmp_path: Path) -> None:
    manifest, _, _ = _fixture(tmp_path, freshness="MISSING")
    with pytest.raises(EvidenceResolutionError, match="EVIDENCE_REFRESH_REQUIRED"):
        resolve_interpreter_evidence(TICKER, manifest_path=manifest)


def _assess(bundle):
    return build_assessment(bundle=bundle, model_output=MODEL, model_id="gpt-test", prompt_version="msi-1",
                            prompt_hash="a" * 64)


def test_an_assessment_on_aged_evidence_is_not_rejected(tmp_path: Path) -> None:
    _, bundle, _ = _fixture(tmp_path, freshness="STALE")
    out = _assess(bundle)
    assert out["assessment_status"] != "REJECTED_STALE_BUNDLE"
    assert any(f.startswith("EVIDENCE_AGE_DISCLOSED") for f in out["validation_findings"])


def test_an_assessment_on_missing_evidence_is_rejected_and_says_why(tmp_path: Path) -> None:
    _, bundle, _ = _fixture(tmp_path, freshness="MISSING")
    out = _assess(bundle)
    assert out["assessment_status"] == "REJECTED_STALE_BUNDLE"
    assert "BUNDLE_EVIDENCE_MISSING_OR_INVALID" in out["validation_findings"]
