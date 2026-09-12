"""Immutable repository for governed advisory macro packets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def archive_macro_packet(
    packet: Mapping[str, Any], archive_root: Path | str,
) -> dict[str, str]:
    """Persist one packet by its governed id/hash, idempotently and atomically."""

    packet_id = str(packet.get("macro_packet_id") or "").strip()
    declared_hash = str(packet.get("macro_packet_sha256") or "").strip().lower()
    if not packet_id or not declared_hash:
        raise ValueError("macro packet identity is incomplete")
    identity_payload = {
        key: value for key, value in packet.items()
        if key not in {
            "macro_packet_sha256", "macro_packet_id", "macro_normalised_at_utc"
        }
    }
    computed_hash = hashlib.sha256(_canonical_bytes(identity_payload)).hexdigest()
    if computed_hash != declared_hash:
        raise ValueError("macro packet hash does not match immutable content")
    root = Path(archive_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{declared_hash}.json"
    document = {
        "schema_version": "macro_packet_archive_v1",
        "packet_id": packet_id,
        "sha256": declared_hash,
        "packet": dict(packet),
    }
    encoded = json.dumps(
        document, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError("immutable macro packet archive conflict")
    else:
        temporary = path.with_suffix(".json.tmp")
        temporary.write_bytes(encoded)
        temporary.replace(path)
    return {"packet_id": packet_id, "sha256": declared_hash, "archive_path": str(path.resolve())}


def load_macro_packet_by_id(
    packet_id: str, archive_root: Path | str,
) -> dict[str, Any]:
    """Resolve a replay packet by immutable id; never consult a latest pointer."""

    wanted = str(packet_id).strip()
    if not wanted:
        raise ValueError("packet_id is required")
    matches = []
    for path in Path(archive_root).glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if payload.get("packet_id") == wanted:
            matches.append((path, payload))
    if len(matches) != 1:
        raise FileNotFoundError(f"macro packet id resolved {len(matches)} archive entries: {wanted}")
    path, document = matches[0]
    packet = document.get("packet")
    if not isinstance(packet, dict):
        raise ValueError("macro packet archive payload is invalid")
    receipt = archive_macro_packet(packet, path.parent)
    if receipt["archive_path"] != str(path.resolve()):
        raise ValueError("macro packet archive path is inconsistent")
    return packet


__all__ = ["archive_macro_packet", "load_macro_packet_by_id"]
