"""Gap 4 (ACK, 25 Sep 2026) — correlated single-source/model outputs collapse
into one evidence family and contribute one vote, not one vote per field.
"""
from __future__ import annotations

from domain.war_corroboration import (
    EvidenceSignal, corroboration_report, corroboration_vote_count,
    group_into_evidence_families,
)


def test_signals_from_disjoint_upstream_sources_are_independent_votes():
    signals = [
        EvidenceSignal("state_transition_flag", True, ("model_a",)),
        EvidenceSignal("order_book_imbalance", 0.6, ("provider_feed_x",)),
    ]
    assert corroboration_vote_count(signals) == 2


def test_correlated_outputs_from_one_model_are_one_evidence_family():
    signals = [
        EvidenceSignal("state_transition_flag", True, ("model_a",)),
        EvidenceSignal("hidden_state_score", 0.81, ("model_a",)),
        EvidenceSignal("hidden_state_confidence", 0.9, ("model_a",)),
    ]
    families = group_into_evidence_families(signals)
    assert len(families) == 1
    assert set(families[0].member_field_names) == {
        "state_transition_flag", "hidden_state_score", "hidden_state_confidence",
    }
    assert corroboration_vote_count(signals) == 1


def test_partial_upstream_overlap_still_merges_conservatively():
    signals = [
        EvidenceSignal("a", 1, ("model_a", "provider_x")),
        EvidenceSignal("b", 2, ("provider_x",)),
        EvidenceSignal("c", 3, ("model_z",)),
    ]
    families = group_into_evidence_families(signals)
    assert len(families) == 2
    sizes = sorted(len(f.member_field_names) for f in families)
    assert sizes == [1, 2]


def test_corroboration_report_flags_single_source_conflation():
    signals = [
        EvidenceSignal("state_transition_flag", True, ("model_a",)),
        EvidenceSignal("hidden_state_score", 0.81, ("model_a",)),
    ]
    report = corroboration_report(signals)
    assert report["raw_field_count"] == 2
    assert report["independent_vote_count"] == 1
    assert report["single_source_conflation_detected"] is True


def test_corroboration_report_does_not_flag_genuinely_independent_signals():
    signals = [
        EvidenceSignal("a", 1, ("model_a",)),
        EvidenceSignal("b", 2, ("provider_feed_x",)),
    ]
    report = corroboration_report(signals)
    assert report["single_source_conflation_detected"] is False


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
