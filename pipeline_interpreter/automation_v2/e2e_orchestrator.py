"""Resumable post-capture orchestration for one staged ticker."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .evidence_package import assemble_evidence_package
from .lab_structured import build_structured_lab_manifest
from .package_publisher import validate_package
from .package_shadow import run_package_shadow


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _write_state(path: Path, payload: dict[str, Any]) -> None:
    handle, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(handle)
    temporary = Path(name)
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_e2e_workflow(
    *,
    ticker: str,
    staging_root: Path,
    pipeline_outputs: Path,
    output_directory: Path,
    invocation_id: str,
    shadow_provider: object | None = None,
) -> Path:
    symbol = ticker.strip().upper()
    root = staging_root.resolve()
    output = output_directory.resolve()
    if not _inside(output, root):
        raise ValueError("E2E_OUTPUT_MUST_BE_INSIDE_TICKER_STAGING_ROOT")
    state_path = output / "workflow_state.json"
    if output.exists():
        if not state_path.is_file():
            raise FileExistsError(output)
        state = _load_report(state_path)
        if state.get("ticker") != symbol or state.get("invocation_id") != invocation_id:
            raise ValueError("E2E_RESUME_IDENTITY_MISMATCH")
    else:
        output.mkdir(parents=True)
        state = {
            "schema_version": "automation_v2.e2e_workflow.1",
            "ticker": symbol,
            "invocation_id": invocation_id,
            "status": "running",
            "steps": {},
            "production_charts_touched": False,
            "published": False,
        }
        _write_state(state_path, state)

    steps = state["steps"]
    lab_path = output / "lab" / f"{symbol}_lab_structured.json"
    if steps.get("lab_structured", {}).get("status") != "complete":
        result = build_structured_lab_manifest(
            ticker=symbol,
            pipeline_outputs=pipeline_outputs,
            output_file=lab_path,
        )
        steps["lab_structured"] = {
            "status": "complete", "manifest": str(result.manifest),
            "run_id": result.run_id, "findings": list(result.findings),
        }
        _write_state(state_path, state)
    elif not lab_path.is_file():
        raise FileNotFoundError("E2E_RESUME_LAB_ARTIFACT_MISSING")

    package_dir = output / "package"
    package_manifest = package_dir / "ticker_evidence_package.json"
    if steps.get("evidence_package", {}).get("status") != "complete":
        manifest, findings = assemble_evidence_package(
            ticker=symbol,
            staging_root=root,
            output_directory=package_dir,
        )
        steps["evidence_package"] = {
            "status": "complete" if not findings else "incomplete",
            "manifest": str(manifest), "findings": list(findings),
        }
        _write_state(state_path, state)
        if findings:
            state["status"] = "incomplete"
            state["go_no_go"] = "NO_GO_INCOMPLETE_EVIDENCE"
            _write_state(state_path, state)
            return state_path
    elif not package_manifest.is_file():
        raise FileNotFoundError("E2E_RESUME_PACKAGE_ARTIFACT_MISSING")

    _, validation_findings = validate_package(package_manifest)
    steps["package_validation"] = {
        "status": "complete" if not validation_findings else "failed",
        "findings": list(validation_findings),
    }
    _write_state(state_path, state)
    if validation_findings:
        state["status"] = "failed"
        state["go_no_go"] = "NO_GO_PACKAGE_VALIDATION"
        _write_state(state_path, state)
        return state_path

    shadow_dir = output / "shadow"
    shadow_report = shadow_dir / "package_shadow_report.json"
    if steps.get("shadow_ingestion", {}).get("status") != "complete":
        shadow_kwargs = dict(
            manifest_path=package_manifest,
            output_directory=shadow_dir,
            invocation_id=invocation_id,
        )
        if shadow_provider is not None:
            shadow_kwargs["provider"] = shadow_provider
        report = run_package_shadow(**shadow_kwargs)
        shadow = _load_report(report)
        passed = (
            shadow.get("status") == "passed"
            and shadow.get("sovereign_preserved") is True
            and shadow.get("production_charts_touched") is False
        )
        steps["shadow_ingestion"] = {
            "status": "complete" if passed else "failed",
            "report": str(report),
            "sovereign_preserved": shadow.get("sovereign_preserved"),
            "effective_verdict": shadow.get("effective_verdict"),
            "provider_mode": shadow.get("provider_mode"),
            "interpreter_artifacts": shadow.get("interpreter_artifacts"),
            "provider_error": shadow.get("provider_error"),
        }
        _write_state(state_path, state)
    elif not shadow_report.is_file():
        raise FileNotFoundError("E2E_RESUME_SHADOW_ARTIFACT_MISSING")

    shadow_passed = steps["shadow_ingestion"]["status"] == "complete"
    state["status"] = "passed" if shadow_passed else "failed"
    state["go_no_go"] = (
        "SHADOW_PASSED_NOT_PRODUCTION_AUTHORIZED"
        if shadow_passed
        else "NO_GO_SHADOW_FAILED"
    )
    state["production_charts_touched"] = False
    state["published"] = False
    _write_state(state_path, state)
    return state_path

