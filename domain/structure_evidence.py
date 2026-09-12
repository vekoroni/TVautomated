"""Advisory structure evidence derived from governed thesis observations."""
from __future__ import annotations
def derive_structure_evidence(*, hidden_state_label, phase, trigger_primary) -> dict:
    hidden = str(hidden_state_label or "").upper()
    phase_value = str(phase or "").upper()
    trigger = str(trigger_primary or "").upper()
    if "LOW_ENERGY" in hidden:
        state, reason = "NO_EDGE", "LOW_ENERGY_HIDDEN_STATE"
    elif not trigger or trigger in {"NONE", "NO_TRIGGER"}:
        state, reason = "DEVELOPING", "TRIGGER_NOT_YET_PRESENT"
    elif any(token in trigger for token in ("CONFLICT", "OPPOSED", "FAIL")):
        state, reason = "OPPOSED", "TRIGGER_OPPOSES_THESIS"
    else:
        state, reason = "SUPPORTIVE", "TRIGGER_SUPPORTS_THESIS"
    return {"structure_evidence_state": state, "structure_evidence_reason": reason,
            "structure_evidence_inputs": f"{hidden}|{phase_value}|{trigger}",
            "structure_evidence_version": "structure_evidence_v1", "structure_evidence_authority":"ADVISORY_ONLY"}
