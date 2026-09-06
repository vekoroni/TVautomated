from __future__ import annotations

import json
from pathlib import Path

import pytest

from contracts.dynamic_session_contract import (
    DynamicSessionFeatureFlags,
    FEATURE_FLAG_ENV_VARS,
    governed_runtime_profile_summary,
    load_governed_runtime_profile,
)
from orchestrator.dynamic_dispatcher import requested_action_from_cli
from orchestrator.dynamic_release import (
    GateEvidence,
    LIVE_GATE_IDS,
    REQUIRED_GATE_IDS,
    ReleaseStatus,
    assess_release,
    controlled_live_cycle_environment,
)


ROOT = Path(__file__).resolve().parents[1]


def _clear_runtime_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in FEATURE_FLAG_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("AVSHUNTER_DYNAMIC_RELEASE_DISABLE_ALL", raising=False)


def test_checked_in_profile_enables_explicit_cycle_and_withholds_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_overrides(monkeypatch)
    profile = load_governed_runtime_profile()
    flags = DynamicSessionFeatureFlags.from_environment()
    assert profile["status"] == "CONTROLLED_LIVE_CYCLE"
    assert all(
        value is True
        for name, value in profile["feature_flags"].items()
        if name != "AVSHUNTER_DYNAMIC_AUTO_ENABLED"
    )
    assert flags.plan_engine
    assert flags.completed_thesis_builder
    assert flags.validation_gate
    assert flags.profile_lifecycle
    assert flags.lab_dynamic_view
    assert flags.interpreter_dynamic_resolver
    assert flags.decision_outcome_ledger
    assert flags.completed_profile_stage
    assert not flags.auto_dispatcher


def test_phase0_explicit_mapping_contract_remains_disabled() -> None:
    flags = DynamicSessionFeatureFlags.from_environment({})
    assert not any(getattr(flags, field) for field in flags.__slots__)


def test_master_rollback_disables_entire_runtime_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_overrides(monkeypatch)
    monkeypatch.setenv("AVSHUNTER_DYNAMIC_RELEASE_DISABLE_ALL", "1")
    flags = DynamicSessionFeatureFlags.from_environment()
    assert not any(getattr(flags, field) for field in flags.__slots__)


def test_environment_can_disable_but_cannot_escalate_governed_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_overrides(monkeypatch)
    monkeypatch.setenv("AVSHUNTER_DYNAMIC_VALIDATION_ENABLED", "0")
    assert not DynamicSessionFeatureFlags.from_environment().validation_gate
    monkeypatch.setenv("AVSHUNTER_DYNAMIC_AUTO_ENABLED", "1")
    with pytest.raises(RuntimeError, match="exceed the governed runtime profile"):
        DynamicSessionFeatureFlags.from_environment()


def test_runtime_profile_is_complete_atomic_and_hash_identified() -> None:
    profile = load_governed_runtime_profile()
    summary = governed_runtime_profile_summary()
    assert set(profile["feature_flags"]) == set(FEATURE_FLAG_ENV_VARS)
    assert set(profile["rollback_feature_flags"]) == set(FEATURE_FLAG_ENV_VARS)
    assert not any(profile["rollback_feature_flags"].values())
    assert profile["feature_flags"]["AVSHUNTER_LAB_DYNAMIC_VIEW_ENABLED"] is (
        profile["feature_flags"]["AVSHUNTER_INTERPRETER_DYNAMIC_RESOLVER_ENABLED"]
    )
    assert len(summary["sha256"]) == 64
    assert Path(summary["path"]).resolve() == (
        ROOT / "contracts" / "dynamic_session_runtime_v1.json"
    ).resolve()


def test_legacy_commands_map_to_governed_explicit_actions() -> None:
    assert requested_action_from_cli(evening=True).value == "BUILD_THESIS"
    assert requested_action_from_cli(morning=True).value == "VALIDATE"


def test_release_guard_allows_supervised_cycle_after_offline_acceptance(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "offline.json"
    evidence_path.write_text(json.dumps({"pass": True}), encoding="utf-8")
    from orchestrator.dynamic_release import EvidenceArtifact

    artifact = EvidenceArtifact.from_path(evidence_path, repo_root=tmp_path)
    evidence = tuple(
        GateEvidence(gate, "PASS", (artifact,), "verified")
        for gate in REQUIRED_GATE_IDS
        if gate not in LIVE_GATE_IDS
    )
    assessment = assess_release(evidence, repo_root=tmp_path)
    assert assessment.status == ReleaseStatus.READY_FOR_LIVE_CYCLE.value
    environment = controlled_live_cycle_environment(assessment)
    assert environment["AVSHUNTER_DYNAMIC_AUTO_ENABLED"] == "0"
    assert all(
        value == "1"
        for name, value in environment.items()
        if name != "AVSHUNTER_DYNAMIC_AUTO_ENABLED"
    )


def test_orchestrator_routes_normal_evening_through_runtime_flags() -> None:
    source = (ROOT / "intelligent_orchestrator.py").read_text(encoding="utf-8")
    assert "if dynamic_requested or runtime_flags.plan_engine:" in source
    assert 'os.environ.get("AVSHUNTER_DYNAMIC_PLAN_ENABLED"' not in source
