"""Provider-free code provenance labels; ACK K9: warnings never stop a run."""
from __future__ import annotations
import logging
from typing import Mapping

def code_identity_reasons(identity: Mapping[str, object]) -> tuple[str, ...]:
    commit = str(identity.get("baseline_commit_hash") or "UNAVAILABLE").strip()
    describe = str(identity.get("git_describe") or "UNAVAILABLE").strip()
    reasons = []
    if commit in {"", "UNAVAILABLE"} or describe in {"", "UNAVAILABLE"}:
        reasons.append("CODE_IDENTITY_UNAVAILABLE")
    receipt = identity.get("code_receipt") or {}
    if describe.lower().endswith("-dirty") or (receipt and receipt.get("state") != "CLEAN_COMMIT"):
        reasons.append("CODE_UNCOMMITTED")
    return tuple(reasons)

def warn_production_eligibility(identity: Mapping[str, object], *, operator_mode: str = "STANDARD",
                                run_kind: str = "PRODUCTION", action: str = "BUILD_THESIS") -> tuple[str, ...]:
    reasons = code_identity_reasons(identity)
    if (str(run_kind).upper() == "PRODUCTION" and str(operator_mode).upper() == "STANDARD"
            and str(action).upper() in {"BUILD_THESIS", "FINALISE"} and reasons):
        logging.getLogger(__name__).warning(
            "PRODUCTION_BASELINE_INELIGIBLE: %s; Evening continues with provenance labels",
            ",".join(reasons))
    return reasons
