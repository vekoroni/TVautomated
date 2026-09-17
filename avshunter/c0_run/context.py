"""Run context assembly (pure)."""

from __future__ import annotations

from datetime import datetime
import hashlib

from avshunter import __version__
from avshunter.config import ConfigSnapshot
from avshunter.config.model import canonical_json

from .model import (
    Action,
    DecisionClock,
    EnvironmentFacts,
    GitFacts,
    OperatorMode,
    PreflightResult,
    RunContext,
    ThesisFacts,
)

FLAG_KEYS = {
    "AVSHUNTER_CANONICAL_DATA_ENABLED": "legacy.flags.canonical_data_enabled",
    "AVSHUNTER_CANONICAL_WRITE_THROUGH": "legacy.flags.canonical_write_through",
    "AVSHUNTER_CDS2_OHLCV_MODE": "legacy.flags.cds2_ohlcv_mode",
}
DYNAMIC_FLAGS_KEY = "legacy.flags.dynamic_session"


def _flag_text(value: object) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def resolve_legacy_flags(snapshot: ConfigSnapshot) -> dict[str, str]:
    """Environment values the launcher sets for the legacy orchestrator, from configuration only."""
    flags = {env: _flag_text(snapshot.get(key).value) for env, key in FLAG_KEYS.items()}
    dynamic = snapshot.get(DYNAMIC_FLAGS_KEY).value
    for env_name, value in sorted(dict(dynamic).items()):
        flags[str(env_name)] = _flag_text(value)
    return flags


def run_context_id(clock: DecisionClock, action: Action, git: GitFacts, snapshot_id: str) -> str:
    stamp = clock.decision_clock_utc.strftime("%Y%m%d-%H%M%S")
    digest = hashlib.sha256(
        canonical_json([clock.decision_clock_utc.isoformat(), action.value, git.commit_hash, snapshot_id]).encode("utf-8")
    ).hexdigest()[:8]
    return f"AVS-{stamp}-{action.value}-{digest}"


def build_run_context(
    *,
    action: Action,
    requested_mode: OperatorMode,
    clock: DecisionClock,
    git: GitFacts,
    environment: EnvironmentFacts,
    snapshot: ConfigSnapshot,
    config_file_hashes: dict[str, str],
    thesis: ThesisFacts | None,
    preflight: PreflightResult,
    created_at_utc: datetime,
    legacy_entrypoint: tuple[str, ...],
) -> RunContext:
    return RunContext(
        run_context_id=run_context_id(clock, action, git, snapshot.snapshot_id),
        action=action,
        requested_mode=requested_mode,
        operator_mode=preflight.effective_mode or requested_mode,
        clock=clock,
        git=git,
        environment=environment,
        config_snapshot_id=snapshot.snapshot_id,
        config_file_hashes=dict(config_file_hashes),
        feature_flags=resolve_legacy_flags(snapshot),
        thesis=thesis,
        preflight=preflight,
        pipeline_version=__version__,
        created_at_utc=created_at_utc,
        legacy_entrypoint=legacy_entrypoint,
    )
