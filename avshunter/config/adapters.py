"""File adapters for the configuration registry (I/O lives here only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import ConfigError
from .registry import ConfigRegistry, ConfigSnapshot

DEFAULT_REGISTRY_DIR = Path(__file__).resolve().parents[2] / "config" / "registry"
LOCK_FILENAME = "LOCK.json"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_documents(registry_dir: Path = DEFAULT_REGISTRY_DIR) -> list[dict[str, Any]]:
    paths = sorted(p for p in registry_dir.glob("*.json") if p.name != LOCK_FILENAME)
    if not paths:
        raise ConfigError(f"no registry documents found in {registry_dir}")
    return [_read_json(path) for path in paths]


def load_lock(registry_dir: Path = DEFAULT_REGISTRY_DIR) -> dict[str, str]:
    path = registry_dir / LOCK_FILENAME
    if not path.is_file():
        raise ConfigError(f"registry lock file missing: {path}")
    payload = _read_json(path)
    return dict(payload.get("entries") or {})


def load_registry(registry_dir: Path = DEFAULT_REGISTRY_DIR) -> ConfigRegistry:
    return ConfigRegistry.from_documents(load_documents(registry_dir), load_lock(registry_dir))


def update_lock(registry_dir: Path = DEFAULT_REGISTRY_DIR) -> dict[str, str]:
    """Add hashes for new entries; refuse if any locked entry changed or vanished."""
    lock_path = registry_dir / LOCK_FILENAME
    existing = load_lock(registry_dir) if lock_path.is_file() else {}
    registry = ConfigRegistry.from_documents(load_documents(registry_dir), existing)
    manifest = registry.lock_manifest()
    payload = {"schema_version": "avs-config-lock-v1", "entries": dict(sorted(manifest.items()))}
    lock_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return manifest


def write_snapshot(snapshot: ConfigSnapshot, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path
