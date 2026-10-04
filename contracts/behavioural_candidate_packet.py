"""Immutable Evening behavioural candidate packet (BEH-001 phase 2A).

Published once after the C5 freeze, from the run's staged behavioural candidates and
Vanguard outputs; later readers get the same bytes. Display and measurement only: no
stage gates on it. A publication failure never aborts the Evening.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from domain.structure_behaviour.handoff_packet import PACKET_VERSION, build_candidate_packet

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "beh001_handoff_v1.json"


class CandidatePacketError(ValueError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _folder(run_root: Path) -> Path:
    return run_root / "forecast" / PACKET_VERSION


def _rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    return frame.replace({"": None}).to_dict(orient="records")


def _candidates(run_root: Path) -> tuple[list[dict], Path]:
    found = sorted((run_root / "discovery").glob(f"behavioural_candidates_{run_root.name}.csv")) or \
        sorted((run_root / "discovery").glob("behavioural_candidates_*.csv"))
    if not found:
        raise CandidatePacketError("behavioural candidates CSV not staged for this run")
    frame = pd.read_csv(found[-1], keep_default_na=True)
    return frame.where(frame.notna(), None).to_dict(orient="records"), found[-1]


def load_candidate_packet(run_root: Path | str) -> dict[str, Any]:
    root = Path(run_root)
    folder = _folder(root)
    try:
        receipt = json.loads((folder / "receipt.json").read_text(encoding="utf-8"))
        if receipt.get("packet_sha256") != _sha(folder / "packet.json"):
            raise CandidatePacketError("candidate packet hash mismatch")
        packet = json.loads((folder / "packet.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CandidatePacketError("candidate packet incomplete or unreadable") from error
    if packet.get("run_id") != root.name or packet.get("packet_version") != PACKET_VERSION:
        raise CandidatePacketError("candidate packet identity mismatch")
    return packet


def load_or_publish_candidate_packet(run_root: Path | str) -> dict[str, Any]:
    root = Path(run_root)
    folder = _folder(root)
    if (folder / "receipt.json").is_file():
        return load_candidate_packet(root)
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    candidates, source = _candidates(root)
    packet = build_candidate_packet(root.name, candidates, _rows(root / "vanguard" / "vanguard_signals.csv"),
                                    _rows(root / "vanguard" / "vanguard_rejects.csv"), policy)
    packet["source_candidates_sha256"] = _sha(source)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "packet.json").write_text(json.dumps(packet, sort_keys=True, default=str), encoding="utf-8")
    if packet["records"]:
        keys = sorted({k for r in packet["records"] for k in r})
        with (folder / "candidates.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=keys)
            writer.writeheader()
            writer.writerows(packet["records"])
    (folder / "receipt.json").write_text(json.dumps({
        "run_id": root.name, "packet_version": PACKET_VERSION, "authority": packet["authority"],
        "packet_sha256": _sha(folder / "packet.json"), "counts": packet["counts"]}, indent=1), encoding="utf-8")
    return load_candidate_packet(root)


def publish_candidate_packet_safely(run_root: Path | str) -> str:
    """Orchestrator entry: returns the status and records it in status.json (listed in
    the final run manifest); never raises."""
    try:
        packet = load_or_publish_candidate_packet(run_root)
        status, counts = f"PUBLISHED:{packet['counts']['records']}", packet["counts"]
    except Exception as error:
        status, counts = f"CANDIDATE_PACKET_UNAVAILABLE:{type(error).__name__}:{error}", {}
    try:
        folder = _folder(Path(run_root))
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "status.json").write_text(json.dumps({"status": status, "counts": counts}, indent=1),
                                            encoding="utf-8")
    except Exception:
        pass
    return status
