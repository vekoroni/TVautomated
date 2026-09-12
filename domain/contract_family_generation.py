"""Pure domain vocabulary for DOI contract-family generation.

The family audit distinguishes structural impossibility from temporary market
conditions.  Low activity, an incomplete quote, or an unattractive entry never
invalidates the underlying ticker thesis and never removes it from monitoring.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Mapping, Sequence

from .dynamic_options_intelligence import DOI_DECISION_AUTHORITY


DOI_FAMILY_POLICY_VERSION = "doi-thesis-conditioned-family-v1"


class _ValueEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class FamilyCandidateState(_ValueEnum):
    ELIGIBLE_TWO_SIDED = "ELIGIBLE_TWO_SIDED"
    MONITOR_ONE_SIDED = "MONITOR_ONE_SIDED"
    MONITOR_NO_QUOTE = "MONITOR_NO_QUOTE"
    EXCLUDED_STRUCTURAL = "EXCLUDED_STRUCTURAL"


class StructuralExclusionReason(_ValueEnum):
    INVALID_OCC_IDENTITY = "INVALID_OCC_IDENTITY"
    WRONG_OPTION_SIDE = "WRONG_OPTION_SIDE"
    EXPIRED_CONTRACT = "EXPIRED_CONTRACT"
    INSUFFICIENT_SESSION_RUNWAY = "INSUFFICIENT_SESSION_RUNWAY"
    NEGATIVE_QUOTE = "NEGATIVE_QUOTE"
    CROSSED_QUOTE = "CROSSED_QUOTE"
    IMPOSSIBLE_STRIKE_OR_EXPIRY = "IMPOSSIBLE_STRIKE_OR_EXPIRY"
    IDENTITY_FIELD_MISMATCH = "IDENTITY_FIELD_MISMATCH"
    DUPLICATE_CONTRACT_AMBIGUOUS = "DUPLICATE_CONTRACT_AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class FamilyCandidateAudit:
    audit_id: str
    source_row_index: int
    raw_contract_symbol: str
    contract_symbol: str | None
    option_side: str | None
    expiry: date | None
    strike: float | None
    remaining_sessions: int | None
    required_sessions: int
    bid: float | None
    ask: float | None
    volume: float | None
    open_interest: float | None
    state: FamilyCandidateState
    structural_exclusions: tuple[StructuralExclusionReason, ...]
    monitor_reasons: tuple[str, ...]
    quote_state: str
    moneyness_bucket: str
    expiry_bucket: str
    target_reachability: str
    display_eligible: bool
    decision_authority: str = DOI_DECISION_AUTHORITY

    def __post_init__(self) -> None:
        if self.decision_authority != DOI_DECISION_AUTHORITY:
            raise ValueError("family candidate audit has no decision authority")
        excluded = self.state is FamilyCandidateState.EXCLUDED_STRUCTURAL
        if excluded != bool(self.structural_exclusions):
            raise ValueError("structural exclusion state and reasons must agree")
        if excluded and self.display_eligible:
            raise ValueError("structurally excluded observations cannot be displayed")
        if self.required_sessions < 1:
            raise ValueError("required_sessions must be positive")

    @property
    def is_family_candidate(self) -> bool:
        return self.state is not FamilyCandidateState.EXCLUDED_STRUCTURAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "source_row_index": self.source_row_index,
            "raw_contract_symbol": self.raw_contract_symbol,
            "contract_symbol": self.contract_symbol,
            "option_side": self.option_side,
            "expiry": self.expiry.isoformat() if self.expiry else None,
            "strike": self.strike,
            "remaining_sessions": self.remaining_sessions,
            "required_sessions": self.required_sessions,
            "bid": self.bid,
            "ask": self.ask,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "state": self.state.value,
            "structural_exclusions": [value.value for value in self.structural_exclusions],
            "monitor_reasons": list(self.monitor_reasons),
            "quote_state": self.quote_state,
            "moneyness_bucket": self.moneyness_bucket,
            "expiry_bucket": self.expiry_bucket,
            "target_reachability": self.target_reachability,
            "display_eligible": self.display_eligible,
            "decision_authority": self.decision_authority,
        }


@dataclass(frozen=True, slots=True)
class ContractFamilyGenerationSummary:
    source_observations: int
    family_candidates: int
    structural_exclusions: int
    two_sided_candidates: int
    monitor_one_sided: int
    monitor_no_quote: int
    retained_low_open_interest: int
    retained_zero_volume: int
    displayed_candidates: int
    direction: str
    counts_by_exclusion: Mapping[str, int]

    def __post_init__(self) -> None:
        if self.source_observations != self.family_candidates + self.structural_exclusions:
            raise ValueError("family population does not reconcile")
        if self.family_candidates != (
            self.two_sided_candidates + self.monitor_one_sided + self.monitor_no_quote
        ):
            raise ValueError("family candidate states do not reconcile")
        if self.displayed_candidates > self.family_candidates:
            raise ValueError("displayed population exceeds family population")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_observations": self.source_observations,
            "family_candidates": self.family_candidates,
            "structural_exclusions": self.structural_exclusions,
            "two_sided_candidates": self.two_sided_candidates,
            "monitor_one_sided": self.monitor_one_sided,
            "monitor_no_quote": self.monitor_no_quote,
            "retained_low_open_interest": self.retained_low_open_interest,
            "retained_zero_volume": self.retained_zero_volume,
            "displayed_candidates": self.displayed_candidates,
            "direction": self.direction,
            "counts_by_exclusion": dict(self.counts_by_exclusion),
        }


@dataclass(frozen=True, slots=True)
class GeneratedContractFamily:
    family: Any
    taxonomy: tuple[FamilyCandidateAudit, ...]
    display_symbols: tuple[str, ...]
    summary: ContractFamilyGenerationSummary

    def __post_init__(self) -> None:
        admitted = {
            item.contract_symbol for item in self.taxonomy
            if item.is_family_candidate and item.contract_symbol
        }
        if set(self.family.candidate_symbols) != admitted:
            raise ValueError("family symbols do not reconcile to complete taxonomy")
        if not set(self.display_symbols).issubset(admitted):
            raise ValueError("display symbols must be admitted family candidates")
        if len(set(self.display_symbols)) != len(self.display_symbols):
            raise ValueError("display symbols contain duplicates")


def audits_to_payload(values: Sequence[FamilyCandidateAudit]) -> list[dict[str, Any]]:
    return [value.to_dict() for value in values]


__all__ = [
    "DOI_FAMILY_POLICY_VERSION",
    "FamilyCandidateState",
    "StructuralExclusionReason",
    "FamilyCandidateAudit",
    "ContractFamilyGenerationSummary",
    "GeneratedContractFamily",
    "audits_to_payload",
]
