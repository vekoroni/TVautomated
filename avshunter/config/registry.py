"""Configuration registry resolution (pure; no I/O, no wall clock)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
from typing import Any, Iterable, Mapping

from avshunter.shared.xnys_calendar import is_xnys_session

from .model import (
    SCHEMA_VERSION,
    AuthorityState,
    ConfigEntry,
    ConfigError,
    ConfigValue,
    ValidationState,
    canonical_json,
)


@dataclass(frozen=True, slots=True)
class ConfigSnapshot:
    """Immutable set of configuration values in force for one session."""

    resolved_for_session: date
    values: tuple[ConfigValue, ...]
    snapshot_id: str

    def _find(self, key: str) -> ConfigValue:
        for item in self.values:
            if item.config_key == key:
                return item
        raise ConfigError(
            f"configuration key {key!r} is unresolvable for session "
            f"{self.resolved_for_session.isoformat()} (no default is ever applied)"
        )

    def get(self, key: str, *, authority: AuthorityState = AuthorityState.SHADOW) -> ConfigValue:
        item = self._find(key)
        if item.validation_state is ValidationState.RETIRED:
            raise ConfigError(f"configuration key {key!r} is RETIRED (version {item.version})")
        if authority is AuthorityState.AUTHORITATIVE and item.validation_state is not ValidationState.VALIDATED:
            raise ConfigError(
                f"configuration key {key!r} is {item.validation_state.value}; "
                "an AUTHORITATIVE context may only use VALIDATED values"
            )
        return item

    def require_validated(self, key: str) -> ConfigValue:
        return self.get(key, authority=AuthorityState.AUTHORITATIVE)

    def pairs(self) -> tuple[tuple[str, int], ...]:
        return tuple((item.config_key, item.version) for item in self.values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "avs-config-snapshot-v1",
            "snapshot_id": self.snapshot_id,
            "resolved_for_session": self.resolved_for_session.isoformat(),
            "values": [
                {
                    "config_key": item.config_key,
                    "version": item.version,
                    "value": item.value,
                    "unit": item.unit,
                    "validation_state": item.validation_state.value,
                }
                for item in self.values
            ],
        }


def _snapshot_id(values: Iterable[ConfigValue]) -> str:
    rows = [[item.config_key, item.version, item.value] for item in values]
    return hashlib.sha256(canonical_json(rows).encode("utf-8")).hexdigest()


class ConfigRegistry:
    """All configuration entries, validated for schema, history and lock."""

    def __init__(self, entries: Iterable[ConfigEntry], lock: Mapping[str, str] | None = None) -> None:
        by_key: dict[str, list[ConfigEntry]] = {}
        seen: set[str] = set()
        for entry in entries:
            if entry.lock_id in seen:
                raise ConfigError(f"duplicate configuration entry {entry.lock_id}")
            seen.add(entry.lock_id)
            by_key.setdefault(entry.config_key, []).append(entry)
        for key, history in by_key.items():
            history.sort(key=lambda item: item.version)
            for position, item in enumerate(history, start=1):
                if item.version != position:
                    raise ConfigError(f"{key}: versions must be 1..n without gaps (found {item.version})")
                if not is_xnys_session(item.effective_from):
                    raise ConfigError(f"{item.lock_id}: effective_from {item.effective_from} is not an XNYS session")
            for earlier, later in zip(history, history[1:]):
                if later.effective_from <= earlier.effective_from:
                    raise ConfigError(
                        f"{later.lock_id}: effective_from must be after version {earlier.version}"
                    )
        self._by_key = {key: tuple(history) for key, history in by_key.items()}
        if lock is not None:
            self.verify_lock(lock)

    @classmethod
    def from_documents(
        cls,
        documents: Iterable[Mapping[str, Any]],
        lock: Mapping[str, str] | None = None,
    ) -> "ConfigRegistry":
        entries: list[ConfigEntry] = []
        for document in documents:
            if document.get("schema_version") != SCHEMA_VERSION:
                raise ConfigError(f"unsupported registry document schema: {document.get('schema_version')!r}")
            prefixes = tuple(str(p) for p in document.get("key_prefixes") or ())
            if not prefixes:
                raise ConfigError(f"registry document {document.get('context')!r} declares no key_prefixes")
            for raw in document.get("entries") or ():
                entry = ConfigEntry.from_mapping(raw)
                if not entry.config_key.startswith(prefixes):
                    raise ConfigError(
                        f"{entry.lock_id} does not belong to context {document.get('context')!r} "
                        f"(allowed prefixes {prefixes})"
                    )
                entries.append(entry)
        return cls(entries, lock)

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_key))

    def entries(self) -> tuple[ConfigEntry, ...]:
        return tuple(item for key in self.keys for item in self._by_key[key])

    def lock_manifest(self) -> dict[str, str]:
        return {entry.lock_id: entry.content_hash() for entry in self.entries()}

    def verify_lock(self, lock: Mapping[str, str]) -> None:
        current = self.lock_manifest()
        problems = []
        for lock_id, expected in sorted(lock.items()):
            actual = current.get(lock_id)
            if actual is None:
                problems.append(f"{lock_id}: locked entry was removed")
            elif actual != expected:
                problems.append(f"{lock_id}: locked entry was modified")
        if problems:
            raise ConfigError("configuration registry is append-only; " + "; ".join(problems))

    def resolve(self, session: date) -> ConfigSnapshot:
        if not is_xnys_session(session):
            raise ConfigError(f"{session.isoformat()} is not an XNYS session")
        values: list[ConfigValue] = []
        for key in self.keys:
            applicable = [item for item in self._by_key[key] if item.effective_from <= session]
            if not applicable:
                continue
            chosen = applicable[-1]
            values.append(
                ConfigValue(
                    config_key=chosen.config_key,
                    version=chosen.version,
                    value=chosen.value,
                    unit=chosen.unit,
                    validation_state=chosen.validation_state,
                )
            )
        ordered = tuple(values)
        return ConfigSnapshot(session, ordered, _snapshot_id(ordered))
