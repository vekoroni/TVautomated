"""Run Context value objects (pure)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any

from avshunter.shared.xnys_calendar import SessionPhase


class Action(str, Enum):
    BUILD = "BUILD"        # evening: build thesis from the last completed session
    REVALUE = "REVALUE"    # morning: live revaluation of the published thesis


class OperatorMode(str, Enum):
    PRODUCTION = "PRODUCTION"
    RESEARCH = "RESEARCH"


class CheckOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FailureEffect(str, Enum):
    """What a failed check does to the run."""

    RECORD_ONLY = "RECORD_ONLY"                      # recorded, run unaffected
    DOWNGRADE_IN_PRODUCTION = "DOWNGRADE_IN_PRODUCTION"  # Option A: PRODUCTION -> RESEARCH
    BLOCK = "BLOCK"                                  # run must not start in any mode


class GateVerdict(str, Enum):
    PROCEED = "PROCEED"
    PROCEED_DOWNGRADED = "PROCEED_DOWNGRADED"
    REFUSE = "REFUSE"


@dataclass(frozen=True, slots=True)
class DecisionClock:
    decision_clock_utc: datetime
    session_phase: SessionPhase
    market_session: date | None
    evidence_session: date   # last completed XNYS session


@dataclass(frozen=True, slots=True)
class GitFacts:
    commit_hash: str
    describe: str
    head_tags: tuple[str, ...]
    modified_tracked_files: tuple[str, ...]
    untracked_production_files: tuple[str, ...]
    untracked_imported_modules: tuple[str, ...]

    @property
    def clean_tree(self) -> bool:
        return not self.modified_tracked_files and not self.untracked_production_files

    @property
    def release_id(self) -> str | None:
        releases = sorted(tag for tag in self.head_tags if tag.startswith("rel-"))
        return releases[-1] if releases else None


@dataclass(frozen=True, slots=True)
class EnvironmentFacts:
    python_executable: str
    python_version: str
    host: str
    shell_flags: dict[str, str]          # AVSHUNTER_* seen in the operator's shell
    running_data_writers: tuple[str, ...]  # other pipeline / backfill processes found


@dataclass(frozen=True, slots=True)
class ThesisFacts:
    """Facts about the thesis a REVALUE run would validate (from the legacy dispatcher plan)."""

    existing_thesis_id: str | None
    thesis_session: date | None
    plan_last_completed_session: date | None
    plan_resolved_action: str | None
    plan_error: str | None = None


@dataclass(frozen=True, slots=True)
class GateCheck:
    check_id: str
    outcome: CheckOutcome
    effect: FailureEffect
    detail: str


@dataclass(frozen=True, slots=True)
class PreflightResult:
    requested_mode: OperatorMode
    effective_mode: OperatorMode | None
    verdict: GateVerdict
    checks: tuple[GateCheck, ...]

    @property
    def failed(self) -> tuple[GateCheck, ...]:
        return tuple(check for check in self.checks if check.outcome is CheckOutcome.FAIL)

    def banner(self) -> str:
        if self.verdict is GateVerdict.PROCEED:
            return f"PRE-FLIGHT PASS - {self.effective_mode.value} run"
        reasons = "; ".join(f"{c.check_id}: {c.detail}" for c in self.failed)
        if self.verdict is GateVerdict.PROCEED_DOWNGRADED:
            return (
                "PRE-FLIGHT: PRODUCTION REQUEST DOWNGRADED TO RESEARCH (not production evidence) - "
                + reasons
            )
        return "PRE-FLIGHT REFUSED - run not started - " + reasons


@dataclass(frozen=True, slots=True)
class RunContext:
    run_context_id: str
    action: Action
    requested_mode: OperatorMode
    operator_mode: OperatorMode
    clock: DecisionClock
    git: GitFacts
    environment: EnvironmentFacts
    config_snapshot_id: str
    config_file_hashes: dict[str, str]
    feature_flags: dict[str, str]
    thesis: ThesisFacts | None
    preflight: PreflightResult
    pipeline_version: str
    created_at_utc: datetime
    legacy_entrypoint: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        def convert(value: Any) -> Any:
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, (datetime, date)):
                return value.isoformat()
            if isinstance(value, dict):
                return {k: convert(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [convert(v) for v in value]
            return value

        payload = convert(asdict(self))
        payload["schema_version"] = "avs-run-context-v1"
        payload["release_id"] = self.git.release_id
        payload["clean_tree"] = self.git.clean_tree
        payload["preflight_banner"] = self.preflight.banner()
        return payload
