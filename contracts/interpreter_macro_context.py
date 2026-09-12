"""Governed advisory macro snapshot for Morning Gate, Lab and Interpreter.

This module performs filesystem reads only. It snapshots the canonical macro
drop into the active run, records source hashes, and removes fields that could
be mistaken for trading authority.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from contracts.us_money_index_contract import normalise_us_money_index_sidecar
from macro_domain.us_money_index import evaluate_scenarios, sector_advisory


SCHEMA_VERSION = "interpreter_macro_context_v1"
AUTHORITY_STATEMENT = (
    "MACRO_ADVISORY_ONLY — macro may explain sector rotation and market context "
    "but cannot change direction, contract, lifecycle, final action, capital "
    "permission or position size."
)
CANONICAL_SOURCES = {
    "core_macro": ("macro_intelligence_latest.json", "json"),
    "bond_macro": ("bond_macro_state.json", "json"),
    "auction_calendar": ("auction_calendar.csv", "csv"),
    "enrichment_delta": ("avshunter_macro_enrichment_delta.json", "json"),
    "us_money_index": ("avshunter_us_money_index.json", "json"),
}
FORBIDDEN_AUTHORITY_KEYS = frozenset({
    "direction", "governed_direction", "selected_contract_symbol",
    "contract_symbol", "thesis_state", "olm_guard_disposition", "final_action",
    "capital_permission", "execution_permission", "size_multiplier",
    "macro_filter", "risk_on_off_switch", "trade_go", "trigger_required",
    "position_size", "position_size_pct", "execution_verdict",
})


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_hash(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        temporary.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _sanitise(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _sanitise(item)
            for key, item in value.items()
            if str(key) not in FORBIDDEN_AUTHORITY_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_sanitise(item) for item in value]
    return value


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _ticker_advisory_index(enrichment: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Normalise both enrichment contract shapes into a ticker-keyed index.

    Early enrichment packets supplied ``macro_exposure_index`` directly.  The
    current production contract supplies ``theme_deltas`` plus normalised
    catalyst records under ``macro_exposure_index_build``.  Supporting both
    shapes keeps the governed packet additive and prevents a valid enrichment
    file from becoming an empty Lab/Interpreter overlay.
    """

    direct = enrichment.get("macro_exposure_index")
    if isinstance(direct, Mapping):
        return {
            _text(ticker).upper(): [dict(item) for item in items if isinstance(item, Mapping)]
            for ticker, items in direct.items()
            if _text(ticker) and isinstance(items, list)
        }

    index: dict[str, list[dict[str, Any]]] = {}

    def add(ticker: Any, item: Mapping[str, Any]) -> None:
        symbol = _text(ticker).upper()
        if not symbol:
            return
        index.setdefault(symbol, []).append(dict(item))

    role_fields = {
        "beneficiary_universe": "BENEFICIARY",
        "vulnerable_universe": "VULNERABLE",
        "context_universe": "CONTEXT_ONLY",
    }
    themes = enrichment.get("theme_deltas")
    if isinstance(themes, list):
        for theme in themes:
            if not isinstance(theme, Mapping):
                continue
            base = {
                "theme_id": theme.get("theme_id"),
                "theme_name": theme.get("theme_name"),
                "delta_type": theme.get("delta_type"),
                "directional_pressure": theme.get("directional_pressure"),
                "event_guards": theme.get("event_guards") or [],
                "confirmation_required": theme.get("confirmation_required") or [],
                "invalidation_conditions": theme.get("invalidation_conditions") or [],
            }
            for field, role in role_fields.items():
                tickers = theme.get(field)
                if not isinstance(tickers, list):
                    continue
                for ticker in tickers:
                    add(ticker, {**base, "role": role, "source": "theme_delta"})

    build = _mapping(enrichment.get("macro_exposure_index_build"))
    records = build.get("normalised_catalyst_records")
    if isinstance(records, list):
        for record in records:
            if not isinstance(record, Mapping):
                continue
            add(record.get("ticker"), {
                "theme_id": record.get("event_category") or record.get("catalyst_type"),
                "theme_name": record.get("event_name") or record.get("event_category"),
                "role": record.get("ticker_role") or "NORMALISED_CATALYST_RECORD",
                "directional_pressure": (
                    record.get("catalyst_direction_bias") or record.get("directional_bias")
                ),
                "event_guards": record.get("event_guards") or [],
                "narrative": record.get("narrative"),
                "confirmation_required": record.get("confirmation_signals"),
                "invalidation_conditions": record.get("invalidation_signals"),
                "source": "normalised_catalyst_record",
            })

    return index


