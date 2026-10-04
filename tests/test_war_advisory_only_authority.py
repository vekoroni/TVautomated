"""Cross-cutting (ACK, 25 Sep 2026, revised) — every evidence-gap module for
the WAR report, including the atomic writer and the bounded assembler added
in the post-acceptance revision, stays advisory-only: none of it selects/
places/replaces an order, changes universe mapping, allocates capital, or
activates a scheduled job. This is a static/behavioural guard, not proof the
WAR is production-ready.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

MODULES = (
    "domain.exact_contract_quote_join",
    "domain.war_temporal_truth",
    "domain.war_transmission_chain",
    "domain.war_corroboration",
    "domain.war_coverage_summary",
    "domain.war_report_provenance",
    "contracts.supplemental_broker_observation_writer",
    "contracts.war_report_assembler",
)

FORBIDDEN_CALL_NAME_TOKENS = (
    "place_order", "submit_order", "dry_run_order", "cancel_order",
    "allocate_capital", "activate_schedule", "schedule_war_job",
)


@pytest.mark.parametrize("module_name", MODULES)
def test_module_defines_no_order_or_capital_or_scheduling_call(module_name):
    module = __import__(module_name, fromlist=["_"])
    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    call_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func
            name = getattr(target, "attr", None) or getattr(target, "id", None)
            if name:
                call_names.add(name.lower())
    for token in FORBIDDEN_CALL_NAME_TOKENS:
        assert token not in call_names, f"{module_name} calls forbidden operation: {token}"


def test_exact_contract_quote_join_authority_field_is_always_advisory_only():
    from datetime import datetime, timezone

    from domain.exact_contract_quote_join import (
        ExactContractQuoteCandidate, join_exact_contract_quote,
    )

    candidate = ExactContractQuoteCandidate(
        source_path="x", source_hash="h", run_id="20260925_061649", ticker="BULL",
        occ_symbol="BULL261120C00007500", provider="MARKETDATA",
        provider_observed_at_utc="2026-09-25T13:34:50Z",
        bid="0.61", ask="0.64", bid_size="1", ask_size="13",
        delta="0.5045", gamma="0.2229", theta="-0.0067", vega="0.0114", quote_quality_raw=None,
    )
    join = join_exact_contract_quote(
        requested_occ_symbol="BULL261120C00007500", requested_run_id="20260925_061649",
        requested_ticker="BULL", candidates=[candidate],
        report_generation_time_utc=datetime(2026, 9, 25, 13, 35, 50, tzinfo=timezone.utc),
    )
    assert join.authority == "ADVISORY_ONLY"


def test_supplemental_record_builder_never_claims_a_persistence_side_effect_it_does_not_have():
    """Regression for the renamed function: the domain layer only builds a
    record; it must not expose anything named 'persist' that performs I/O."""
    import domain.exact_contract_quote_join as module

    assert not hasattr(module, "persist_supplemental_broker_observation"), (
        "the old, misleadingly-named function must not still exist in the domain layer"
    )
    assert hasattr(module, "build_supplemental_broker_observation_record")


def test_provenance_payload_authority_field_is_always_advisory_only():
    from domain.war_report_provenance import build_war_report_payload

    payload = build_war_report_payload(
        report_version="v11", run_id="20260925_061649", ticker="BULL", thesis_id="t",
        selected_contract_symbol=None, report_generation_time_utc="2026-09-25T13:35:50Z",
        intelligence_cutoff_utc="2026-09-24T21:00:00Z", sources=[], missing_inputs=[],
        counter_cases=[], war_synthesis="", claim_timeline={}, transmission_chain={},
        coverage_summary={}, contradictions=[], option_economics={}, judgment={}, qa_registry=[],
    )
    assert payload.authority == "ADVISORY_ONLY"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
