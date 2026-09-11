"""Compact, governed market-environment and trade-plan domain models.

The projector consumes the frozen ``interpreter_macro_context_v1`` packet. It
does not read files, call providers, select contracts, change direction, grant
capital, or reject a candidate. Missing evidence stays unavailable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from typing import Any, Mapping

from .domain import ContractError, EvidenceBundle, digest, instant, sha, utc


MARKET_ENVIRONMENT_SCHEMA = "market_environment_v1"
TRADE_PLAN_SCHEMA = "trade_plan_snapshot_v1"
MAX_COMPACT_BYTES = 30_000
_AUTHORITY = "ADVISORY_ONLY"
_FORBIDDEN_OUTPUT_KEYS = frozenset({
    "capital_permission", "execution_permission", "final_action",
    "final_verdict", "position_size", "position_size_pct", "trade_go",
    "selected_contract", "selected_contract_symbol", "governed_direction",
})


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    if type(value) not in (int, float):
        return None
    value = float(value)
    return value if value == value and abs(value) != float("inf") else None


def _first(*values: Any) -> Any:
    return next((value for value in values if value not in (None, "")), None)


def _nested(value: Mapping[str, Any], *path: str) -> dict[str, Any]:
    current: Any = value
    for key in path:
        current = current.get(key) if isinstance(current, Mapping) else None
    return _mapping(current)


def _cross_asset(usmi: Mapping[str, Any]) -> dict[str, Any]:
    direct = _mapping(usmi.get("cross_asset"))
    if direct:
        return direct
    return _nested(usmi, "advisory_context", "cross_asset")


def _fact(name: str, value: Any, unit: str = "state") -> "EnvironmentFact":
    if isinstance(value, (dict, list, tuple)):
        raise ContractError("market-environment facts must be scalar")
    if type(value) not in (str, int, float, bool, type(None)):
        value = None
    if type(value) is float and (value != value or abs(value) == float("inf")):
        value = None
    return EnvironmentFact(name=name, value=value, unit=unit)


@dataclass(frozen=True, slots=True)
class EnvironmentFact:
    name: str
    value: str | int | float | bool | None
    unit: str

    def __post_init__(self) -> None:
        if not self.name or not re.fullmatch(r"[a-z][a-z0-9_]*", self.name):
            raise ContractError("environment fact requires a canonical name")
        if not self.unit:
            raise ContractError("environment fact requires a unit")
        if type(self.value) not in (str, int, float, bool, type(None)):
            raise ContractError("environment fact must be a JSON scalar")


@dataclass(frozen=True, slots=True)
class EnvironmentDomain:
    domain: str
    state: str
    data_quality: str
    interpretation: str
    facts: tuple[EnvironmentFact, ...]

    def __post_init__(self) -> None:
        if self.domain not in {"EQUITY_PARTICIPATION", "RATES", "OIL", "RISK_APPETITE"}:
            raise ContractError("unknown market-environment domain")
        if not self.state or not self.data_quality or not self.interpretation:
            raise ContractError("market-environment domain is incomplete")
        if type(self.facts) is not tuple or any(not isinstance(x, EnvironmentFact) for x in self.facts):
            raise ContractError("environment facts must be immutable")
        if len({x.name for x in self.facts}) != len(self.facts):
            raise ContractError("duplicate environment fact")


@dataclass(frozen=True, slots=True)
class MarketEnvironmentSnapshot:
    run_id: str
    session_date: str
    evidence_cutoff_utc: str
    source_packet_id: str
    source_packet_sha256: str
    source_fingerprint: str
    domains: tuple[EnvironmentDomain, ...]
    contradictions: tuple[str, ...]
    schema_version: str = MARKET_ENVIRONMENT_SCHEMA
    authority: str = _AUTHORITY

    def __post_init__(self) -> None:
        if self.schema_version != MARKET_ENVIRONMENT_SCHEMA or self.authority != _AUTHORITY:
            raise ContractError("unsupported market-environment authority contract")
        if not self.run_id or not self.source_packet_id:
            raise ContractError("market-environment identity is incomplete")
        sha(self.source_packet_sha256)
        object.__setattr__(self, "evidence_cutoff_utc", utc(self.evidence_cutoff_utc))
        if type(self.domains) is not tuple or len(self.domains) != 4:
            raise ContractError("all four market-environment domains are required")
        if len({domain.domain for domain in self.domains}) != 4:
            raise ContractError("market-environment domains must be unique")

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        if _FORBIDDEN_OUTPUT_KEYS.intersection(payload):
            raise ContractError("market environment attempted to grant trade authority")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_COMPACT_BYTES:
            raise ContractError("market environment exceeds compact payload limit")
        return payload

    @property
    def snapshot_hash(self) -> str:
        return digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class TradePlanSnapshot:
    run_id: str
    ticker: str
    thesis_id: str
    direction: str
    planned_hold_sessions: int
    thesis_state: str
    entry_posture: str
    current_reference_price: float | None
    entry_reference_price: float | None
    structural_target: float | None
    thesis_invalidation_price: float | None
    trigger_primary: str
    trigger_quality: str
    monitoring_conditions: tuple[str, ...]
    data_gaps: tuple[str, ...]
    schema_version: str = TRADE_PLAN_SCHEMA
    authority: str = _AUTHORITY
    candidate_retained: bool = True

    def __post_init__(self) -> None:
        if self.schema_version != TRADE_PLAN_SCHEMA or self.authority != _AUTHORITY:
            raise ContractError("unsupported trade-plan authority contract")
        if not self.run_id or not self.ticker or not self.thesis_id or not self.direction:
            raise ContractError("trade-plan identity is incomplete")
        if type(self.planned_hold_sessions) is not int or not 1 <= self.planned_hold_sessions <= 20:
            raise ContractError("trade plan requires a 1-20 session horizon")
        if self.candidate_retained is not True:
            raise ContractError("Worker 3 may not discard a governed candidate")

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        if _FORBIDDEN_OUTPUT_KEYS.intersection(payload):
            raise ContractError("trade plan attempted to grant execution authority")
        return payload

    @property
    def plan_hash(self) -> str:
        return digest(self.to_payload())


def _equity_domain(usmi: Mapping[str, Any]) -> EnvironmentDomain:
    equities = _mapping(_cross_asset(usmi).get("equities"))
    cash = _mapping(equities.get("last_us_cash_session"))
    flow = _text(equities.get("capital_flow_state"))
    breadth = _text(cash.get("breadth_state")).upper()
    if flow:
        state = flow
    elif breadth in {"NEGATIVE", "WEAK", "DETERIORATING"}:
        state = "BROAD_OUTFLOW_PRESSURE_PROXY"
    elif breadth in {"POSITIVE", "STRONG", "IMPROVING"}:
        state = "BROAD_INFLOW_SUPPORT_PROXY"
    else:
        state = "UNAVAILABLE"
    quality = "AVAILABLE" if state != "UNAVAILABLE" else "INSUFFICIENT_DATA"
    interpretation = (
        "Participation and concentration proxy; not a direct measurement of institutional fund flows."
        if state != "UNAVAILABLE" else
        "Equity participation evidence is unavailable; no flow state is inferred."
    )
    return EnvironmentDomain("EQUITY_PARTICIPATION", state, quality, interpretation, (
        _fact("capital_flow_state", flow or None),
        _fact("breadth_state", breadth or None),
        _fact("sp500_return_pct", _number(cash.get("sp500_pct")), "percent"),
        _fact("decliners_to_advancers", _number(cash.get("sp500_decliners_to_advancers")), "ratio"),
        _fact("small_cap_confirmation", _text(equities.get("small_cap_confirmation")) or None),
    ))


def _rates_domain(packet: Mapping[str, Any], usmi: Mapping[str, Any]) -> EnvironmentDomain:
    bond = _mapping(packet.get("bond"))
    curve = _mapping(bond.get("yield_curve"))
    rates = _mapping(_cross_asset(usmi).get("rates"))
    impulse = _text(_mapping(packet.get("core_macro")).get("rates_impulse") or packet.get("rates_impulse"))
    move = _text(curve.get("curve_move_1d"))
    evidence = " ".join((impulse, move, _text(rates.get("state")))).upper()
    if any(token in evidence for token in ("BEAR_", "RESTRICTIVE", "RISING", "HAWKISH")):
        state = "RATES_PRESSURE"
    elif any(token in evidence for token in ("BULL_", "EASING", "FALLING", "DOVISH")):
        state = "RATES_RELIEF"
    elif evidence.strip():
        state = "MIXED_OR_STABLE"
    else:
        state = "UNAVAILABLE"
    stale_value = curve.get("stale_flag") if type(curve.get("stale_flag")) is bool else None
    stale = stale_value is True
    quality = "SOURCE_MARKED_STALE" if stale else "AVAILABLE" if state != "UNAVAILABLE" else "INSUFFICIENT_DATA"
    interpretation = "Rates context is advisory and cannot reverse the governed ticker direction."
    return EnvironmentDomain("RATES", state, quality, interpretation, (
        _fact("rates_impulse", impulse or None),
        _fact("curve_move_1d", move or None),
        _fact("curve_state", _text(curve.get("curve_state")) or None),
        _fact("yield_2y_pct", _number(_first(curve.get("yield_2y"), rates.get("us_2y_pct"))), "percent"),
        _fact("yield_10y_pct", _number(_first(curve.get("yield_10y"), rates.get("us_10y_pct"))), "percent"),
        _fact("spread_2s10s_bps", _number(_first(curve.get("spread_bps"), rates.get("curve_2s10s_bp"))), "basis_points"),
        _fact("source_stale", stale_value, "boolean"),
    ))


def _oil_domain(usmi: Mapping[str, Any]) -> EnvironmentDomain:
    oil = _mapping(_cross_asset(usmi).get("oil_inflation"))
    source_state = _text(oil.get("state")).upper()
    if any(token in source_state for token in ("ACUTE", "SHOCK", "CRISIS", "STRESS")):
        state = "SHOCK"
    elif any(token in source_state for token in ("CALM", "NORMAL", "BENIGN", "CONTAINED")):
        state = "CALM"
    elif source_state:
        state = "ELEVATED_OR_MIXED"
    else:
        state = "UNAVAILABLE"
    quality = "AVAILABLE" if state != "UNAVAILABLE" else "INSUFFICIENT_DATA"
    return EnvironmentDomain("OIL", state, quality,
        "Oil state and inflation transmission are context, not ticker or execution authority.", (
            _fact("source_state", source_state or None),
            _fact("wti_usd", _number(oil.get("wti_usd")), "USD/barrel"),
            _fact("brent_usd", _number(oil.get("brent_usd")), "USD/barrel"),
            _fact("inflation_transmission", _text(oil.get("inflation_transmission")) or None),
        ))


def _risk_domain(packet: Mapping[str, Any], usmi: Mapping[str, Any]) -> EnvironmentDomain:
    cross = _cross_asset(usmi)
    vol = _mapping(cross.get("volatility")) or _mapping(packet.get("volatility"))
    credit = _mapping(cross.get("credit")) or _nested(packet, "bond", "credit_stress")
    usmi_state = _mapping(usmi.get("state")) or _mapping(usmi.get("current_state"))
    panic_value = vol.get("panic_state") if type(vol.get("panic_state")) is bool else None
    risk_off_value = (
        usmi_state.get("risk_off_transition")
        if type(usmi_state.get("risk_off_transition")) is bool else None
    )
    credit_values = [
        credit.get(key) for key in ("credit_alert", "credit_warning")
        if type(credit.get(key)) is bool
    ]
    credit_alert_value = any(credit_values) if credit_values else None
    panic = panic_value is True
    risk_off = risk_off_value is True
    credit_alert = credit_alert_value is True
    vol_state = _text(vol.get("state") or vol.get("regime")).upper()
    vix = _number(_first(vol.get("vix_spot"), packet.get("vix_spot")))
    if panic or risk_off or credit_alert:
        state = "FEAR_OR_RISK_OFF"
    elif any(token in vol_state for token in ("ELEVATED", "CAUTION", "STRESS")) or (vix is not None and vix >= 20):
        state = "CAUTIOUS"
    elif any(token in vol_state for token in ("CONTAINED", "LOW", "CALM")) or (vix is not None and vix < 17):
        state = "COMPLACENT_OR_CONTAINED"
    elif vol_state or vix is not None:
        state = "MIXED"
    else:
        state = "UNAVAILABLE"
    quality = "AVAILABLE" if state != "UNAVAILABLE" else "INSUFFICIENT_DATA"
    return EnvironmentDomain("RISK_APPETITE", state, quality,
        "Risk-appetite proxy combines volatility, credit and transmission evidence; it is not investor intent.", (
            _fact("vix_spot", vix, "index_points"),
            _fact("volatility_state", vol_state or None),
            _fact("panic_state", panic_value, "boolean"),
            _fact("credit_alert", credit_alert_value, "boolean"),
            _fact("risk_off_transition", risk_off_value, "boolean"),
        ))


def project_market_environment(*, packet: Mapping[str, Any], packet_sha256: str,
                               run_id: str, evidence_cutoff_utc: str) -> MarketEnvironmentSnapshot:
    """Project one frozen governed macro packet into a small Worker 3 input."""
    if not isinstance(packet, Mapping) or packet.get("schema_version") != "interpreter_macro_context_v1":
        raise ContractError("Worker 3 requires interpreter_macro_context_v1")
    sha(packet_sha256)
    cutoff = utc(evidence_cutoff_utc)
    as_of = _text(packet.get("as_of_utc"))
    if as_of and instant(as_of) > instant(cutoff):
        raise ContractError("macro evidence is later than the Worker 3 cutoff")
    created_at = _text(packet.get("created_at_utc"))
    if created_at and instant(created_at) > instant(cutoff):
        raise ContractError("macro packet was created after the Worker 3 cutoff")
    authority = _text(packet.get("authority_statement")).upper()
    if "ADVISORY_ONLY" not in authority:
        raise ContractError("macro packet authority is not advisory-only")
    usmi = _mapping(packet.get("us_money_index"))
    contradictions = tuple(sorted({
        _text(item) for item in (packet.get("conflicts") or []) if _text(item)
    }))
    return MarketEnvironmentSnapshot(
        run_id=run_id,
        session_date=_text(packet.get("session_date")) or "UNKNOWN",
        evidence_cutoff_utc=cutoff,
        source_packet_id=_text(packet.get("packet_id")),
        source_packet_sha256=packet_sha256,
        source_fingerprint=_text(packet.get("source_fingerprint")),
        domains=(
            _equity_domain(usmi),
            _rates_domain(packet, usmi),
            _oil_domain(usmi),
            _risk_domain(packet, usmi),
        ),
        contradictions=contradictions,
    )


def build_trade_plan(bundle: EvidenceBundle) -> TradePlanSnapshot:
    """Explain governed levels without deciding whether or when to trade."""
    if not isinstance(bundle, EvidenceBundle):
        raise ContractError("validated evidence bundle required")
    available: dict[str, Any] = {}
    for observation in bundle.observations:
        if observation.status == "AVAILABLE" and observation.field not in available:
            available[observation.field] = observation.value
    trigger = _text(available.get("trigger_primary"))
    quality = _text(available.get("trigger_quality"))
    thesis_state = _text(available.get("thesis_state")) or "UNAVAILABLE"
    trigger_price = _number(available.get("trigger_price"))
    signal_price = _number(available.get("signal_price"))
    entry_posture = (
        "THESIS_REQUIRES_REVIEW" if "INVALID" in thesis_state.upper()
        else "TRIGGER_OBSERVED" if trigger and quality.upper() not in {"", "NONE", "UNAVAILABLE"}
        else "MONITOR_FOR_ENTRY_CONDITION"
    )
    gaps = []
    for field in ("signal_price", "structural_target", "invalidation_price", "trigger_primary"):
        if available.get(field) in (None, ""):
            gaps.append(field)
    conditions = [
        "Reassess when the governed thesis state changes.",
        "Reassess when the morning price materially changes target or invalidation geometry.",
        "Human operator judges executable entry and exit from current market evidence.",
    ]
    if trigger:
        conditions.insert(0, f"Observe governed trigger condition: {trigger}.")
    return TradePlanSnapshot(
        run_id=bundle.identity.run_id,
        ticker=bundle.identity.ticker,
        thesis_id=bundle.identity.thesis_id,
        direction=bundle.identity.direction.value,
        planned_hold_sessions=bundle.identity.planned_hold_sessions,
        thesis_state=thesis_state,
        entry_posture=entry_posture,
        current_reference_price=signal_price,
        entry_reference_price=trigger_price if trigger_price is not None else signal_price,
        structural_target=_number(available.get("structural_target")),
        thesis_invalidation_price=_number(available.get("invalidation_price")),
        trigger_primary=trigger or "UNAVAILABLE",
        trigger_quality=quality or "UNAVAILABLE",
        monitoring_conditions=tuple(conditions),
        data_gaps=tuple(sorted(gaps)),
    )


__all__ = [
    "EnvironmentDomain", "EnvironmentFact", "MarketEnvironmentSnapshot",
    "TradePlanSnapshot", "build_trade_plan", "project_market_environment",
]
