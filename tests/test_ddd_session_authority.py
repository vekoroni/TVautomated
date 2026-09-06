from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from domain.session_authority import (
    EvidenceAuthority,
    EvidenceMode,
    EvidenceState,
    SessionFacts,
    SessionPhase,
    resolve_session_authority,
)
from orchestrator.session_authority_adapter import resolve_pipeline_session_authority


@pytest.mark.parametrize("phase", list(SessionPhase))
def test_thesis_build_always_uses_last_completed_session(phase: SessionPhase) -> None:
    facts = SessionFacts(
        phase=phase,
        last_completed_session=date(2026, 9, 3),
        current_session=date(2026, 9, 4),
    )

    decision = resolve_session_authority(requested_mode="AUTO", facts=facts)

    assert decision.resolved_mode is EvidenceMode.COMPLETED
    assert decision.evidence_state is EvidenceState.COMPLETED_SESSION
    assert decision.evidence_session == date(2026, 9, 3)
    assert decision.provider_query_end == date(2026, 9, 3)
    assert decision.include_developing_bar is False
    assert decision.authority_ceiling is EvidenceAuthority.EOD_PREPARED
    assert decision.legacy_data_mode == "EOD"


def test_eod_is_a_compatibility_alias_for_completed_evidence() -> None:
    decision = resolve_session_authority(
        requested_mode="EOD",
        facts=SessionFacts(
            phase=SessionPhase.REGULAR,
            last_completed_session=date(2026, 9, 3),
            current_session=date(2026, 9, 4),
        ),
    )
    assert decision.resolved_mode is EvidenceMode.COMPLETED
    assert decision.evidence_session == date(2026, 9, 3)


def test_latest_is_review_only_and_does_not_advance_provider_daily_boundary() -> None:
    decision = resolve_session_authority(
        requested_mode="LATEST",
        facts=SessionFacts(
            phase=SessionPhase.REGULAR,
            last_completed_session=date(2026, 9, 3),
            current_session=date(2026, 9, 4),
        ),
    )
    assert decision.resolved_mode is EvidenceMode.CURRENT
    assert decision.evidence_session == date(2026, 9, 4)
    assert decision.provider_query_end == date(2026, 9, 3)
    assert decision.include_developing_bar is True
    assert decision.authority_ceiling is EvidenceAuthority.REVIEW_ONLY
    assert decision.legacy_data_mode == "LATEST"


def test_weekend_auto_resolves_friday_completed_session() -> None:
    decision = resolve_pipeline_session_authority(
        requested_mode="AUTO",
        as_of_utc=datetime(2026, 9, 5, 12, tzinfo=timezone.utc),
    )
    assert decision.evidence_session == date(2026, 9, 4)
    assert decision.evidence_state is EvidenceState.COMPLETED_SESSION


def test_naive_clock_is_rejected_at_adapter_boundary() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        resolve_pipeline_session_authority(
            requested_mode="AUTO", as_of_utc=datetime(2026, 9, 4, 12)
        )


def test_legacy_evening_command_reaches_preflight_during_regular_session(
    monkeypatch, tmp_path
) -> None:
    import intelligent_orchestrator as orchestrator

    reached_preflight = {"value": False}

    monkeypatch.setattr(orchestrator.cfg, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(orchestrator, "load_scanner_manifest", lambda: {})
    monkeypatch.setattr(orchestrator, "load_manual_ticker_upload", lambda: {})
    monkeypatch.setattr(orchestrator, "merge_scanner_inputs", lambda *_: {})
    monkeypatch.setattr(
        orchestrator, "build_augmented_universe", lambda *_: tmp_path / "universe.csv"
    )
    monkeypatch.setattr(orchestrator, "write_scanner_context", lambda *_: None)
    monkeypatch.setattr(orchestrator, "run_dropoff_audit_checkpoint", lambda *_: None)

    def fail_preflight(**_kwargs):
        reached_preflight["value"] = True
        return False, None

    monkeypatch.setattr(orchestrator, "run_preflight_checks", fail_preflight)
    result = orchestrator.evening_workflow(
        run_id="DDD_REGULAR_SESSION_TEST",
        data_mode="AUTO",
        as_of_utc=datetime(2026, 9, 4, 15, 42, tzinfo=timezone.utc),
    )

    assert result is False
    assert reached_preflight["value"] is True
