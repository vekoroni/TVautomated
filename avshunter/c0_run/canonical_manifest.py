"""Run input manifest: what a run consumed, cited by hash (AVS-PKG-002 P1).

Canonical data design v1 §4.1 item 5: ``runs/<run_id>/canonical_manifest.json`` is the
immutable list of dataset IDs and hashes a pipeline run consumed. This module builds it from
the run's own inputs and the canonical stores. It copies nothing, calls no provider, and grants
no authority (``INPUT_CITATION_ONLY``). Every discovery ticker is listed with a typed
history verdict judged against the run's evidence session (R1: missing is never neutral).

Pure construction lives in :func:`build_canonical_manifest`; file and database access is
confined to :func:`collect_canonical_inputs`, :func:`write_canonical_manifest` and
:func:`validate_canonical_manifest`.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from canonical_data.history_bridge import (
    DEFAULT_HISTORY_MAX_STALENESS_DAYS,
    database_path as history_database_path,
    history_staleness_days,
)
from canonical_data.historical_prices import HistoricalPriceDatabase
from scripts.data_contract_validator import DataContractValidator

CONTRACT_VERSION = "canonical_manifest_v1"
MANIFEST_FILENAME = "canonical_manifest.json"
AUTHORITY = "INPUT_CITATION_ONLY"
HASHED_SOURCES = ("discovery", "macro_snapshot", "macro_quant_packet", "actuarial_database")
_CRITICAL = ("open", "high", "low", "close")

HistoryReader = Callable[[str], "pd.DataFrame | None"]


# --------------------------------------------------------------------------- value objects
@dataclass(frozen=True)
class SourceCitation:
    status: str                      # PRESENT | MISSING
    path: str | None
    sha256: str | None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "path": self.path, "sha256": self.sha256, **self.extra}


@dataclass(frozen=True)
class CanonicalInputs:
    run_id: str
    evidence_session: date
    as_of_utc: str
    run_condition: str
    discovery_rows: tuple[dict[str, str], ...]
    discovery: SourceCitation
    macro_snapshot: SourceCitation
    macro_regime_present: bool
    macro_quant_packet: SourceCitation
    actuarial_database: SourceCitation
    historical_prices: SourceCitation
    history_reader: HistoryReader
    worklist: tuple[str, ...] | None = None
    min_bars: int = DataContractValidator.MIN_BARS
    max_staleness_days: int = DEFAULT_HISTORY_MAX_STALENESS_DAYS


# --------------------------------------------------------------------------- helpers
def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _citation(path: Path | None, **extra: Any) -> SourceCitation:
    if path is None or not path.is_file():
        return SourceCitation("MISSING", str(path) if path is not None else None, None, extra)
    return SourceCitation("PRESENT", str(path), _sha256_file(path), extra)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload if isinstance(payload, dict) else {}


def _history_fingerprint(db_path: Path) -> tuple[str, str]:
    """A coverage fingerprint of the canonical store: cheap, deterministic, disclosed as such."""
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
        rows, tickers, max_session = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT ticker), MAX(trading_date) FROM ohlcv_daily"
        ).fetchone()
    basis = f"COVERAGE:tickers={tickers},rows={rows},max_session={max_session}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest(), basis


def _frame_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for record in frame.to_dict("records"):
        row = dict(record)
        value = row.get("date")
        row["date"] = value.strftime("%Y-%m-%d") if hasattr(value, "strftime") else str(value)[:10]
        for column in _CRITICAL:
            number = row.get(column)
            row[column] = None if number is None or pd.isna(number) else number
        rows.append(row)
    return rows


def _history_verdict(
    frame: pd.DataFrame | None, *, reference_session: date, min_bars: int, max_staleness_days: int
) -> dict[str, Any]:
    """The data-contract verdict on canonical bars, judged against the evidence session."""
    out: dict[str, Any] = {
        "bar_count": 0, "first_session": None, "last_session": None, "staleness_days": None,
        "dcv_verdict": False, "dcv_reason": "NO_OHLCV", "dcv_confidence": "NONE",
    }
    if frame is None or frame.empty or "date" not in frame.columns:
        return out
    rows = _frame_rows(frame)
    out.update({
        "bar_count": len(rows), "first_session": rows[0]["date"], "last_session": rows[-1]["date"],
        "staleness_days": history_staleness_days(rows[-1]["date"], reference_date=reference_session),
        "dcv_confidence": DataContractValidator.confidence_level({"ohlcv": rows}),
    })
    if len(rows) < min_bars:
        out["dcv_reason"] = f"INSUFFICIENT_HISTORY ({len(rows)}<{min_bars})"
        return out
    tail = rows[-min(10, len(rows)):]
    for column in _CRITICAL:
        if any(row.get(column) is None for row in tail):
            out["dcv_reason"] = f"NULLS_IN_CRITICAL_COLS ({column})"
            return out
    age = out["staleness_days"]
    if age is None or age < 0 or age > max_staleness_days:
        out["dcv_reason"] = f"STALE_DATA ({rows[-1]['date']}, {age}d old)"
        return out
    out["dcv_verdict"] = True
    out["dcv_reason"] = "VALID"
    return out


# --------------------------------------------------------------------------- adapter: gather inputs
def collect_canonical_inputs(
    *,
    run_dir: Path | str,
    repo_root: Path | str,
    actuarial_path: Path | str | None = None,
    worklist: Sequence[str] | None = None,
    environment: Mapping[str, str] | None = None,
) -> CanonicalInputs:
    """Read the run's inputs and open the canonical stores read-only. No provider access."""
    run_dir = Path(run_dir)
    repo_root = Path(repo_root)
    run_id = run_dir.name
    env = os.environ if environment is None else environment

    meta = _read_json(run_dir / "run_meta.json") if (run_dir / "run_meta.json").is_file() else {}
    plan = meta.get("dynamic_plan") if isinstance(meta.get("dynamic_plan"), dict) else {}
    session_text = str(plan.get("last_completed_session") or meta.get("evidence_session") or "").strip()
    if not session_text:
        raise ValueError(f"run_meta.json has no last_completed_session for run {run_id}")
    evidence_session = date.fromisoformat(session_text[:10])

    discovery_path = run_dir / "discovery" / f"discovery_candidates_ultimate_{run_id}.csv"
    if not discovery_path.is_file():
        raise FileNotFoundError(discovery_path)
    with discovery_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = tuple({str(k): str(v) for k, v in row.items()} for row in csv.DictReader(handle))

    macro_path = run_dir / "macro_snapshot.json"
    if not macro_path.is_file():
        raise FileNotFoundError(macro_path)
    macro = _read_json(macro_path)
    macro_citation = _citation(macro_path, as_of_utc=macro.get("as_of_utc"),
                               contract_version=macro.get("contract_version"),
                               macro_authority=macro.get("macro_authority"))

    if actuarial_path is None:
        registry = repo_root / "config" / "actuarial_registry.json"
        if registry.is_file():
            declared = _read_json(registry).get("canonical_database") or {}
            actuarial_path = declared.get("path") or None
            expected = declared.get("expected_schema_fingerprint")
        else:
            expected = None
    else:
        expected = None
    actuarial_citation = _citation(Path(actuarial_path) if actuarial_path else None,
                                   schema_fingerprint_expected=expected)

    db_path = history_database_path(env)
    if not db_path.is_absolute():
        db_path = repo_root / db_path
    if db_path.is_file():
        fingerprint, basis = _history_fingerprint(db_path)
        history_citation = SourceCitation("PRESENT", str(db_path), None,
                                          {"dataset_fingerprint": fingerprint, "fingerprint_basis": basis})
        database = HistoricalPriceDatabase(db_path)

        def reader(ticker: str) -> pd.DataFrame | None:
            frame = database.read(ticker, end_date=evidence_session)
            return None if frame.empty else frame
    else:
        history_citation = SourceCitation("MISSING", str(db_path), None,
                                          {"dataset_fingerprint": None, "fingerprint_basis": None})

        def reader(ticker: str) -> pd.DataFrame | None:  # noqa: ARG001
            return None

    return CanonicalInputs(
        run_id=run_id, evidence_session=evidence_session,
        as_of_utc=str(plan.get("evidence_cutoff_utc") or meta.get("evidence_cutoff_utc") or ""),
        run_condition=str(plan.get("run_condition") or meta.get("run_condition") or "UNKNOWN"),
        discovery_rows=rows, discovery=_citation(discovery_path, row_count=len(rows)),
        macro_snapshot=macro_citation, macro_regime_present=bool(str(macro.get("regime_state") or "").strip()),
        macro_quant_packet=_citation(run_dir / "macro_quant_packet.json"),
        actuarial_database=actuarial_citation, historical_prices=history_citation,
        history_reader=reader,
        worklist=tuple(str(t).strip().upper() for t in worklist) if worklist is not None else None,
    )


