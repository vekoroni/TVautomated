"""Immutable Evening C5 description and additive Lab/Interpreter projection.

No broker reads, model fit, option valuation, execution or capital authority.
Morning may reuse the packet but may not rewrite the frozen Evening claim.
"""

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping

from domain.descriptive_forecast_handoff import PACKET_VERSION, build_descriptive_packet


class DescriptivePacketError(ValueError):
    pass


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _packet_dir(run_root: Path) -> Path:
    return run_root / "forecast" / PACKET_VERSION


# ── Advisory publication status (ACK 21 Nov 2026) ────────────────────────────
# C5, C6 and C8 describe; they hold no trading authority, so a failure to
# publish one is recorded here and never ends the Evening. Only failures are
# written: a healthy run has no status file.
ADVISORY_STATUS_FILE = "advisory_publication_status.json"
ADVISORY_STATUS_VERSION = "advisory_publication_status_v1"
C5_STAGE = "C5_DESCRIPTIVE_FORECAST"


def _advisory_status_path(run_root: Path) -> Path:
    return Path(run_root) / "forecast" / ADVISORY_STATUS_FILE


def _read_advisory_status(run_root: Path) -> dict[str, Any]:
    path = _advisory_status_path(run_root)
    if not path.is_file():
        return {}
    try:
        stages = json.loads(path.read_text(encoding="utf-8")).get("stages")
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(stages) if isinstance(stages, dict) else {}


