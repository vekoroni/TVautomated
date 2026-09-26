"""Read-only INT-001 release/import baseline; no pipeline or provider calls.

The static import walk is deliberately scoped to named production entrypoints.
Dynamic imports and runtime routes need separate integration tests; this tool
must not be presented as proof that every repository import is healthy.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys
from typing import Iterable


ENTRYPOINTS = (
    "pipeline_interpreter/war_view.py",
    "canonical_data/macro_publication.py",
    "domain/pretrade_focus.py",
    "contracts/lab_control.py",
)
RESEARCH_ONLY = (
    "contracts/war_report_assembler.py",
    "domain/war_temporal_truth.py",
    "domain/war_transmission_chain.py",
    "domain/war_corroboration.py",
    "domain/war_coverage_summary.py",
    "domain/war_report_provenance.py",
)
DESIGN = "docs/AVS-SD-INT-001_DECISION_GRADE_PIPELINE_INTEGRATION.md"


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True,
        encoding="utf-8", check=True,
    )
    return result.stdout.strip()


def _local_module(root: Path, dotted: str) -> str | None:
    if not dotted:
        return None
    relative = Path(*dotted.split("."))
    candidates = (relative.with_suffix(".py"), relative / "__init__.py")
    for candidate in candidates:
        if (root / candidate).is_file():
            return candidate.as_posix()
    return None


def _imports(root: Path, relative: str) -> set[str]:
    source = (root / relative).read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=relative)
    owner = Path(relative).with_suffix("")
    package_parts = owner.parts[:-1]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            candidates = [item.name for item in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = len(package_parts) - node.level + 1
                if keep < 0:
                    continue
                base = ".".join((*package_parts[:keep], *(node.module or "").split(".")))
            else:
                base = node.module or ""
            candidates = [base]
            candidates += [f"{base}.{item.name}" for item in node.names if item.name != "*"]
        else:
            continue
        for dotted in candidates:
            local = _local_module(root, dotted.strip("."))
            if local:
                found.add(local)
    return found


def inspect_static_imports(
    root: Path, entrypoints: Iterable[str], tracked: set[str],
) -> dict[str, object]:
    """Return scoped import closure and any local file missing from Git index."""
    entries = tuple(entrypoints)
    queue = list(entries)
    visited: set[str] = set()
    missing: set[str] = set()
    parse_errors: dict[str, str] = {}
    while queue:
        relative = queue.pop()
        if relative in visited:
            continue
        visited.add(relative)
        if not (root / relative).is_file():
            missing.add(relative)
            continue
        if relative not in tracked:
            missing.add(relative)
        try:
            queue.extend(_imports(root, relative) - visited)
        except (SyntaxError, UnicodeError) as exc:
            parse_errors[relative] = type(exc).__name__
    return {
        "entrypoints": list(entries),
        "local_import_closure_count": len(visited),
        "untracked_or_absent_local_imports": sorted(missing),
        "parse_errors": parse_errors,
        "static_only": True,
    }


def build_baseline(root: Path) -> dict[str, object]:
    tracked = set(_git(root, "ls-files", "-z").split("\0"))
    closure = inspect_static_imports(root, ENTRYPOINTS, tracked)
    head = _git(root, "rev-parse", "--short", "HEAD")
    tags = _git(root, "tag", "--points-at", "HEAD").splitlines()
    return {
        "schema": "avs_int001_stage0_v1",
        "head": head,
        "tags_at_head": tags,
        "tracked_changes": sorted(set(filter(None, (
            _git(root, "diff", "--name-only") + "\n"
            + _git(root, "diff", "--cached", "--name-only")
        ).splitlines()))),
        "design_tracked": DESIGN in tracked,
        "research_only_files": {
            path: ("TRACKED" if path in tracked else "LOCAL_UNTRACKED")
            if (root / path).is_file() else "ABSENT"
            for path in RESEARCH_ONLY
        },
        "production_static_imports": closure,
        "limitations": [
            "Named-entrypoint AST imports only; dynamic imports and browser routes need integration tests.",
            "A tag or tracked file does not establish completed-session acceptance or model authority.",
        ],
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(build_baseline(root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
