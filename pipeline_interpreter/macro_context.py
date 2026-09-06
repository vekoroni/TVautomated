"""Hash-bound, advisory-only macro packet adapter for the Interpreter."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from contracts.interpreter_macro_context import (
    AUTHORITY_STATEMENT as GOVERNED_MACRO_AUTHORITY_STATEMENT,
    FORBIDDEN_AUTHORITY_KEYS as GOVERNED_FORBIDDEN_AUTHORITY_KEYS,
)


MACRO_PACKET_SCHEMA = "macro_quant_packet"
MACRO_AUTHORITY_STATEMENT = GOVERNED_MACRO_AUTHORITY_STATEMENT


class MacroContextState(str, Enum):
    TAILWIND = "TAILWIND"
    NEUTRAL = "NEUTRAL"
    HEADWIND = "HEADWIND"
    CONFLICTING_SOURCES = "CONFLICTING_SOURCES"
    STALE_CONTEXT = "STALE_CONTEXT"
    DATA_MISSING = "DATA_MISSING"


class MacroPacketError(ValueError):
    pass


ALLOWED_CONTEXT_KEYS = (
    "sector_rotation", "sector_tilt", "rates", "rates_impulse", "usd",
    "usd_state", "credit", "volatility", "bond", "auction", "liquidity_pulse",
    "regime_state", "macro_conviction", "notes", "plain_language_advisory",
)
FORBIDDEN_AUTHORITY_KEYS = frozenset({
    "direction", "governed_direction", "selected_contract_symbol",
    "contract_symbol", "thesis_state", "olm_guard_disposition", "final_action",
    "capital_permission", "execution_permission", "size_multiplier",
    "macro_filter", "risk_on_off_switch", "trade_go", "trigger_required",
}) | GOVERNED_FORBIDDEN_AUTHORITY_KEYS


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class MacroContext:
    packet_id: str
    state: MacroContextState
    as_of_utc: str
    session_date: str
    freshness: str
    quality: str
    advisory: Mapping[str, Any]
    ignored_authority_fields: tuple[str, ...]
    authority_statement: str = MACRO_AUTHORITY_STATEMENT

    def prompt_block(self) -> str:
        payload = {
            "macro_context_state": self.state.value,
            "packet_id": self.packet_id,
            "as_of_utc": self.as_of_utc,
            "session_date": self.session_date,
            "freshness": self.freshness,
            "quality": self.quality,
            "advisory": dict(self.advisory),
            "authority_statement": self.authority_statement,
        }
        return "GOVERNED MACRO ADVISORY:\n" + json.dumps(payload, sort_keys=True, default=str)


def missing_macro_context() -> MacroContext:
    return MacroContext(
        packet_id="",
        state=MacroContextState.DATA_MISSING,
        as_of_utc="",
        session_date="",
        freshness="MISSING",
        quality="MISSING",
        advisory={},
        ignored_authority_fields=(),
    )


def load_macro_packet(
    reference: Mapping[str, Any],
    *,
    run_root: Path | str,
    ticker: str = "",
) -> MacroContext:
    """Load only the packet explicitly referenced by a validated bundle."""
    if not reference:
        return missing_macro_context()
    for field in ("packet_id", "path", "sha256", "as_of_utc", "session_date", "freshness"):
        if not _text(reference.get(field)):
            raise MacroPacketError(f"MACRO_REFERENCE_MISSING_{field.upper()}")
    root = Path(run_root).resolve()
    packet_path = Path(_text(reference["path"]))
    if not packet_path.is_absolute():
        packet_path = (root / packet_path).resolve()
    else:
        packet_path = packet_path.resolve()
    try:
        packet_path.relative_to(root)
    except ValueError as error:
        raise MacroPacketError("MACRO_PACKET_OUTSIDE_RUN") from error
    if not packet_path.is_file():
        raise MacroPacketError("MACRO_PACKET_MISSING")
    if _sha256(packet_path) != _text(reference["sha256"]).lower():
        raise MacroPacketError("MACRO_PACKET_HASH_MISMATCH")
    try:
        datetime.fromisoformat(_text(reference["as_of_utc"]).replace("Z", "+00:00"))
    except ValueError as error:
        raise MacroPacketError("MACRO_PACKET_AS_OF_INVALID") from error
    payload = json.loads(packet_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, Mapping):
        raise MacroPacketError("MACRO_PACKET_PAYLOAD_INVALID")
    payload_id = _text(payload.get("packet_id") or payload.get("macro_packet_id"))
    if payload_id and payload_id != _text(reference["packet_id"]):
        raise MacroPacketError("MACRO_PACKET_ID_MISMATCH")
    freshness = _text(reference["freshness"]).upper()
    if freshness in {"STALE", "MISSING", "INVALID"}:
        state = MacroContextState.STALE_CONTEXT
    else:
        raw_state = _text(
            reference.get("macro_context_state") or payload.get("macro_context_state")
        ).upper()
        try:
            state = MacroContextState(raw_state) if raw_state else MacroContextState.NEUTRAL
        except ValueError:
            state = MacroContextState.CONFLICTING_SOURCES
    ignored = tuple(sorted(key for key in payload if key in FORBIDDEN_AUTHORITY_KEYS))
    advisory = {key: payload[key] for key in ALLOWED_CONTEXT_KEYS if key in payload}
    # v1 composite packets carry all four canonical macro sources.  Expose a
    # compact, ticker-aware view to the prompt rather than dumping the complete
    # raw payload, while retaining source hashes and data-quality lineage.
    if _text(payload.get("schema_version")) == "interpreter_macro_context_v1":
        quant = payload.get("macro_quant_packet")
        bond = payload.get("bond")
        auction = payload.get("auction_calendar")
        enrichment = payload.get("enrichment")
        ticker_map = payload.get("ticker_advisories")
        symbol = _text(ticker).upper()
        advisory.update({
            "source_fingerprint": payload.get("source_fingerprint"),
            "source_manifest": payload.get("source_manifest"),
            "macro_quant_packet": quant if isinstance(quant, Mapping) else {},
            "bond": bond if isinstance(bond, Mapping) else {},
            "auction_calendar": auction if isinstance(auction, Mapping) else {},
            "conflicts": payload.get("conflicts") or [],
            "plain_language_advisory": payload.get("plain_language_advisory"),
            "ticker_advisory": (
                ticker_map.get(symbol, [])
                if symbol and isinstance(ticker_map, Mapping)
                else []
            ),
            "enrichment_narrative": (
                enrichment.get("narrative_overlay", {})
                if isinstance(enrichment, Mapping)
                else {}
            ),
            "event_guards": (
                enrichment.get("event_guard_deltas", [])
                if isinstance(enrichment, Mapping)
                else []
            ),
        })
    return MacroContext(
        packet_id=_text(reference["packet_id"]),
        state=state,
        as_of_utc=_text(reference["as_of_utc"]),
        session_date=_text(reference["session_date"]),
        freshness=freshness,
        quality=_text(reference.get("quality") or payload.get("quality") or "UNKNOWN").upper(),
        advisory=advisory,
        ignored_authority_fields=ignored,
    )


def assert_macro_did_not_change_authority(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> None:
    for field in FORBIDDEN_AUTHORITY_KEYS:
        if field in before and before.get(field) != after.get(field):
            raise MacroPacketError(f"MACRO_AUTHORITY_MUTATION:{field}")


__all__ = [
    "FORBIDDEN_AUTHORITY_KEYS", "MACRO_AUTHORITY_STATEMENT", "MacroContext",
    "MacroContextState", "MacroPacketError", "assert_macro_did_not_change_authority",
    "load_macro_packet", "missing_macro_context",
]

