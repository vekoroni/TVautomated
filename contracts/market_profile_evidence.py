"""Typed advisory Market Profile evidence shared by EOD, Vanguard and Morning."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Mapping


PROFILE_EVIDENCE_VERSION = "market_profile_evidence_v1"
USABLE_PROFILE_STATES = {"COMPLETED_SESSION", "DEVELOPING_SESSION"}
USABLE_PROFILE_QUALITIES = {
    "ONE_MINUTE_ESTIMATED", "FIVE_MINUTE_ESTIMATED",
    "COARSE_15_MINUTE", "COARSE_30_MINUTE",
}


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
    authority: str = "ADVISORY_ONLY"
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
        # These are invariants of the frozen authority contract, not fields a
        # producer payload may choose.  Pin them even for direct construction
        # so malformed or hostile evidence cannot advertise trading authority.
        object.__setattr__(self, "authority", "ADVISORY_ONLY")
        object.__setattr__(self, "can_grant_capital", False)
        object.__setattr__(self, "can_reverse_direction", False)

    @property
    def usable(self) -> bool:
        levels = (self.poc, self.value_area_low, self.value_area_high)
        return (
            self.evidence_state in USABLE_PROFILE_STATES
            and self.completeness_status == "COMPLETE"
            and self.quality in USABLE_PROFILE_QUALITIES
            and all(value is not None and float(value) > 0 for value in levels)
            and float(self.value_area_low) <= float(self.poc) <= float(self.value_area_high)
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
            authority="ADVISORY_ONLY",
            can_grant_capital=False,
            can_reverse_direction=False,
            uncertainty_score=float(value.get("uncertainty_score", 1.0)),
            reason_code=str(value.get("reason_code") or value.get("ms_reason_code") or ""),
        )
