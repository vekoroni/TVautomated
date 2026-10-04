"""Temporal truth for the WAR report.

Gap 2 (ACK, 25 Sep 2026): the Evening thesis and its cutoff are frozen once
formed. Every claim carries its own source-observation time, report-generation
time and evidence classification (OBSERVED / DERIVED / INFERRED). A Morning
or live observation may only be recorded as an ADDITIVE update layered on top
of the frozen thesis; it never mutates or silently replaces a frozen claim,
and evidence observed after a frozen claim's own cutoff is rejected from that
claim (it may still land in a later additive layer with its own, later
cutoff). A report must never declare one intelligence cutoff while a frozen
claim silently used evidence captured after it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EvidenceClassification(str, Enum):
    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    INFERRED = "INFERRED"


class TemporalLayer(str, Enum):
    EVENING_FROZEN = "EVENING_FROZEN"
    MORNING_ADDITIVE = "MORNING_ADDITIVE"
    LIVE_ADDITIVE = "LIVE_ADDITIVE"


class TemporalRejectionError(ValueError):
    """Raised when evidence observed after a frozen claim's cutoff is offered to that claim."""


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class TimedClaim:
    claim_id: str
    layer: str
    statement: str
    classification: str
    source_observed_at_utc: str
    report_generation_time_utc: str
    cutoff_utc: str

    def __post_init__(self) -> None:
        observed = _parse(self.source_observed_at_utc)
        cutoff = _parse(self.cutoff_utc)
        generated = _parse(self.report_generation_time_utc)
        if observed > cutoff:
            raise TemporalRejectionError(
                f"{self.claim_id}: source_observed_at_utc {self.source_observed_at_utc} "
                f"is after this claim's cutoff {self.cutoff_utc}"
            )
        if generated < observed:
            raise TemporalRejectionError(
                f"{self.claim_id}: report_generation_time_utc precedes source_observed_at_utc"
            )


def make_frozen_evening_claim(
    *, claim_id: str, statement: str, classification: EvidenceClassification | str,
    source_observed_at_utc: str, report_generation_time_utc: str, evening_cutoff_utc: str,
) -> TimedClaim:
    return TimedClaim(
        claim_id=claim_id, layer=TemporalLayer.EVENING_FROZEN.value, statement=statement,
        classification=str(getattr(classification, "value", classification)),
        source_observed_at_utc=source_observed_at_utc,
        report_generation_time_utc=report_generation_time_utc,
        cutoff_utc=evening_cutoff_utc,
    )


def make_additive_update(
    *, claim_id: str, statement: str, classification: EvidenceClassification | str,
    source_observed_at_utc: str, report_generation_time_utc: str, layer_cutoff_utc: str,
    layer: TemporalLayer = TemporalLayer.MORNING_ADDITIVE,
) -> TimedClaim:
    """An additive layer augments the frozen thesis; it never edits it."""
    if layer is TemporalLayer.EVENING_FROZEN:
        raise ValueError("an additive update cannot claim the EVENING_FROZEN layer")
    return TimedClaim(
        claim_id=claim_id, layer=layer.value, statement=statement,
        classification=str(getattr(classification, "value", classification)),
        source_observed_at_utc=source_observed_at_utc,
        report_generation_time_utc=report_generation_time_utc,
        cutoff_utc=layer_cutoff_utc,
    )


def assert_intelligence_cutoff_matches_evidence(
    *, declared_cutoff_utc: str, claims: list[TimedClaim],
) -> None:
    """Reject a report that declares one cutoff while a frozen claim used later evidence.

    Only EVENING_FROZEN claims are checked against the declared cutoff;
    additive layers carry their own, separately declared cutoffs.
    """
    declared = _parse(declared_cutoff_utc)
    for claim in claims:
        if claim.layer != TemporalLayer.EVENING_FROZEN.value:
            continue
        observed = _parse(claim.source_observed_at_utc)
        if observed > declared:
            raise TemporalRejectionError(
                f"{claim.claim_id}: observed at {claim.source_observed_at_utc} "
                f"is after the declared intelligence cutoff {declared_cutoff_utc}"
            )


def build_claim_timeline(frozen: list[TimedClaim], additive: list[TimedClaim]) -> dict[str, Any]:
    """Assemble the frozen thesis plus its additive layers for provenance."""
    return {
        "frozen_claims": [asdict(c) for c in frozen],
        "additive_claims": [asdict(c) for c in additive],
        "frozen_claim_count": len(frozen),
        "additive_claim_count": len(additive),
    }


__all__ = [
    "EvidenceClassification", "TemporalLayer", "TemporalRejectionError", "TimedClaim",
    "make_frozen_evening_claim", "make_additive_update",
    "assert_intelligence_cutoff_matches_evidence", "build_claim_timeline",
]
