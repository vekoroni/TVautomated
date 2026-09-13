"""Pure domain contract for canonical dataset projection events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
import hashlib
from typing import Any, Mapping


CANONICAL_DATASET_EVENT_VERSION = "canonical-dataset-event-v1"
PHANTOM_OPTION_CHAIN_PROJECTION = "PHANTOM_OPTION_CHAIN_V1"
ACTUARIAL_FEATURE_PROJECTION = "ACTUARIAL_FEATURE_OBSERVATION_V1"


class ProjectionEventType(str, Enum):
    CANONICAL_DATASET_COMMITTED = "CANONICAL_DATASET_COMMITTED"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("projection event timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class CanonicalDatasetCommitted:
    """Immutable request to project one canonical dataset."""

    event_id: str
    projection_name: str
    dataset_id: str
    dataset_type: str
    instrument_id: str
    session_date: date
    content_hash: str
    storage_uri: str
    dataset_as_of_utc: datetime
    source_run_id: str | None
    created_at_utc: datetime
    event_type: ProjectionEventType = ProjectionEventType.CANONICAL_DATASET_COMMITTED
    event_version: str = CANONICAL_DATASET_EVENT_VERSION

    def __post_init__(self) -> None:
        required = {
            "event_id": self.event_id,
            "projection_name": self.projection_name,
            "dataset_id": self.dataset_id,
            "dataset_type": self.dataset_type,
            "instrument_id": self.instrument_id,
            "content_hash": self.content_hash,
            "storage_uri": self.storage_uri,
        }
        for name, value in required.items():
            if not str(value).strip():
                raise ValueError(f"{name} is required")
        object.__setattr__(self, "projection_name", self.projection_name.strip().upper())
        object.__setattr__(self, "dataset_type", self.dataset_type.strip().upper())
        object.__setattr__(self, "instrument_id", self.instrument_id.strip().upper())
        object.__setattr__(self, "dataset_as_of_utc", _utc(self.dataset_as_of_utc))
        object.__setattr__(self, "created_at_utc", _utc(self.created_at_utc))
        expected = projection_event_id(self.projection_name, self.dataset_id)
        if self.event_id != expected:
            raise ValueError("projection event_id does not match its immutable identity")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "event_version": self.event_version,
            "projection_name": self.projection_name,
            "dataset_id": self.dataset_id,
            "dataset_type": self.dataset_type,
            "instrument_id": self.instrument_id,
            "session_date": self.session_date.isoformat(),
            "content_hash": self.content_hash,
            "storage_uri": self.storage_uri,
            "dataset_as_of_utc": self.dataset_as_of_utc.isoformat(),
            "source_run_id": self.source_run_id,
            "created_at_utc": self.created_at_utc.isoformat(),
            "authority": "DATA_PROJECTION_ONLY",
            "execution_authority": "NONE",
            "capital_authority": "NONE",
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CanonicalDatasetCommitted":
        return cls(
            event_id=str(value["event_id"]),
            event_type=ProjectionEventType(str(value["event_type"])),
            event_version=str(value["event_version"]),
            projection_name=str(value["projection_name"]),
            dataset_id=str(value["dataset_id"]),
            dataset_type=str(value["dataset_type"]),
            instrument_id=str(value["instrument_id"]),
            session_date=date.fromisoformat(str(value["session_date"])),
            content_hash=str(value["content_hash"]),
            storage_uri=str(value["storage_uri"]),
            dataset_as_of_utc=datetime.fromisoformat(
                str(value["dataset_as_of_utc"]).replace("Z", "+00:00")
            ),
            source_run_id=(
                str(value["source_run_id"]) if value.get("source_run_id") else None
            ),
            created_at_utc=datetime.fromisoformat(
                str(value["created_at_utc"]).replace("Z", "+00:00")
            ),
        )


def projection_event_id(projection_name: str, dataset_id: str) -> str:
    projection = str(projection_name).strip().upper()
    dataset = str(dataset_id).strip()
    if not projection or not dataset:
        raise ValueError("projection_name and dataset_id are required")
    identity = f"{CANONICAL_DATASET_EVENT_VERSION}|{projection}|{dataset}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def canonical_dataset_committed(
    *,
    projection_name: str,
    dataset_id: str,
    dataset_type: str,
    instrument_id: str,
    session_date: date,
    content_hash: str,
    storage_uri: str,
    dataset_as_of_utc: datetime,
    source_run_id: str | None,
    created_at_utc: datetime | None = None,
) -> CanonicalDatasetCommitted:
    projection = str(projection_name).strip().upper()
    return CanonicalDatasetCommitted(
        event_id=projection_event_id(projection, dataset_id),
        projection_name=projection,
        dataset_id=dataset_id,
        dataset_type=dataset_type,
        instrument_id=instrument_id,
        session_date=session_date,
        content_hash=content_hash,
        storage_uri=storage_uri,
        dataset_as_of_utc=dataset_as_of_utc,
        source_run_id=source_run_id,
        created_at_utc=created_at_utc or datetime.now(timezone.utc),
    )


__all__ = [
    "ACTUARIAL_FEATURE_PROJECTION",
    "CANONICAL_DATASET_EVENT_VERSION",
    "CanonicalDatasetCommitted",
    "PHANTOM_OPTION_CHAIN_PROJECTION",
    "ProjectionEventType",
    "canonical_dataset_committed",
    "projection_event_id",
]

