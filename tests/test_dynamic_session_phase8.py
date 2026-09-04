from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path

import pytest

from canonical_data.run_plan import RequestedAction, resolve_run_plan
from contracts.dynamic_session_contract import (
    DynamicSessionFeatureFlags,
    FEATURE_FLAG_ENV_VARS,
)
from orchestrator.dynamic_release import (
    EvidenceArtifact,
    GateEvidence,
    LIVE_GATE_IDS,
    PromotionStage,
    REQUIRED_GATE_IDS,
    ReleaseStatus,
    assess_release,
    load_evidence,
    promotion_environment,
    write_assessment_atomic,
)
from scripts import release_baseline


def _artifact(tmp_path: Path, name: str = "evidence.json") -> EvidenceArtifact:
    path = tmp_path / name
    path.write_text(json.dumps({"passed": True}), encoding="utf-8")
    return EvidenceArtifact.from_path(path, repo_root=tmp_path)


def _evidence(tmp_path: Path, *, omit: set[str] | None = None):
    artifact = _artifact(tmp_path)
    return tuple(
        GateEvidence(gate, "PASS", (artifact,), "verified")
        for gate in REQUIRED_GATE_IDS
        if gate not in (omit or set())
    )


@pytest.mark.parametrize(
    ("instant", "state", "action", "has_developing_profile"),
    [
        (datetime(2026, 9, 8, 7, 0, tzinfo=timezone.utc), "CLOSED", "AUTO", False),
        (datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc), "PREMARKET", "VALIDATE", False),
        (datetime(2026, 9, 8, 14, 0, tzinfo=timezone.utc), "REGULAR", "VALIDATE", True),
        (datetime(2026, 9, 8, 21, 0, tzinfo=timezone.utc), "AFTER_HOURS", "VALIDATE", False),
        (datetime(2026, 9, 12, 14, 0, tzinfo=timezone.utc), "CLOSED", "BUILD_THESIS", False),
    ],
)
def test_fixed_cutoff_matrix_is_deterministic(
    instant: datetime, state: str, action: str, has_developing_profile: bool
) -> None:
    kwargs = dict(
        requested_action="AUTO",
        as_of_utc=instant,
        existing_thesis_id="book-1",
        existing_thesis_session=date(2026, 9, 4),
        authorised_tickers=("AAPL", "MSFT"),
        pipeline_run_id="run-1",
    )
    first = resolve_run_plan(**kwargs)
    second = resolve_run_plan(**kwargs)
    assert first.plan_hash == second.plan_hash
    assert first.session_state == state
    assert first.resolved_action == action
    assert ("DEVELOPING_MARKET_PROFILE" in first.stages_to_run) is has_developing_profile
    if instant.weekday() >= 5:
        assert first.current_session is None
        assert first.last_completed_session == "2026-09-11"


def test_after_hours_provider_confirmation_is_required_for_finalisation() -> None:
    kwargs = dict(
        requested_action="AUTO",
        as_of_utc=datetime(2026, 9, 8, 21, 0, tzinfo=timezone.utc),
        existing_thesis_id="book-1",
        existing_thesis_session=date(2026, 9, 4),
        authorised_tickers=("AAPL",),
        pipeline_run_id="run-1",
    )
    assert resolve_run_plan(**kwargs).resolved_action == "VALIDATE"
    assert resolve_run_plan(**kwargs, provider_session_finalised=True).resolved_action == "FINALISE"


def test_exact_cache_hit_means_zero_requests_and_partial_fetches_missing_only() -> None:
    common = dict(
        requested_action="BUILD_THESIS",
        as_of_utc=datetime(2026, 9, 8, 22, 0, tzinfo=timezone.utc),
        authorised_tickers=("AAPL", "MSFT", "NVDA"),
        pipeline_run_id="run-new",
    )
    warm = resolve_run_plan(
        **common,
        cache_coverage={"DAILY_OHLCV": 3, "INTRADAY_BAR": 3, "OPTION_CHAIN": 3},
    )
    partial = resolve_run_plan(
        **common,
        cache_coverage={"DAILY_OHLCV": 2, "INTRADAY_BAR": 1, "OPTION_CHAIN": 0},
    )
    assert warm.estimated_physical_requests == 0
    assert partial.estimated_physical_requests == 1 + 2 + 3


def test_replay_has_no_provider_requirements_or_capital_authority() -> None:
    plan = resolve_run_plan(
        requested_action=RequestedAction.REPLAY,
        as_of_utc=datetime(2026, 9, 8, 14, 0, tzinfo=timezone.utc),
        evidence_cutoff_utc=datetime(2026, 9, 4, 20, 0, tzinfo=timezone.utc),
        authorised_tickers=("AAPL",),
    )
    assert plan.datasets_required == ()
    assert plan.estimated_physical_requests == 0
    assert plan.execution_authority_ceiling == "RESEARCH_ONLY"


def test_release_is_only_live_ready_when_offline_gates_pass(tmp_path: Path) -> None:
    assessment = assess_release(_evidence(tmp_path, omit=set(LIVE_GATE_IDS)), repo_root=tmp_path)
    assert assessment.status == ReleaseStatus.READY_FOR_LIVE_CYCLE.value
    assert not assessment.promotable
    with pytest.raises(RuntimeError, match="promotion refused"):
        promotion_environment(assessment, PromotionStage.AUTO)


def test_complete_hash_bound_evidence_allows_staged_promotion(tmp_path: Path) -> None:
    assessment = assess_release(_evidence(tmp_path), repo_root=tmp_path)
    assert assessment.promotable
    plan_only = promotion_environment(assessment, PromotionStage.PLAN_ONLY)
    auto = promotion_environment(assessment, PromotionStage.AUTO)
    assert plan_only["AVSHUNTER_DYNAMIC_PLAN_ENABLED"] == "1"
    assert sum(value == "1" for value in plan_only.values()) == 1
    assert set(auto) == set(FEATURE_FLAG_ENV_VARS)
    assert all(value == "1" for value in auto.values())


def test_missing_or_changed_release_artifact_fails_closed(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    (tmp_path / "evidence.json").write_text("changed", encoding="utf-8")
    assessment = assess_release(evidence, repo_root=tmp_path)
    assert assessment.status == ReleaseStatus.NOT_READY.value
    assert assessment.invalid_artifacts


def test_release_evidence_roundtrip_and_atomic_assessment(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    evidence_path = tmp_path / "release_evidence.json"
    evidence_path.write_text(
        json.dumps({"gates": [
            {
                "gate_id": item.gate_id,
                "status": item.status,
                "detail": item.detail,
                "artifacts": [
                    {"path": artifact.path, "sha256": artifact.sha256}
                    for artifact in item.artifacts
                ],
            }
            for item in evidence
        ]}),
        encoding="utf-8",
    )
    assessment = assess_release(load_evidence(evidence_path), repo_root=tmp_path)
    output = write_assessment_atomic(assessment, tmp_path / "assessment.json")
    assert output.is_file()
    assert not output.with_suffix(".json.tmp").exists()
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == assessment.status


def test_dynamic_features_remain_disabled_until_controlled_promotion() -> None:
    flags = DynamicSessionFeatureFlags.from_environment({})
    assert not any(getattr(flags, field) for field in flags.__slots__)


def test_restore_verify_cli_returns_success_for_a_passed_verification(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        release_baseline,
        "verify_backup",
        lambda _path: {"passed": True, "restore_verification": "not-required"},
    )
    assert release_baseline.main(
        ["--backup-dir", str(tmp_path), "--repo", str(tmp_path), "--verify-only"]
    ) == 0
    assert '"passed": true' in capsys.readouterr().out.lower()
