"""Atomic persistence for immutable Macro input manifests."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
import shutil
from typing import Any, Mapping

from domain.macro_input_governance import validate_manifest_lineage


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _encoded(manifest: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(manifest), indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def publish_macro_input_manifest(
    manifest: Mapping[str, Any], archive_root: Path | str, latest_path: Path | str,
    evidence_root: Path | str | None = None,
) -> dict[str, str]:
    """Archive by content identity, then atomically advance the latest pointer."""

    validation = validate_manifest_lineage(manifest)
    if not validation["valid"]:
        raise ValueError("macro input manifest lineage invalid: " + "|".join(validation["errors"]))
    digest = str(manifest.get("manifest_sha256") or "").strip().lower()
    identity = str(manifest.get("manifest_id") or "").strip()
    if not digest or not identity:
        raise ValueError("macro input manifest identity is incomplete")
    archive = Path(archive_root) / f"{digest}.json"
    content = _encoded(manifest)
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        if archive.read_bytes() != content:
            raise ValueError("immutable macro input manifest conflict")
    else:
        _atomic_write(archive, content)
    _atomic_write(Path(latest_path), content)
    receipt = {
        "manifest_id": identity,
        "manifest_sha256": digest,
        "archive_path": str(archive.resolve()),
        "latest_path": str(Path(latest_path).resolve()),
    }
    if evidence_root is not None:
        evidence = archive_macro_input_evidence(manifest, evidence_root)
        receipt["evidence_archive_root"] = evidence["archive_root"]
        receipt["evidence_file_count"] = str(evidence["file_count"])
        receipt["evidence_bytes"] = str(evidence["bytes"])
    return receipt


def archive_macro_input_evidence(
    manifest: Mapping[str, Any], evidence_root: Path | str,
) -> dict[str, Any]:
    """Preserve every source byte by content hash for deterministic replay."""

    root = Path(evidence_root)
    root.mkdir(parents=True, exist_ok=True)
    count = 0
    total_bytes = 0
    for entry in manifest.get("entries", []):
        source = Path(str(entry.get("path") or ""))
        digest = str(entry.get("sha256") or "").lower()
        if not source.is_file() or not digest:
            raise ValueError(f"macro evidence source unavailable: {entry.get('key')}")
        suffix = source.suffix.lower() or ".bin"
        destination = root / digest[:2] / f"{digest}{suffix}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if _file_sha256(destination) != digest:
                raise ValueError("content-addressed macro evidence conflict")
        else:
            temporary = destination.with_name(destination.name + ".tmp")
            shutil.copyfile(source, temporary)
            temporary.replace(destination)
        count += 1
        total_bytes += int(entry.get("bytes") or 0)
    return {"archive_root": str(root.resolve()), "file_count": count, "bytes": total_bytes}


__all__ = ["archive_macro_input_evidence", "publish_macro_input_manifest"]