# --------------------------------------------------------------------------- pure: build
def build_canonical_manifest(inputs: CanonicalInputs, *, created_at_utc: datetime) -> dict[str, Any]:
    if created_at_utc.tzinfo is None:
        raise ValueError("created_at_utc must be timezone-aware")
    first_row: dict[str, dict[str, str]] = {}
    duplicates: list[str] = []
    for row in inputs.discovery_rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        if ticker in first_row:
            if ticker not in duplicates:
                duplicates.append(ticker)
            continue
        first_row[ticker] = row
    if inputs.worklist is not None:
        tickers, ticker_set_source = sorted(set(inputs.worklist)), "GOVERNED_WORKLIST"
    else:
        tickers, ticker_set_source = sorted(first_row), "DISCOVERY_DEDUPED"

    rows_out: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    for ticker in tickers:
        verdict = _history_verdict(
            inputs.history_reader(ticker), reference_session=inputs.evidence_session,
            min_bars=inputs.min_bars, max_staleness_days=inputs.max_staleness_days,
        )
        row = first_row.get(ticker)
        if row is None:
            verdict["dcv_verdict"] = False
            verdict["dcv_reason"] = "WORKLIST_TICKER_MISSING_FROM_DISCOVERY"
        reasons[verdict["dcv_reason"].split(" ")[0]] += 1
        rows_out.append({
            "ticker": ticker,
            "discovery_row_sha256": _sha256_json(row) if row is not None else None,
            **verdict,
            "regime_present": inputs.macro_regime_present,
        })
    valid = sum(1 for r in rows_out if r["dcv_verdict"])
    discovery_source = inputs.discovery.to_dict()
    discovery_source["duplicate_tickers"] = duplicates
    body: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "authority": AUTHORITY,
        "run_id": inputs.run_id,
        "evidence_session": inputs.evidence_session.isoformat(),
        "as_of_utc": inputs.as_of_utc,
        "run_condition": inputs.run_condition,
        "ticker_set_source": ticker_set_source,
        "sources": {
            "discovery": discovery_source,
            "macro_snapshot": inputs.macro_snapshot.to_dict(),
            "macro_quant_packet": inputs.macro_quant_packet.to_dict(),
            "actuarial_database": inputs.actuarial_database.to_dict(),
            "historical_prices": inputs.historical_prices.to_dict(),
        },
        "history_policy": {
            "min_bars": inputs.min_bars,
            "max_staleness_days": inputs.max_staleness_days,
            "reference_session": inputs.evidence_session.isoformat(),
            "verdict_source": "CANONICAL_HISTORICAL_PRICE_DB",
        },
        "tickers": rows_out,
        "coverage": {
            "tickers": len(rows_out), "valid": valid, "rejected": len(rows_out) - valid,
            "rejected_by_reason": dict(sorted(
                (k, v) for k, v in reasons.items() if k != "VALID")),
            "valid_ratio": (valid / len(rows_out)) if rows_out else 0.0,
        },
    }
    return {
        **body,
        "created_at_utc": created_at_utc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "manifest_sha256": _sha256_json(body),
    }


