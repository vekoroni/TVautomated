"""Capture and verify a restorable AVSHUNTER release baseline.

The verifier uses SQLite's backup API and integrity checks rather than copying
live WAL files.  It never restores over production paths.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from typing import Iterable


RUNTIME_SNAPSHOT_PREFIXES = (
    "source_current/pipeline_interpreter/automation_v2_shadow_outputs/",
)

REBUILDABLE_SUFFIXES = frozenset({
    ".py", ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".sql",
    ".md", ".txt", ".ps1", ".bat", ".cmd", ".html", ".css", ".js",
})
SOURCE_EXCLUDED_PARTS = frozenset({
    ".git", "__pycache__", ".pytest_cache", "venv", ".venv", "node_modules",
    "backups", "audit", "archive", "_cleanup_holding", "data", "dropbox",
    "logs", "output", "dist", "build", "tmp", "temp",
    ".claude", ".codex_python313_runtime",
})
SOURCE_TREE_CANDIDATES = (
    "source_full_prechange", "source_rebuildable", "source_current"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sqlite_inventory(path: Path) -> dict[str, object]:
    uri = f"file:{path.as_posix()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        counts = {
            table: connection.execute(
                f'SELECT COUNT(*) FROM "{table.replace(chr(34), chr(34) * 2)}"'
            ).fetchone()[0]
            for table in tables
        }
    finally:
        connection.close()
    return {"integrity_check": integrity, "table_counts": counts}


def sqlite_snapshot(source: Path, destination: Path) -> dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_uri = f"file:{source.as_posix()}?mode=ro"
    source_connection = sqlite3.connect(source_uri, uri=True)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
        destination_connection.commit()
    finally:
        destination_connection.close()
        source_connection.close()
    inventory = sqlite_inventory(destination)
    return {
        "source": str(source),
        "snapshot": str(destination),
        "bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
        **inventory,
    }


def _csv_population(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            next(reader)
        except StopIteration:
            return 0
        return sum(1 for _ in reader)


def _json_population(path: Path) -> int | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("rows", "candidates", "trades", "opportunities"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
    return None


def artifact_record(path: Path, root: Path) -> dict[str, object]:
    population: int | None = None
    if path.suffix.lower() == ".csv":
        population = _csv_population(path)
    elif path.suffix.lower() == ".json":
        population = _json_population(path)
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "population": population,
    }


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout.strip()


def repository_source_inventory(repo: Path) -> set[str]:
    """Enumerate rebuildable tracked and untracked source from Git itself.

    This prevents a hand-maintained directory list from silently omitting a
    production package or launcher.  Runtime stores, virtual environments and
    generated audit evidence are deliberately outside the source rollback set.
    """
    listing = _git(
        repo, "ls-files", "--cached", "--others", "--exclude-standard"
    )
    result: set[str] = set()
    for raw in listing.splitlines():
        relative = raw.strip().replace("\\", "/")
        if not relative:
            continue
        path = Path(relative)
        if path.name.startswith("~$"):
            # Ephemeral Microsoft Office lock files are neither source nor a
            # reproducible release input.
            continue
        lowered_parts = {part.lower() for part in path.parts}
        if lowered_parts & SOURCE_EXCLUDED_PARTS:
            continue
        if any(
            part.lower().startswith((".codex_tmp", ".codex_test", "pip-", "tmp"))
            for part in path.parts
        ):
            continue
        if path.suffix.lower() not in REBUILDABLE_SUFFIXES:
            continue
        # A dirty tree may contain intentionally deleted tracked files.  The
        # rollback snapshot represents the filesystem state at capture time;
        # those deletions are separately preserved by git_status/patch.
        if not (repo / Path(relative)).is_file():
            continue
        result.add(relative)
    return result


def source_snapshot_coverage(backup_dir: Path, repo: Path) -> dict[str, object]:
    source_tree = next(
        (name for name in SOURCE_TREE_CANDIDATES if (backup_dir / name).is_dir()),
        "",
    )
    current_inventory = repository_source_inventory(repo)
    frozen_inventory_path = backup_dir / "source_inventory_prechange.json"
    if frozen_inventory_path.is_file():
        frozen_payload = json.loads(
            frozen_inventory_path.read_text(encoding="utf-8-sig")
        )
        expected = {
            str(item).replace("\\", "/")
            for item in frozen_payload.get("paths", [])
        }
        inventory_source = "source_inventory_prechange.json"
    else:
        expected = current_inventory
        inventory_source = "live_repository_inventory"
    if not source_tree:
        return {
            "passed": False,
            "source_tree": "",
            "expected_count": len(expected),
            "captured_count": 0,
            "missing": sorted(expected),
        }
    root = backup_dir / source_tree
    captured = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and not path.name.startswith("~$")
        and path.suffix.lower() in REBUILDABLE_SUFFIXES
    }
    missing = sorted(expected - captured)
    manifest_name = (
        "source_full_prechange_manifest.json"
        if source_tree == "source_full_prechange"
        else "source_rebuildable_manifest.json"
        if source_tree == "source_rebuildable"
        else "release_file_manifest.json"
    )
    manifest_path = backup_dir / manifest_name
    manifest_missing: list[str] = sorted(expected)
    manifest_hash_failures: list[str] = []
    if manifest_path.is_file():
        records = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        by_relative = {
            str(record["relative_path"]).replace("\\", "/"): record
            for record in records
        }
        manifest_missing = sorted(expected - set(by_relative))
        for relative in sorted(expected & set(by_relative)):
            candidate = root / Path(relative)
            if (
                not candidate.is_file()
                or sha256_file(candidate) != by_relative[relative].get("sha256")
            ):
                manifest_hash_failures.append(relative)
    return {
        "passed": not missing and not manifest_missing and not manifest_hash_failures,
        "source_tree": source_tree,
        "expected_count": len(expected),
        "captured_count": len(captured),
        "missing": missing,
        "inventory_source": inventory_source,
        "added_after_baseline": sorted(current_inventory - expected),
        "removed_after_baseline": sorted(expected - current_inventory),
        "captured_sha256_manifest": manifest_name,
        "manifest_missing": manifest_missing,
        "manifest_hash_failures": manifest_hash_failures,
    }


def test_runtime_record(executable: Path | None = None) -> dict[str, object]:
    """Probe the interpreter that is authorised to produce acceptance XML."""
    target = Path(executable or sys.executable).resolve()
    probe = (
        "import json,sys;"
        "record={'python_executable':sys.executable,'python_version':sys.version};"
        "\ntry:\n import pytest\n"
        "except Exception as exc:\n record.update(pytest_available=False,pytest_error=type(exc).__name__)\n"
        "else:\n record.update(pytest_available=True,pytest_version=pytest.__version__,pytest_path=pytest.__file__)\n"
        "print(json.dumps(record))"
    )
    try:
        completed = subprocess.run(
            [str(target), "-c", probe], check=True, capture_output=True,
            text=True, encoding="utf-8", errors="replace",
        )
        record = json.loads(completed.stdout.strip())
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        record = {
            "python_executable": str(target),
            "pytest_available": False,
            "probe_error": f"{type(error).__name__}:{error}",
        }
    record["recorded_at_utc"] = datetime.now(timezone.utc).isoformat()
    record["pythonpath"] = os.environ.get("PYTHONPATH", "")
    return record


def environment_record(
    repo: Path, *, test_python: Path | None = None
) -> dict[str, object]:
    distributions = sorted(
        (
            {"name": distribution.metadata["Name"], "version": distribution.version}
            for distribution in importlib.metadata.distributions()
            if distribution.metadata.get("Name")
        ),
        key=lambda item: str(item["name"]).lower(),
    )
    try:
        git_head = _git(repo, "rev-parse", "HEAD")
        status = _git(repo, "status", "--short", "--untracked-files=all")
    except (OSError, subprocess.CalledProcessError) as error:
        git_head = f"UNAVAILABLE:{type(error).__name__}"
        status = ""
    return {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_executable": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "git_head": git_head,
        "git_status_lines": status.splitlines(),
        "dependencies": distributions,
        "acceptance_test_runtime": test_runtime_record(test_python),
    }


def verify_backup(backup_dir: Path) -> dict[str, object]:
    release_manifest_path = backup_dir / "release_file_manifest.json"
    manifest_path = (
        release_manifest_path
        if release_manifest_path.is_file()
        else backup_dir / "file_manifest.json"
    )
    records = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    hash_failures: list[str] = []
    for record in records:
        candidate = backup_dir / record["relative_path"]
        if not candidate.is_file() or sha256_file(candidate) != record["sha256"]:
            hash_failures.append(record["relative_path"])

    database_results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(
        prefix="avs_phase0_restore_", dir=str(backup_dir)
    ) as temporary:
        restore_root = Path(temporary).resolve()
        if backup_dir.resolve() not in restore_root.parents:
            raise RuntimeError("isolated restore target escaped the backup directory")
        for source in sorted((backup_dir / "databases").glob("*")):
            if source.suffix.lower() not in {".sqlite", ".db"}:
                continue
            # A failed snapshot attempt can leave an empty destination behind.
            # It is not a database and must never be presented as rollback
            # evidence.  The authoritative manifest records it separately.
            if not source.is_file() or source.stat().st_size == 0:
                continue
            restored = restore_root / source.name
            shutil.copy2(source, restored)
            source_inventory = sqlite_inventory(source)
            restored_inventory = sqlite_inventory(restored)
            database_results.append(
                {
                    "database": source.name,
                    "source_sha256": sha256_file(source),
                    "restored_sha256": sha256_file(restored),
                    "integrity_check": restored_inventory["integrity_check"],
                    "table_counts_match": source_inventory["table_counts"]
                    == restored_inventory["table_counts"],
                }
            )

    passed = not hash_failures and all(
        item["source_sha256"] == item["restored_sha256"]
        and item["integrity_check"] == "ok"
        and item["table_counts_match"]
        for item in database_results
    )
    return {
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "hash_failures": hash_failures,
        "database_results": database_results,
        "isolated_restore_removed_after_verification": True,
    }


def finalise(
    backup_dir: Path, repo: Path, *, test_python: Path | None = None
) -> dict[str, object]:
    environment = environment_record(repo, test_python=test_python)
    prechange_metadata_path = backup_dir / "backup_metadata.json"
    prechange_metadata = (
        json.loads(prechange_metadata_path.read_text(encoding="utf-8-sig"))
        if prechange_metadata_path.is_file()
        else {}
    )
    environment["capture_note"] = (
        "Environment captured during Phase 0 finalisation. The source tree "
        "selected by source_coverage and the database snapshots are the "
        "authoritative pre-change rollback baseline."
    )
    (backup_dir / "environment.json").write_text(
        json.dumps(environment, indent=2), encoding="utf-8"
    )
    raw_manifest = backup_dir / "file_manifest.json"
    full_source_manifest = backup_dir / "source_full_prechange_manifest.json"
    rebuildable_manifest = backup_dir / "source_rebuildable_manifest.json"
    if raw_manifest.is_file():
        raw_file_records = json.loads(raw_manifest.read_text(encoding="utf-8-sig"))
    elif full_source_manifest.is_file():
        source_records = json.loads(
            full_source_manifest.read_text(encoding="utf-8-sig")
        )
        raw_file_records = [
            {
                **record,
                "relative_path": (
                    "source_full_prechange/"
                    + str(record["relative_path"]).replace("\\", "/")
                ),
            }
            for record in source_records
        ]
    elif rebuildable_manifest.is_file():
        source_records = json.loads(
            rebuildable_manifest.read_text(encoding="utf-8-sig")
        )
        raw_file_records = [
            {
                **record,
                "relative_path": (
                    "source_rebuildable/" + str(record["relative_path"]).replace("\\", "/")
                ),
            }
            for record in source_records
        ]
    else:
        raise FileNotFoundError("backup source manifest is missing")
    release_file_records = [
        record
        for record in raw_file_records
        if not any(
            str(record["relative_path"]).replace("\\", "/").startswith(prefix)
            for prefix in RUNTIME_SNAPSHOT_PREFIXES
        )
    ]
    (backup_dir / "release_file_manifest.json").write_text(
        json.dumps(release_file_records, indent=2), encoding="utf-8"
    )
    artifact_root = backup_dir / "accepted_artifacts"
    artifacts = [
        artifact_record(path, artifact_root)
        for path in sorted(artifact_root.rglob("*"))
        if path.is_file()
    ]
    database_candidates = [
        path
        for path in sorted((backup_dir / "databases").glob("*"))
        if path.is_file() and path.suffix.lower() in {".sqlite", ".db"}
    ]
    zero_byte_database_artifacts = [
        path.relative_to(backup_dir).as_posix()
        for path in database_candidates
        if path.stat().st_size == 0
    ]
    databases = [
        {
            "path": path.relative_to(backup_dir).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            **sqlite_inventory(path),
        }
        for path in database_candidates
        if path.stat().st_size > 0
    ]
    verification = verify_backup(backup_dir)
    source_coverage = source_snapshot_coverage(backup_dir, repo)
    runtime_ready = bool(
        environment["acceptance_test_runtime"].get("pytest_available")
    )
    verification["source_coverage"] = source_coverage
    verification["acceptance_test_runtime_ready"] = runtime_ready
    verification["passed"] = bool(
        verification["passed"] and source_coverage["passed"] and runtime_ready
    )
    result = {
        "release": "AVS-SD-002-REV1.1",
        "phase": "PHASE_0",
        "source_baseline": {
            "git_head": prechange_metadata.get("git_head", environment["git_head"]),
            "dirty_entry_count": prechange_metadata.get(
                "dirty_entry_count", len(environment["git_status_lines"])
            ),
            "source_manifest": "release_file_manifest.json",
            "source_tree": source_coverage["source_tree"],
            "captured_before_phase0_contract_changes": bool(prechange_metadata),
            "excluded_runtime_prefixes": list(RUNTIME_SNAPSHOT_PREFIXES),
        },
        "databases": databases,
        "ignored_zero_byte_database_artifacts": zero_byte_database_artifacts,
        "accepted_artifacts": artifacts,
        "restore_verification": verification,
        "excluded_large_dependencies": [
            {
                "path": "data/phantom/phantom_history.db",
                "reason": "No writer is changed in Phase 0; snapshot before any later writer change.",
            }
        ],
    }
    (backup_dir / "phase0_release_manifest.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    (backup_dir / "restore_verification.json").write_text(
        json.dumps(verification, indent=2), encoding="utf-8"
    )
    return result


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-dir", required=True, type=Path)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument(
        "--test-python", type=Path,
        help="Exact Python executable used to produce acceptance-test evidence",
    )
    arguments = parser.parse_args(argv)
    if arguments.verify_only:
        result = verify_backup(arguments.backup_dir.resolve())
    else:
        result = finalise(
            arguments.backup_dir.resolve(), arguments.repo.resolve(),
            test_python=(arguments.test_python.resolve() if arguments.test_python else None),
        )
    print(json.dumps(result, indent=2))
    passed = (
        bool(result["passed"])
        if "passed" in result
        else bool(result["restore_verification"]["passed"])
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
