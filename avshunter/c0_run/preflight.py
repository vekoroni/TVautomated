"""Pre-flight gate (pure). Decides whether and in which mode a run may start.

Failure effects (P0-3 §3.4, Option A approved 16 Sep 2026):
- BLOCK: data-safety or integrity problems; the run never starts.
- DOWNGRADE_IN_PRODUCTION: release problems; a PRODUCTION request runs as RESEARCH
  (configuration ``run.production_gate_failure_mode``).
- RECORD_ONLY: recorded in the run context.
"""

from __future__ import annotations

from avshunter.config import ConfigSnapshot
from avshunter.shared.xnys_calendar import SessionPhase

from .model import (
    Action,
    CheckOutcome,
    DecisionClock,
    EnvironmentFacts,
    FailureEffect,
    GateCheck,
    GateVerdict,
    GitFacts,
    OperatorMode,
    PreflightResult,
    ThesisFacts,
)

DOWNGRADE_MODE = "DOWNGRADE_TO_RESEARCH"
REFUSE_MODE = "REFUSE"


def _check(check_id: str, passed: bool | None, effect: FailureEffect, detail: str) -> GateCheck:
    if passed is None:
        outcome = CheckOutcome.NOT_APPLICABLE
    else:
        outcome = CheckOutcome.PASS if passed else CheckOutcome.FAIL
    return GateCheck(check_id, outcome, effect, detail)


def evaluate_preflight(
    *,
    action: Action,
    requested_mode: OperatorMode,
    clock: DecisionClock,
    git: GitFacts,
    environment: EnvironmentFacts,
    snapshot: ConfigSnapshot,
    thesis: ThesisFacts | None,
) -> PreflightResult:
    production_interpreter = str(snapshot.get("run.production_interpreter").value)
    requires_clean = bool(snapshot.get("run.production_requires_clean_tree").value)
    failure_mode = str(snapshot.get("run.production_gate_failure_mode").value)

    checks: list[GateCheck] = []

    # --- BLOCK in any mode -------------------------------------------------
    checks.append(_check(
        "NO_CONCURRENT_DATA_WRITERS",
        not environment.running_data_writers,
        FailureEffect.BLOCK,
        "other pipeline or backfill processes running: " + ", ".join(environment.running_data_writers)
        if environment.running_data_writers else "no other pipeline or backfill process running",
    ))
    checks.append(_check(
        "NO_UNTRACKED_IMPORTS",
        not git.untracked_imported_modules,
        FailureEffect.BLOCK,
        "untracked modules imported by production code: " + ", ".join(git.untracked_imported_modules)
        if git.untracked_imported_modules else "every imported repository module is tracked",
    ))
    if action is Action.BUILD:
        checks.append(_check(
            "ACTION_MATCHES_SESSION_PHASE",
            clock.session_phase is not SessionPhase.REGULAR,
            FailureEffect.BLOCK,
            f"BUILD requested during {clock.session_phase.value}; the evening build runs outside regular hours",
        ))
        checks.append(_check("THESIS_CURRENT_FOR_REVALUE", None, FailureEffect.BLOCK, "not applicable to BUILD"))
    else:
        checks.append(_check(
            "ACTION_MATCHES_SESSION_PHASE",
            clock.session_phase in (SessionPhase.PREMARKET, SessionPhase.REGULAR),
            FailureEffect.BLOCK,
            f"REVALUE requested during {clock.session_phase.value}; morning revaluation needs PREMARKET or REGULAR",
        ))
        if thesis is None or thesis.plan_error:
            detail = "could not resolve the thesis to validate" + (f": {thesis.plan_error}" if thesis and thesis.plan_error else "")
            checks.append(_check("THESIS_CURRENT_FOR_REVALUE", False, FailureEffect.BLOCK, detail))
        else:
            current = (
                thesis.thesis_session is not None
                and thesis.thesis_session == clock.evidence_session
            )
            checks.append(_check(
                "THESIS_CURRENT_FOR_REVALUE",
                current,
                FailureEffect.BLOCK,
                f"thesis {thesis.existing_thesis_id} is for session "
                f"{thesis.thesis_session.isoformat() if thesis.thesis_session else 'UNKNOWN'}; "
                f"last completed session is {clock.evidence_session.isoformat()}",
            ))

    # --- DOWNGRADE in PRODUCTION (Option A) ---------------------------------
    checks.append(_check(
        "CLEAN_TREE",
        git.clean_tree if requires_clean else None,
        FailureEffect.DOWNGRADE_IN_PRODUCTION,
        "clean tree" if git.clean_tree else
        f"modified tracked files: {len(git.modified_tracked_files)}; "
        f"untracked files in production paths: {len(git.untracked_production_files)}",
    ))
    checks.append(_check(
        "RELEASE_TAG_AT_HEAD",
        git.release_id is not None,
        FailureEffect.DOWNGRADE_IN_PRODUCTION,
        f"release {git.release_id}" if git.release_id else "HEAD has no rel-YYYYMMDD-N release tag",
    ))
    checks.append(_check(
        "PRODUCTION_INTERPRETER",
        _same_path(environment.python_executable, production_interpreter),
        FailureEffect.DOWNGRADE_IN_PRODUCTION,
        f"running {environment.python_executable}; production interpreter is {production_interpreter}",
    ))

    # --- verdict ---------------------------------------------------------------
    failed = [c for c in checks if c.outcome is CheckOutcome.FAIL]
    if any(c.effect is FailureEffect.BLOCK for c in failed):
        return PreflightResult(requested_mode, None, GateVerdict.REFUSE, tuple(checks))
    release_failures = [c for c in failed if c.effect is FailureEffect.DOWNGRADE_IN_PRODUCTION]
    if requested_mode is OperatorMode.PRODUCTION and release_failures:
        if failure_mode == REFUSE_MODE:
            return PreflightResult(requested_mode, None, GateVerdict.REFUSE, tuple(checks))
        if failure_mode != DOWNGRADE_MODE:
            raise ValueError(f"unknown run.production_gate_failure_mode {failure_mode!r}")
        return PreflightResult(requested_mode, OperatorMode.RESEARCH, GateVerdict.PROCEED_DOWNGRADED, tuple(checks))
    return PreflightResult(requested_mode, requested_mode, GateVerdict.PROCEED, tuple(checks))


def _same_path(left: str, right: str) -> bool:
    def norm(value: str) -> str:
        return value.replace("/", "\\").rstrip("\\").lower()

    return norm(left) == norm(right)
