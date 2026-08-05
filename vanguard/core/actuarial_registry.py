from __future__ import annotations

import json
import os
import warnings
from pathlib import Path
from typing import Any, Dict, Optional


class ActuarialRegistryError(RuntimeError):
    """Raised when the actuarial registry or database path is invalid."""


STRICT_ENV = "AVSHUNTER_STRICT_ACTUARIAL_V6"
REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "config" / "actuarial_registry.json"


def strict_mode() -> bool:
    return os.environ.get(STRICT_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def load_registry(path: Optional[Path] = None) -> Dict[str, Any]:
    registry_path = Path(path) if path is not None else REGISTRY_PATH
    if not registry_path.exists():
        raise ActuarialRegistryError(f"Actuarial registry not found: {registry_path}")
    with registry_path.open("r", encoding="utf-8") as f:
        registry = json.load(f)
    return registry


def _normalise_path(path: Path) -> Path:
    return Path(path).expanduser().resolve()


def canonical_db_path(registry: Optional[Dict[str, Any]] = None, *, require_exists: bool = True) -> Path:
    registry = registry or load_registry()
    raw = (registry.get("canonical_database") or {}).get("path")
    if not raw:
        raise ActuarialRegistryError("Registry missing canonical_database.path")
    path = _normalise_path(Path(raw))
    validate_production_db_path(path, registry=registry, strict=True)
    if require_exists and not path.exists():
        raise FileNotFoundError(f"Canonical actuarial database not found: {path}")
    return path


def canonical_cache_path(registry: Optional[Dict[str, Any]] = None) -> Path:
    registry = registry or load_registry()
    raw = (registry.get("canonical_cache") or {}).get("path")
    if not raw:
        raise ActuarialRegistryError("Registry missing canonical_cache.path")
    return _normalise_path(Path(raw))


def pipeline_status_path(registry: Optional[Dict[str, Any]] = None) -> Path:
    registry = registry or load_registry()
    raw = (registry.get("pipeline_status") or {}).get("path")
    if not raw:
        raise ActuarialRegistryError("Registry missing pipeline_status.path")
    return _normalise_path(Path(raw))


def expected_schema_fingerprint(registry: Optional[Dict[str, Any]] = None) -> str:
    registry = registry or load_registry()
    return str((registry.get("canonical_database") or {}).get("expected_schema_fingerprint") or "")


def schema_version(registry: Optional[Dict[str, Any]] = None) -> str:
    registry = registry or load_registry()
    return str(registry.get("schema_version") or "unknown")


def is_forbidden_database_path(path: Path, registry: Optional[Dict[str, Any]] = None) -> bool:
    registry = registry or load_registry()
    name = Path(path).name.lower()
    forbidden_names = {str(x).lower() for x in registry.get("forbidden_production_databases", [])}
    forbidden_suffixes = tuple(str(x).lower() for x in registry.get("forbidden_suffixes", []))
    return name in forbidden_names or name.endswith(forbidden_suffixes)


def validate_production_db_path(
    path: Path,
    registry: Optional[Dict[str, Any]] = None,
    *,
    strict: Optional[bool] = None,
) -> bool:
    registry = registry or load_registry()
    strict = strict_mode() if strict is None else strict
    requested = _normalise_path(Path(path))
    canonical = _normalise_path(Path((registry.get("canonical_database") or {}).get("path", "")))

    problems = []
    if requested != canonical:
        problems.append(f"non-canonical actuarial database path: {requested}")
    if is_forbidden_database_path(requested, registry=registry):
        problems.append(f"forbidden actuarial production database path: {requested.name}")

    if not problems:
        return True

    message = "; ".join(problems)
    if strict:
        raise ActuarialRegistryError(message)
    warnings.warn(message, RuntimeWarning, stacklevel=2)
    return False
