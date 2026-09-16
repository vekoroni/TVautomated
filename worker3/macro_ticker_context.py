"""Ticker-conditioned macro evidence derived from one frozen run packet.

This domain module performs no IO.  It maps advisory macro evidence to one
already-governed ticker thesis without changing direction, contract, lifecycle,
capital permission, position size, or candidate population.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import json
import re
from typing import Any, Mapping

from .domain import ContractError, digest, instant, sha, utc
from .market_environment import MarketEnvironmentSnapshot
from .lab_contract import SUPPORTED_LAB_SCHEMAS


SCHEMA_VERSION = "macro_ticker_context_v1"
AUTHORITY = "ADVISORY_ONLY"
MAX_CONTEXT_BYTES = 16 * 1024
_TICKER = re.compile(r"[A-Z0-9][A-Z0-9.\-]*")
_SHA = re.compile(r"[0-9a-f]{64}")
_LIMITS = {
    "roles": 8,
    "themes": 8,
    "event_guards": 8,
    "monitoring_conditions": 12,
    "contradictions": 12,
    "reason_codes": 12,
}
_PROHIBITED_KEYS = frozenset({
    "capital_permission", "execution_permission", "final_action",
    "final_verdict", "trade_go", "position_size", "position_size_pct",
    "selected_contract", "selected_contract_symbol", "direction_override",
    "direction_vote", "governed_direction_override",
})
_ETF_SECTOR = {
    "XLB": "MATERIALS",
    "XLC": "COMMUNICATION_SERVICES",
    "XLE": "ENERGY",
    "XLF": "FINANCIALS",
    "XLI": "INDUSTRIALS",
    "XLK": "INFORMATION_TECHNOLOGY",
    "XLP": "CONSUMER_STAPLES",
    "XLRE": "REAL_ESTATE",
    "XLU": "UTILITIES",
    "XLV": "HEALTH_CARE",
    "XLY": "CONSUMER_DISCRETIONARY",
}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _key(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", _text(value).upper()).strip("_")


def _nested(value: Mapping[str, Any], *path: str) -> dict[str, Any]:
    current: Any = value
    for key in path:
        current = current.get(key) if isinstance(current, Mapping) else None
    return _mapping(current)


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [_text(item) for item in value if _text(item)]
    return []


def _bounded(values: list[str], category: str) -> tuple[tuple[str, ...], int]:
    cleaned = sorted({item for item in values if item and len(item) <= 320})
    invalid = len({item for item in values if item and len(item) > 320})
    limit = _LIMITS[category]
    return tuple(cleaned[:limit]), invalid + max(0, len(cleaned) - limit)


def _contains_prohibited(value: Any) -> bool:
    if isinstance(value, Mapping):
        return bool(_PROHIBITED_KEYS.intersection(value)) or any(
            _contains_prohibited(item) for item in value.values()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_prohibited(item) for item in value)
    return False


@dataclass(frozen=True, slots=True)
class MacroSourceItem:
    name: str
    status: str
    source_hash: str
    source_as_of: str | None
    quality: str

    def __post_init__(self) -> None:
        if not _key(self.name) or not _key(self.status) or not _key(self.quality):
            raise ContractError("macro source item is incomplete")
        sha(self.source_hash)


@dataclass(frozen=True, slots=True)
class MacroTransmission:
    channel: str
    state: str
    applicability: str
    quality: str

    def __post_init__(self) -> None:
        if self.channel not in {
            "EQUITY_PARTICIPATION", "RATES", "OIL", "RISK_APPETITE",
            "VOLATILITY", "GEX",
        }:
            raise ContractError("unknown macro transmission channel")
        if not all(_text(value) for value in (self.state, self.applicability, self.quality)):
            raise ContractError("macro transmission is incomplete")


@dataclass(frozen=True, slots=True)
class MacroTickerContext:
    run_id: str
    session_date: str
    evidence_cutoff_utc: str
    ticker: str
    sector: str
    industry: str
    governed_direction: str
    source_packet_id: str
    source_packet_sha256: str
    source_fingerprint: str
    context_status: str
    applicability_state: str
    alignment: str
    reason_codes: tuple[str, ...]
    roles: tuple[str, ...]
    themes: tuple[str, ...]
    event_guards: tuple[str, ...]
    transmission: tuple[MacroTransmission, ...]
    monitoring_conditions: tuple[str, ...]
    quality_status: str
    stale_sources: tuple[str, ...]
    missing_sources: tuple[str, ...]
    unverified_metric_count: int
    source_items: tuple[MacroSourceItem, ...]
    contradictions: tuple[str, ...]
    omitted_counts: tuple[tuple[str, int], ...]
    schema_version: str = SCHEMA_VERSION
    authority: str = AUTHORITY
    candidate_retained: bool = True

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or self.authority != AUTHORITY:
            raise ContractError("unsupported macro ticker context authority")
        if not self.run_id or _TICKER.fullmatch(self.ticker) is None:
            raise ContractError("macro ticker context identity is incomplete")
        if self.governed_direction not in {"CALL", "PUT", "NON_DIRECTIONAL"}:
            raise ContractError("unsupported governed direction")
        if not self.source_packet_id or not self.source_fingerprint:
            raise ContractError("macro source identity is incomplete")
        sha(self.source_packet_sha256)
        object.__setattr__(self, "evidence_cutoff_utc", utc(self.evidence_cutoff_utc))
        if self.context_status not in {
            "AVAILABLE", "PARTIAL", "STALE", "CONFLICTING", "UNMAPPED",
        }:
            raise ContractError("unknown macro ticker context status")
        if self.applicability_state not in {
            "EXACT_TICKER", "SECTOR_ONLY", "UNMAPPED",
        }:
            raise ContractError("unknown macro applicability state")
        if self.alignment not in {"TAILWIND", "HEADWIND", "MIXED", "NEUTRAL", "UNMAPPED"}:
            raise ContractError("unknown macro alignment")
        if type(self.unverified_metric_count) is not int or self.unverified_metric_count < 0:
            raise ContractError("unverified metric count must be non-negative")
        if type(self.candidate_retained) is not bool or self.candidate_retained is not True:
            raise ContractError("macro context may not discard a candidate")
        if len({item.channel for item in self.transmission}) != len(self.transmission):
            raise ContractError("duplicate macro transmission channel")
        if any(count < 0 for _, count in self.omitted_counts):
            raise ContractError("invalid omitted-count disclosure")

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "authority": self.authority,
            "run_id": self.run_id,
            "session_date": self.session_date,
            "evidence_cutoff_utc": self.evidence_cutoff_utc,
            "ticker": self.ticker,
            "sector": self.sector,
            "industry": self.industry,
            "governed_direction": self.governed_direction,
            "source_packet_id": self.source_packet_id,
            "source_packet_sha256": self.source_packet_sha256,
            "source_fingerprint": self.source_fingerprint,
            "context_status": self.context_status,
            "applicability": {
                "state": self.applicability_state,
                "alignment": self.alignment,
                "reason_codes": list(self.reason_codes),
            },
            "roles": list(self.roles),
            "themes": list(self.themes),
            "event_guards": list(self.event_guards),
            "transmission": {item.channel.lower(): {
                "state": item.state,
                "applicability": item.applicability,
                "quality": item.quality,
            } for item in self.transmission},
            "monitoring_conditions": list(self.monitoring_conditions),
            "data_quality": {
                "status": self.quality_status,
                "stale_sources": list(self.stale_sources),
                "missing_sources": list(self.missing_sources),
                "unverified_metric_count": self.unverified_metric_count,
            },
            "source_items": [asdict(item) for item in self.source_items],
            "contradictions": list(self.contradictions),
            "omitted_counts": dict(self.omitted_counts),
            "candidate_retained": self.candidate_retained,
        }
        if _contains_prohibited(payload):
            raise ContractError("macro ticker context attempted to grant trade authority")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_CONTEXT_BYTES:
            raise ContractError("macro ticker context exceeds 16 KiB contract")
        return payload

    @property
    def context_hash(self) -> str:
        return digest(self.to_payload())


def _sector(row: Mapping[str, Any]) -> tuple[str, str]:
    raw_sector = _text(
        row.get("gics_sector_norm") or row.get("gics_sector")
        or row.get("sector") or row.get("sector_etf")
    )
    sector_key = _ETF_SECTOR.get(_key(raw_sector), _key(raw_sector))
    industry = _key(row.get("industry") or row.get("industry_group"))
    return sector_key or "UNAVAILABLE", industry or "UNAVAILABLE"


def _sector_bias(packet: Mapping[str, Any], sector: str) -> str:
    bias_map = _nested(packet, "sector_rotation", "sector_bias_map")
    for source_key, value in bias_map.items():
        if _key(source_key) == sector:
            return _key(value)
    return ""


def _usmi_route(packet: Mapping[str, Any], direction: str, sector: str, industry: str) -> dict[str, Any]:
    usmi = _mapping(packet.get("us_money_index"))
    routing = _mapping(usmi.get("sector_routing"))
    direction_map = _mapping(routing.get(direction))
    candidates = {sector, industry}
    candidates.discard("UNAVAILABLE")
    for source_key, value in direction_map.items():
        if _key(source_key) in candidates and isinstance(value, Mapping):
            return dict(value)
    return {}


def _source_items(packet: Mapping[str, Any], packet_hash: str) -> tuple[
    tuple[MacroSourceItem, ...], tuple[str, ...], tuple[str, ...]
]:
    manifest = _mapping(packet.get("source_manifest"))
    bond = _mapping(packet.get("bond"))
    curve = _mapping(bond.get("yield_curve"))
    enrichment = _mapping(packet.get("enrichment"))
    usmi = _mapping(packet.get("us_money_index"))
    dates = {
        "core_macro": _text(packet.get("as_of_utc")),
        "bond_macro": _text(curve.get("as_of_date") or bond.get("as_of_date")),
        "auction_calendar": None,
        "enrichment_delta": _text(enrichment.get("as_of_utc")),
        "us_money_index": _text(usmi.get("market_data_as_of_utc") or usmi.get("generated_at_utc")),
    }
    stale: list[str] = []
    missing: list[str] = []
    items: list[MacroSourceItem] = []
    for name in ("core_macro", "bond_macro", "auction_calendar", "enrichment_delta", "us_money_index"):
        source = _mapping(manifest.get(name))
        status = _key(source.get("status") or "MISSING")
        source_hash = _text(source.get("sha256") or source.get("embedded_sha256")).lower()
        if _SHA.fullmatch(source_hash) is None:
            source_hash = packet_hash
        unavailable = "MISSING" in status or "INVALID" in status
        source_stale = (
            "STALE" in status
            or (name == "bond_macro" and curve.get("stale_flag") is True)
            or (name == "core_macro" and _key(packet.get("freshness")) == "STALE")
        )
        if unavailable:
            missing.append(name)
        quality = "AVAILABLE"
        if unavailable:
            quality = "UNAVAILABLE"
        elif source_stale:
            quality = "STALE"
            stale.append(name)
        elif source_hash == packet_hash and not source.get("sha256") and not source.get("embedded_sha256"):
            quality = "PACKET_ATTESTED_ONLY"
        items.append(MacroSourceItem(name, status, source_hash, dates[name] or None, quality))
    return tuple(items), tuple(sorted(set(stale))), tuple(sorted(set(missing)))


def _alignment(
    *, items: list[dict[str, Any]], packet: Mapping[str, Any], direction: str,
    sector: str, industry: str,
) -> tuple[str, list[str], bool]:
    if direction == "NON_DIRECTIONAL":
        return "UNMAPPED", ["NON_DIRECTIONAL_NO_MACRO_DIRECTION_MAPPING"], bool(
            items or _sector_bias(packet, sector)
        )
    votes: set[str] = set()
    reasons: list[str] = []
    for item in items:
        role = _key(item.get("role"))
        pressure = _key(item.get("directional_pressure"))
        if role == "BENEFICIARY":
            votes.add("TAILWIND" if direction == "CALL" else "HEADWIND")
            reasons.append("TICKER_ROLE_BENEFICIARY")
        elif role == "VULNERABLE":
            votes.add("TAILWIND" if direction == "PUT" else "HEADWIND")
            reasons.append("TICKER_ROLE_VULNERABLE")
        call_only = ("LONG_CALL" in pressure or "CALL_FAVOURED" in pressure) and not (
            "LONG_PUT" in pressure or "PUT_FAVOURED" in pressure
        )
        put_only = ("LONG_PUT" in pressure or "PUT_FAVOURED" in pressure) and not (
            "LONG_CALL" in pressure or "CALL_FAVOURED" in pressure
        )
        if call_only:
            votes.add("TAILWIND" if direction == "CALL" else "HEADWIND")
            reasons.append("EXPLICIT_CALL_PRESSURE")
        elif put_only:
            votes.add("TAILWIND" if direction == "PUT" else "HEADWIND")
            reasons.append("EXPLICIT_PUT_PRESSURE")
    sector_bias = _sector_bias(packet, sector)
    sector_mapped = bool(sector_bias)
    if sector_bias in {"TAILWIND", "HEADWIND"}:
        vote = sector_bias if direction == "CALL" else (
            "HEADWIND" if sector_bias == "TAILWIND" else "TAILWIND"
        )
        votes.add(vote)
        reasons.append("SECTOR_ROTATION_" + sector_bias)
    elif sector_bias in {"MIXED", "NEUTRAL"}:
        votes.add(sector_bias)
        reasons.append("SECTOR_ROTATION_" + sector_bias)
    route = _usmi_route(packet, direction, sector, industry)
    if route:
        if _key(route.get("alignment")) == "ALIGNED":
            votes.add("TAILWIND")
        reasons.append(_key(route.get("reason")) or "USMI_DIRECTION_SECTOR_MAPPING")
        sector_mapped = True
    directional = votes.intersection({"TAILWIND", "HEADWIND"})
    if len(directional) == 2:
        result = "MIXED"
    elif directional:
        result = next(iter(directional))
    elif "MIXED" in votes:
        result = "MIXED"
    elif "NEUTRAL" in votes:
        result = "NEUTRAL"
    else:
        result = "UNMAPPED"
    return result, reasons, sector_mapped


def project_macro_ticker_context(
    *,
    packet: Mapping[str, Any],
    packet_sha256: str,
    market_environment: MarketEnvironmentSnapshot,
    lab_row: Mapping[str, Any],
    run_id: str,
    session_date: str,
    evidence_cutoff_utc: str,
) -> MacroTickerContext:
    """Project one exact ticker context from already-verified frozen evidence."""
    if not isinstance(packet, Mapping) or packet.get("schema_version") != "interpreter_macro_context_v1":
        raise ContractError("macro ticker context requires interpreter_macro_context_v1")
    sha(packet_sha256)
    cutoff = utc(evidence_cutoff_utc)
    for field in ("as_of_utc", "created_at_utc"):
        value = _text(packet.get(field))
        if value and instant(value) > instant(cutoff):
            raise ContractError(f"macro {field} is later than the evidence cutoff")
    source_manifest = _mapping(packet.get("source_manifest"))
    for source_name, raw_source in source_manifest.items():
        source = _mapping(raw_source)
        for field in ("as_of_utc", "modified_at_utc", "available_at_utc"):
            value = _text(source.get(field))
            if value and instant(value) > instant(cutoff):
                raise ContractError(
                    f"macro source {source_name} {field} is later than the evidence cutoff"
                )
    if "ADVISORY_ONLY" not in _text(packet.get("authority_statement")).upper():
        raise ContractError("macro packet authority is not advisory-only")
    if _text(packet.get("session_date")) != session_date:
        raise ContractError("macro packet trading session differs from ticker context")
    if market_environment.run_id != run_id or market_environment.session_date != session_date:
        raise ContractError("market environment identity differs from ticker context")
    if market_environment.source_packet_sha256 != packet_sha256:
        raise ContractError("market environment and ticker context use different macro packets")
    if not isinstance(lab_row, Mapping) or _text(lab_row.get("run_id")) != run_id:
        raise ContractError("Lab row run differs from ticker context")
    if lab_row.get("lab_schema_version") not in SUPPORTED_LAB_SCHEMAS:
        raise ContractError("unsupported Lab row schema")
    ticker = _text(lab_row.get("ticker")).upper()
    if _TICKER.fullmatch(ticker) is None:
        raise ContractError("ticker context requires canonical ticker")
    direction = _key(lab_row.get("governed_direction"))
    if direction in {"STRANGLE", "UNRESOLVED"}:
        direction = "NON_DIRECTIONAL"
    if direction not in {"CALL", "PUT", "NON_DIRECTIONAL"}:
        raise ContractError("ticker context requires governed direction")
    sector, industry = _sector(lab_row)
    index = packet.get("ticker_advisories")
    raw_items = index.get(ticker, []) if isinstance(index, Mapping) else []
    items = [dict(item) for item in raw_items if isinstance(item, Mapping)]

    roles_raw = [_key(item.get("role")) for item in items if _key(item.get("role"))]
    themes_raw = [_key(item.get("theme_id") or item.get("theme_name")) for item in items]
    guards_raw = [guard for item in items for guard in _strings(item.get("event_guards"))]
    forward = _nested(packet, "us_money_index", "advisory_context", "forward_triggers")
    guards_raw.extend(_strings(forward.get("event_guards")))
    monitoring_raw: list[str] = []
    for item in items:
        monitoring_raw.extend("CONFIRM: " + value for value in _strings(item.get("confirmation_required")))
        monitoring_raw.extend("INVALIDATE: " + value for value in _strings(item.get("invalidation_conditions")))
    roles, omitted_roles = _bounded(roles_raw, "roles")
    themes, omitted_themes = _bounded(themes_raw, "themes")
    guards, omitted_guards = _bounded(guards_raw, "event_guards")
    monitoring, omitted_monitoring = _bounded(monitoring_raw, "monitoring_conditions")

    alignment, reasons_raw, sector_mapped = _alignment(
        items=items, packet=packet, direction=direction,
        sector=sector, industry=industry,
    )
    reasons, omitted_reasons = _bounded(reasons_raw, "reason_codes")
    applicability = "EXACT_TICKER" if items else "SECTOR_ONLY" if sector_mapped else "UNMAPPED"

    domains = {domain.domain: domain for domain in market_environment.domains}
    all_theme_text = " ".join(themes_raw + [
        _key(item.get("directional_pressure")) for item in items
    ])
    transmissions: list[MacroTransmission] = []
    for channel in ("EQUITY_PARTICIPATION", "RATES", "OIL", "RISK_APPETITE"):
        domain = domains[channel]
        specific = channel == "EQUITY_PARTICIPATION"
        if channel == "RATES":
            specific = any(token in all_theme_text for token in ("RATE", "YIELD", "DURATION", "TREASURY"))
        elif channel == "OIL":
            specific = sector in {"ENERGY", "INDUSTRIALS", "CONSUMER_DISCRETIONARY"} or any(
                token in all_theme_text for token in ("OIL", "ENERGY", "FUEL", "BRENT", "WTI", "HORMUZ")
            )
        transmissions.append(MacroTransmission(
            channel, domain.state,
            "TICKER_MAPPED" if specific and applicability != "UNMAPPED" else "GLOBAL_CONTEXT_ONLY",
            domain.data_quality,
        ))
    risk = domains["RISK_APPETITE"]
    volatility_state = next(
        (_text(fact.value) for fact in risk.facts if fact.name == "volatility_state" and fact.value is not None),
        "UNAVAILABLE",
    )
    transmissions.append(MacroTransmission(
        "VOLATILITY", volatility_state, "GLOBAL_CONTEXT_ONLY", risk.data_quality,
    ))
    gex = _nested(packet, "core_macro", "extras", "gex")
    gex_state = _text(gex.get("regime") or gex.get("data_status")) or "UNAVAILABLE"
    transmissions.append(MacroTransmission(
        "GEX", gex_state, "GLOBAL_CONTEXT_ONLY",
        "AVAILABLE" if gex_state != "UNAVAILABLE" else "INSUFFICIENT_DATA",
    ))

    source_items, stale_sources, missing_sources = _source_items(packet, packet_sha256)
    for source_item in source_items:
        value = _text(source_item.source_as_of)
        if not value:
            continue
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            if date.fromisoformat(value) > instant(cutoff).date():
                raise ContractError(
                    f"macro source {source_item.name} is later than the evidence cutoff"
                )
        elif instant(value) > instant(cutoff):
            raise ContractError(
                f"macro source {source_item.name} is later than the evidence cutoff"
            )
    usmi = _mapping(packet.get("us_money_index"))
    unverified = usmi.get("unverified_metrics")
    unverified_count = len(unverified) if isinstance(unverified, list) else 0
    conflict_values = [_key(item) for item in (packet.get("conflicts") or []) if _key(item)]
    if alignment == "MIXED":
        conflict_values.append("TICKER_MACRO_ALIGNMENT_MIXED")
    conflicts, omitted_conflicts = _bounded(conflict_values, "contradictions")
    quality_raw = _key(packet.get("quality"))
    # Preserve packet conflict text for review, but only elevate this ticker to
    # CONFLICTING when its applicable mapped evidence materially disagrees.
    # Global warnings and already-resolved reconciliation notes are not a
    # ticker-specific contradiction merely because they share the packet.
    if alignment == "MIXED":
        quality = "CONFLICTING"
    elif stale_sources:
        quality = "STALE"
    elif (
        missing_sources or unverified_count or conflicts
        or "PARTIAL" in quality_raw or "UNVERIFIED" in quality_raw
    ):
        quality = "PARTIAL"
    else:
        quality = "AVAILABLE"
    context_status = "UNMAPPED" if applicability == "UNMAPPED" and quality == "AVAILABLE" else quality
    omitted = tuple((name, count) for name, count in (
        ("roles", omitted_roles),
        ("themes", omitted_themes),
        ("event_guards", omitted_guards),
        ("monitoring_conditions", omitted_monitoring),
        ("reason_codes", omitted_reasons),
        ("contradictions", omitted_conflicts),
    ) if count)
    context = MacroTickerContext(
        run_id=run_id,
        session_date=session_date,
        evidence_cutoff_utc=cutoff,
        ticker=ticker,
        sector=sector,
        industry=industry,
        governed_direction=direction,
        source_packet_id=_text(packet.get("packet_id")),
        source_packet_sha256=packet_sha256,
        source_fingerprint=_text(packet.get("source_fingerprint")),
        context_status=context_status,
        applicability_state=applicability,
        alignment=alignment,
        reason_codes=reasons,
        roles=roles,
        themes=themes,
        event_guards=guards,
        transmission=tuple(transmissions),
        monitoring_conditions=monitoring,
        quality_status=quality,
        stale_sources=stale_sources,
        missing_sources=missing_sources,
        unverified_metric_count=unverified_count,
        source_items=source_items,
        contradictions=conflicts,
        omitted_counts=omitted,
    )
    context.to_payload()
    return context


def macro_ticker_context_diagnostics(
    payloads: tuple[Mapping[str, Any], ...],
    *,
    requested: int,
    invalid: int = 0,
) -> dict[str, int | bool | str]:
    """Reconcile mutually exclusive context outcomes without granting authority."""
    if type(payloads) is not tuple or type(requested) is not int or type(invalid) is not int:
        raise ContractError("macro ticker diagnostics require immutable integer inputs")
    if requested < 0 or invalid < 0 or requested != len(payloads) + invalid:
        raise ContractError("macro ticker diagnostics population does not reconcile")
    statuses = {name: 0 for name in (
        "AVAILABLE", "PARTIAL", "STALE", "CONFLICTING", "UNMAPPED",
    )}
    applicability = {name: 0 for name in ("EXACT_TICKER", "SECTOR_ONLY", "UNMAPPED")}
    bytes_total = 0
    omitted_total = 0
    for payload in payloads:
        if not isinstance(payload, Mapping):
            raise ContractError("macro ticker diagnostics require context payloads")
        if (
            payload.get("schema_version") != SCHEMA_VERSION
            or payload.get("authority") != AUTHORITY
            or payload.get("candidate_retained") is not True
        ):
            raise ContractError("macro ticker diagnostics received an invalid context")
        status = _text(payload.get("context_status"))
        app = _mapping(payload.get("applicability"))
        app_state = _text(app.get("state"))
        if status not in statuses or app_state not in applicability:
            raise ContractError("macro ticker diagnostics received an unknown state")
        omitted = _mapping(payload.get("omitted_counts"))
        if any(type(value) is not int or value < 0 for value in omitted.values()):
            raise ContractError("macro ticker diagnostics received invalid omissions")
        statuses[status] += 1
        applicability[app_state] += 1
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        bytes_total += len(encoded.encode("utf-8"))
        omitted_total += sum(omitted.values())
    accounted = sum(statuses.values()) + invalid
    return {
        "macro_ticker_context_contract": SCHEMA_VERSION,
        "macro_ticker_context_requested": requested,
        "macro_ticker_context_available": statuses["AVAILABLE"],
        "macro_ticker_context_partial": statuses["PARTIAL"],
        "macro_ticker_context_stale": statuses["STALE"],
        "macro_ticker_context_conflicting": statuses["CONFLICTING"],
        "macro_ticker_context_unmapped": statuses["UNMAPPED"],
        "macro_ticker_context_invalid": invalid,
        "macro_ticker_context_bytes_total": bytes_total,
        "macro_ticker_context_omitted_items_total": omitted_total,
        "macro_ticker_context_exact_ticker": applicability["EXACT_TICKER"],
        "macro_ticker_context_sector_only": applicability["SECTOR_ONLY"],
        "macro_ticker_context_applicability_unmapped": applicability["UNMAPPED"],
        "macro_ticker_context_reconciled": requested == accounted,
        "authority": AUTHORITY,
        "trading_authority": False,
    }


__all__ = [
    "AUTHORITY", "MAX_CONTEXT_BYTES", "MacroSourceItem", "MacroTickerContext",
    "MacroTransmission", "SCHEMA_VERSION", "macro_ticker_context_diagnostics",
    "project_macro_ticker_context",
]
