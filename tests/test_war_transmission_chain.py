"""Gap 3 (ACK, 25 Sep 2026) — event/macro -> sector/peer -> ticker -> selected
contract transmission chain, evidenced link by link. A business-description
sector match is never promoted to measured money flow.
"""
from __future__ import annotations

from domain.war_transmission_chain import (
    LinkEvidenceState, build_transmission_chain, classify_contract_link,
    classify_sector_link, classify_ticker_link,
)


def test_business_description_match_alone_is_inferred_not_measured():
    link = classify_sector_link(
        has_measured_flow_metric=False, sector_flow_source_reference=None,
        business_description_match_only=True,
    )
    assert link.evidence_state == LinkEvidenceState.INFERRED.value


def test_measured_sector_flow_requires_both_metric_and_source():
    link = classify_sector_link(
        has_measured_flow_metric=True, sector_flow_source_reference="dropbox/macro/sector_flow.json",
        business_description_match_only=False,
    )
    assert link.evidence_state == LinkEvidenceState.MEASURED.value


def test_missing_sector_linkage_is_recorded_missing_not_silently_skipped():
    link = classify_sector_link(
        has_measured_flow_metric=False, sector_flow_source_reference=None,
        business_description_match_only=False,
    )
    assert link.evidence_state == LinkEvidenceState.MISSING.value


def test_ticker_link_cannot_be_measured_on_top_of_an_inferred_sector_link():
    sector_link = classify_sector_link(
        has_measured_flow_metric=False, sector_flow_source_reference=None,
        business_description_match_only=True,
    )
    ticker_link = classify_ticker_link(
        has_ticker_level_metric=True, ticker_source_reference="run/ticker_participation.json",
        sector_link=sector_link,
    )
    assert ticker_link.evidence_state == LinkEvidenceState.INFERRED.value


def test_full_chain_only_reports_measured_when_every_link_is_measured():
    sector_link = classify_sector_link(
        has_measured_flow_metric=True, sector_flow_source_reference="a.json",
        business_description_match_only=False,
    )
    ticker_link = classify_ticker_link(
        has_ticker_level_metric=True, ticker_source_reference="b.json", sector_link=sector_link,
    )
    contract_link = classify_contract_link(
        selected_contract_symbol="BULL261016C00007000", ticker_link=ticker_link,
    )
    chain = build_transmission_chain(
        sector_link=sector_link, ticker_link=ticker_link, contract_link=contract_link,
    )
    assert chain["chain_complete_and_measured"] is True
    assert chain["weakest_link_state"] == LinkEvidenceState.MEASURED.value


def test_missing_sector_linkage_drags_the_whole_chain_below_measured():
    sector_link = classify_sector_link(
        has_measured_flow_metric=False, sector_flow_source_reference=None,
        business_description_match_only=False,
    )
    ticker_link = classify_ticker_link(
        has_ticker_level_metric=True, ticker_source_reference="b.json", sector_link=sector_link,
    )
    contract_link = classify_contract_link(
        selected_contract_symbol="BULL261016C00007000", ticker_link=ticker_link,
    )
    chain = build_transmission_chain(
        sector_link=sector_link, ticker_link=ticker_link, contract_link=contract_link,
    )
    assert chain["chain_complete_and_measured"] is False
    assert chain["weakest_link_state"] == LinkEvidenceState.MISSING.value


def test_no_selected_contract_is_missing_not_inferred():
    ticker_link = classify_ticker_link(
        has_ticker_level_metric=False, ticker_source_reference=None,
        sector_link=classify_sector_link(
            has_measured_flow_metric=False, sector_flow_source_reference=None,
            business_description_match_only=False,
        ),
    )
    contract_link = classify_contract_link(selected_contract_symbol=None, ticker_link=ticker_link)
    assert contract_link.evidence_state == LinkEvidenceState.MISSING.value


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
