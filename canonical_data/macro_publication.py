"""Atomic publication and verification for advisory macro compatibility views.

The Dropbox macro file is the mutable operator-facing publication.  The other
``latest`` files are byte-identical projections for legacy consumers; they are
never independent authorities.  Production runs still pin their own immutable,
run-scoped macro view before applying run-local enrichment.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable
from uuid import uuid4


MACRO_FILENAME = "macro_intelligence_latest.json"
MACRO_AUTHORITY = "ADVISORY_ONLY"


def macro_projection_paths(repository_root: Path | str) -> tuple[Path, Path]:
    root = Path(repository_root)
    return (
        root / "data" / "macro" / MACRO_FILENAME,
        root / "pipeline_interpreter" / "MA_Inputs" / "macro" / MACRO_FILENAME,
    )


def authoritative_macro_root(path: Path | str) -> Path | None:
    """Return the repository root only for the governed Dropbox latest path."""

    candidate = Path(path)
    try:
        root = candidate.parents[2]
    except IndexError:
        return None
    expected = root / "dropbox" / "macro" / MACRO_FILENAME
    return root if candidate.resolve() == expected.resolve() else None


def publish_if_authoritative(path: Path | str) -> dict | None:
    """Synchronize projections when ``path`` is the governed mutable pointer.

    Run-scoped macro files intentionally remain isolated and are not projected
    back into the operator-facing latest package.
    """

    root = authoritative_macro_root(path)
    if root is None:
        return None
    return publish_macro_projections(path, macro_projection_paths(root))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{uuid4().hex}")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _validated_macro_bytes(authoritative_path: Path) -> tuple[bytes, dict]:
    content = authoritative_path.read_bytes()
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"macro publication is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("macro publication must be a JSON object")
    declared = str(payload.get("macro_authority") or MACRO_AUTHORITY).strip().upper()
    if declared != MACRO_AUTHORITY:
        raise ValueError("macro publication authority must remain ADVISORY_ONLY")
    return content, payload


def validate_macro_projection_alignment(
    authoritative_path: Path | str,
    projection_paths: Iterable[Path | str] | None = None,
) -> dict:
    authority = Path(authoritative_path)
    root = authority.parents[2]
    projections = tuple(
        Path(path) for path in (
            projection_paths if projection_paths is not None else macro_projection_paths(root)
        )
    )
    content, _ = _validated_macro_bytes(authority)
    digest = _sha256(content)
    projection_hashes: dict[str, str | None] = {}
    stale_or_missing: list[str] = []
    for path in projections:
        resolved = str(path.resolve())
        observed = _sha256(path.read_bytes()) if path.is_file() else None
        projection_hashes[resolved] = observed
        if observed != digest:
            stale_or_missing.append(resolved)
    return {
        "contract_version": "macro_projection_alignment_v1",
        "authority": MACRO_AUTHORITY,
        "authoritative_path": str(authority.resolve()),
        "sha256": digest,
        "projection_hashes": projection_hashes,
        "stale_or_missing": stale_or_missing,
        "aligned": not stale_or_missing,
    }


def publish_macro_projections(
    authoritative_path: Path | str,
    projection_paths: Iterable[Path | str] | None = None,
    *,
    receipt_path: Path | str | None = None,
) -> dict:
    """Atomically replace every compatibility view with the authority bytes."""

    authority = Path(authoritative_path)
    root = authority.parents[2]
    projections = tuple(
        Path(path) for path in (
            projection_paths if projection_paths is not None else macro_projection_paths(root)
        )
    )
    content, _ = _validated_macro_bytes(authority)
    for path in projections:
        if path.resolve() == authority.resolve():
            continue
        _atomic_bytes(path, content)

    alignment = validate_macro_projection_alignment(authority, projections)
    if not alignment["aligned"]:
        raise RuntimeError(
            "macro projections failed hash verification: "
            + ",".join(alignment["stale_or_missing"])
        )
    receipt = {
        **alignment,
        "published_at_utc": datetime.now(timezone.utc).isoformat(),
        "byte_count": len(content),
    }
    target = Path(receipt_path) if receipt_path is not None else (
        root / "data" / "macro" / "macro_projection_manifest_latest.json"
    )
    receipt_bytes = json.dumps(
        receipt, indent=2, sort_keys=True, allow_nan=False
    ).encode("utf-8")
    _atomic_bytes(target, receipt_bytes)
    return receipt


def write_authoritative_macro(
    authoritative_path: Path | str,
    payload: dict,
    projection_paths: Iterable[Path | str] | None = None,
) -> dict:
    """Atomically write one advisory packet and advance all compatibility views."""

    if not isinstance(payload, dict):
        raise ValueError("macro publication must be a JSON object")
    declared = str(payload.get("macro_authority") or MACRO_AUTHORITY).strip().upper()
    if declared != MACRO_AUTHORITY:
        raise ValueError("macro publication authority must remain ADVISORY_ONLY")
    authority = Path(authoritative_path)
    content = json.dumps(payload, indent=2, allow_nan=False).encode("utf-8")
    _atomic_bytes(authority, content)
    return publish_macro_projections(authority, projection_paths)


__all__ = [
    "MACRO_AUTHORITY",
    "MACRO_FILENAME",
    "authoritative_macro_root",
    "macro_projection_paths",
    "publish_if_authoritative",
    "publish_macro_projections",
    "validate_macro_projection_alignment",
    "write_authoritative_macro",
]
