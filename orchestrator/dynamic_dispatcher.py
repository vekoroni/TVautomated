"""Plan-first dynamic dispatcher for the AVSHUNTER production entry point.

This module owns orchestration only.  It does not calculate a trading signal,
change a frozen thesis, or grant capital authority.  Preview resolution is
read-only; callers must explicitly persist the plan before executing it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
from typing import Callable, Iterable, Mapping

from canonical_data.run_plan import (
    RequestedAction,
    RunPlan,
    RunPlanStore,
    resolve_run_plan,
    write_plan_atomic,
)


@dataclass(frozen=True, slots=True)
class AcceptedThesis:
    """The exact accepted EOD book selected for current validation."""

    pipeline_run_id: str
    thesis_book_id: str
    completed_session: date
    authorised_tickers: tuple[str, ...]
    source_path: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class DispatchResult:
    plan: RunPlan
    executed: bool
    reused: bool
    success: bool
    message: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_latest_pointer(output_dir: Path) -> str | None:
    pointer = output_dir / "latest.json"
    if not pointer.is_file():
        return None
    payload = json.loads(pointer.read_text(encoding="utf-8-sig"))
    run_id = str(payload.get("run_id") or "").strip()
    return run_id or None


def _accepted_book_path(output_dir: Path, run_id: str) -> Path | None:
    run_dir = output_dir / "runs" / run_id
    run_meta = run_dir / "run_meta.json"
    if not run_meta.is_file():
        return None
    meta = json.loads(run_meta.read_text(encoding="utf-8-sig"))
    if str(meta.get("run_status") or "").strip().upper() != "COMPLETED":
        return None
    preferred = (
        run_dir
        / "intelligence_lab"
        / f"final_opportunity_book_{run_id}.csv"
    )
    fallback = (
        run_dir
        / "morning_validation"
        / f"morning_candidates_{run_id}.csv"
    )
    if preferred.is_file():
        return preferred
    return fallback if fallback.is_file() else None


def resolve_accepted_thesis(
    output_dir: Path | str,
    *,
    run_id: str | None = None,
) -> AcceptedThesis | None:
    """Resolve the governed pointer and explicit session fields, read-only.

    Folder modification time and newest-folder ordering are deliberately not
    accepted as authority.  Mixed completed-session dates fail closed.
    """

    root = Path(output_dir)
    selected_run = str(run_id or _read_latest_pointer(root) or "").strip()
    if not selected_run:
        return None
    book = _accepted_book_path(root, selected_run)
    if book is None:
        return None

    tickers: set[str] = set()
    sessions: set[date] = set()
    thesis_ids: set[str] = set()
    with book.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            ticker = str(row.get("ticker") or row.get("Ticker") or "").strip().upper()
            if ticker:
                tickers.add(ticker)
            thesis_id = str(row.get("thesis_id") or "").strip()
            if thesis_id:
                thesis_ids.add(thesis_id)
            raw_session = next(
                (
                    str(row.get(name) or "").strip()
                    for name in (
                        "evidence_session_date",
                        "completed_session",
                        "thesis_session_date",
                        "source_session_date",
                    )
                    if str(row.get(name) or "").strip()
                ),
                "",
            )
            if not raw_session and thesis_id:
                parts = thesis_id.split(":")
                raw_session = next(
                    (part for part in parts if len(part) == 10 and part[4:5] == "-"),
                    "",
                )
            if raw_session:
                try:
                    sessions.add(date.fromisoformat(raw_session[:10]))
                except ValueError as exc:
                    raise ValueError(
                        f"accepted thesis has invalid completed-session value: {raw_session}"
                    ) from exc
    if not tickers or not sessions:
        return None
    if len(sessions) != 1:
        values = ",".join(sorted(item.isoformat() for item in sessions))
        raise ValueError(f"accepted thesis has ambiguous completed sessions: {values}")
    completed = next(iter(sessions))
    content_hash = _sha256(book)
    return AcceptedThesis(
        pipeline_run_id=selected_run,
        thesis_book_id=f"book:{selected_run}:{completed.isoformat()}:{content_hash[:12]}",
        completed_session=completed,
        authorised_tickers=tuple(sorted(tickers)),
        source_path=str(book.resolve()),
        source_sha256=content_hash,
    )


def resolve_dispatch_plan(
    *,
    output_dir: Path | str,
    requested_action: RequestedAction | str,
    as_of_utc: datetime,
    evidence_cutoff_utc: datetime | None = None,
    run_id: str | None = None,
    authorised_tickers: Iterable[str] = (),
    provider_session_finalised: bool = False,
) -> tuple[RunPlan, AcceptedThesis | None]:
    """Return an operator-previewable plan without filesystem mutation."""

    action = RequestedAction(
        str(getattr(requested_action, "value", requested_action)).strip().upper()
    )
    thesis = resolve_accepted_thesis(output_dir, run_id=run_id)
    tickers = tuple(authorised_tickers) or (
        thesis.authorised_tickers if thesis is not None else ()
    )
    generated_run_id = as_of_utc.astimezone(timezone.utc).strftime("%Y%m%d_%H%M%S")
    selected_run_id = run_id
    if action is RequestedAction.VALIDATE and thesis is not None:
        selected_run_id = thesis.pipeline_run_id
    elif action is RequestedAction.AUTO and thesis is not None:
        # First resolve semantic action against the selected frozen thesis.
        # Validation must retain its run id; finalisation/build must mint a new
        # run id so the accepted source run is never overwritten.
        preview = resolve_run_plan(
            requested_action=action,
            as_of_utc=as_of_utc,
            evidence_cutoff_utc=evidence_cutoff_utc,
            existing_thesis_id=thesis.thesis_book_id,
            existing_thesis_session=thesis.completed_session,
            authorised_tickers=tickers,
            provider_session_finalised=provider_session_finalised,
            pipeline_run_id=thesis.pipeline_run_id,
        )
        selected_run_id = (
            thesis.pipeline_run_id
            if preview.resolved_action in {"AUTO", "VALIDATE"}
            else generated_run_id
        )
    elif selected_run_id is None:
        selected_run_id = generated_run_id
    plan = resolve_run_plan(
        requested_action=action,
        as_of_utc=as_of_utc,
        evidence_cutoff_utc=evidence_cutoff_utc,
        existing_thesis_id=thesis.thesis_book_id if thesis else None,
        existing_thesis_session=thesis.completed_session if thesis else None,
        authorised_tickers=tickers,
        provider_session_finalised=provider_session_finalised,
        pipeline_run_id=selected_run_id,
    )
    return plan, thesis


def requested_action_from_cli(
    *,
    evening: bool = False,
    morning: bool = False,
    premarket: bool = False,
    auto: bool = False,
    finalise: bool = False,
    replay: bool = False,
) -> RequestedAction:
    """Map compatibility CLI switches to one unambiguous governed action."""

    selected = [
        (evening, RequestedAction.BUILD_THESIS),
        (morning or premarket, RequestedAction.VALIDATE),
        (auto, RequestedAction.AUTO),
        (finalise, RequestedAction.FINALISE),
        (replay, RequestedAction.REPLAY),
    ]
    actions = [action for enabled, action in selected if enabled]
    if len(actions) != 1:
        raise ValueError("specify exactly one of --evening, --morning, --auto, --finalise or --replay")
    return actions[0]


def operator_summary(plan: RunPlan, thesis: AcceptedThesis | None) -> str:
    reuse = ", ".join(plan.stages_to_reuse) or "none"
    stages = ", ".join(plan.stages_to_run) or "none (reuse only)"
    thesis_text = (
        f"{thesis.pipeline_run_id} / {thesis.completed_session.isoformat()}"
        if thesis
        else "none"
    )
    return (
        f"Dynamic plan {plan.plan_hash[:12]}: requested={plan.requested_action}; "
        f"resolved={plan.resolved_action}; session={plan.session_state}; "
        f"last_completed={plan.last_completed_session}; thesis={thesis_text}; "
        f"run=[{stages}]; reuse=[{reuse}]; requests<=\n"
        f"{plan.estimated_physical_requests}; ceiling={plan.execution_authority_ceiling}"
    ).replace("requests<=\n", "requests<=")


def persist_dispatch_plan(
    plan: RunPlan,
    *,
    output_dir: Path | str,
    plan_store_path: Path | str,
) -> tuple[Path, bool]:
    """Persist the immutable plan before any execution callback is invoked."""

    plan_path = (
        Path(output_dir)
        / "run_plans"
        / f"run_plan_{plan.invocation_id}.json"
    )
    write_plan_atomic(plan, plan_path)
    inserted = RunPlanStore(plan_store_path).persist(plan)
    return plan_path, inserted


def execute_dispatch_plan(
    plan: RunPlan,
    *,
    callbacks: Mapping[str, Callable[[RunPlan], bool]],
) -> DispatchResult:
    """Execute exactly the action named by a previously persisted plan."""

    action = RequestedAction(plan.resolved_action)
    if action is RequestedAction.AUTO and not plan.stages_to_run:
        return DispatchResult(plan, False, True, True, "REUSED_EXISTING_THESIS")
    if action is RequestedAction.REPLAY:
        return DispatchResult(
            plan, False, False, False, "REPLAY_REQUIRES_OFFLINE_REPLAY_RUNNER"
        )
    callback = callbacks.get(action.value)
    if callback is None:
        return DispatchResult(
            plan, False, False, False, f"NO_DISPATCH_CALLBACK_FOR_{action.value}"
        )
    success = bool(callback(plan))
    return DispatchResult(
        plan,
        True,
        False,
        success,
        "DISPATCH_COMPLETE" if success else "DISPATCH_FAILED",
    )
