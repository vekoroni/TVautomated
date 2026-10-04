"""Append-only Morning observations against the frozen Evening ticker packet.

This record does not re-estimate C4 probabilities or change C5 direction. It
explains the dated validation transition without rewriting the prior packet.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from contracts.descriptive_forecast_packet import load_descriptive_packet


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publish_morning_revisions(
    run_root: Path | str,
    rows: Iterable[Mapping[str, Any]],
    *,
    observation_cutoff_utc: str,
) -> dict[str, Any]:
    root = Path(run_root)
    cutoff = datetime.fromisoformat(observation_cutoff_utc.replace("Z", "+00:00"))
    if cutoff.tzinfo is None:
        raise ValueError("Morning observation cutoff requires a timezone")
    frozen = load_descriptive_packet(root)
    source = root / "forecast" / "ticker_forecast_descriptive_v1" / "packet.json"
    prior_hash = _sha(source)
    by_ticker = {item["ticker"]: item for item in frozen["rows"]}
    revisions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker or ticker in seen or ticker not in by_ticker:
            raise ValueError("Morning ticker missing, duplicate or absent from frozen forecast")
        seen.add(ticker)
        transition = str(row.get("validation_transition") or "").strip().upper()
        if transition not in {"THESIS_CONFIRMED", "THESIS_DEVELOPING", "THESIS_INVALIDATED"}:
            transition = "UNRESOLVED_REVIEW"
        revisions.append({
            "ticker": ticker,
            "frozen_thesis_id": by_ticker[ticker]["forecast_thesis_id"],
            "frozen_forecast_state": by_ticker[ticker]["forecast_state"],
            "frozen_forecast_direction": by_ticker[ticker]["forecast_direction"],
            "morning_transition": transition,
            "validation_event_id": row.get("validation_event_id"),
            "observation_cutoff_utc": observation_cutoff_utc,
            "authority": "VALIDATION_ONLY",
        })
    packet = {
        "schema_version": "forecast_morning_revision_v1",
        "run_id": root.name,
        "frozen_packet_sha256": prior_hash,
        "observation_cutoff_utc": observation_cutoff_utc,
        "row_count": len(revisions),
        "rows": revisions,
    }
    destination = root / "forecast" / "forecast_morning_revision_v1"
    destination = destination / "events"
    destination.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(packet, sort_keys=True, separators=(",", ":"), allow_nan=False)
    event_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    output = destination / f"{event_hash}.json"
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing != packet:
            raise ValueError("Morning forecast revision hash collision or mutation")
        return existing
    fd, temporary_name = tempfile.mkstemp(prefix=".revision_", suffix=".json", dir=destination)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(encoded)
        if output.exists():
            raise ValueError("Morning forecast revision was published concurrently")
        temporary.rename(output)
    finally:
        temporary.unlink(missing_ok=True)
    return packet


def load_morning_revisions(run_root: Path | str) -> list[dict[str, Any]]:
    """Read every immutable dated observation; no later event rewrites Evening."""
    root = Path(run_root)
    folder = root / "forecast" / "forecast_morning_revision_v1" / "events"
    if not folder.is_dir():
        return []
    frozen_path = root / "forecast" / "ticker_forecast_descriptive_v1" / "packet.json"
    frozen_hash = _sha(frozen_path)
    result: list[dict[str, Any]] = []
    for path in folder.glob("*.json"):
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != path.stem:
            raise ValueError("Morning revision filename/content mismatch")
        event = json.loads(payload)
        if (event.get("run_id") != root.name or event.get("frozen_packet_sha256") != frozen_hash
                or event.get("row_count") != len(event.get("rows", []))):
            raise ValueError("Morning revision has wrong frozen identity or row count")
        result.append(event)
    return sorted(result, key=lambda item: item["observation_cutoff_utc"])
