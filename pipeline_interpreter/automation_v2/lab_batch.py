"""Lab-driven batch launcher for the stateless ticker workflow."""

from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

from .e2e_orchestrator import run_e2e_workflow
from .numeric_validation import invalid_or_negative, positive_finite


BLOCKING_VERDICTS = {"BLOCKED", "NEGATIVE_RR", "NO_TRADE", "STOP"}
VALIDATION_VERDICTS = {"GO"}


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(handle)
    temporary = Path(name)
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _rank(row: dict[str, str]) -> tuple[int, str]:
    raw = row.get("lab_rank") or row.get("priority_rank") or "999999"
    try:
        return int(float(raw)), row.get("ticker", "")
    except ValueError:
        return 999999, row.get("ticker", "")


def _normalise_signal_row(row: dict[str, str]) -> dict[str, str]:
    """Map the Intelligence Lab export contract to Automation v2 names."""
    normalised = {str(key).strip().lower(): value for key, value in row.items()}
    return {
        **normalised,
        "ticker": str(row.get("Ticker") or normalised.get("ticker") or "").strip().upper(),
        "run_id": str(row.get("Run_ID") or normalised.get("run_id") or "").strip(),
        "lab_rank": str(row.get("Priority_Rank") or normalised.get("lab_rank") or "").strip(),
        "lab_verdict": str(row.get("Verdict") or normalised.get("lab_verdict") or "").strip().upper(),
        "rr_predicted": str(row.get("RR") or normalised.get("rr_predicted") or "").strip(),
        "ev_predicted": str(row.get("EV") or normalised.get("ev_predicted") or "").strip(),
        "source_contract": "AVSHUNTER_SIGNALS",
    }


def _negative_rr(row: dict[str, str]) -> bool:
    """Return True for negative or invalid/missing R:R (fail closed)."""
    return invalid_or_negative(row.get("rr_predicted"))


def discover_latest_lab_universe(
    pipeline_outputs: Path,
) -> tuple[Path, str, list[dict[str, str]]]:
    outputs = pipeline_outputs.resolve()
    lab_export = outputs.parent / "lab_export"
    signal_files = list(lab_export.glob("avshunter_signals_*.csv")) if lab_export.exists() else []
    signal_files.extend(outputs.glob("avshunter_signals_*.csv"))
    files = sorted(
        signal_files or list(outputs.glob("lab_triage_view_*.csv")),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError("LAB_TRIAGE_SOURCE_NOT_FOUND")
    source = files[0]
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        raw_rows = [dict(row) for row in csv.DictReader(handle)]
    is_signal_export = source.name.lower().startswith("avshunter_signals_")
    rows = (
        [_normalise_signal_row(row) for row in raw_rows]
        if is_signal_export else raw_rows
    )
    if not rows:
        raise ValueError("LAB_TRIAGE_SOURCE_EMPTY")
    run_ids = {row.get("run_id", "").strip() for row in rows}
    if "" in run_ids or len(run_ids) != 1:
        raise ValueError("LAB_RUN_ID_INCONSISTENT")
    return source, run_ids.pop(), rows


def run_lab_batch(
    *,
    pipeline_outputs: Path,
    staging_root: Path,
    output_directory: Path,
    invocation_id: str,
    max_candidates: int = 10,
    execute_shadow: bool = False,
    capture_runner: Callable[[str, Path], object] | None = None,
    shadow_provider: object | None = None,
) -> Path:
    source, run_id, rows = discover_latest_lab_universe(pipeline_outputs)
    output = output_directory.resolve()
    state_path = output / "lab_batch_state.json"
    if output.exists():
        if not state_path.is_file():
            raise FileExistsError(output)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state["invocation_id"] != invocation_id or state["run_id"] != run_id:
            raise ValueError("LAB_BATCH_RESUME_IDENTITY_MISMATCH")
    else:
        candidates, stopped = [], []
        for row in sorted(rows, key=_rank):
            ticker = row.get("ticker", "").strip().upper()
            verdict = row.get("lab_verdict", "").strip().upper()
            vetoes: list[str] = []
            source_contract = row.get("source_contract", "LAB_TRIAGE_VIEW")
            if _negative_rr(row) or verdict == "NEGATIVE_RR":
                vetoes.append("NEGATIVE_RR")
            if source_contract == "AVSHUNTER_SIGNALS" and not positive_finite(
                row.get("ev_predicted")
            ):
                vetoes.append("NON_POSITIVE_EV")
            if source_contract == "AVSHUNTER_SIGNALS" and verdict != "GO":
                vetoes.append(f"UPSTREAM_{verdict or 'VERDICT_MISSING'}")
            if verdict in BLOCKING_VERDICTS and verdict != "NEGATIVE_RR":
                vetoes.append(f"UPSTREAM_{verdict}")
            record = {
                "ticker": ticker,
                "lab_rank": _rank(row)[0],
                "lab_verdict": verdict,
                "veto_codes": vetoes,
                "effective_verdict": "STOP" if vetoes else "WAIT",
                "eil_action": "STOP",
            }
            if not ticker or vetoes:
                stopped.append(record)
            elif verdict in VALIDATION_VERDICTS:
                candidates.append(record)
        candidates = candidates[:max_candidates]
        output.mkdir(parents=True)
        state = {
            "schema_version": "automation_v2.lab_batch.1",
            "invocation_id": invocation_id,
            "run_id": run_id,
            "source": str(source),
            "status": "planned",
            "mode": "SHADOW" if execute_shadow else "PLAN",
            "candidates": candidates,
            "stopped": stopped,
            "steps": {},
            "production_charts_touched": False,
            "published": False,
        }
        _atomic_write(state_path, state)

    if not execute_shadow:
        return state_path

    for candidate in state["candidates"]:
        ticker = candidate["ticker"]
        if state["steps"].get(ticker, {}).get("status") == "passed":
            continue
        ticker_root = staging_root.resolve() / ticker
        ticker_root.mkdir(parents=True, exist_ok=True)
        ticker_output = ticker_root / f"{invocation_id}-{ticker.lower()}"
        try:
            if capture_runner is not None:
                capture_runner(ticker, ticker_root)
            workflow_kwargs = dict(
                ticker=ticker,
                staging_root=ticker_root,
                pipeline_outputs=pipeline_outputs,
                output_directory=ticker_output,
                invocation_id=f"{invocation_id}:{ticker}",
            )
            if shadow_provider is not None:
                workflow_kwargs["shadow_provider"] = shadow_provider
            workflow = run_e2e_workflow(**workflow_kwargs)
            result = json.loads(workflow.read_text(encoding="utf-8"))
            state["steps"][ticker] = {
                "status": result["status"],
                "go_no_go": result.get("go_no_go"),
                "effective_verdict": result.get("steps", {})
                .get("shadow_ingestion", {}).get("effective_verdict"),
                "workflow_state": str(workflow),
            }
        except Exception as exc:
            state["steps"][ticker] = {
                "status": "stopped", "finding": str(exc),
                "effective_verdict": "STOP",
            }
        _atomic_write(state_path, state)

    statuses = [step["status"] for step in state["steps"].values()]
    state["status"] = (
        "passed" if statuses and all(item == "passed" for item in statuses)
        else "incomplete"
    )
    state["go_no_go"] = (
        "SHADOW_BATCH_PASSED_NOT_PRODUCTION_AUTHORIZED"
        if state["status"] == "passed"
        else "NO_GO_BATCH_INCOMPLETE"
    )
    _atomic_write(state_path, state)
    return state_path
