"""Pure market-profile and market-structure evidence policy.

The domain owns evidence state, usability, lifecycle and authority.  It does
not fetch candles, calculate TPO bins, persist payloads or decide whether
capital may be deployed.  Those application concerns remain in their existing
adapters.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from enum import Enum
from typing import Any, Mapping


PROFILE_EVIDENCE_VERSION = "market_profile_evidence_v1"
MARKET_STRUCTURE_AUTHORITY = "ADVISORY_ONLY"


class ProfileEvidenceState(str, Enum):
    COMPLETED_SESSION = "COMPLETED_SESSION"
    DEVELOPING_SESSION = "DEVELOPING_SESSION"
    PARTIAL_SESSION = "PARTIAL_SESSION"
    PENDING_MARKET_OPEN = "PENDING_MARKET_OPEN"
    UNAVAILABLE_PROVIDER = "UNAVAILABLE_PROVIDER"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DATA_DEFECT = "DATA_DEFECT"
    NOT_EVALUATED = "NOT_EVALUATED"


class ProfileUsability(str, Enum):
    USABLE = "USABLE"
    NOT_USABLE = "NOT_USABLE"


class MarketStructureLifecycle(str, Enum):
    NONE = "MS_NONE"
    DEVELOPING = "MS_DEVELOPING"
    ACCEPTED = "MS_ACCEPTED"
    CONTINUING = "MS_CONTINUING"
    REPAIRING = "MS_REPAIRING"
    FAILED = "MS_FAILED"


USABLE_PROFILE_STATES = {
    ProfileEvidenceState.COMPLETED_SESSION.value,
    ProfileEvidenceState.DEVELOPING_SESSION.value,
}
USABLE_PROFILE_QUALITIES = {
    "ONE_MINUTE_ESTIMATED",
    "FIVE_MINUTE_ESTIMATED",
    "COARSE_15_MINUTE",
    "COARSE_30_MINUTE",
}


def profile_evidence_state_for_session(session_state: str) -> ProfileEvidenceState:
    """Translate a trading-session state into observable profile evidence."""

    state = str(getattr(session_state, "value", session_state) or "").strip().upper()
    return {
        "PREMARKET": ProfileEvidenceState.PENDING_MARKET_OPEN,
        "REGULAR": ProfileEvidenceState.DEVELOPING_SESSION,
        "AFTER_HOURS": ProfileEvidenceState.PARTIAL_SESSION,
    }.get(state, ProfileEvidenceState.NOT_EVALUATED)


def profile_levels_are_usable(
    *, poc: float | None, value_area_low: float | None, value_area_high: float | None
) -> bool:
    levels = (poc, value_area_low, value_area_high)
    if not all(value is not None for value in levels):
        return False
    try:
        point = float(poc)
        low = float(value_area_low)
        high = float(value_area_high)
    except (TypeError, ValueError):
        return False
    return point > 0 and low > 0 and high > 0 and low <= point <= high


def profile_evidence_is_usable(
    *,
    evidence_state: str,
    completeness_status: str,
    quality: str,
    poc: float | None,
    value_area_low: float | None,
    value_area_high: float | None,
) -> bool:
    return (
        str(evidence_state).strip().upper() in USABLE_PROFILE_STATES
        and str(completeness_status).strip().upper() == "COMPLETE"
        and str(quality).strip().upper() in USABLE_PROFILE_QUALITIES
        and profile_levels_are_usable(
            poc=poc,
            value_area_low=value_area_low,
            value_area_high=value_area_high,
        )
    )


def profile_reason_code(
    *, evidence_state: str, completeness_status: str, levels_available: bool
) -> str:
    state = str(evidence_state or "").strip().upper()
    completeness = str(completeness_status or "UNAVAILABLE").strip().upper()
    if state == ProfileEvidenceState.PENDING_MARKET_OPEN.value:
        return "REGULAR_SESSION_NOT_YET_OBSERVABLE"
    if state == ProfileEvidenceState.UNAVAILABLE_PROVIDER.value:
        return "PROFILE_PROVIDER_UNAVAILABLE"
    if completeness != "COMPLETE":
        return "PROFILE_INPUT_PARTIAL"
    if not levels_available:
        return "PROFILE_INSUFFICIENT_DATA"
    return "PROFILE_COMPLETE"


@dataclass(frozen=True, slots=True)
class MarketProfileEvidence:
    evidence_id: str
    ticker: str
    session_date: str
    evidence_state: str
    interval_minutes: int
    poc: float | None
    value_area_low: float | None
    value_area_high: float | None
    profile_type: str
    quality: str
    completeness_status: str
    input_dataset_ids: tuple[str, ...]
    input_hashes: tuple[str, ...]
    observed_at_utc: str
    calculated_at_utc: str
    algorithm_version: str
    authority: str = MARKET_STRUCTURE_AUTHORITY
    can_grant_capital: bool = False
    can_reverse_direction: bool = False
    uncertainty_score: float = 1.0
    reason_code: str = ""

    def __post_init__(self) -> None:
        if not self.evidence_id.strip() or not self.ticker.strip():
            raise ValueError("profile evidence identity and ticker are required")
        date.fromisoformat(self.session_date)
        if self.interval_minutes <= 0:
            raise ValueError("profile interval must be positive")
        if not 0.0 <= float(self.uncertainty_score) <= 1.0:
            raise ValueError("profile uncertainty_score must be in [0,1]")
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
        object.__setattr__(self, "evidence_state", self.evidence_state.strip().upper())
        object.__setattr__(self, "quality", self.quality.strip().upper())
        object.__setattr__(self, "completeness_status", self.completeness_status.strip().upper())
        # Evidence may advise a frozen thesis but can never become a second
        # direction or capital authority, even when reconstructed from input.
        object.__setattr__(self, "authority", MARKET_STRUCTURE_AUTHORITY)
        object.__setattr__(self, "can_grant_capital", False)
        object.__setattr__(self, "can_reverse_direction", False)

    @property
    def usable(self) -> bool:
        return profile_evidence_is_usable(
            evidence_state=self.evidence_state,
            completeness_status=self.completeness_status,
            quality=self.quality,
            poc=self.poc,
            value_area_low=self.value_area_low,
            value_area_high=self.value_area_high,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["input_dataset_ids"] = list(self.input_dataset_ids)
        payload["input_hashes"] = list(self.input_hashes)
        payload["usable"] = self.usable
        payload["contract_version"] = PROFILE_EVIDENCE_VERSION
        return payload

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MarketProfileEvidence":
        return cls(
            evidence_id=str(value.get("evidence_id") or value.get("ms_evidence_id") or ""),
            ticker=str(value.get("ticker") or ""),
            session_date=str(value.get("session_date") or ""),
            evidence_state=str(value.get("evidence_state") or "COMPLETED_SESSION"),
            interval_minutes=int(value.get("interval_minutes") or 0),
            poc=value.get("poc", value.get("ms_final_poc")),
            value_area_low=value.get("value_area_low", value.get("ms_value_area_low")),
            value_area_high=value.get("value_area_high", value.get("ms_value_area_high")),
            profile_type=str(value.get("profile_type") or value.get("ms_profile_type") or "UNKNOWN"),
            quality=str(value.get("quality") or value.get("ms_quality_class") or "INSUFFICIENT_DATA"),
            completeness_status=str(value.get("completeness_status") or "UNAVAILABLE"),
            input_dataset_ids=tuple(value.get("input_dataset_ids") or value.get("ms_input_dataset_ids") or ()),
            input_hashes=tuple(value.get("input_hashes") or value.get("ms_input_hashes") or ()),
            observed_at_utc=str(value.get("observed_at_utc") or value.get("ms_calculated_utc") or ""),
            calculated_at_utc=str(value.get("calculated_at_utc") or value.get("ms_calculated_utc") or ""),
            algorithm_version=str(value.get("algorithm_version") or value.get("ms_algorithm_version") or PROFILE_EVIDENCE_VERSION),
            uncertainty_score=float(value.get("uncertainty_score", 1.0)),
            reason_code=str(value.get("reason_code") or value.get("ms_reason_code") or ""),
        )


def transition_market_structure_lifecycle(
    *,
    prior: str | None,
    detected: bool,
    accepted: bool,
    repair_pct: float,
    invalidated: bool = False,
    intact_repair: float,
    failed_repair: float,
) -> str:
    previous = str(prior or "").upper()
    if previous == MarketStructureLifecycle.FAILED.value:
        return MarketStructureLifecycle.FAILED.value
    if not detected or invalidated or repair_pct > failed_repair:
        return (
            MarketStructureLifecycle.FAILED.value
            if previous else MarketStructureLifecycle.NONE.value
        )
    if previous in {"", MarketStructureLifecycle.NONE.value}:
        return (
            MarketStructureLifecycle.ACCEPTED.value
            if accepted else MarketStructureLifecycle.DEVELOPING.value
        )
    if previous == MarketStructureLifecycle.DEVELOPING.value:
        return (
            MarketStructureLifecycle.ACCEPTED.value
            if accepted else MarketStructureLifecycle.DEVELOPING.value
        )
    if (
        previous == MarketStructureLifecycle.REPAIRING.value
        and accepted and repair_pct < intact_repair
    ):
        return MarketStructureLifecycle.CONTINUING.value
    if (
        previous in {
            MarketStructureLifecycle.ACCEPTED.value,
            MarketStructureLifecycle.CONTINUING.value,
        }
        and accepted and repair_pct < intact_repair
    ):
        return MarketStructureLifecycle.CONTINUING.value
    return MarketStructureLifecycle.REPAIRING.value


def market_structure_direction_relationship(
    *,
    governed_direction: str,
    structure_direction: str | None,
    lifecycle: str,
    quality: str,
) -> str:
    if str(quality).upper() in {"INSUFFICIENT_DATA", "COARSE_DATA_LOW_CONFIDENCE"}:
        return "INSUFFICIENT_DATA"
    if not structure_direction:
        return "INSUFFICIENT_DATA"
    direction = str(governed_direction).strip().upper()
    if direction not in {"CALL", "PUT"}:
        return "NEUTRAL"
    if str(lifecycle).upper() not in {
        MarketStructureLifecycle.ACCEPTED.value,
        MarketStructureLifecycle.CONTINUING.value,
    }:
        return "NEUTRAL"
    aligned = (
        direction == "CALL" and str(structure_direction).upper() == "ABOVE"
    ) or (
        direction == "PUT" and str(structure_direction).upper() == "BELOW"
    )
    return "ALIGNED" if aligned else "CONFLICTING"


def pin_market_structure_authority(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return evidence with its non-trading authority invariants enforced."""

    pinned = dict(payload)
    pinned["ms_authority"] = MARKET_STRUCTURE_AUTHORITY
    pinned["ms_can_grant_capital"] = False
    pinned["ms_can_reverse_direction"] = False
    return pinned
