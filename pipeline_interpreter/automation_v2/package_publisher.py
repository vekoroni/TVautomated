"""Fail-closed publication gate for a complete staged evidence package."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PUBLISH_FEATURE_FLAG = "AVSHUNTER_CAPTURE_PUBLISH"


@dataclass(frozen=True, slots=True)
class PublicationResult:
    status: str
    findings: tuple[str, ...]
    published_files: tuple[Path, ...] = ()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def validate_package(manifest_path: Path) -> tuple[dict[str, Any], tuple[str, ...]]:
    manifest = manifest_path.resolve()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    findings: list[str] = []
    if payload.get("schema_version") != "automation_v2.evidence_package.1":
        findings.append("PACKAGE_SCHEMA_INVALID")
    if payload.get("status") != "complete":
        findings.append("PACKAGE_NOT_COMPLETE")
    if payload.get("findings"):
        findings.append("PACKAGE_HAS_FINDINGS")
    ticker = str(payload.get("ticker", "")).strip().upper()
    if not ticker:
        findings.append("PACKAGE_TICKER_MISSING")
    required = set(payload.get("required_kinds", []))
    seen = set()
    for record in payload.get("assets", []):
        kind = str(record.get("kind", ""))
        seen.add(kind)
        filename = str(record.get("filename", ""))
        source = (manifest.parent / filename).resolve()
        if not filename.startswith(f"{ticker}_") or Path(filename).name != filename:
            findings.append(f"PACKAGE_ASSET_NAME_INVALID:{kind}")
            continue
        if not _inside(source, manifest.parent) or not source.is_file():
            findings.append(f"PACKAGE_ASSET_MISSING:{kind}")
            continue
        if _sha256(source) != record.get("sha256"):
            findings.append(f"PACKAGE_HASH_MISMATCH:{kind}")
    for kind in sorted(required - seen):
        findings.append(f"PACKAGE_REQUIRED_KIND_MISSING:{kind}")
    lab = payload.get("structured_lab")
    if not lab:
        findings.append("PACKAGE_LAB_MISSING")
    else:
        source = (manifest.parent / str(lab.get("filename", ""))).resolve()
        if not _inside(source, manifest.parent) or not source.is_file():
            findings.append("PACKAGE_LAB_MISSING")
        elif _sha256(source) != lab.get("sha256"):
            findings.append("PACKAGE_LAB_HASH_MISMATCH")
    return payload, tuple(dict.fromkeys(findings))


def publish_package(
    *,
    manifest_path: Path,
    charts_directory: Path,
    publish_requested: bool = False,
    feature_enabled: bool | None = None,
    replace_existing: bool = False,
) -> PublicationResult:
    payload, findings = validate_package(manifest_path)
    if findings:
        return PublicationResult("stopped", findings)
    if not publish_requested:
        return PublicationResult("validated", ())
    enabled = (
        os.environ.get(PUBLISH_FEATURE_FLAG, "").strip() == "1"
        if feature_enabled is None
        else feature_enabled
    )
    if not enabled:
        return PublicationResult("stopped", ("PUBLISH_FEATURE_FLAG_DISABLED",))

    source_root = manifest_path.resolve().parent
    target_root = charts_directory.resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    records = payload["assets"]
    collisions = [
        target_root / record["filename"]
        for record in records
        if (target_root / record["filename"]).exists()
    ]
    if collisions and not replace_existing:
        return PublicationResult(
            "stopped",
            tuple(f"PUBLISH_TARGET_EXISTS:{path.name}" for path in collisions),
        )

    transaction = Path(tempfile.mkdtemp(
        prefix=".capture_publish.", dir=target_root
    ))
    created: list[Path] = []
    backups: list[tuple[Path, Path]] = []
    try:
        for record in records:
            shutil.copy2(
                source_root / record["filename"],
                transaction / record["filename"],
            )
        for record in records:
            target = target_root / record["filename"]
            staged = transaction / record["filename"]
            if target.exists():
                backup = transaction / f"{target.name}.backup"
                os.replace(target, backup)
                backups.append((target, backup))
            os.replace(staged, target)
            created.append(target)
        shutil.rmtree(transaction)
        return PublicationResult("published", (), tuple(created))
    except Exception:
        for target in reversed(created):
            target.unlink(missing_ok=True)
        for target, backup in reversed(backups):
            if backup.exists():
                os.replace(backup, target)
        shutil.rmtree(transaction, ignore_errors=True)
        raise