def _write_advisory_status(run_root: Path, stages: Mapping[str, Any]) -> None:
    path = _advisory_status_path(run_root)
    if not stages:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps({"version": ADVISORY_STATUS_VERSION, "run_id": Path(run_root).name,
                    "stages": dict(stages)}, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def record_advisory_publication(
    run_root: Path | str, stage: str, state: str, *, reason: str = "", recorded_at_utc: str = "",
) -> None:
    """Record that an advisory packet is missing, and why. Missing is never neutral."""
    root = Path(run_root)
    stages = _read_advisory_status(root)
    stages[stage] = {"state": state, "reason": str(reason)[:500], "authority": "ADVISORY_ONLY",
                     "recorded_at_utc": recorded_at_utc}
    _write_advisory_status(root, stages)


def clear_advisory_publication(run_root: Path | str, stage: str) -> None:
    """Drop an earlier failure record for a stage that is being attempted again."""
    root = Path(run_root)
    stages = _read_advisory_status(root)
    if stages.pop(stage, None) is not None:
        _write_advisory_status(root, stages)


def advisory_publication_state(run_root: Path | str, stage: str) -> str | None:
    """The recorded failure state for a stage, or None when no failure is recorded."""
    return (_read_advisory_status(Path(run_root)).get(stage) or {}).get("state")


def may_publish_descriptive_packet(run_root: Path | str) -> bool:
    """False once the pre-option freeze has failed: the description is never published late."""
    return advisory_publication_state(run_root, C5_STAGE) is None


def load_descriptive_packet(run_root: Path | str) -> dict[str, Any]:
    root = Path(run_root)
    folder = _packet_dir(root)
    try:
        receipt = json.loads((folder / "receipt.json").read_text(encoding="utf-8"))
        packet_file = folder / "packet.json"
        if receipt.get("packet_sha256") != _sha(packet_file):
            raise DescriptivePacketError("descriptive packet hash mismatch")
        packet = json.loads(packet_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DescriptivePacketError("descriptive packet incomplete or unreadable") from error
    if (receipt.get("run_id") != root.name or packet.get("run_id") != root.name
            or receipt.get("packet_version") != PACKET_VERSION
            or packet.get("packet_version") != PACKET_VERSION
            or receipt.get("authority") != "ADVISORY_ONLY"
            or packet.get("row_count") != len(packet.get("rows", []))):
        raise DescriptivePacketError("descriptive packet identity mismatch")
    return packet


def load_or_publish_descriptive_packet(run_root: Path | str) -> dict[str, Any]:
    """Publish only once from Discovery; later Morning reads the same bytes."""
    root = Path(run_root)
    target = _packet_dir(root)
    if target.exists():
        return load_descriptive_packet(root)
    if not may_publish_descriptive_packet(root):
        # The Evening recorded that the pre-option freeze failed. Files on disk
        # now may already carry option-stage changes, so nothing is published.
        raise DescriptivePacketError("descriptive packet was not frozen before options; it is not published late")
    discovery = root / "discovery" / f"discovery_candidates_ultimate_{root.name}.csv"
    vanguard_dir = root / "vanguard"
    vanguard_csv = vanguard_dir / "vanguard_signals.csv"
    rejects_csv = vanguard_dir / "vanguard_rejects.csv"
    vanguard_summary = vanguard_dir / "vanguard_run_summary.json"
    try:
        meta = json.loads((root / "run_meta.json").read_text(encoding="utf-8-sig"))
        if (meta.get("canonical_run_id") != root.name
                or meta.get("pipeline_mode") != "EOD"):
            raise DescriptivePacketError("EOD run identity is not governed")
        plan = meta["dynamic_plan"]
        session = plan["last_completed_session"]
        cutoff = plan["evidence_cutoff_utc"]
        with discovery.open(newline="", encoding="utf-8-sig") as handle:
            source_rows = list(csv.DictReader(handle))
        vanguard_rows: list[dict[str, str]] = []
        vanguard_rejections: list[dict[str, str]] = []
        if vanguard_summary.is_file():
            summary = json.loads(vanguard_summary.read_text(encoding="utf-8"))
            if summary.get("run_id") != root.name or not vanguard_csv.is_file():
                raise DescriptivePacketError("Vanguard summary and run identity do not reconcile")
            with vanguard_csv.open(newline="", encoding="utf-8-sig") as handle:
                vanguard_rows = list(csv.DictReader(handle))
            if rejects_csv.is_file():
                with rejects_csv.open(newline="", encoding="utf-8-sig") as handle:
                    vanguard_rejections = list(csv.DictReader(handle))
            if (int(summary.get("passed", -1)) != len(vanguard_rows)
                    or int(summary.get("rejected", -1)) != len(vanguard_rejections)
                    or int(summary.get("packages_total", -1)) != len(source_rows)):
                raise DescriptivePacketError("Vanguard/Discovery population does not reconcile")
        elif vanguard_csv.exists() or rejects_csv.exists():
            raise DescriptivePacketError("Vanguard files exist without terminal summary")
    except (OSError, KeyError, json.JSONDecodeError) as error:
        raise DescriptivePacketError("EOD Discovery or run metadata unavailable") from error
    packet = build_descriptive_packet(
        root.name, session, cutoff, source_rows,
        discovery_sha256=_sha(discovery),
        vanguard_rows=vanguard_rows,
        vanguard_rejections=vanguard_rejections,
        vanguard_sha256=_sha(vanguard_csv) if vanguard_summary.is_file() else None,
    )
    if vanguard_summary.is_file():
        packet["source_vanguard_summary_sha256"] = _sha(vanguard_summary)
        packet["source_vanguard_rejections_sha256"] = _sha(rejects_csv) if rejects_csv.is_file() else None
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".descriptive_", dir=parent))
    try:
        packet_file = staging / "packet.json"
        packet_file.write_text(json.dumps(packet, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        receipt = {"packet_version": PACKET_VERSION, "run_id": root.name,
                   "authority": "ADVISORY_ONLY", "packet_sha256": _sha(packet_file)}
        (staging / "receipt.json").write_text(
            json.dumps(receipt, sort_keys=True, separators=(",", ":")), encoding="utf-8"
        )
        # The directory rename exposes only a complete packet. Never replace a
        # published Evening assessment if another writer won a race.
        if target.exists():
            return load_descriptive_packet(root)
        staging.rename(target)
        return packet
    finally:
        if staging.exists():
            for child in staging.iterdir():
                child.unlink()
            staging.rmdir()


def project_lab_descriptive_rows(
    rows: Iterable[Mapping[str, Any]], packet: Mapping[str, Any] | None,
    expression_packet: Mapping[str, Any] | None = None,
    valuation_packet: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Append C5/C8 descriptive fields without changing legacy decisions."""
    index = {item["ticker"]: item for item in (packet or {}).get("rows", [])}
    expressions = {item["ticker"]: item for item in (expression_packet or {}).get("rows", [])}
    valuations = {item["ticker"]: item for item in (valuation_packet or {}).get("rows", [])}
    projected = []
    for source in rows:
        row = dict(source)
        ticker = str(row.get("ticker") or "").strip().upper()
        claim = index.get(ticker)
        if claim is None:
            claim = {
                "forecast_version": "ticker_forecast_v2",
                "forecast_state": "DATA_INSUFFICIENT",
                "forecast_direction": None,
                "forecast_reference_spot": None,
                "forecast_target_spot": None,
                "forecast_invalidation_spot": None,
                "forecast_thesis_id": None,
                "forecast_reason": (
                    "TICKER_NOT_IN_DISCOVERY_PACKET" if packet else "FORECAST_PACKET_UNAVAILABLE"
                ),
                "c4_reliability_state": "NOT_ESTIMABLE",
                "c8_valuation_state": "NOT_VALUED_STATISTICAL_SUPPORT",
                "forecast_authority": "ADVISORY_ONLY",
                "forecast_source": "DISCOVERY_PREOPTION" if packet else "UNAVAILABLE",
                "forecast_vanguard_state": "UNAVAILABLE",
                "forecast_vanguard_reason": None,
                "forecast_auction_state": None,
                "forecast_auction_control": None,
                "forecast_legacy_statistical_context": None,
                "forecast_structure_stage": None,
                "forecast_compression_state": None,
                "forecast_evidence_state": "UNRESOLVED",
                "forecast_scenarios_json": None,
                "forecast_countercase": None,
                "forecast_thesis_status": None,
                "forecast_trade_plan_state": None,
                "forecast_candidate_geometry_json": None,
                "forecast_legacy_statistical_basis": None,
            }
        row.update(claim)
        row["forecast_packet_state"] = "AVAILABLE" if packet else "UNAVAILABLE"
        selected = row.get("selected_contract_symbols") or row.get("selected_contract_symbol")
        if isinstance(selected, str) and selected.strip().lower() in {
            "", "[]", "null", "none", "nan",
        }:
            selected = None
        expression = expressions.get(ticker)
        if str(row.get("validation_transition") or "").strip().upper() == "THESIS_INVALIDATED":
            expression_state = "NOT_APPLICABLE_CURRENTLY_INVALIDATED"
        elif claim["forecast_state"] != "DESCRIPTIVE_ONLY":
            expression_state = "NOT_APPLICABLE_NO_GOVERNED_FORECAST"
        elif expression is not None:
            expression_state = str(expression["expression_state"])
        else:
            expression_state = "LEGACY_PROPOSAL_UNVALUED" if selected else "NO_VERIFIED_EXPRESSION"
        row["option_expression_state"] = expression_state
        row["option_expression_candidate_count"] = len(expression["candidates"]) if expression else 0
        row["option_expression_packet_state"] = "AVAILABLE" if expression_packet else "UNAVAILABLE"
        valuation = valuations.get(ticker)
        row["c8_valuation_state"] = (
            valuation["valuation_state"] if valuation is not None
            else "NOT_VALUED_STATISTICAL_SUPPORT"
        )
        row["c8_numeric_ev"] = None
        research = [
            {"option_symbol": item["option_symbol"], **item["research_ev"]}
            for item in (valuation or {}).get("expressions", [])
            if item.get("research_ev", {}).get("state") == "RESEARCH_EV_UNCALIBRATED"
        ]
        row["research_ev_state"] = (
            "RESEARCH_EV_UNCALIBRATED" if research else
            "NO_RESEARCH_EV" if valuation is not None else "RESEARCH_NOT_ASSESSED"
        )
        row["research_ev_candidate_count"] = len(research)
        row["research_ev_contracts_json"] = json.dumps(
            research, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ) if research else None
        projected.append(row)
    return projected
