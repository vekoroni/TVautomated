"""Governed authority policy for Dynamic Options Intelligence.

The options, EV, EIL, entry, exit and timing layers produce evidence for a
human trader.  They do not own ticker-thesis existence and therefore may not
remove an otherwise governed opportunity from downstream views.
"""

from __future__ import annotations

from typing import Any, Dict


DOI_POLICY_VERSION = "doi-authority-v1"
DECISION_AUTHORITY_NONE = "NONE"
EXECUTION_AUTHORITY_HUMAN = "HUMAN_ONLY"


def advisory_authority_fields() -> Dict[str, Any]:
    """Return the canonical fields carried by every DOI-governed row."""

    return {
        "doi_policy_version": DOI_POLICY_VERSION,
        "doi_decision_authority": DECISION_AUTHORITY_NONE,
        "eil_advisory_only": True,
        "ev_advisory_only": True,
        "entry_exit_timing_advisory_only": True,
        "execution_authority": EXECUTION_AUTHORITY_HUMAN,
        "opportunity_retention_policy": "PRESERVE_AND_DISCLOSE",
    }


def apply_advisory_authority(row: Dict[str, Any]) -> Dict[str, Any]:
    """Stamp DOI authority without changing the evidence values themselves."""

    row.update(advisory_authority_fields())
    return row


def eil_advisory_flags(verdict: Any) -> list[str]:
    """Translate an EIL verdict into disclosure flags, never vetoes."""

    value = str(verdict or "").strip().upper()
    if not value:
        return ["EIL_NOT_EVALUATED"]
    if value in {"BLOCKED", "BLOCK"}:
        return ["EIL_ADVISORY_BLOCKED"]
    if value in {"WATCHLIST", "WAIT", "DEFER"}:
        return [f"EIL_ADVISORY_{value}"]
    return [f"EIL_ADVISORY_{value}"]

