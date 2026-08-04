"""Stable JSON serialization for immutable request replay."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .models import EvidenceItem, EvidenceManifest, TickerRunRequest


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def request_to_dict(request: TickerRunRequest) -> dict[str, Any]:
    return {
        "schema_version": "automation_v2.request.1",
        "ticker": request.ticker,
        "run_id": request.run_id,
        "invocation_id": request.invocation_id,
        "manifest": {
            "ticker": request.manifest.ticker,
            "run_id": request.manifest.run_id,
            "invocation_id": request.manifest.invocation_id,
            "as_of": request.manifest.as_of,
            "findings": list(request.manifest.findings),
            "items": [
                {
                    "kind": item.kind,
                    "source": item.source,
                    "ticker": item.ticker,
                    "run_id": item.run_id,
                    "as_of": item.as_of,
                    "sha256": item.sha256,
                    "required": item.required,
                    "fresh": item.fresh,
                    "metadata": _plain(item.metadata),
                }
                for item in request.manifest.items
            ],
        },
        "pipeline_row": _plain(request.pipeline_row),
        "lab_context": _plain(request.lab_context),
        "option_context": _plain(request.option_context),
        "chart_assets": list(request.chart_assets),
        "macro_context": _plain(request.macro_context),
        "sector_context": _plain(request.sector_context),
        "trader_note": request.trader_note,
        "live_validation": _plain(request.live_validation),
        "mode": request.mode,
        "shadow": request.shadow,
        "execution_enabled": request.execution_enabled,
    }


def request_from_dict(value: Mapping[str, Any]) -> TickerRunRequest:
    if value.get("schema_version") != "automation_v2.request.1":
        raise ValueError("unsupported request replay schema")
    manifest_value = value["manifest"]
    manifest = EvidenceManifest(
        ticker=manifest_value["ticker"],
        run_id=manifest_value["run_id"],
        invocation_id=manifest_value["invocation_id"],
        as_of=manifest_value["as_of"],
        findings=tuple(manifest_value.get("findings", ())),
        items=tuple(
            EvidenceItem(
                kind=item["kind"],
                source=item["source"],
                ticker=item["ticker"],
                run_id=item["run_id"],
                as_of=item.get("as_of", ""),
                sha256=item.get("sha256", ""),
                required=bool(item.get("required", False)),
                fresh=bool(item.get("fresh", True)),
                metadata=item.get("metadata", {}),
            )
            for item in manifest_value.get("items", ())
        ),
    )
    return TickerRunRequest(
        ticker=value["ticker"],
        run_id=value["run_id"],
        invocation_id=value["invocation_id"],
        manifest=manifest,
        pipeline_row=value["pipeline_row"],
        lab_context=value.get("lab_context", {}),
        option_context=tuple(value.get("option_context", ())),
        chart_assets=tuple(value.get("chart_assets", ())),
        macro_context=value.get("macro_context", {}),
        sector_context=value.get("sector_context", {}),
        trader_note=value.get("trader_note", ""),
        live_validation=value.get("live_validation", {}),
        mode=value.get("mode", "full"),
        shadow=bool(value.get("shadow", True)),
        execution_enabled=bool(value.get("execution_enabled", False)),
    )


def write_request_fixture(request: TickerRunRequest, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(request_to_dict(request), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output


def read_request_fixture(path: str | Path) -> TickerRunRequest:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("request fixture must contain an object")
    return request_from_dict(value)
