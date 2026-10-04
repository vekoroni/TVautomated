"""Gap 2 (ACK, 25 Sep 2026) — temporal truth: frozen Evening thesis, per-claim
observation/generation times and classification, additive-only later layers,
and rejection of future-to-cutoff evidence from a frozen claim.
"""
from __future__ import annotations

import pytest

from domain.war_temporal_truth import (
    EvidenceClassification, TemporalLayer, TemporalRejectionError,
    assert_intelligence_cutoff_matches_evidence, build_claim_timeline,
    make_additive_update, make_frozen_evening_claim,
)

EVENING_CUTOFF = "2026-09-24T21:00:00Z"


def test_frozen_evening_claim_observed_before_cutoff_is_accepted():
    claim = make_frozen_evening_claim(
        claim_id="bull_thesis_direction", statement="BULL CALL thesis formed",
        classification=EvidenceClassification.OBSERVED,
        source_observed_at_utc="2026-09-24T20:45:00Z",
        report_generation_time_utc="2026-09-24T21:05:00Z",
        evening_cutoff_utc=EVENING_CUTOFF,
    )
    assert claim.layer == TemporalLayer.EVENING_FROZEN.value
    assert claim.classification == "OBSERVED"


def test_future_to_cutoff_evidence_is_rejected_from_a_frozen_claim():
    with pytest.raises(TemporalRejectionError):
        make_frozen_evening_claim(
            claim_id="bull_thesis_direction", statement="BULL CALL thesis formed",
            classification=EvidenceClassification.OBSERVED,
            source_observed_at_utc="2026-09-25T06:16:49Z",  # after the Evening cutoff
            report_generation_time_utc="2026-09-25T06:20:00Z",
            evening_cutoff_utc=EVENING_CUTOFF,
        )


def test_morning_observation_is_additive_never_a_frozen_layer():
    with pytest.raises(ValueError):
        make_additive_update(
            claim_id="x", statement="x", classification=EvidenceClassification.OBSERVED,
            source_observed_at_utc="2026-09-25T06:16:49Z",
            report_generation_time_utc="2026-09-25T06:20:00Z",
            layer_cutoff_utc="2026-09-25T06:20:00Z",
            layer=TemporalLayer.EVENING_FROZEN,
        )


def test_morning_additive_claim_does_not_require_the_evening_cutoff():
    claim = make_additive_update(
        claim_id="bull_morning_quote", statement="Morning quote observed",
        classification=EvidenceClassification.OBSERVED,
        source_observed_at_utc="2026-09-25T06:16:49Z",
        report_generation_time_utc="2026-09-25T06:20:00Z",
        layer_cutoff_utc="2026-09-25T06:20:00Z",
        layer=TemporalLayer.MORNING_ADDITIVE,
    )
    assert claim.layer == TemporalLayer.MORNING_ADDITIVE.value


def test_declared_intelligence_cutoff_is_checked_against_frozen_claims_only():
    frozen = make_frozen_evening_claim(
        claim_id="a", statement="a", classification=EvidenceClassification.OBSERVED,
        source_observed_at_utc="2026-09-24T20:45:00Z",
        report_generation_time_utc="2026-09-24T21:05:00Z",
        evening_cutoff_utc=EVENING_CUTOFF,
    )
    additive = make_additive_update(
        claim_id="b", statement="b", classification=EvidenceClassification.OBSERVED,
        source_observed_at_utc="2026-09-25T06:16:49Z",
        report_generation_time_utc="2026-09-25T06:20:00Z",
        layer_cutoff_utc="2026-09-25T06:20:00Z",
    )
    # Must not raise: the additive claim is later than the Evening cutoff by
    # design, and is not checked against it.
    assert_intelligence_cutoff_matches_evidence(
        declared_cutoff_utc=EVENING_CUTOFF, claims=[frozen, additive],
    )


def test_a_report_cannot_silently_use_post_cutoff_evidence_under_the_declared_cutoff_label():
    # Bypass the per-claim guard using a later per-claim cutoff, to prove the
    # report-level cross-check still catches the mislabel.
    claim = make_frozen_evening_claim(
        claim_id="c", statement="c", classification=EvidenceClassification.OBSERVED,
        source_observed_at_utc="2026-09-25T06:16:49Z",
        report_generation_time_utc="2026-09-25T06:20:00Z",
        evening_cutoff_utc="2026-09-25T06:20:00Z",  # a looser per-claim cutoff
    )
    with pytest.raises(TemporalRejectionError):
        assert_intelligence_cutoff_matches_evidence(
            declared_cutoff_utc=EVENING_CUTOFF, claims=[claim],
        )


def test_claim_timeline_separates_frozen_from_additive():
    frozen = make_frozen_evening_claim(
        claim_id="a", statement="a", classification=EvidenceClassification.OBSERVED,
        source_observed_at_utc="2026-09-24T20:45:00Z",
        report_generation_time_utc="2026-09-24T21:05:00Z",
        evening_cutoff_utc=EVENING_CUTOFF,
    )
    additive = make_additive_update(
        claim_id="b", statement="b", classification=EvidenceClassification.DERIVED,
        source_observed_at_utc="2026-09-25T06:16:49Z",
        report_generation_time_utc="2026-09-25T06:20:00Z",
        layer_cutoff_utc="2026-09-25T06:20:00Z",
    )
    timeline = build_claim_timeline([frozen], [additive])
    assert timeline["frozen_claim_count"] == 1
    assert timeline["additive_claim_count"] == 1
    assert timeline["frozen_claims"][0]["layer"] == TemporalLayer.EVENING_FROZEN.value
    assert timeline["additive_claims"][0]["layer"] == TemporalLayer.MORNING_ADDITIVE.value


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
