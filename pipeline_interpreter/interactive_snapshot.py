"""Freeze an Evening Lab book before Morning rewrites same-run files.

The package is a read-only advisory source for selected Interpreter reports.
It neither changes the Morning handoff nor grants execution authority.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any


SNAPSHOT_VERSION = "interpreter_eod_snapshot_v1"


class SnapshotError(ValueError):
    pass


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"invalid snapshot input: {path.name}") from exc
    if not isinstance(value, dict):
        raise SnapshotError(f"snapshot input must be an object: {path.name}")
    return value


def _package_dir(run_root: Path) -> Path:
    return run_root / "interpreter" / "eod_review_v1"


def publish_eod_snapshot(run_root: Path | str) -> dict[str, Any]:
    """Publish one frozen, hash-bound EOD book; idempotent after Morning.

    Call only once EOD run_meta is COMPLETED and the EOD final manifest is
    technically healthy. Existing packages are verified, never overwritten.
    """

    root = Path(run_root).resolve()
    target = _package_dir(root)
    if target.exists():
        return load_eod_snapshot(root)["receipt"]
    run_id = root.name
    manifest_path = root / "final_run_manifest.json"
    meta_path = root / "run_meta.json"
    book_path = root / "intelligence_lab" / f"final_opportunity_book_{run_id}.json"
    manifest = _read_json(manifest_path)
    meta = _read_json(meta_path)
    if (
        manifest.get("run_id") != run_id
        or manifest.get("pipeline_mode") != "EOD"
        or manifest.get("pipeline_technical_health") not in {"PASS", "DEGRADED"}
        or manifest.get("fatal_flags")
    ):
        raise SnapshotError("EOD manifest is not a completed healthy source")
    if not manifest.get("created_at_utc"):
        raise SnapshotError("EOD manifest lacks a point-in-time evidence cutoff")
    if (
        meta.get("canonical_run_id") != run_id
        or meta.get("pipeline_mode") != "EOD"
        or meta.get("run_status") != "COMPLETED"
    ):
        raise SnapshotError("EOD run metadata is not terminal")
    if not book_path.is_file():
        raise SnapshotError("governed Lab opportunity book is missing")

    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=".eod_review_", dir=parent)).resolve()
    try:
        shutil.copyfile(manifest_path, staged / "eod_final_manifest.json")
        shutil.copyfile(meta_path, staged / "eod_run_meta.json")
        book_digest = hashlib.sha256()
        with book_path.open("rb") as source, (staged / "book.json.gz").open("wb") as compressed:
            with gzip.GzipFile(filename="", mode="wb", fileobj=compressed, mtime=0) as sink:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    book_digest.update(block)
                    sink.write(block)
        receipt = {
            "schema_version": SNAPSHOT_VERSION,
            "run_id": run_id,
            "pipeline_mode": "EOD",
            "authority": "ADVISORY_ONLY",
            "eod_technical_health": manifest["pipeline_technical_health"],
            "evidence_cutoff_utc": manifest["created_at_utc"],
            "source_manifest_sha256": _sha(staged / "eod_final_manifest.json"),
            "source_run_meta_sha256": _sha(staged / "eod_run_meta.json"),
            "source_book_sha256": book_digest.hexdigest(),
            "compressed_book_sha256": _sha(staged / "book.json.gz"),
        }
        (staged / "receipt.json").write_text(
            json.dumps(receipt, sort_keys=True, separators=(",", ":")), encoding="utf-8"
        )
        # Directory rename exposes only a complete package. Windows rejects an
        # existing destination; it is never replaced on a restart or race.
        staged.rename(target)
        return receipt
    except (OSError, ValueError) as exc:
        raise SnapshotError(f"EOD snapshot publication failed: {exc}") from exc
    finally:
        if staged.exists():
            if staged != parent and parent in staged.parents:
                shutil.rmtree(staged)


def load_eod_snapshot(run_root: Path | str) -> dict[str, Any]:
    root = Path(run_root).resolve()
    package = _package_dir(root)
    receipt = _read_json(package / "receipt.json")
    if (
        receipt.get("schema_version") != SNAPSHOT_VERSION
        or receipt.get("run_id") != root.name
        or receipt.get("authority") != "ADVISORY_ONLY"
    ):
        raise SnapshotError("EOD snapshot receipt identity mismatch")
    expected = {
        "source_manifest_sha256": package / "eod_final_manifest.json",
        "source_run_meta_sha256": package / "eod_run_meta.json",
        "compressed_book_sha256": package / "book.json.gz",
    }
    for key, path in expected.items():
        if receipt.get(key) != _sha(path):
            raise SnapshotError(f"EOD snapshot hash mismatch: {key}")
    manifest = _read_json(package / "eod_final_manifest.json")
    meta = _read_json(package / "eod_run_meta.json")
    if (manifest.get("run_id") != root.name or manifest.get("pipeline_mode") != "EOD"
            or receipt.get("evidence_cutoff_utc") != manifest.get("created_at_utc")):
        raise SnapshotError("frozen EOD manifest identity mismatch")
    if (meta.get("canonical_run_id") != root.name or meta.get("pipeline_mode") != "EOD"
            or meta.get("run_status") != "COMPLETED"):
        raise SnapshotError("frozen EOD run metadata identity mismatch")
    digest = hashlib.sha256()
    try:
        with gzip.open(package / "book.json.gz", "rb") as handle:
            chunks = []
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
                chunks.append(block)
        book = json.loads(b"".join(chunks))
    except (OSError, UnicodeError, json.JSONDecodeError, EOFError) as exc:
        raise SnapshotError("frozen EOD book is unreadable") from exc
    if digest.hexdigest() != receipt.get("source_book_sha256"):
        raise SnapshotError("frozen EOD book content hash mismatch")
    rows = book.get("rows") if isinstance(book, dict) else None
    if (
        not isinstance(rows, list)
        or book.get("run_id") != root.name
        or book.get("candidate_count") not in (None, len(rows))
    ):
        raise SnapshotError("frozen EOD book population does not reconcile")
    return {"receipt": receipt, "rows": rows, "book": book, "manifest": manifest, "meta": meta}
