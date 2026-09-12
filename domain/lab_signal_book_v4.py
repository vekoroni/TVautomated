"""Versioned bounded-context read model for the Intelligence Lab."""
from __future__ import annotations
from typing import Any, Mapping
from .presentation import derive_opportunity_presentation_v1

LAB_SIGNAL_BOOK_VERSION = "lab_signal_book_v4"

def project_lab_signal_v4(row: Mapping[str, Any]) -> dict[str, Any]:
    thesis_state = str(row.get("thesis_state") or row.get("morning_transition_state") or "UNKNOWN")
    contract_state = str(row.get("doi_monetisability_state") or row.get("monetisability_state") or "NOT_EVALUATED")
    execution_state = str(row.get("execution_state") or row.get("execution_viability_state") or "EXECUTION_REVIEWABLE")
    macro = str(row.get("usmi_sector_alignment") or row.get("macro_sector_alignment") or "UNAVAILABLE")
    presentation = derive_opportunity_presentation_v1(
        thesis_state=thesis_state, contract_state=contract_state,
        execution_state=execution_state, macro_context=macro,
    )
    return {
        "lab_schema_version": LAB_SIGNAL_BOOK_VERSION,
        "lab_v4_thesis_state": thesis_state,
        "lab_v4_structure_evidence_state": row.get("structure_evidence_state") or "DEVELOPING",
        "lab_v4_reach_ratio": row.get("doi_reach_ratio"),
        "lab_v4_contract_state": contract_state,
        "lab_v4_ranking_score": row.get("doi_ranking_score"),
        "lab_v4_ranking_score_kind": row.get("doi_ranking_score_kind") or "DETERMINISTIC_UTILITY",
        "lab_v4_execution_state": execution_state,
        "lab_v4_quote_provider_timestamp_utc": row.get("quote_provider_timestamp_utc") or row.get("selected_quote_timestamp_utc"),
        "lab_v4_macro_alignment": macro,
        "lab_v4_macro_scenario": row.get("usmi_scenario") or "UNRESOLVED",
        "lab_v4_summary_state": presentation.summary_state,
        "lab_v4_summary_reason": presentation.summary_reason,
        "lab_v4_authority": "DISPLAY_ONLY",
        "lab_v4_calculation_version": LAB_SIGNAL_BOOK_VERSION,
    }
