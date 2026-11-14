"""Fail-closed, lossless artifact retention. Never remove run folders or databases.

Only archived outcome-learning diagnostics are eligible. Decision books, source
run files, paid responses, ledgers, backups and unknown artifacts are untouched.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid

POLICY_PATH = Path(__file__).resolve().parents[1] / "config/artifact_retention_v1.json"


def policy():
    value = json.loads(POLICY_PATH.read_text(encoding="utf-8-sig"))
    if (value["version"] != "artifact_retention_v1" or value["whole_run_age_deletion"] is not False
            or value["historical_evidence"] != "PRESERVE_LOSSLESS"
            or value["archive_diagnostic_template"] != "diagnostics/outcome_learning_{run_id}.json"
            or not 1 <= int(value["gzip_compression_level"]) <= 9):
        raise ValueError("Unsupported artifact retention policy")
    return value


def _inside(path, root):
    path, root = Path(path).absolute(), Path(root).absolute()
    if path == root or not path.is_relative_to(root):
        raise ValueError("Artifact path escapes retention root")
    if ".." in path.relative_to(root).parts or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Artifact traversal/reparse escape")
    for parent in (root, *path.relative_to(root).parents):
        check = parent if parent == root else root / parent
        if check.exists() and (check.is_symlink() or getattr(check.lstat(), "st_file_attributes", 0) & 1024):
            raise ValueError("Reparse directory is not eligible")
    if path.exists() and (path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 1024):
        raise ValueError("Reparse artifact is not eligible")
    if path.resolve().parent != path.parent.resolve():
        raise ValueError("Unexpected artifact resolution")
    return path


def _hash(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path, value):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


@contextmanager
def _lock(root):
    path = root / ".artifact-retention.lock"
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(descriptor, str(os.getpid()).encode())
        yield
    finally:
        os.close(descriptor)
        path.unlink()


def _index(root, record):
    path = _inside(root / "artifact_retention.json", root)
    value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"version": "artifact_retention_v1", "artifacts": []}
    if value.get("version") != "artifact_retention_v1":
        raise ValueError("Unknown existing retention index; preserve evidence")
    by_path = {r["original_relative_path"]: r for r in value["artifacts"]}
    by_path[record["original_relative_path"]] = record
    value["artifacts"] = list(by_path.values())
    _atomic_json(path, value)


def _archive_diagnostic(source, destination, archive_root):
    rules = policy()
    source = Path(source).absolute()
    root = Path(archive_root).absolute()
    destination = _inside(destination, root)
    # Exactly one recognised diagnostic, not generic JSON/Parquet cleanup.
    match = re.fullmatch(r"outcome_learning_(\d{8}_\d{6})\.json", destination.name)
    if not match or destination.parent.name != "diagnostics" or destination.parent.parent.name != match[1]:
        raise ValueError("Unknown artifact: retain")
    if source.is_symlink() or getattr(source.lstat(), "st_file_attributes", 0) & 1024:
        raise ValueError("Linked source: retain")
    before = source.stat()
    if source == destination and before.st_nlink != 1:
        raise ValueError("Hard-linked archive artifact retained")
    with source.open("rb") as handle:
        original_hash = _hash(handle)
    destination.parent.mkdir(parents=True, exist_ok=True)
    keeper = _inside(destination.with_suffix(".json.gz"), root)
    temporary = keeper.with_name(keeper.name + "." + uuid.uuid4().hex + ".tmp")
    if keeper.exists():
        with gzip.open(keeper, "rb") as handle:
            if _hash(handle) != original_hash:
                raise ValueError("Compressed keeper content conflict: preserve both")
    else:
        try:
            with temporary.open("xb") as raw:
                with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0,
                                   compresslevel=int(rules["gzip_compression_level"])) as compressed:
                    with source.open("rb") as handle:
                        shutil.copyfileobj(handle, compressed, 4 * 1024 * 1024)
                raw.flush()
                os.fsync(raw.fileno())
            with gzip.open(temporary, "rb") as handle:
                if _hash(handle) != original_hash:
                    raise ValueError("Compressed evidence verification failed")
            if keeper.exists():
                raise FileExistsError("Keeper appeared concurrently; retain original")
            os.replace(temporary, keeper)
        finally:
            if temporary.exists():
                temporary.unlink()
    after = source.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError("Source changed during compression; retain original")
    record = {"original_relative_path": str(destination.relative_to(root)),
              "keeper_relative_path": str(keeper.relative_to(root)), "sha256": original_hash,
              "original_bytes": before.st_size, "compressed_bytes": keeper.stat().st_size,
              "original_removed": False, "evidence": "LOSSLESS_SHA256_VERIFIED",
              "recorded_at_utc": datetime.now(timezone.utc).isoformat()}
    _index(root, record)  # Durable proof exists BEFORE removing any raw copy.
    if destination.exists():
        _inside(destination, root)
        with destination.open("rb") as handle:
            if _hash(handle) != original_hash:
                raise ValueError("Raw archive differs; preserve it")
        if source == destination and destination.stat().st_mtime_ns != before.st_mtime_ns:
            raise ValueError("Original changed before removal")
        # Single exact archived file. No recursive deletion or directory cleanup.
        destination.unlink()
        record["original_removed"] = True
        _index(root, record)
    return record


def archive_diagnostic(source, destination, archive_root):
    root = Path(archive_root).absolute()
    for parent in (root, *root.parents):
        if parent.exists() and (parent.is_symlink() or getattr(parent.lstat(), "st_file_attributes", 0) & 1024):
            raise ValueError("Linked archive ancestry is not eligible")
    root.mkdir(parents=True, exist_ok=True)
    with _lock(root):
        return _archive_diagnostic(source, destination, root)


def read_retained_artifact(original_path):
    """Read the original bytes regardless of whether the archived file is compacted."""
    path = Path(original_path)
    if path.exists():
        return path.read_bytes()
    keeper = path.with_suffix(path.suffix + ".gz")
    with gzip.open(keeper, "rb") as handle:
        content = handle.read()
    for ancestor in path.parents:
        index = ancestor / "artifact_retention.json"
        if index.exists():
            receipt = json.loads(index.read_text(encoding="utf-8"))
            for record in receipt.get("artifacts", []):
                if record["original_relative_path"] == str(path.relative_to(ancestor)):
                    if (hashlib.sha256(content).hexdigest() != record["sha256"]
                            or len(content) != record["original_bytes"]):
                        raise ValueError("Retained evidence failed hash/size verification")
                    return content
    raise ValueError("Compressed evidence has no matching retention receipt")


def compact_archives(archive_root, *, execute=True):
    rules = policy()
    root = Path(archive_root).absolute()
    report = {"status": "COMPLETE" if execute else "PLAN", "policy_version": rules["version"],
              "records": [], "original_bytes": 0, "compressed_bytes": 0,
              "whole_run_folders_deleted": 0, "provider_calls": 0}
    if not root.exists():
        return report
    if root.is_symlink() or getattr(root.lstat(), "st_file_attributes", 0) & 1024:
        raise ValueError("Archive root is linked")
    for session in sorted(root.iterdir()):
        if not session.is_dir() or not re.fullmatch(r"\d{8}_\d{6}", session.name):
            continue
        _inside(session, root)
        snapshots = [session]
        revisions = session / "revisions"
        if revisions.exists():
            _inside(revisions, root)
            snapshots += [p for p in revisions.iterdir() if p.is_dir() and re.fullmatch(r"snapshot_[0-9a-f]{32}", p.name)]
        for snapshot in snapshots:
            original = snapshot / "runs" / session.name / rules["archive_diagnostic_template"].format(run_id=session.name)
            _inside(original, root)
            if not original.exists():
                continue
            record = archive_diagnostic(original, original, snapshot) if execute else {"path":str(original), "original_bytes":original.stat().st_size, "compressed_bytes":0}
            report["records"].append(record)
            report["original_bytes"] += record["original_bytes"]
            report["compressed_bytes"] += record["compressed_bytes"]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    result = compact_archives(args.archive_root, execute=args.execute)
    args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k != "records"}, indent=2))


if __name__ == "__main__":
    main()