def _load(path: Path, kind: str) -> tuple[Any, dict[str, Any]]:
    record = {
        "filename": path.name,
        "path": str(path.resolve()),
        "status": "MISSING",
        "sha256": "",
        "as_of_utc": "",
    }
    if not path.is_file():
        return ({} if kind == "json" else []), record
    record["sha256"] = _sha256(path)
    record["modified_at_utc"] = datetime.fromtimestamp(
        path.stat().st_mtime, timezone.utc
    ).isoformat()
    try:
        if kind == "json":
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(value, Mapping):
                raise ValueError("JSON root must be an object")
            value = dict(value)
        else:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                value = [
                    dict(row)
                    for row in csv.DictReader(handle)
                    if any(_text(item) for item in row.values())
                ]
        record["status"] = "VALID" if value else "EMPTY"
        if isinstance(value, Mapping):
            record["as_of_utc"] = next(
                (
                    _text(value.get(key))
                    for key in ("as_of_utc", "generated_at", "report_date", "as_of_date")
                    if _text(value.get(key))
                ),
                record["modified_at_utc"],
            )
        else:
            record["as_of_utc"] = record["modified_at_utc"]
        return value, record
    except (OSError, csv.Error, json.JSONDecodeError, ValueError) as error:
        record.update({"status": "INVALID", "error": str(error)})
        return ({} if kind == "json" else []), record


def _embedded(core: Mapping[str, Any], name: str) -> Any:
    extras = core.get("extras") if isinstance(core.get("extras"), Mapping) else {}
    if name == "bond_macro":
        return extras.get("bond_macro") if isinstance(extras.get("bond_macro"), Mapping) else {}
    if name == "enrichment_delta":
        value = extras.get("macro_enrichment_delta")
        return value if isinstance(value, Mapping) else {}
    if name == "auction_calendar":
        bond = _embedded(core, "bond_macro")
        auction = bond.get("auction") if isinstance(bond.get("auction"), Mapping) else {}
        rows = auction.get("calendar_rows")
        return rows if isinstance(rows, list) else []
    if name == "us_money_index":
        value = extras.get("us_money_index")
        return value if isinstance(value, Mapping) else {}
    return {}


def _run_snapshot(run_dir: Path) -> tuple[dict[str, Any], Path | None]:
    path = run_dir / "macro_snapshot.json"
    if not path.is_file():
        return {}, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}, None
    return (dict(payload), path) if isinstance(payload, Mapping) else ({}, None)


