"""Git facts for the release gate."""

from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath
import subprocess
from typing import Iterable
import warnings

from ..model import GitFacts


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()[:300]}")
    return result.stdout


def _in_production_paths(path: str, production_paths: Iterable[str]) -> bool:
    for prefix in production_paths:
        if prefix == "./*.py":
            if "/" not in path and path.endswith(".py"):
                return True
        elif path.startswith(prefix):
            return True
    return False


def _module_names(path: str) -> set[str]:
    pure = PurePosixPath(path)
    parts = list(pure.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    names = {".".join(parts[i:]) for i in range(len(parts))} if parts else set()
    return {name for name in names if name}


def _imported_names(source: str) -> set[str]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)  # legacy files with invalid escapes
            tree = ast.parse(source)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module)
            for alias in node.names:
                names.add(f"{node.module}.{alias.name}")
    return names


def untracked_imported_modules(
    repo: Path, tracked_py: list[str], untracked_py: list[str], production_paths: Iterable[str]
) -> tuple[str, ...]:
    """Untracked repository modules that tracked production code imports.

    A bare-name match (e.g. ``lab_contract``) is only reported when no tracked
    module provides the same name, to avoid false positives from common names.
    """
    if not untracked_py:
        return ()
    tracked_names: set[str] = set()
    for path in tracked_py:
        tracked_names |= _module_names(path)
    imported: set[str] = set()
    for path in tracked_py:
        if not _in_production_paths(path, production_paths):
            continue
        try:
            imported |= _imported_names((repo / path).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    found = []
    for path in untracked_py:
        for name in sorted(_module_names(path), key=len, reverse=True):
            if name in imported and (("." in name) or name not in tracked_names):
                found.append(f"{path} (imported as {name})")
                break
    return tuple(found)


def collect_git_facts(repo: Path, production_paths: list[str]) -> GitFacts:
    commit = _git(repo, "rev-parse", "HEAD").strip()
    describe = _git(repo, "describe", "--tags", "--always", "--dirty").strip()
    tags = tuple(t for t in _git(repo, "tag", "--points-at", "HEAD").split() if t)
    modified = tuple(
        line[3:].strip() for line in _git(repo, "status", "--porcelain", "--untracked-files=no").splitlines() if line.strip()
    )
    untracked_all = [
        line.strip().replace("\\", "/")
        for line in _git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
        if line.strip()
    ]
    untracked_production = tuple(p for p in untracked_all if _in_production_paths(p, production_paths))
    tracked_py = [p for p in _git(repo, "ls-files", "*.py").splitlines() if p.strip()]
    untracked_py = [p for p in untracked_production if p.endswith(".py")]
    return GitFacts(
        commit_hash=commit,
        describe=describe,
        head_tags=tags,
        modified_tracked_files=modified,
        untracked_production_files=untracked_production,
        untracked_imported_modules=untracked_imported_modules(repo, tracked_py, untracked_py, production_paths),
    )