# --------------------------------------------------------------------------- adapter: write / validate
def write_canonical_manifest(run_dir: Path | str, manifest: Mapping[str, Any]) -> Path:
    target = Path(run_dir) / MANIFEST_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + f".tmp-{os.getpid()}")
    try:
        temporary.write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def validate_canonical_manifest(path: Path | str) -> dict[str, Any]:
    """Recompute every cited hash; report what no longer matches. Never repairs."""
    manifest = _read_json(Path(path))
    body = {k: v for k, v in manifest.items() if k not in {"manifest_sha256", "created_at_utc"}}
    mismatches: list[str] = []
    missing: list[str] = []
    if manifest.get("contract_version") != CONTRACT_VERSION or _sha256_json(body) != manifest.get("manifest_sha256"):
        mismatches.append("manifest")
    sources = manifest.get("sources") or {}
    for name in HASHED_SOURCES:
        source = sources.get(name) or {}
        if source.get("status") != "PRESENT":
            continue
        cited = Path(str(source.get("path") or ""))
        if not cited.is_file():
            missing.append(name)
        elif _sha256_file(cited) != source.get("sha256"):
            mismatches.append(name)
    history = sources.get("historical_prices") or {}
    if history.get("status") == "PRESENT":
        cited = Path(str(history.get("path") or ""))
        if not cited.is_file():
            missing.append("historical_prices")
        elif _history_fingerprint(cited)[0] != history.get("dataset_fingerprint"):
            mismatches.append("historical_prices")
    return {"valid": not mismatches and not missing, "mismatches": mismatches, "missing": missing,
            "run_id": manifest.get("run_id"), "manifest_sha256": manifest.get("manifest_sha256")}


__all__ = [
    "AUTHORITY", "CONTRACT_VERSION", "MANIFEST_FILENAME", "CanonicalInputs", "SourceCitation",
    "build_canonical_manifest", "collect_canonical_inputs", "validate_canonical_manifest",
    "write_canonical_manifest",
]
