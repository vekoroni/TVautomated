"""Prediction identity, evidence-session resolution and provenance (pure)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import re
from typing import Any, Mapping

from avshunter.shared.xnys_calendar import is_xnys_session, session_bounds, session_state, xnys_sessions_between

from .model import Geometry

ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
RUN_ID = re.compile(r"(\d{8})_(\d{6})")


@dataclass(frozen=True, slots=True)
class EvidenceSession:
    session: date | None
    source: str   # THESIS_ID | RUN_META | DERIVED_FROM_RUN_ID | UNRESOLVED


def session_from_thesis_id(thesis_id: Any) -> date | None:
    for part in str(thesis_id or "").split(":"):
        if ISO_DATE.fullmatch(part):
            try:
                value = date.fromisoformat(part)
            except ValueError:
                return None
            return value if is_xnys_session(value) else None
    return None


def run_start_utc(run_id: str) -> datetime | None:
    match = RUN_ID.fullmatch(run_id)
    if not match:
        return None
    return datetime.strptime("".join(match.groups()) + "+0000", "%Y%m%d%H%M%S%z")


def resolve_evidence_session(thesis_id: Any, run_meta: Mapping[str, Any], run_id: str) -> EvidenceSession:
    from_thesis = session_from_thesis_id(thesis_id)
    if from_thesis:
        return EvidenceSession(from_thesis, "THESIS_ID")
    meta_value = str(run_meta.get("session_date") or "")
    if ISO_DATE.fullmatch(meta_value) and is_xnys_session(date.fromisoformat(meta_value)):
        return EvidenceSession(date.fromisoformat(meta_value), "RUN_META")
    started = run_start_utc(run_id)
    if started is None:
        return EvidenceSession(None, "UNRESOLVED")
    _, _, last_completed = session_state(started)
    return EvidenceSession(last_completed, "DERIVED_FROM_RUN_ID")


def provenance_class(book_mtime_utc: datetime, evidence_session: date, first_session: date | None) -> str:
    """RECORDED_AT_RUN only if the book existed before the close of the first outcome session."""
    if first_session is None:
        return "RECORDED_AT_RUN"   # no outcome session has happened yet
    _, close_utc = session_bounds(first_session)
    return "RECORDED_AT_RUN" if book_mtime_utc < close_utc else "RETROSPECTIVE_UNVERIFIED"


def prediction_id(ticker: str, geometry: Geometry, evidence_session: date | None) -> str:
    payload = [
        ticker.upper(), geometry.direction_text.upper(), evidence_session.isoformat() if evidence_session else None,
        geometry.reference_price, geometry.invalidation_price, geometry.target_price, geometry.contract_symbol,
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]


def sessions_observed_between(evidence_session: date, as_of: date, window: int) -> int:
    return min(window, xnys_sessions_between(evidence_session, as_of))
