"""Create the AVS-FIX-002 Stage 0 dependency and database baseline.

The tool is deliberately read-only against production databases. SQLite
snapshots are created with the backup API and verified in an isolated copy;
production files are never restored or mutated.
"""

from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
from typing import Iterable


DEFAULT_ENTRYPOINTS = (
    "intelligent_orchestrator.py",
    "morning_gate.py",
    "scripts/avshunter_options_intelligence.py",
    "intelligence-lab/intelligence_lab.py",
    "pipeline_interpreter/pipeline_interpreter.py",
    "worker3/integration/runner.py",
)

DEFAULT_DATABASES = (
    "data/canonical/control_plane.sqlite",
    "data/canonical/historical_prices.sqlite",
    "data/canonical/decision_outcome_ledger.sqlite",
)

GOVERNING_REQUIREMENTS = (
    "docs/requirements/AVS-REQ-FIX-002_Annex_A_algorithms_and_models.md",
    "docs/requirements/AVS-REQ-FIX-002_developer_requirements.md",
)

EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "venv",
    ".venv",
    "node_modules",
    "backups",
    "archive",
    "_attic",
    "_cleanup_holding",
    "data",
    "logs",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip()


def python_files(repo: Path) -> list[Path]:
    files: list[Path] = []
    for path in repo.rglob("*.py"):
        relative = path.relative_to(repo)
        if any(part.lower() in EXCLUDED_PARTS for part in relative.parts):
            continue
        if any(part.lower().startswith(("pip-", "tmp", ".codex_")) for part in relative.parts):
            continue
        files.append(relative)
    return sorted(files)


