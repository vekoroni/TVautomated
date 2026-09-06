"""Explicit-path adapter from legacy Interpreter files to immutable requests.

This module deliberately does not implement "latest file" discovery. Callers
must select the run and sources before invoking it.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .evidence import (
    classify_chart_asset,
    discover_ticker_assets,
    filename_belongs_to_ticker,
    sha256_file,
)
from .models import EvidenceItem, EvidenceManifest, TickerRunRequest


class LegacyInputError(ValueError):
    """Base error for deterministic legacy ingestion failures."""


class MissingTickerError(LegacyInputError):
    pass


class AmbiguousTickerError(LegacyInputError):
    pass


@dataclass(frozen=True, slots=True)
class LegacyInputSpec:
    ticker: str
    run_id: str
    invocation_id: str
    as_of: str
    pipeline_csv: str | Path
    lab_csv: str | Path | None = None
    option_csvs: tuple[str | Path, ...] = ()
    chart_roots: tuple[str | Path, ...] = ()
    macro_json: str | Path | None = None
    trader_note: str = ""
    mode: str = "full"
    require_lab: bool = False
    max_age_hours: float | None = None


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise LegacyInputError(f"missing CSV: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _exact_rows(
    rows: Iterable[dict[str, str]], ticker: str
) -> list[dict[str, str]]:
    symbol = ticker.strip().upper()
    return [
        row
        for row in rows
        if str(row.get("ticker", "")).strip().upper() == symbol
    ]


def _one_exact_row(
    path: Path,
    ticker: str,
    *,
    required: bool,
    kind: str,
) -> dict[str, str]:
    matches = _exact_rows(_read_csv(path), ticker)
    if not matches:
        if required:
            raise MissingTickerError(f"{ticker} absent from {kind}: {path}")
        return {}
    if len(matches) > 1:
        raise AmbiguousTickerError(
            f"{ticker} has {len(matches)} exact rows in {kind}: {path}"
        )
    return matches[0]


def _parse_as_of(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _file_item(
    *,
    path: Path,
    kind: str,
    ticker: str,
    run_id: str,
    as_of: str,
    required: bool,
    max_age_hours: float | None,
) -> EvidenceItem:
    modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    fresh = True
    age_hours: float | None = None
    if max_age_hours is not None:
        age_hours = (_parse_as_of(as_of) - modified).total_seconds() / 3600
        fresh = age_hours <= max_age_hours
    metadata: dict[str, Any] = {
        "modified_at": modified.isoformat().replace("+00:00", "Z"),
        "size_bytes": path.stat().st_size,
    }
    if age_hours is not None:
        metadata["age_hours"] = round(age_hours, 6)
    return EvidenceItem(
        kind=kind,
        source=str(path.resolve()),
        ticker=ticker,
        run_id=run_id,
        as_of=as_of,
        sha256=sha256_file(path),
        required=required,
        fresh=fresh,
        metadata=metadata,
    )


def _row_run_finding(
    row: dict[str, str], expected_run_id: str, kind: str
) -> str | None:
    actual = str(row.get("run_id", "")).strip()
    if actual and actual != expected_run_id:
        return f"ROW_RUN_ID_MISMATCH:{kind}:{actual}:{expected_run_id}"
    return None


def _load_macro(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.is_file():
        raise LegacyInputError(f"missing macro JSON: {path}")
    import json

    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise LegacyInputError(f"macro JSON must contain an object: {path}")
    return value


def build_request_from_legacy(spec: LegacyInputSpec) -> TickerRunRequest:
    """Build a complete immutable request from caller-selected legacy inputs."""
    ticker = spec.ticker.strip().upper()
    pipeline_path = Path(spec.pipeline_csv).resolve()
    pipeline_row = _one_exact_row(
        pipeline_path, ticker, required=True, kind="pipeline"
    )

    findings: list[str] = []
    items = [
        _file_item(
            path=pipeline_path,
            kind="pipeline",
            ticker=ticker,
            run_id=spec.run_id,
            as_of=spec.as_of,
            required=True,
            max_age_hours=spec.max_age_hours,
        )
    ]
    mismatch = _row_run_finding(pipeline_row, spec.run_id, "pipeline")
    if mismatch:
        findings.append(mismatch)

    lab_row: dict[str, str] = {}
    if spec.lab_csv is not None:
        lab_path = Path(spec.lab_csv).resolve()
        lab_row = _one_exact_row(
            lab_path, ticker, required=spec.require_lab, kind="lab"
        )
        items.append(
            _file_item(
                path=lab_path,
                kind="lab",
                ticker=ticker,
                run_id=spec.run_id,
                as_of=spec.as_of,
                required=spec.require_lab,
                max_age_hours=spec.max_age_hours,
            )
        )
        if lab_row:
            mismatch = _row_run_finding(lab_row, spec.run_id, "lab")
            if mismatch:
                findings.append(mismatch)
    elif spec.require_lab:
        findings.append("MISSING_REQUIRED_EVIDENCE:lab")

    option_rows: list[dict[str, str]] = []
    for option_value in spec.option_csvs:
        option_path = Path(option_value).resolve()
        row = _one_exact_row(
            option_path, ticker, required=False, kind="option_context"
        )
        if row:
            option_rows.append(row)
            mismatch = _row_run_finding(row, spec.run_id, "option_context")
            if mismatch:
                findings.append(mismatch)
        items.append(
            _file_item(
                path=option_path,
                kind="option_context",
                ticker=ticker,
                run_id=spec.run_id,
                as_of=spec.as_of,
                required=False,
                max_age_hours=spec.max_age_hours,
            )
        )

    chart_assets = discover_ticker_assets(spec.chart_roots, ticker)
    for asset in chart_assets:
        if not filename_belongs_to_ticker(asset, ticker):
            findings.append(f"REJECTED_AMBIGUOUS_ASSET:{asset.name}")
            continue
        items.append(
            _file_item(
                path=asset,
                kind=f"chart:{classify_chart_asset(asset, ticker)}",
                ticker=ticker,
                run_id=spec.run_id,
                as_of=spec.as_of,
                required=False,
                max_age_hours=spec.max_age_hours,
            )
        )

    macro_path = Path(spec.macro_json).resolve() if spec.macro_json else None
    macro_context = _load_macro(macro_path)
    if macro_path:
        items.append(
            _file_item(
                path=macro_path,
                kind="macro",
                ticker=ticker,
                run_id=spec.run_id,
                as_of=spec.as_of,
                required=False,
                max_age_hours=spec.max_age_hours,
            )
        )

    manifest = EvidenceManifest(
        ticker=ticker,
        run_id=spec.run_id,
        invocation_id=spec.invocation_id,
        as_of=spec.as_of,
        items=tuple(items),
        findings=tuple(findings),
    )
    return TickerRunRequest(
        ticker=ticker,
        run_id=spec.run_id,
        invocation_id=spec.invocation_id,
        manifest=manifest,
        pipeline_row=pipeline_row,
        lab_context=lab_row,
        option_context=tuple(option_rows),
        chart_assets=tuple(str(path) for path in chart_assets),
        macro_context=macro_context,
        trader_note=spec.trader_note,
        mode=spec.mode,
        shadow=True,
        execution_enabled=False,
    )

