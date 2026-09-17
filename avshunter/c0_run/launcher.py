"""Single entry point for evening and morning runs (P0-3 increment 1).

  python -m avshunter preflight --action BUILD|REVALUE [--mode PRODUCTION|RESEARCH] [--as-of-utc ...]
  python -m avshunter run       --action BUILD|REVALUE [--mode PRODUCTION|RESEARCH]

Increment 1 wraps the legacy orchestrator unchanged: the launcher establishes the
run context, applies the pre-flight gate, sets legacy flags from configuration,
writes the context and completion records, and then runs
``intelligent_orchestrator.py --evening|--morning``.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from avshunter.config import ConfigError
from avshunter.config.adapters import load_registry

from .adapters import legacy
from .adapters.clock import parse_as_of, wall_clock_utc
from .adapters.environment import collect_environment_facts
from .adapters.git import collect_git_facts
from .adapters.storage import legacy_config_hashes, write_completion, write_context
from .clock import build_decision_clock
from .context import build_run_context, resolve_legacy_flags
from .model import Action, GateVerdict, OperatorMode
from .preflight import evaluate_preflight

REPO = Path(__file__).resolve().parents[2]
EXIT_REFUSED = 3
EXIT_CONFIG = 2


def _config_session(action: Action, clock) -> object:
    """Configuration applies to the session a run belongs to."""
    if action is Action.BUILD:
        return clock.evidence_session
    return clock.market_session


def _print_summary(context, context_path: Path, conflicts: dict[str, tuple[str, str]]) -> None:
    print("=" * 78)
    print(context.preflight.banner())
    print("=" * 78)
    print(f"run context      : {context.run_context_id}")
    print(f"action / mode    : {context.action.value} requested {context.requested_mode.value} -> "
          f"{context.operator_mode.value if context.preflight.verdict is not GateVerdict.REFUSE else 'NOT STARTED'}")
    print(f"decision clock   : {context.clock.decision_clock_utc.isoformat()} "
          f"({context.clock.session_phase.value}); evidence session {context.clock.evidence_session.isoformat()}")
    print(f"code             : {context.git.describe} release={context.git.release_id} clean={context.git.clean_tree}")
    print(f"interpreter      : {context.environment.python_executable} (Python {context.environment.python_version})")
    print(f"config snapshot  : {context.config_snapshot_id[:16]}")
    if context.thesis is not None:
        print(f"thesis           : {context.thesis.existing_thesis_id} session={context.thesis.thesis_session}")
    for check in context.preflight.checks:
        print(f"  [{check.outcome.value:<14}] {check.check_id:<30} {check.detail}")
    for name, (shell_value, configured) in sorted(conflicts.items()):
        print(f"  WARNING shell {name}={shell_value!r} overridden by configuration {configured!r}")
    print(f"context written  : {context_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m avshunter")
    parser.add_argument("command", choices=["preflight", "run"])
    parser.add_argument("--action", required=True, choices=[a.value for a in Action])
    parser.add_argument("--mode", default=OperatorMode.PRODUCTION.value, choices=[m.value for m in OperatorMode])
    parser.add_argument("--as-of-utc", default=None,
                        help="decision clock for preflight checks (testing); live runs use the wall clock")
    args = parser.parse_args(argv)

    action = Action(args.action)
    requested_mode = OperatorMode(args.mode)
    if args.command == "run" and args.as_of_utc:
        print("--as-of-utc is only supported with preflight in increment 1", file=sys.stderr)
        return EXIT_CONFIG
    created_at = wall_clock_utc()
    instant = parse_as_of(args.as_of_utc) if args.as_of_utc else created_at
    clock = build_decision_clock(instant)

    try:
        registry = load_registry()
        session = _config_session(action, clock)
        if session is None:
            raise ConfigError(f"{action.value} at {instant.isoformat()} is outside any XNYS session")
        snapshot = registry.resolve(session)
        production_paths = list(snapshot.get("run.production_code_paths").value)
        flags = resolve_legacy_flags(snapshot)
    except ConfigError as error:
        print(f"CONFIG ERROR - run not started: {error}", file=sys.stderr)
        return EXIT_CONFIG

    git = collect_git_facts(REPO, production_paths)
    environment = collect_environment_facts()
    child_env = legacy.child_environment(legacy.base_environment(), flags, {})
    thesis = (
        legacy.resolve_revalue_thesis(REPO, instant, child_env) if action is Action.REVALUE else None
    )
    preflight = evaluate_preflight(
        action=action, requested_mode=requested_mode, clock=clock, git=git,
        environment=environment, snapshot=snapshot, thesis=thesis,
    )
    command = legacy.legacy_command(action)
    context = build_run_context(
        action=action, requested_mode=requested_mode, clock=clock, git=git, environment=environment,
        snapshot=snapshot, config_file_hashes=legacy_config_hashes(REPO), thesis=thesis,
        preflight=preflight, created_at_utc=created_at, legacy_entrypoint=command,
    )
    context_path = write_context(REPO, context, snapshot)
    conflicts = {
        name: (value, flags[name])
        for name, value in environment.shell_flags.items()
        if name in flags and value != flags[name]
    }
    _print_summary(context, context_path, conflicts)

    if preflight.verdict is GateVerdict.REFUSE:
        return EXIT_REFUSED
    if args.command == "preflight":
        return 0

    run_env = legacy.child_environment(legacy.base_environment(), flags, {
        "AVSHUNTER_RUN_CONTEXT": str(context_path),
        "AVSHUNTER_RUN_CONTEXT_ID": context.run_context_id,
        "AVSHUNTER_OPERATOR_MODE": context.operator_mode.value,
        "AVSHUNTER_DECISION_CLOCK_UTC": context.clock.decision_clock_utc.isoformat(),
    })
    exit_code = legacy.run_legacy(REPO, command, run_env)
    completion = {
        "schema_version": "avs-run-completion-v1",
        "run_context_id": context.run_context_id,
        "operator_mode": context.operator_mode.value,
        "legacy_exit_code": exit_code,
        "legacy_run": legacy.latest_legacy_run(REPO),
        "note": "RESEARCH marking inside legacy run records arrives with P0-3 increment 2"
        if context.operator_mode is OperatorMode.RESEARCH else "",
    }
    completion_path = write_completion(REPO, context, completion)
    print(f"legacy exit code : {exit_code}; completion written: {completion_path}")
    return exit_code
