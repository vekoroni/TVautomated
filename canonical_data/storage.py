"""Content-hashed, atomic filesystem payload storage."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .errors import PayloadConflictError


@dataclass(frozen=True, slots=True)
class StoredPayload:
    path: Path
    content_hash: str
    byte_count: int
    reused_existing: bool


class AtomicPayloadStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve_path(self, relative_path: str | Path) -> Path:
        candidate = (self.root / relative_path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as error:
            raise ValueError("payload path escapes the canonical store") from error
        return candidate

    @staticmethod
    def hash_bytes(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    def write_bytes(
        self,
        relative_path: str | Path,
        payload: bytes,
        *,
        overwrite: bool = False,
    ) -> StoredPayload:
        target = self.resolve_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        content_hash = self.hash_bytes(payload)
        if target.exists():
            current = target.read_bytes()
            if self.hash_bytes(current) == content_hash:
                return StoredPayload(target, content_hash, len(payload), True)
            if not overwrite:
                raise PayloadConflictError(
                    f"different content already exists at {target}"
                )

        handle, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            if self.hash_bytes(temporary.read_bytes()) != content_hash:
                raise IOError("temporary payload hash verification failed")
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return StoredPayload(target, content_hash, len(payload), False)

    def write_json(
        self,
        relative_path: str | Path,
        payload: Any,
        *,
        overwrite: bool = False,
    ) -> StoredPayload:
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return self.write_bytes(relative_path, encoded, overwrite=overwrite)

    def promote_parquet(
        self,
        source_path: str | Path,
        relative_path: str | Path,
        *,
        expected_hash: str | None = None,
        overwrite: bool = False,
    ) -> StoredPayload:
        """Atomically promote a validated Parquet artifact without deleting source."""
        source = Path(source_path)
        target = Path(relative_path)
        if source.suffix.lower() != ".parquet" or target.suffix.lower() != ".parquet":
            raise ValueError("Parquet promotion requires .parquet source and target")
        payload = source.read_bytes()
        content_hash = self.hash_bytes(payload)
        if expected_hash is not None and content_hash != expected_hash:
            raise ValueError("source Parquet hash does not match expected_hash")
        return self.write_bytes(target, payload, overwrite=overwrite)

    def verify(self, relative_path: str | Path, expected_hash: str) -> bool:
        target = self.resolve_path(relative_path)
        return target.exists() and self.hash_bytes(target.read_bytes()) == expected_hash
