from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from canonical_data.contracts import DataScope, DatasetRequest, DatasetType
from canonical_data.lifecycle import DropClass as PersistenceDropClass
from canonical_data.lifecycle import LifecycleState
from domain.market_evidence import (
    DropClass,
    EvidenceCandidate,
    EvidenceFreshnessState,
    MarketEvidenceInvariantError,
    TickerLifecycleState,
    decide_evidence_reuse,
    decide_ticker_acquisition_authority,
    evaluate_evidence_freshness,
    validate_lifecycle_transition,
)


NOW = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)


def test_persistence_lifecycle_vocabulary_is_domain_owned() -> None:
    assert LifecycleState is TickerLifecycleState
    assert PersistenceDropClass is DropClass


def test_request_identity_remains_byte_compatible() -> None:
    request = DatasetRequest(
        run_id="RUN-1", invocation_id="INV-1", requesting_stage="options",
        dataset_type=DatasetType.OPTION_CHAIN, instrument_id="aapl",
        session_date=date(2026, 9, 4),
        scope=DataScope(start_date=date(2026, 9, 4), end_date=date(2026, 9, 4)),
        evidence_cutoff_utc=NOW, exchange_calendar="xnys",
        evidence_state="completed_session",
    )
    payload = {
        "run_id": "RUN-1", "invocation_id": "INV-1",
        "requesting_stage": "OPTIONS", "dataset_type": "OPTION_CHAIN",
        "instrument_id": "AAPL", "session_date": "2026-09-04",
        "scope_fingerprint": request.scope.fingerprint,
        "evidence_cutoff_utc": "2026-09-05T12:00:00Z",
        "exchange_calendar": "XNYS", "evidence_state": "COMPLETED_SESSION",
    }
    expected = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert request.request_fingerprint == expected


@pytest.mark.parametrize(
    ("as_of", "expires_at", "limit", "state", "fresh"),
    [
        (NOW - timedelta(seconds=30), None, 60, "FRESH", True),
        (NOW - timedelta(seconds=61), None, 60, "STALE", False),
        (NOW - timedelta(seconds=30), NOW - timedelta(seconds=1), None, "EXPIRED", False),
        (NOW + timedelta(seconds=1), None, None, "FUTURE_DATED", False),
    ],
)
def test_freshness_policy_never_accepts_expired_stale_or_future_evidence(
    as_of, expires_at, limit, state, fresh
) -> None:
    decision = evaluate_evidence_freshness(
        as_of=as_of, now=NOW, freshness_seconds=limit, expires_at=expires_at
    )
    assert decision.state is EvidenceFreshnessState(state)
    assert decision.fresh is fresh


@pytest.mark.parametrize(
    ("overrides", "authorised", "reason"),
    [
        ({"registered": False}, False, "TICKER_NOT_REGISTERED"),
        ({"lifecycle_state": "DROPPED_STAGE"}, False, "STATE_DROPPED_STAGE_BLOCKS_FETCH"),
        ({"lifecycle_stage": "CORE"}, False, "STAGE_MISMATCH_CURRENT_CORE"),
        ({"allowed_capabilities": ("DAILY_OHLCV",)}, False, "CAPABILITY_NOT_AUTHORISED"),
        ({"require_worklist": True, "worklisted": False}, False, "TICKER_NOT_IN_STAGE_WORKLIST"),
        ({"require_worklist": True, "worklisted": True}, True, "AUTHORISED"),
    ],
)
def test_per_ticker_acquisition_authority(overrides, authorised, reason) -> None:
    facts = {
        "lifecycle_state": "ACTIVE_OPTIONS", "lifecycle_stage": "OPTIONS",
        "allowed_capabilities": ("OPTION_CHAIN",), "requested_stage": "OPTIONS",
        "requested_dataset_type": "OPTION_CHAIN", "registered": True,
        "require_worklist": False, "worklisted": False, **overrides,
    }
    decision = decide_ticker_acquisition_authority(**facts)
    assert decision.authorised is authorised
    assert decision.reason == reason


def test_drop_is_terminal_for_acquisition_but_stage_drop_can_be_reactivated_legally() -> None:
    drop_class = validate_lifecycle_transition(
        previous_state="ACTIVE_CORE", new_state="DROPPED_STAGE",
        explicit_reactivation=False, reason_code="NOT_IN_OPTIONS_SCOPE",
    )
    assert drop_class is DropClass.STAGE
    assert validate_lifecycle_transition(
        previous_state="DROPPED_STAGE", new_state="ACTIVE_OPTIONS",
        explicit_reactivation=False, reason_code="",
    ) is DropClass.NONE
    with pytest.raises(MarketEvidenceInvariantError, match="illegal transition"):
        validate_lifecycle_transition(
            previous_state="DROPPED_TERMINAL_DATA", new_state="ACTIVE_OPTIONS",
            explicit_reactivation=False, reason_code="",
        )


def test_reuse_precedence_is_exact_then_superset_then_partial_then_miss() -> None:
    partial = EvidenceCandidate("PARTIAL", False, False, False, True)
    superset = EvidenceCandidate("SUPER", True, False, True, True)
    exact = EvidenceCandidate("EXACT", True, True, True, True)
    assert decide_evidence_reuse((partial, superset, exact)).kind.value == "EXACT_HIT"
    assert decide_evidence_reuse((partial, superset)).kind.value == "SUPERSET_HIT"
    partial_result = decide_evidence_reuse((partial,))
    assert partial_result.kind.value == "PARTIAL_HIT"
    assert partial_result.requires_provider_fetch is True
    assert decide_evidence_reuse(()).kind.value == "MISS"


def test_market_evidence_domain_has_no_infrastructure_dependency() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "domain" / "market_evidence.py"
    ).read_text(encoding="utf-8")
    for forbidden in ("canonical_data", "sqlite", "pandas", "requests", "urllib", "MarketData"):
        assert forbidden not in source

