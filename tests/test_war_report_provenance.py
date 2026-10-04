"""Gap 6 (ACK, 25 Sep 2026, revised post-acceptance review) — provenance
JSON schema v2 and HTML render from it. v1 rendered only a source table,
missing inputs and counter-cases; v2 adds the WAR synthesis, claim timeline,
transmission chain, contradictions, option economics, judgment and the
78-question registry as first-class schema fields, and the renderer draws
every one of them from the payload. Opening a saved report (rendering an
already-built payload) still makes zero provider calls.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import domain.war_report_provenance as provenance_module
from domain.war_report_provenance import (
    CounterCase, QaAnswer, SourceReference, WAR_REPORT_SCHEMA_VERSION,
    build_war_report_payload, render_war_report_html,
)
from domain.war_temporal_truth import EvidenceClassification, make_frozen_evening_claim, build_claim_timeline
from domain.war_transmission_chain import classify_contract_link, classify_sector_link, classify_ticker_link, build_transmission_chain
from domain.war_coverage_summary import SourceCoverageEntry, SourceCoverageState, build_ticker_coverage_summary

RUN = "20260925_061649"


def _sample_claim_timeline():
    frozen = make_frozen_evening_claim(
        claim_id="bull_thesis_direction", statement="BULL CALL thesis formed",
        classification=EvidenceClassification.OBSERVED,
        source_observed_at_utc="2026-09-24T20:45:00Z",
        report_generation_time_utc="2026-09-24T21:05:00Z",
        evening_cutoff_utc="2026-09-24T21:00:00Z",
    )
    return build_claim_timeline([frozen], [])


def _sample_transmission_chain():
    sector_link = classify_sector_link(
        has_measured_flow_metric=False, sector_flow_source_reference=None,
        business_description_match_only=True,
    )
    ticker_link = classify_ticker_link(
        has_ticker_level_metric=False, ticker_source_reference=None, sector_link=sector_link,
    )
    contract_link = classify_contract_link(
        selected_contract_symbol="BULL261120C00007500", ticker_link=ticker_link,
    )
    return build_transmission_chain(sector_link=sector_link, ticker_link=ticker_link, contract_link=contract_link)


def _sample_coverage_summary():
    return build_ticker_coverage_summary(
        ticker="BULL",
        source_states={"exact_option_quote": SourceCoverageEntry(
            "exact_option_quote", SourceCoverageState.AVAILABLE.value, "joined to run 20260925_061649")},
    )


def _sample_qa_registry():
    return [
        QaAnswer(n=4, q="Did control transfer at the break bar?", s="interp",
                 req="later-session intraday bars", src="dropbox/macro/bar_exports",
                 obs="control-transfer bar at 13:40Z", interp="tentative absorption read",
                 counter="could be a liquidity air-pocket, not absorption",
                 conf="MEDIUM", miss="rest-of-session bars", chg="a confirmed reaction bar at POC"),
    ]


def _sample_payload():
    return build_war_report_payload(
        report_version="v11", run_id=RUN, ticker="BULL", thesis_id="bull_thesis_20260924",
        selected_contract_symbol="BULL261120C00007500",
        report_generation_time_utc="2026-09-25T13:35:50Z",
        intelligence_cutoff_utc="2026-09-24T21:00:00Z",
        sources=[
            SourceReference(
                "exact_option_quote",
                "data/canonical/market_observations/exact_option_quote/2026-09-25/BULL/"
                "e87aff2d2b6a28e790cdd4e5b718f25c88ec9a442401ebf873508984be9335de.json",
                None, "e87aff2d", "2026-09-25T13:34:50Z", "OBSERVED",
            ),
        ],
        missing_inputs=["later_session_intraday_bars"],
        counter_cases=[CounterCase(
            "Thesis assumes continued sector rotation into financials",
            "sector flow reverses on the next completed session",
        )],
        war_synthesis="BULL CALL thesis remains structurally valid at report generation.",
        claim_timeline=_sample_claim_timeline(),
        transmission_chain=_sample_transmission_chain(),
        coverage_summary=_sample_coverage_summary(),
        contradictions=["option_economics: EXECUTABLE_NOW reported without FRESH freshness"],
        option_economics={"quote_quality": "TWO_SIDED", "quote_freshness": "FRESH", "bid": "0.61", "ask": "0.64"},
        judgment={"action": "MANUAL_REVIEW", "reason": "AWAITING_HUMAN_CONFIRMATION", "eligibility": "REVIEW_REQUIRED"},
        qa_registry=_sample_qa_registry(),
    )


def test_schema_version_is_v2():
    assert WAR_REPORT_SCHEMA_VERSION == "war-report-provenance-v2"
    assert _sample_payload().to_dict()["schema_version"] == "war-report-provenance-v2"


def test_payload_carries_every_required_provenance_field():
    payload = _sample_payload().to_dict()
    for field in (
        "report_version", "run_id", "ticker", "thesis_id", "selected_contract_symbol",
        "report_generation_time_utc", "intelligence_cutoff_utc", "sources",
        "missing_inputs", "counter_cases", "authority", "schema_version",
        "war_synthesis", "claim_timeline", "transmission_chain", "coverage_summary",
        "contradictions", "option_economics", "judgment", "qa_registry",
    ):
        assert field in payload, field


def test_payload_authority_is_advisory_only():
    assert _sample_payload().to_dict()["authority"] == "ADVISORY_ONLY"


def test_render_covers_every_v2_section_not_just_sources_and_missing_inputs():
    html = render_war_report_html(_sample_payload())
    for expected in (
        "WAR Synthesis", "Judgment", "Option Economics", "Claim Timeline",
        "Transmission Chain", "Coverage Summary", "Contradictions",
        "78-Question Registry",
    ):
        assert expected in html, expected
    # Spot-check actual content, not just section headers.
    assert "BULL CALL thesis remains structurally valid" in html
    assert "MANUAL_REVIEW" in html
    assert "TWO_SIDED" in html
    assert "bull_thesis_direction" in html
    assert "EVENT_MACRO" in html
    assert "exact_option_quote" in html
    assert "EXECUTABLE_NOW reported without FRESH freshness" in html
    assert "control-transfer bar at 13:40Z" in html


def test_saved_json_and_rendered_html_stay_in_parity_across_a_save_reload_cycle(tmp_path):
    payload = _sample_payload()
    json_path = tmp_path / "war_report.json"
    json_path.write_text(json.dumps(payload.to_dict(), sort_keys=True), encoding="utf-8")

    html_before_save = render_war_report_html(payload)
    reloaded = json.loads(json_path.read_text(encoding="utf-8"))
    html_after_reload = render_war_report_html(reloaded)

    assert html_before_save == html_after_reload


def test_render_is_a_pure_function_of_the_payload_same_input_same_output():
    payload = _sample_payload()
    assert render_war_report_html(payload) == render_war_report_html(payload)


def test_render_escapes_html_special_characters_in_source_data():
    payload = build_war_report_payload(
        report_version="v11", run_id=RUN, ticker="BULL", thesis_id="t",
        selected_contract_symbol=None,
        report_generation_time_utc="2026-09-25T13:35:50Z",
        intelligence_cutoff_utc="2026-09-24T21:00:00Z",
        sources=[], missing_inputs=[],
        counter_cases=[CounterCase("<script>alert(1)</script>", "x & y")],
        war_synthesis="<b>bold</b> attempt", claim_timeline={}, transmission_chain={},
        coverage_summary={}, contradictions=[], option_economics={}, judgment={}, qa_registry=[],
    )
    html = render_war_report_html(payload)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_opening_a_saved_report_makes_zero_provider_calls():
    """The renderer's own source imports no broker/provider/network client."""
    source = Path(provenance_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    forbidden_tokens = ("tastytrade", "broker", "provider_client", "requests", "httpx", "urllib")
    for module_name in imported_modules:
        lowered = module_name.lower()
        assert not any(token in lowered for token in forbidden_tokens), module_name
    payload = _sample_payload()
    render_war_report_html(payload)  # would raise/hang on any real network dependency


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