def _quant_packet(core: Mapping[str, Any], run_dir: Path) -> dict[str, Any]:
    embedded = core.get("macro_quant_packet")
    if isinstance(embedded, Mapping) and embedded:
        return dict(embedded)
    path = run_dir / "macro_quant_packet.json"
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            return dict(payload) if isinstance(payload, Mapping) else {}
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def materialize_interpreter_macro_context(
    *,
    run_dir: Path | str,
    session_date: str,
    macro_dir: Path | str,
    prefer_run_snapshot: bool = False,
) -> dict[str, Any]:
    """Materialize one advisory packet from canonical or run-frozen inputs.

    ``prefer_run_snapshot`` is the production orchestration mode. It consumes
    only ``macro_snapshot.json`` and sidecars already embedded in that frozen
    snapshot; later Dropbox changes cannot alter an in-progress run.
    """

    root = Path(run_dir).resolve()
    source_root = Path(macro_dir).resolve()
    if type(prefer_run_snapshot) is not bool:
        raise TypeError("prefer_run_snapshot must be boolean")
    loaded: dict[str, Any] = {}
    manifest: dict[str, dict[str, Any]] = {}
    if prefer_run_snapshot:
        core, snapshot_path = _run_snapshot(root)
        snapshot_hash = _sha256(snapshot_path) if snapshot_path is not None else ""
        loaded["core_macro"] = core
        manifest["core_macro"] = {
            "filename": "macro_snapshot.json",
            "path": str(snapshot_path.resolve()) if snapshot_path is not None else "",
            "status": "RUN_SNAPSHOT" if core else "MISSING_RUN_SNAPSHOT",
            "sha256": snapshot_hash,
            "as_of_utc": _text(core.get("as_of_utc")) if core else "",
        }
        for name in ("bond_macro", "auction_calendar", "enrichment_delta", "us_money_index"):
            filename, _kind = CANONICAL_SOURCES[name]
            embedded = _embedded(core, name) if core else {}
            loaded[name] = embedded
            manifest[name] = {
                "filename": filename,
                "path": str(snapshot_path.resolve()) if snapshot_path is not None else "",
                "status": "EMBEDDED_RUN_SNAPSHOT" if embedded else "MISSING_IN_RUN_SNAPSHOT",
                "sha256": snapshot_hash,
                "embedded_sha256": _canonical_hash(embedded) if embedded else "",
                "as_of_utc": _text(core.get("as_of_utc")) if core else "",
            }
    else:
        for name, (filename, kind) in CANONICAL_SOURCES.items():
            loaded[name], manifest[name] = _load(source_root / filename, kind)

        core = _mapping(loaded["core_macro"])
        if not core:
            core, fallback_path = _run_snapshot(root)
            if core and fallback_path is not None:
                manifest["core_macro"].update({
                    "status": "RUN_SNAPSHOT_FALLBACK",
                    "path": str(fallback_path.resolve()),
                    "sha256": _sha256(fallback_path),
                })

        for name in ("bond_macro", "auction_calendar", "enrichment_delta", "us_money_index"):
            if loaded[name]:
                continue
            fallback = _embedded(core, name)
            if fallback:
                loaded[name] = fallback
                manifest[name]["status"] = "EMBEDDED_FALLBACK"
                manifest[name]["embedded_sha256"] = _canonical_hash(fallback)

    core = _mapping(loaded["core_macro"])

    quant = _quant_packet(core, root)
    bond = _mapping(loaded["bond_macro"])
    enrichment = _mapping(loaded["enrichment_delta"])
    usmi_raw = _mapping(loaded["us_money_index"])
    usmi: dict[str, Any] = {}
    if usmi_raw:
        try:
            usmi = (
                dict(usmi_raw)
                if usmi_raw.get("contract_version") == "us_money_index_v1_0"
                and usmi_raw.get("authority") == "ADVISORY_ONLY"
                else normalise_us_money_index_sidecar(usmi_raw)
            )
        except Exception as error:
            manifest["us_money_index"]["status"] = "INVALID_UNAVAILABLE"
            manifest["us_money_index"]["error"] = str(error)
    usmi_scenario = evaluate_scenarios(
        usmi.get("scenarios") if isinstance(usmi, Mapping) else {},
        {},
    )
    auction_rows = (
        loaded["auction_calendar"]
        if isinstance(loaded["auction_calendar"], list)
        else []
    )
    source_fingerprint = _canonical_hash({
        name: {
            "filename": item.get("filename"),
            "sha256": item.get("sha256") or item.get("embedded_sha256"),
            "status": item.get("status"),
        }
        for name, item in sorted(manifest.items())
    })
    freshness = _text(
        quant.get("macro_freshness_status")
        or core.get("macro_freshness_status")
        or "UNKNOWN"
    ).upper()
    quality = _text(
        quant.get("macro_data_quality") or core.get("macro_data_quality") or "UNKNOWN"
    ).upper()
    conflicts = quant.get("macro_active_conflict_flags")
    conflicts = conflicts if isinstance(conflicts, list) else []
    context_state = (
        "STALE_CONTEXT"
        if freshness in {"STALE", "MISSING", "INVALID"}
        else "CONFLICTING_SOURCES"
        if conflicts
        else "NEUTRAL"
    )
    extras = core.get("extras") if isinstance(core.get("extras"), Mapping) else {}
    narrative = _mapping(enrichment.get("narrative_overlay"))
    plain_language = _text(narrative.get("overlay_summary"))
    if not plain_language:
        composite = _mapping(bond.get("composite"))
        plain_language = _text(composite.get("summary") or core.get("notes"))

    payload = _sanitise({
        "schema_version": SCHEMA_VERSION,
        "packet_id": f"MACRO:{source_fingerprint[:24]}",
        "source_fingerprint": source_fingerprint,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_utc": _text(core.get("as_of_utc") or quant.get("macro_generated_at_utc")),
        "session_date": _text(session_date),
        "freshness": freshness,
        "quality": quality,
        "macro_context_state": context_state,
        "authority_statement": AUTHORITY_STATEMENT,
        "source_manifest": manifest,
        "core_macro": core,
        "macro_quant_packet": quant,
        "bond": bond,
        "auction_calendar": {
            "status": manifest["auction_calendar"].get("status", "MISSING"),
            "rows": auction_rows,
        },
        "enrichment": enrichment,
        "us_money_index": usmi,
        "us_money_index_scenario": usmi_scenario,
        "ticker_advisories": _ticker_advisory_index(enrichment),
        "sector_rotation": _mapping(core.get("sector_rotation")),
        "rates": _mapping(extras.get("rates")),
        "usd": {"state": core.get("usd_state") or quant.get("usd_state")},
        "volatility": _mapping(extras.get("volatility")),
        "liquidity_pulse": core.get("liquidity_pulse") or quant.get("liquidity_pulse"),
        "regime_state": core.get("regime_state") or quant.get("macro_regime_label"),
        "macro_conviction": core.get("macro_conviction") or quant.get("macro_confidence"),
        "notes": core.get("notes"),
        "plain_language_advisory": plain_language,
        "conflicts": conflicts,
    })
    packet_path = root / "interpreter" / "interpreter_macro_context.json"
    _atomic_json(packet_path, payload)
    packet_hash = _sha256(packet_path)
    reference = {
        "packet_id": payload["packet_id"],
        "path": str(packet_path),
        "sha256": packet_hash,
        "source_fingerprint": source_fingerprint,
        "as_of_utc": payload["as_of_utc"] or payload["created_at_utc"],
        "session_date": payload["session_date"],
        "freshness": payload["freshness"],
        "quality": payload["quality"],
        "macro_context_state": payload["macro_context_state"],
        "authority_statement": AUTHORITY_STATEMENT,
    }
    return {"packet": payload, "packet_path": str(packet_path), "reference": reference}


