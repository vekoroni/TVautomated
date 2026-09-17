"""Run context persistence and configuration file hashes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from avshunter.config.adapters import write_snapshot
from avshunter.config.registry import ConfigSnapshot

from ..model import RunContext


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def legacy_config_hashes(repo: Path) -> dict[str, str]:
    paths = sorted((repo / "config").glob("*.json")) + sorted((repo / "config" / "registry").glob("*.json"))
    return {p.relative_to(repo).as_posix(): sha256_file(p) for p in paths}


def context_dir(repo: Path, context: RunContext) -> Path:
    return repo / "data" / "output" / "run_contexts" / context.run_context_id


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_context(repo: Path, context: RunContext, snapshot: ConfigSnapshot) -> Path:
    folder = context_dir(repo, context)
    write_snapshot(snapshot, folder / "config_snapshot.json")
    path = folder / "run_context.json"
    _atomic_json(path, context.to_dict())
    return path


def write_completion(repo: Path, context: RunContext, payload: dict[str, Any]) -> Path:
    path = context_dir(repo, context) / "run_completion.json"
    _atomic_json(path, payload)
    return path
