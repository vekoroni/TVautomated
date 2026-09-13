"""Pure non-authoritative Lab presentation state."""
from __future__ import annotations
from dataclasses import dataclass

PRESENTATION_VERSION = "opportunity_presentation_v1"

@dataclass(frozen=True, slots=True)
class OpportunityPresentation:
    summary_state: str
    summary_reason: str
    authority: str = "DISPLAY_ONLY"
    calculation_version: str = PRESENTATION_VERSION
    def to_dict(self) -> dict:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

def derive_opportunity_presentation_v1(*, thesis_state: str, contract_state: str,
                                      execution_state: str, macro_context: str) -> OpportunityPresentation:
    thesis = str(thesis_state).upper()
    contract = str(contract_state).upper()
    execution = str(execution_state).upper()
    if thesis in {"", "UNKNOWN", "NOT_EVALUATED", "NOT_EVALUATED_DATA_MISSING"}:
        return OpportunityPresentation(
            "DATA_INCOMPLETE", "THESIS_STATE_NOT_EVALUATED_DATA_MISSING"
        )
    if thesis in {"INVALID", "THESIS_INVALIDATED"}:
        return OpportunityPresentation("THESIS_INVALID", "GOVERNED_THESIS_INVALIDATED")
    if contract in {"", "NOT_EVALUATED", "NOT_EVALUATED_DATA_MISSING"}:
        return OpportunityPresentation(
            "MONITOR", "THESIS_ACTIVE|CONTRACT_NOT_EVALUATED_DATA_MISSING"
        )
    if execution in {"EXECUTION_EXECUTABLE_NOW", "EXECUTABLE_QUOTE"}:
        return OpportunityPresentation("EXECUTION_REVIEW", f"THESIS_ACTIVE|{contract_state}|HUMAN_CONFIRMATION_REQUIRED")
    return OpportunityPresentation("MONITOR", f"THESIS_ACTIVE|{contract_state}|{execution}|MACRO_{macro_context}")