def advisory_fields_for_row(
    packet: Mapping[str, Any],
    row: Mapping[str, Any],
    *,
    packet_sha256: str,
) -> dict[str, Any]:
    """Return display-only macro fields for one governed Lab row."""

    ticker = _text(row.get("ticker")).upper()
    sector = _text(
        row.get("gics_sector_norm") or row.get("gics_sector") or row.get("sector")
    )
    quant = _mapping(packet.get("macro_quant_packet"))
    rotation = _mapping(packet.get("sector_rotation"))
    sector_bias = _mapping(rotation.get("sector_bias_map"))
    advisories = packet.get("ticker_advisories")
    ticker_items = advisories.get(ticker, []) if isinstance(advisories, Mapping) else []
    ticker_items = ticker_items if isinstance(ticker_items, list) else []
    themes = sorted({
        _text(item.get("theme_id"))
        for item in ticker_items
        if isinstance(item, Mapping) and _text(item.get("theme_id"))
    })
    guards = sorted({
        _text(guard)
        for item in ticker_items
        if isinstance(item, Mapping)
        for guard in (item.get("event_guards") or [])
        if _text(guard)
    })
    roles = sorted({
        _text(item.get("role")).upper()
        for item in ticker_items
        if isinstance(item, Mapping) and _text(item.get("role"))
    })
    pressures = sorted({
        _text(item.get("directional_pressure"))
        for item in ticker_items
        if isinstance(item, Mapping) and _text(item.get("directional_pressure"))
    })
    bond = _mapping(packet.get("bond"))
    bond_composite = _mapping(bond.get("composite"))
    auction = _mapping(packet.get("auction_calendar"))
    usmi = _mapping(packet.get("us_money_index"))
    usmi_advisory = sector_advisory(
        usmi,
        sector=sector,
        direction=_text(row.get("governed_direction") or row.get("direction")),
        industry=_text(row.get("industry") or row.get("industry_group")),
    )
    return {
        "macro_packet_id": packet.get("packet_id", ""),
        "macro_packet_sha256": packet_sha256,
        "macro_source_fingerprint": packet.get("source_fingerprint", ""),
        "macro_as_of_utc": packet.get("as_of_utc", ""),
        "macro_session_date": packet.get("session_date", ""),
        "macro_freshness": packet.get("freshness", "UNKNOWN"),
        "macro_data_quality": packet.get("quality", "UNKNOWN"),
        "macro_context_state": packet.get("macro_context_state", "NEUTRAL"),
        "macro_regime": packet.get("regime_state") or quant.get("macro_regime_label") or "",
        "macro_sector_alignment": _text(sector_bias.get(sector)) or "UNMAPPED",
        "macro_ticker_alignment": " | ".join(roles) if roles else "NO_TICKER_SPECIFIC_OVERLAY",
        "macro_rates_context": json.dumps(_mapping(packet.get("rates")), separators=(",", ":"), default=str),
        "macro_usd_context": json.dumps(_mapping(packet.get("usd")), separators=(",", ":"), default=str),
        "macro_volatility_context": json.dumps(_mapping(packet.get("volatility")), separators=(",", ":"), default=str),
        "macro_liquidity_context": _text(packet.get("liquidity_pulse")),
        "macro_bond_context": _text(
            bond_composite.get("summary") or bond_composite.get("primary_warning")
        ),
        "macro_auction_risk": json.dumps(auction, separators=(",", ":"), default=str),
        "macro_active_themes": json.dumps(themes, separators=(",", ":")),
        "macro_event_guards": json.dumps(guards, separators=(",", ":")),
        "macro_directional_pressure": " | ".join(pressures),
        "macro_conflicts": json.dumps(
            packet.get("conflicts") or [], separators=(",", ":"), default=str
        ),
        "macro_plain_language_advisory": packet.get("plain_language_advisory", ""),
        "macro_authority": AUTHORITY_STATEMENT,
        "macro_data_role": "ADVISORY_ONLY",
        "usmi_packet_id": usmi.get("packet_id", ""),
        "usmi_packet_sha256": usmi.get("packet_sha256", ""),
        "usmi_quality_status": usmi.get("quality_status", "UNAVAILABLE"),
        "usmi_state": _text(_mapping(usmi.get("state")).get("US_MONEY_INDEX_STATE")),
        "usmi_sector_alignment": usmi_advisory["alignment"],
        "usmi_alignment_priority": usmi_advisory["priority"],
        "usmi_alignment_reason": usmi_advisory["reason"],
        "usmi_authority": "ADVISORY_ONLY",
        "usmi_scenario": _mapping(packet.get("us_money_index_scenario")).get("scenario", "UNRESOLVED"),
    }


__all__ = [
    "AUTHORITY_STATEMENT",
    "CANONICAL_SOURCES",
    "FORBIDDEN_AUTHORITY_KEYS",
    "SCHEMA_VERSION",
    "advisory_fields_for_row",
    "materialize_interpreter_macro_context",
]
