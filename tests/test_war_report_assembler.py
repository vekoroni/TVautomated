"""Gap 5 wiring (ACK, 25 Sep 2026) — the six evidence-gap modules compose
through one bounded assembler into a schema-v2 WarReportPayload.

IMPORTANT: this proves the modules wire together without raising and stay
advisory-only. It does NOT prove the WAR is production-ready end to end —
that requires this repository's real acceptance suite, which this test file
does not run and does not claim to satisfy.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from contracts.war_report_assembler import assemble_war_report_payload
from domain.exact_contract_quote_join import (
    ExactContractQuoteCandidate, join_exact_contract_quote,
)
from domain.war_corroboration import EvidenceSignal
from domain.war_coverage_summary import SourceCoverageEntry, SourceCoverageState
from domain.war_report_provenance import CounterCase, QaAnswer, SourceReference, render_war_report_html
from domain.war_temporal_truth import EvidenceClassification, make_frozen_evening_claim
from domain.war_transmission_chain import (
    classify_contract_link, classify_sector_link, classify_ticker_link,
)

RUN = "20260925_061649"
BULL_SYMBOL = "BULL261120C00007500"
GEN_TIME = datetime(2026, 9, 25, 13, 35, 50, tzinfo=timezone.utc)


def _real_bull_candidate() -> ExactContractQuoteCandidate:
    return ExactContractQuoteCandidate(
        source_path=(
            "data/canonical/market_observations/exact_option_quote/2026-09-25/BULL/"
            "e87aff2d2b6a28e790cdd4e5b718f25c88ec9a442401ebf873508984be9335de.json"
        ),
        source_hash="e87aff2d", run_id=RUN, ticker="BULL", occ_symbol=BULL_SYMBOL,
        provider="MARKETDATA", provider_observed_at_utc="2026-09-25T13:34:50Z",
        bid="0.61", ask="0.64", bid_size="1", ask_size="13",
        delta="0.5045", gamma="0.2229", theta="-0.0067", vega="0.0114",
        quote_quality_raw=None,
    )


def _assemble(**overrides):
    quote_join = overrides.pop("quote_join", None) or join_exact_contract_quote(
        requested_occ_symbol=BULL_SYMBOL, requested_run_id=RUN, requested_ticker="BULL",
        candidates=[_real_bull_candidate()], report_generation_time_utc=GEN_TIME,
    )
    frozen = [make_frozen_evening_claim(
        claim_id="bull_thesis_direction", statement="BULL CALL thesis formed",
        classification=EvidenceClassification.OBSERVED,
        source_observed_at_utc="2026-09-24T20:45:00Z",
        report_generation_time_utc="2026-09-24T21:05:00Z",
        evening_cutoff_utc="2026-09-24T21:00:00Z",
    )]
    sector_link = classify_sector_link(
        has_measured_flow_metric=False, sector_flow_source_reference=None,
        business_description_match_only=True,
    )
    ticker_link = classify_ticker_link(
        has_ticker_level_metric=False, ticker_source_reference=None, sector_link=sector_link,
    )
    contract_link = classify_contract_link(
        selected_contract_symbol=BULL_SYMBOL, ticker_link=ticker_link,
    )
    kwargs = dict(
        report_version="v11", run_id=RUN, ticker="BULL", thesis_id="bull_thesis_20260924",
        report_generation_time_utc="2026-09-25T13:35:50Z",
        declared_intelligence_cutoff_utc="2026-09-24T21:00:00Z",
        quote_join=quote_join, frozen_claims=frozen, additive_claims=[],
        sector_link=sector_link, ticker_link=ticker_link, contract_link=contract_link,
        corroboration_signals=[
            EvidenceSignal("state_transition_flag", True, ("model_a",)),
            EvidenceSignal("hidden_state_score", 0.8, ("model_a",)),
        ],
        coverage_source_states={
            "exact_option_quote": SourceCoverageEntry(
                "exact_option_quote", SourceCoverageState.AVAILABLE.value, "joined"),
        },
        war_synthesis="BULL CALL thesis remains structurally valid at report generation.",
        judgment={"action": "MANUAL_REVIEW", "reason": "AWAITING_HUMAN_CONFIRMATION"},
        qa_registry=[QaAnswer(4, "Did control transfer?", "interp", "bars", "dropbox/macro",
                               "obs", "interp", "counter", "MEDIUM", "rest-of-session bars", "confirmed bar")],
        sources=[SourceReference(
            "exact_option_quote", _real_bull_candidate().source_path, None,
            "e87aff2d", "2026-09-25T13:34:50Z", "OBSERVED",
        )],
        missing_inputs=["later_session_intraday_bars"],
        counter_cases=[CounterCase("sector rotation continues", "sector flow reverses")],
    )
    kwargs.update(overrides)
    return assemble_war_report_payload(**kwargs)


def test_assembler_wires_all_six_modules_into_one_payload():
    payload = _assemble()
    data = payload.to_dict()
    assert data["ticker"] == "BULL"
    assert data["selected_contract_symbol"] == BULL_SYMBOL
    assert data["authority"] == "ADVISORY_ONLY"
    assert data["judgment"]["authority"] == "ADVISORY_ONLY"
    assert data["claim_timeline"]["frozen_claim_count"] == 1
    assert "links" in data["transmission_chain"]
    assert data["coverage_summary"]["ticker"] == "BULL"
    assert data["option_economics"]["quote_quality"] == "TWO_SIDED"


def test_assembler_surfaces_single_source_conflation_as_a_contradiction():
    payload = _assemble()
    data = payload.to_dict()
    assert any("collapse to a single upstream source family" in c for c in data["contradictions"])


def test_assembler_surfaces_inferred_sector_link_as_a_coverage_gap_or_chain_flag():
    payload = _assemble()
    data = payload.to_dict()
    assert data["transmission_chain"]["weakest_link_state"] != "MEASURED"


def test_assembled_payload_renders_end_to_end_with_zero_provider_calls():
    payload = _assemble()
    html = render_war_report_html(payload)
    assert "BULL" in html
    assert "ADVISORY_ONLY" in html


def test_assembler_rejects_future_to_cutoff_evidence_rather_than_silently_dropping_it():
    from domain.war_temporal_truth import TemporalRejectionError

    with pytest.raises(TemporalRejectionError):
        _assemble(frozen_claims=[
            make_frozen_evening_claim(
                claim_id="bad", statement="bad", classification=EvidenceClassification.OBSERVED,
                source_observed_at_utc="2026-09-25T06:16:49Z",  # after the declared cutoff
                report_generation_time_utc="2026-09-25T06:20:00Z",
                evening_cutoff_utc="2026-09-25T06:20:00Z",  # looser per-claim cutoff to bypass the local guard
            ),
        ])


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
