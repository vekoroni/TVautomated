"""Bounded WAR-report assembler.

Gap 5 wiring (ACK, 25 Sep 2026, post-acceptance review): composes the six
evidence-gap domain modules into one versioned WarReportPayload (schema v2)
and, on request, its rendered HTML — a single, named integration point
instead of leaving callers to wire the modules themselves ad hoc.

This module is orchestration only. It holds no new business rules of its
own: every decision was already made by the domain module that owns it
(temporal rejection, quote freshness, transmission-chain state, corroboration
grouping, coverage gaps). Its only job is routing inputs to the right domain
call and shaping the result into the provenance contract.

IMPORTANT — passing this module's own tests proves the six modules compose
without raising and produce a well-formed, advisory-only payload. It does
NOT prove the WAR report is production-ready. That requires running this
repository's real acceptance suite (the design-baseline artifact's Section E,
plus the existing broker-quote / Interactive Desk suites) end to end against
this module, which was not done from the session that wrote this file — see
the delivered README for exactly what was and was not run, and why.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from domain.exact_contract_quote_join import ExactContractQuoteJoin
from domain.war_corroboration import EvidenceSignal, corroboration_report
from domain.war_coverage_summary import SourceCoverageEntry, build_ticker_coverage_summary
from domain.war_report_provenance import (
    CounterCase, QaAnswer, SourceReference, WarReportPayload, build_war_report_payload,
)
from domain.war_temporal_truth import TimedClaim, assert_intelligence_cutoff_matches_evidence, build_claim_timeline
from domain.war_transmission_chain import TransmissionLink, build_transmission_chain


def _derive_contradictions(
    *,
    quote_join: ExactContractQuoteJoin,
    coverage_summary: Mapping[str, Any],
    corroboration: Mapping[str, Any],
) -> tuple[str, ...]:
    """Surface a small set of structural contradictions the assembler can see directly.

    This is deliberately narrow: it flags mechanical contradictions between
    the outputs of the domain modules it already has in hand, not a general
    narrative-consistency check.
    """
    flags: list[str] = []
    if quote_join.identity_state != "MATCHED":
        flags.append(
            f"option_economics: no matched exact-contract quote for run "
            f"{quote_join.requested_run_id} ({quote_join.identity_state})"
        )
    elif quote_join.executable_now == "EXECUTABLE_NOW" and quote_join.quote_freshness != "FRESH":
        flags.append("option_economics: EXECUTABLE_NOW reported without FRESH freshness")
    if not coverage_summary.get("may_render_full_narrative", False):
        flags.append(
            "coverage_summary: narrative is PARTIAL_NO_DATA — gaps: "
            + ", ".join(coverage_summary.get("coverage_gaps", []))
        )
    if corroboration.get("single_source_conflation_detected"):
        flags.append(
            "corroboration: multiple evidence fields collapse to a single upstream source family"
        )
    return tuple(flags)


def assemble_war_report_payload(
    *,
    report_version: str,
    run_id: str,
    ticker: str,
    thesis_id: str,
    report_generation_time_utc: str,
    declared_intelligence_cutoff_utc: str,
    quote_join: ExactContractQuoteJoin,
    frozen_claims: Sequence[TimedClaim],
    additive_claims: Sequence[TimedClaim],
    sector_link: TransmissionLink,
    ticker_link: TransmissionLink,
    contract_link: TransmissionLink,
    corroboration_signals: Sequence[EvidenceSignal],
    coverage_source_states: Mapping[str, SourceCoverageEntry],
    war_synthesis: str,
    judgment: Mapping[str, Any],
    qa_registry: Sequence[QaAnswer],
    sources: Sequence[SourceReference],
    missing_inputs: Sequence[str],
    counter_cases: Sequence[CounterCase],
) -> WarReportPayload:
    """Wire the six evidence-gap modules into one schema-v2 WarReportPayload.

    Raises domain.war_temporal_truth.TemporalRejectionError if a frozen claim
    used evidence observed after the declared intelligence cutoff — the
    assembler does not swallow that rejection, since silently dropping it
    would recreate the exact mislabeling gap 2 exists to prevent.
    """
    all_claims = list(frozen_claims) + list(additive_claims)
    assert_intelligence_cutoff_matches_evidence(
        declared_cutoff_utc=declared_intelligence_cutoff_utc, claims=all_claims,
    )
    claim_timeline = build_claim_timeline(list(frozen_claims), list(additive_claims))
    transmission_chain = build_transmission_chain(
        sector_link=sector_link, ticker_link=ticker_link, contract_link=contract_link,
    )
    corroboration = corroboration_report(corroboration_signals)
    coverage_summary = build_ticker_coverage_summary(
        ticker=ticker, source_states=coverage_source_states,
    )
    contradictions = _derive_contradictions(
        quote_join=quote_join, coverage_summary=coverage_summary, corroboration=corroboration,
    )
    selected_contract_symbol = (
        quote_join.requested_occ_symbol if quote_join.identity_state == "MATCHED" else None
    )
    governed_judgment = dict(judgment)
    governed_judgment["authority"] = "ADVISORY_ONLY"
    governed_judgment.setdefault("corroboration", corroboration)

    return build_war_report_payload(
        report_version=report_version, run_id=run_id, ticker=ticker, thesis_id=thesis_id,
        selected_contract_symbol=selected_contract_symbol,
        report_generation_time_utc=report_generation_time_utc,
        intelligence_cutoff_utc=declared_intelligence_cutoff_utc,
        sources=sources, missing_inputs=missing_inputs, counter_cases=counter_cases,
        war_synthesis=war_synthesis, claim_timeline=claim_timeline,
        transmission_chain=transmission_chain, coverage_summary=coverage_summary,
        contradictions=contradictions, option_economics=quote_join.to_dict(),
        judgment=governed_judgment, qa_registry=qa_registry,
    )


__all__ = ["assemble_war_report_payload"]
