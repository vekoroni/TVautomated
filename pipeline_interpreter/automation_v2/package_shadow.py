"""Isolated publication and stateless-ingestion proof for evidence packages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core import interpret_ticker
from .models import (
    AnalysisPayload,
    EvidenceItem,
    EvidenceManifest,
    TickerRunRequest,
)
from .package_publisher import publish_package, validate_package


class PackageVerificationProvider:
    """Deterministic provider used only to prove request ingestion and vetoes."""

    def analyze(self, request: TickerRunRequest) -> AnalysisPayload:
        return AnalysisPayload(
            proposed_verdict="WAIT",
            narrative=(
                f"Verified complete staged evidence package for {request.ticker}; "
                "no execution authority granted."
            ),
        )


def _flatten_sections(payload: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for section in payload.get("sections", {}).values():
        if isinstance(section, dict):
            merged.update(section)
    sovereign = payload.get("sovereign", {})
    merged["rr"] = sovereign.get("rr", "")
    return merged


def run_package_shadow(
    *,
    manifest_path: Path,
    output_directory: Path,
    invocation_id: str,
    provider: object | None = None,
) -> Path:
    package, findings = validate_package(manifest_path)
    if findings:
        raise RuntimeError("|".join(findings))
    final = output_directory.resolve()
    if final.exists():
        raise FileExistsError(final)
    final.mkdir(parents=True)

    publication = publish_package(
        manifest_path=manifest_path,
        charts_directory=final / "shadow_charts",
        publish_requested=True,
        feature_enabled=True,
    )
    if publication.status != "published":
        raise RuntimeError("|".join(publication.findings))

    package_root = manifest_path.resolve().parent
    lab_record = package["structured_lab"]
    lab_path = package_root / lab_record["filename"]
    lab = json.loads(lab_path.read_text(encoding="utf-8"))
    ticker = str(package["ticker"]).upper()
    run_id = str(lab["run_id"])
    items = tuple(
        EvidenceItem(
            kind=f"chart:{record['kind']}",
            source=str((final / "shadow_charts" / record["filename"]).resolve()),
            ticker=ticker,
            run_id=run_id,
            sha256=record["sha256"],
            required=True,
            fresh=True,
        )
        for record in package["assets"]
    )
    evidence = EvidenceManifest(
        ticker=ticker,
        run_id=run_id,
        invocation_id=invocation_id,
        as_of=run_id,
        items=items,
    )
    request = TickerRunRequest(
        ticker=ticker,
        run_id=run_id,
        invocation_id=invocation_id,
        manifest=evidence,
        pipeline_row=_flatten_sections(lab),
        lab_context=lab,
        chart_assets=tuple(item.source for item in items),
        live_validation={},
        shadow=True,
        execution_enabled=False,
    )
    live_interpretation = provider is not None
    result = interpret_ticker(request, provider or PackageVerificationProvider())
    interpreter_artifacts = None
    if live_interpretation and result.analysis is not None:
        from .renderers import publish_complete_shadow_artifacts

        interpreter_artifacts = publish_complete_shadow_artifacts(
            result, final / "interpreter_artifacts"
        )
    expected_vetoes = set(lab.get("sovereign", {}).get("veto_codes", []))
    actual_vetoes = set(result.veto_codes)
    sovereign_preserved = expected_vetoes.issubset(actual_vetoes)
    report = {
        "schema_version": "automation_v2.package_shadow.1",
        "ticker": ticker,
        "run_id": run_id,
        "invocation_id": invocation_id,
        "status": "passed" if sovereign_preserved else "failed",
        "package_manifest": str(manifest_path.resolve()),
        "shadow_charts": str((final / "shadow_charts").resolve()),
        "asset_count": len(items),
        "manifest_findings": list(evidence.validate()),
        "expected_sovereign_vetoes": sorted(expected_vetoes),
        "actual_sovereign_vetoes": sorted(actual_vetoes),
        "sovereign_preserved": sovereign_preserved,
        "effective_verdict": result.effective_verdict,
        "provider_mode": "LIVE_SHADOW" if live_interpretation else "VERIFICATION_ONLY",
        "interpreter_artifacts": (
            str(interpreter_artifacts) if interpreter_artifacts else None
        ),
        "provider_error": result.provider_error,
        "eil_action": result.eil_action,
        "execution_permission": result.execution_permission,
        "capital_permission": result.capital_permission,
        "production_charts_touched": False,
        "published": False,
    }
    report_path = final / "package_shadow_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    return report_path

