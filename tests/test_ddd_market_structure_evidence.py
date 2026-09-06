from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from contracts.market_profile_evidence import MarketProfileEvidence as LegacyProfileEvidence
from domain.market_structure_evidence import (
    MARKET_STRUCTURE_AUTHORITY,
    MarketProfileEvidence,
    ProfileEvidenceState,
    market_structure_direction_relationship,
    pin_market_structure_authority,
    profile_evidence_is_usable,
    profile_evidence_state_for_session,
    profile_levels_are_usable,
    transition_market_structure_lifecycle,
)
from market_structure.service import calculate_market_structure_evidence


def _profile(**overrides) -> MarketProfileEvidence:
    values = {
        "evidence_id": "PROFILE-1",
        "ticker": "aapl",
        "session_date": "2026-09-04",
        "evidence_state": "COMPLETED_SESSION",
        "interval_minutes": 5,
        "poc": 100.0,
        "value_area_low": 98.0,
        "value_area_high": 102.0,
        "profile_type": "SINGLE_DISTRIBUTION",
        "quality": "FIVE_MINUTE_ESTIMATED",
        "completeness_status": "COMPLETE",
        "input_dataset_ids": ("BAR-1",),
        "input_hashes": ("HASH-1",),
        "observed_at_utc": "2026-09-04T20:00:00Z",
        "calculated_at_utc": "2026-09-04T20:01:00Z",
        "algorithm_version": "completed_market_profile_v1",
    }
    values.update(overrides)
    return MarketProfileEvidence(**values)


@pytest.mark.parametrize(
    ("session_state", "expected"),
    [
        ("PREMARKET", ProfileEvidenceState.PENDING_MARKET_OPEN),
        ("REGULAR", ProfileEvidenceState.DEVELOPING_SESSION),
        ("AFTER_HOURS", ProfileEvidenceState.PARTIAL_SESSION),
        ("CLOSED", ProfileEvidenceState.NOT_EVALUATED),
    ],
)
def test_session_state_has_one_profile_evidence_translation(session_state, expected) -> None:
    assert profile_evidence_state_for_session(session_state) is expected


def test_legacy_contract_is_the_domain_contract() -> None:
    assert LegacyProfileEvidence is MarketProfileEvidence


def test_profile_usability_requires_complete_ordered_positive_levels() -> None:
    assert profile_levels_are_usable(
        poc=100.0, value_area_low=98.0, value_area_high=102.0
    )
    assert not profile_levels_are_usable(
        poc=None, value_area_low=None, value_area_high=None
    )
    assert not profile_levels_are_usable(
        poc=100.0, value_area_low=103.0, value_area_high=104.0
    )
    assert profile_evidence_is_usable(
        evidence_state="COMPLETED_SESSION",
        completeness_status="COMPLETE",
        quality="FIVE_MINUTE_ESTIMATED",
        poc=100.0,
        value_area_low=98.0,
        value_area_high=102.0,
    )
    assert not profile_evidence_is_usable(
        evidence_state="PARTIAL_SESSION",
        completeness_status="COMPLETE",
        quality="FIVE_MINUTE_ESTIMATED",
        poc=100.0,
        value_area_low=98.0,
        value_area_high=102.0,
    )


def test_profile_evidence_pins_advisory_authority() -> None:
    evidence = _profile(
        authority="CAPITAL_AUTHORITY",
        can_grant_capital=True,
        can_reverse_direction=True,
    )
    assert evidence.usable
    assert evidence.authority == MARKET_STRUCTURE_AUTHORITY
    assert evidence.can_grant_capital is False
    assert evidence.can_reverse_direction is False
    assert pin_market_structure_authority(
        {
            "ms_authority": "CAPITAL_AUTHORITY",
            "ms_can_grant_capital": True,
            "ms_can_reverse_direction": True,
        }
    ) == {
        "ms_authority": "ADVISORY_ONLY",
        "ms_can_grant_capital": False,
        "ms_can_reverse_direction": False,
    }


@pytest.mark.parametrize(
    ("direction", "structure", "expected"),
    [
        ("CALL", "ABOVE", "ALIGNED"),
        ("CALL", "BELOW", "CONFLICTING"),
        ("PUT", "BELOW", "ALIGNED"),
        ("PUT", "ABOVE", "CONFLICTING"),
    ],
)
def test_relationship_is_directionally_symmetric(direction, structure, expected) -> None:
    assert market_structure_direction_relationship(
        governed_direction=direction,
        structure_direction=structure,
        lifecycle="MS_ACCEPTED",
        quality="FIVE_MINUTE_ESTIMATED",
    ) == expected


def test_insufficient_profile_cannot_claim_alignment() -> None:
    assert market_structure_direction_relationship(
        governed_direction="CALL",
        structure_direction="ABOVE",
        lifecycle="MS_ACCEPTED",
        quality="INSUFFICIENT_DATA",
    ) == "INSUFFICIENT_DATA"


def test_lifecycle_transition_is_irreversible_after_failure() -> None:
    assert transition_market_structure_lifecycle(
        prior="MS_FAILED",
        detected=True,
        accepted=True,
        repair_pct=0.0,
        intact_repair=0.2,
        failed_repair=0.6,
    ) == "MS_FAILED"
    assert transition_market_structure_lifecycle(
        prior=None,
        detected=True,
        accepted=False,
        repair_pct=0.0,
        intact_repair=0.2,
        failed_repair=0.6,
    ) == "MS_DEVELOPING"


def test_service_keeps_missing_levels_null_and_authority_advisory() -> None:
    bars = pd.DataFrame(
        [{
            "timestamp_utc": "2026-09-04T13:30:00Z",
            "open": 100.0,
            "high": 100.5,
            "low": 99.5,
            "close": 100.1,
            "volume": 1_000.0,
            "interval_minutes": 5,
            "session_segment": "REGULAR",
        }]
    )
    evidence = calculate_market_structure_evidence(
        ticker="AAPL",
        session_date=date(2026, 9, 4),
        run_id="DDD-PHASE6",
        bars=bars,
        exchange_tick=0.01,
        atr14=2.0,
        regular_open_utc=datetime(2026, 9, 4, 13, 30, tzinfo=timezone.utc),
        governed_direction="CALL",
        input_dataset_ids=("BAR-1",),
        input_hashes=("HASH-1",),
    )
    assert evidence["ms_quality_class"] == "INSUFFICIENT_DATA"
    assert evidence["ms_developing_poc"] is None
    assert evidence["ms_final_poc"] is None
    assert evidence["ms_value_area_low"] is None
    assert evidence["ms_value_area_high"] is None
    assert evidence["ms_direction_relationship"] == "INSUFFICIENT_DATA"
    assert evidence["ms_authority"] == "ADVISORY_ONLY"
    assert evidence["ms_can_grant_capital"] is False
    assert evidence["ms_can_reverse_direction"] is False


def test_domain_module_has_no_infrastructure_dependency() -> None:
    source = (
        Path(__file__).parents[1] / "domain" / "market_structure_evidence.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "import pandas",
        "import numpy",
        "canonical_data",
        "MarketData",
        "requests",
        "sqlite3",
        "Path(",
    ):
        assert forbidden not in source