def module_names(path: Path) -> set[str]:
    parts = list(path.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return set()
    names = {".".join(parts)}
    # Hyphenated paths can be CLI entrypoints but cannot be imported by dotted name.
    return {name for name in names if "-" not in name}


def module_index(repo: Path) -> tuple[dict[str, Path], set[str]]:
    tracked = {
        line.replace("\\", "/")
        for line in git(repo, "ls-files", "--cached").splitlines()
        if line
    }
    index: dict[str, Path] = {}
    for path in python_files(repo):
        for name in module_names(path):
            index[name] = path
    return index, tracked


def resolve_from(current: Path, node: ast.ImportFrom) -> str:
    module = node.module or ""
    if node.level <= 0:
        return module
    package = list(current.with_suffix("").parts[:-1])
    if current.name == "__init__.py":
        package.append(current.parent.name)
    trim = max(node.level - 1, 0)
    if trim:
        package = package[:-trim]
    return ".".join([*package, *([module] if module else [])])


def local_dependencies(path: Path, repo: Path, index: dict[str, Path]) -> tuple[set[Path], list[str]]:
    try:
        tree = ast.parse((repo / path).read_text(encoding="utf-8-sig"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError) as error:
        return set(), [f"PARSE_ERROR:{path.as_posix()}:{type(error).__name__}"]
    dependencies: set[Path] = set()
    dynamic: list[str] = []
    for node in ast.walk(tree):
        candidates: list[str] = []
        if isinstance(node, ast.Import):
            candidates.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = resolve_from(path, node)
            if base:
                candidates.append(base)
            candidates.extend(
                f"{base}.{alias.name}" for alias in node.names if base and alias.name != "*"
            )
        elif isinstance(node, ast.Call):
            function = node.func
            is_dynamic = (
                isinstance(function, ast.Attribute)
                and function.attr == "import_module"
            ) or (
                isinstance(function, ast.Name)
                and function.id == "__import__"
            )
            if is_dynamic:
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    candidates.append(node.args[0].value)
                else:
                    dynamic.append(f"{path.as_posix()}:{getattr(node, 'lineno', 0)}")
        for candidate in candidates:
            probe = candidate
            while probe:
                if probe in index:
                    dependencies.add(index[probe])
                    break
                probe = probe.rpartition(".")[0]
    return dependencies, dynamic


def import_graph(repo: Path, entrypoints: Iterable[str]) -> dict[str, object]:
    index, tracked = module_index(repo)
    pending = [Path(item) for item in entrypoints]
    visited: set[Path] = set()
    edges: dict[str, list[str]] = {}
    dynamic: list[str] = []
    missing_entrypoints: list[str] = []
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        if not (repo / current).is_file():
            missing_entrypoints.append(current.as_posix())
            continue
        visited.add(current)
        dependencies, unresolved_dynamic = local_dependencies(current, repo, index)
        dynamic.extend(unresolved_dynamic)
        edges[current.as_posix()] = sorted(item.as_posix() for item in dependencies)
        pending.extend(item for item in dependencies if item not in visited)
    untracked = sorted(
        path.as_posix() for path in visited if path.as_posix() not in tracked
    )
    records = [
        {
            "path": path.as_posix(),
            "sha256": sha256_file(repo / path),
            "tracked": path.as_posix() in tracked,
        }
        for path in sorted(visited)
    ]
    return {
        "entrypoints": list(entrypoints),
        "node_count": len(visited),
        "edge_count": sum(len(items) for items in edges.values()),
        "nodes": records,
        "edges": edges,
        "untracked_reachable_dependencies": untracked,
        "missing_entrypoints": sorted(missing_entrypoints),
        "unresolved_dynamic_import_sites": sorted(set(dynamic)),
        "passed": not untracked and not missing_entrypoints,
    }


def sqlite_inventory(path: Path) -> dict[str, object]:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
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


def snapshot_database(source: Path, destination: Path) -> dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
        destination_connection.commit()
    finally:
        destination_connection.close()
        source_connection.close()
    source_inventory = sqlite_inventory(source)
    snapshot_inventory = sqlite_inventory(destination)
    with tempfile.TemporaryDirectory(prefix="avs_fix_002_restore_", dir=destination.parent) as temporary:
        restored = Path(temporary) / destination.name
        shutil.copy2(destination, restored)
        restored_inventory = sqlite_inventory(restored)
        restorable = (
            restored_inventory == snapshot_inventory
            and restored_inventory["integrity_check"] == "ok"
        )
    return {
        "source": str(source),
        "snapshot": str(destination),
        "bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
        "source_integrity": source_inventory["integrity_check"],
        "snapshot_integrity": snapshot_inventory["integrity_check"],
        "table_counts_match_source": source_inventory["table_counts"] == snapshot_inventory["table_counts"],
        "isolated_restore_verified": restorable,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--entrypoint", action="append", default=[])
    parser.add_argument("--database", action="append", default=[])
    args = parser.parse_args()
    repo = args.repo.resolve()
    output = args.output.resolve()
    backup_root = args.backup_root.resolve()
    entrypoints = tuple(args.entrypoint or DEFAULT_ENTRYPOINTS)
    databases = tuple(args.database or DEFAULT_DATABASES)

    design = repo / "docs/AVS-SD-FIX-002_MONETISABLE_PIPELINE_REMEDIATION.md"
    requirement_records: list[dict[str, str]] = []
    missing_requirements: list[str] = []
    for relative in GOVERNING_REQUIREMENTS:
        requirement = repo / relative
        if not requirement.is_file():
            missing_requirements.append(relative)
            continue
        requirement_records.append(
            {
                "path": relative,
                "sha256": sha256_file(requirement),
                "status": "FINAL v1.2",
            }
        )
    graph = import_graph(repo, entrypoints)
    database_records: list[dict[str, object]] = []
    missing_databases: list[str] = []
    for relative in databases:
        source = (repo / relative).resolve()
        if not source.is_file():
            missing_databases.append(relative)
            continue
        database_records.append(
            snapshot_database(source, backup_root / "databases" / source.name)
        )

    status = git(repo, "status", "--short", "--untracked-files=all").splitlines()
    manifest = {
        "release_id": "AVS-FIX-002",
        "stage": "STAGE_0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": git(repo, "rev-parse", "HEAD"),
        "git_branch": git(repo, "branch", "--show-current"),
        "git_status_lines": status,
        "design": {
            "path": design.relative_to(repo).as_posix(),
            "sha256": sha256_file(design),
            "status": "FINAL v1.2",
        },
        "requirements": requirement_records,
        "missing_requirements": missing_requirements,
        "import_graph": graph,
        "database_snapshots": database_records,
        "missing_databases": missing_databases,
    }
    manifest["passed"] = bool(
        graph["passed"]
        and not missing_requirements
        and not missing_databases
        and all(
            item["source_integrity"] == "ok"
            and item["snapshot_integrity"] == "ok"
            and item["table_counts_match_source"]
            and item["isolated_restore_verified"]
            for item in database_records
        )
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({
        "passed": manifest["passed"],
        "import_nodes": graph["node_count"],
        "untracked_reachable": graph["untracked_reachable_dependencies"],
        "missing_entrypoints": graph["missing_entrypoints"],
        "dynamic_import_sites": len(graph["unresolved_dynamic_import_sites"]),
        "database_snapshots": len(database_records),
        "requirements": len(requirement_records),
        "missing_requirements": missing_requirements,
        "output": str(output),
    }, indent=2))
    return 0 if manifest["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
