"""Contract and normaliser for the advisory US Money Index sidecar."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


CONTRACT_VERSIONS = {
    "avshunter_us_money_index_v1_0",
    "us_money_index_v1_0",
    "avshunter_us_money_index_v2_0",
}
V2_CONTRACT_VERSION = "avshunter_us_money_index_v2_0"
V2_PACKET_TYPE = "US_MONEY_INDEX_CONSOLIDATED"
V2_MERGE_MODE = "AUGMENT_ONLY_DO_NOT_REPLACE"
AUTHORITY = "ADVISORY_ONLY"
EXECUTION_PERMISSION = "NONE_INTELLIGENCE_ONLY"
FORBIDDEN_AUTHORITY_KEYS = {
    "capital_permission", "final_action", "final_verdict", "position_size",
    "selected_contract", "selected_contract_symbol", "governed_direction",
}


class USMoneyIndexValidationError(ValueError):
    pass


def _canonical_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_timestamp(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise USMoneyIndexValidationError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise USMoneyIndexValidationError(f"{field} is not ISO-8601") from error
    if parsed.tzinfo is None:
        raise USMoneyIndexValidationError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _parse_date(value: Any, field: str) -> date:
    text = str(value or "").strip()
    if not text:
        raise USMoneyIndexValidationError(f"{field} is required")
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise USMoneyIndexValidationError(f"{field} must be YYYY-MM-DD") from error


def _mapping(value: Any, field: str, *, required: bool = True) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if not required and value is None:
        return {}
    raise USMoneyIndexValidationError(f"{field} must be an object")


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise USMoneyIndexValidationError(f"{field} must be an array")
    return value


def _number(
    value: Any,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool):
        raise USMoneyIndexValidationError(f"{field} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise USMoneyIndexValidationError(f"{field} must be numeric") from error
    if minimum is not None and result < minimum:
        raise USMoneyIndexValidationError(f"{field} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise USMoneyIndexValidationError(f"{field} must be <= {maximum}")
    return result


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise USMoneyIndexValidationError(f"{field} is required")
    return text


def _find_forbidden(node: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            child = f"{path}.{key}"
            if str(key).strip().lower() in FORBIDDEN_AUTHORITY_KEYS:
                found.append(child)
            found.extend(_find_forbidden(value, child))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_find_forbidden(value, f"{path}[{index}]"))
    return found


def _metric(value: Any, *, as_of: str, source: str = "") -> dict[str, Any]:
    return {
        "value": value,
        "as_of": as_of,
        "source": source,
        "evidence_status": "CONFIRMED" if source else "UNVERIFIED_SOURCE",
        "usable_for_calculation": bool(source),
    }


def _raw_metrics(state: Mapping[str, Any], as_of: str) -> dict[str, Any]:
    core = state.get("core_market_snapshot") if isinstance(state.get("core_market_snapshot"), Mapping) else {}
    rates = state.get("rates_and_fed") if isinstance(state.get("rates_and_fed"), Mapping) else {}
    usd = state.get("usd_and_liquidity") if isinstance(state.get("usd_and_liquidity"), Mapping) else {}
    oil = state.get("oil_and_inflation") if isinstance(state.get("oil_and_inflation"), Mapping) else {}
    credit = state.get("credit") if isinstance(state.get("credit"), Mapping) else {}
    gex = state.get("gamma_gex") if isinstance(state.get("gamma_gex"), Mapping) else {}
    breadth = core.get("sp500_breadth") if isinstance(core.get("sp500_breadth"), Mapping) else {}
    semi = core.get("semiconductors") if isinstance(core.get("semiconductors"), Mapping) else {}
    software = core.get("software") if isinstance(core.get("software"), Mapping) else {}
    vix = core.get("vix") if isinstance(core.get("vix"), Mapping) else {}
    values = {
        "sp500_change_pct": core.get("sp500_pct"), "nasdaq100_change_pct": core.get("nasdaq100_pct"),
        "russell2000_change_pct": core.get("russell2000_pct"), "spx_advancers": breadth.get("advancers"),
        "spx_decliners": breadth.get("decliners"), "smh_change_pct": semi.get("pct"),
        "igv_change_pct": software.get("pct"), "vix_spot": vix.get("spot"),
        "treasury_2y_pct": rates.get("treasury_2y_pct"), "treasury_10y_pct": rates.get("treasury_10y_pct"),
        "treasury_30y_pct": rates.get("treasury_30y_pct"), "curve_2s10s_bp": rates.get("curve_2s10s_bp"),
        "dxy": usd.get("dxy"), "dxy_change_pct": usd.get("dxy_change_pct"),
        "wti_close_usd": oil.get("wti_close_usd"), "hy_oas_pct": credit.get("hy_oas_pct"),
        "spx_close": gex.get("spx_close"), "zero_gamma": gex.get("zero_gamma"),
        "net_gex_bn_per_1pct": gex.get("net_gex_bn_per_1pct"), "call_wall": gex.get("call_wall"),
        "put_wall": gex.get("put_wall"),
    }
    sources = state.get("metric_sources") if isinstance(state.get("metric_sources"), Mapping) else {}
    return {key: _metric(value, as_of=as_of, source=str(sources.get(key) or "")) for key, value in values.items() if value is not None}


def _v2_metrics(state: Mapping[str, Any], as_of: str) -> dict[str, Any]:
    """Expose v2 numeric evidence without promoting unsourced claims to facts."""

    cross = _mapping(state.get("cross_asset"), "cross_asset")
    equities = _mapping(cross.get("equities"), "cross_asset.equities")
    cash = _mapping(equities.get("last_us_cash_session"), "cross_asset.equities.last_us_cash_session")
    global_session = _mapping(equities.get("current_global_session"), "cross_asset.equities.current_global_session")
    rates = _mapping(cross.get("rates"), "cross_asset.rates")
    fx = _mapping(cross.get("usd_fx"), "cross_asset.usd_fx")
    liquidity = _mapping(cross.get("liquidity"), "cross_asset.liquidity")
    oil = _mapping(cross.get("oil_inflation"), "cross_asset.oil_inflation")
    credit = _mapping(cross.get("credit"), "cross_asset.credit")
    volatility = _mapping(cross.get("volatility"), "cross_asset.volatility")
    score = _mapping(state.get("risk_off_transmission_score"), "risk_off_transmission_score")
    values = {
        "sp500_change_pct": cash.get("sp500_pct"),
        "nasdaq_change_pct": cash.get("nasdaq_composite_pct"),
        "dow_change_pct": cash.get("dow_pct"),
        "russell2000_change_pct": cash.get("russell2000_pct"),
        "sp500_decliners_to_advancers": cash.get("sp500_decliners_to_advancers"),
        "nasdaq_new_lows": cash.get("nasdaq_new_lows"),
        "nasdaq_new_highs": cash.get("nasdaq_new_highs"),
        "sp500_futures_change_pct": global_session.get("sp500_futures_pct"),
        "treasury_2y_pct": rates.get("us_2y_pct"),
        "treasury_10y_pct": rates.get("us_10y_pct"),
        "treasury_30y_pct": rates.get("us_30y_pct"),
        "curve_2s10s_bp": rates.get("curve_2s10s_bp"),
        "usd_jpy": fx.get("usd_jpy"),
        "yen_5d_change_pct": fx.get("yen_5d_change_approx_pct"),
        "reserve_balances_usd_trn": liquidity.get("reserve_balances_usd_trn"),
        "tga_usd_bn": liquidity.get("tga_usd_bn"),
        "brent_usd": oil.get("brent_usd"),
        "wti_usd": oil.get("wti_usd"),
        "hy_oas_pct": credit.get("hy_oas_pct"),
        "bbb_oas_pct": credit.get("bbb_oas_pct"),
        "vix_spot": volatility.get("vix_spot"),
        "risk_off_transmission_score": score.get("current_score"),
    }
    # v2 intentionally carries a narrative/consolidated intelligence packet,
    # not source URLs per metric.  Keep values visible but non-calculative.
    return {
        key: _metric(value, as_of=as_of)
        for key, value in values.items()
        if value is not None
    }


def _validate_v2(state: Mapping[str, Any]) -> tuple[datetime, datetime, list[str]]:
    if str(state.get("packet_type") or "").strip().upper() != V2_PACKET_TYPE:
        raise USMoneyIndexValidationError(f"packet_type must be {V2_PACKET_TYPE}")
    if str(state.get("merge_mode") or "").strip().upper() != V2_MERGE_MODE:
        raise USMoneyIndexValidationError(f"merge_mode must be {V2_MERGE_MODE}")

    window = _mapping(state.get("analysis_window"), "analysis_window")
    start = _parse_date(window.get("start"), "analysis_window.start")
    end = _parse_date(window.get("end"), "analysis_window.end")
    if end < start:
        raise USMoneyIndexValidationError("analysis_window.end cannot precede start")
    as_of_utc = _parse_timestamp(window.get("as_of_utc"), "analysis_window.as_of_utc")
    as_of_local = _parse_timestamp(window.get("as_of_local"), "analysis_window.as_of_local")
    if as_of_utc != as_of_local:
        raise USMoneyIndexValidationError("analysis_window UTC/local timestamps must identify the same instant")
    if end > as_of_utc.date():
        raise USMoneyIndexValidationError("analysis_window.end cannot be after analysis_window.as_of_utc")
    _required_text(window.get("market_context"), "analysis_window.market_context")

    required_objects = (
        "noise_filter", "current_state", "cross_asset", "leadership",
        "options_monetisation", "forward_triggers", "data_quality",
        "geopolitical_escalation", "hormuz_flow",
        "risk_off_confirmation_matrix", "china_inflation_transmission",
        "risk_off_transmission_score",
    )
    for field in required_objects:
        _mapping(state.get(field), field)
    timeline = _list(state.get("timeline_since_monday"), "timeline_since_monday")
    if not timeline:
        raise USMoneyIndexValidationError("timeline_since_monday must not be empty")

    current = _mapping(state.get("current_state"), "current_state")
    _required_text(current.get("US_MONEY_INDEX_STATE"), "current_state.US_MONEY_INDEX_STATE")
    _number(current.get("state_confidence"), "current_state.state_confidence", minimum=0, maximum=1)
    for field in ("regime_change_since_monday", "monetisation_change_since_monday", "risk_off_transition"):
        if not isinstance(current.get(field), bool):
            raise USMoneyIndexValidationError(f"current_state.{field} must be boolean")

    quality = _mapping(state.get("data_quality"), "data_quality")
    _required_text(quality.get("overall"), "data_quality.overall")
    for field in ("fresh", "lagged", "unconfirmed"):
        values = _list(quality.get(field), f"data_quality.{field}")
        if any(not isinstance(item, str) or not item.strip() for item in values):
            raise USMoneyIndexValidationError(f"data_quality.{field} must contain non-empty strings")

    score = _mapping(state.get("risk_off_transmission_score"), "risk_off_transmission_score")
    headline = _number(score.get("current_score"), "risk_off_transmission_score.current_score", minimum=0, maximum=100)
    state_score = _number(current.get("risk_off_transmission_score"), "current_state.risk_off_transmission_score", minimum=0, maximum=100)
    if headline != state_score:
        raise USMoneyIndexValidationError("current_state and risk_off_transmission_score headline values disagree")
    components = _mapping(score.get("components"), "risk_off_transmission_score.components")
    if not components:
        raise USMoneyIndexValidationError("risk_off_transmission_score.components must not be empty")
    component_total = 0.0
    weight_total = 0.0
    for name, raw_component in components.items():
        component = _mapping(raw_component, f"risk_off_transmission_score.components.{name}")
        weight = _number(component.get("weight"), f"risk_off_transmission_score.components.{name}.weight", minimum=0)
        value = _number(component.get("score"), f"risk_off_transmission_score.components.{name}.score", minimum=0)
        if value > weight:
            raise USMoneyIndexValidationError(f"risk_off_transmission_score.components.{name}.score exceeds weight")
        weight_total += weight
        component_total += value
    if abs(weight_total - 100.0) > 0.001:
        raise USMoneyIndexValidationError("risk_off_transmission_score component weights must total 100")

    issues: list[str] = []
    if abs(component_total - headline) > 1.0:
        raise USMoneyIndexValidationError("risk_off_transmission_score headline does not reconcile to components")
    if component_total != headline:
        issues.append(
            f"RISK_SCORE_ROUNDING_COMPONENTS_{component_total:g}_HEADLINE_{headline:g}"
        )
    return as_of_utc, as_of_utc, issues


def _v2_sector_routing(state: Mapping[str, Any]) -> dict[str, Any]:
    monetisation = _mapping(state.get("options_monetisation"), "options_monetisation")
    calls = _list(monetisation.get("long_call_priority"), "options_monetisation.long_call_priority")
    puts = _list(monetisation.get("long_put_priority"), "options_monetisation.long_put_priority")
    routes: dict[str, dict[str, dict[str, Any]]] = {"CALL": {}, "PUT": {}}

    broad_aliases = {
        "AI_HARDWARE": ("AI_HARDWARE", "SEMICONDUCTORS"),
        "SEMICONDUCTORS": ("SEMICONDUCTORS",),
        "MEMORY": ("SEMICONDUCTORS",),
        "SEMICONDUCTOR_EQUIPMENT": ("SEMICONDUCTORS",),
        "DATA_CENTRE_INFRASTRUCTURE": ("TECHNOLOGY",),
        "OPTICAL_NETWORKING": ("TECHNOLOGY",),
        "ENERGY": ("ENERGY",),
        "REFINERS": ("ENERGY",),
        "WEAK_SOFTWARE": ("SOFTWARE",),
        "AIRLINES": ("TRANSPORT_TRAVEL", "INDUSTRIALS"),
        "TRANSPORT_LOGISTICS": ("TRANSPORT_TRAVEL", "INDUSTRIALS"),
        "FUEL_SENSITIVE_CONSUMER": ("WEAK_CONSUMER_DISCRETIONARY",),
        "WEAK_CYCLICALS": ("WEAK_CONSUMER_DISCRETIONARY",),
        "RELATIVE_WEAKNESS_NAMES": ("RELATIVE_WEAKNESS_NAMES",),
    }

    def add(direction: str, raw_values: list[Any]) -> None:
        for index, raw_value in enumerate(raw_values, start=1):
            theme = _required_text(raw_value, f"options_monetisation.{direction.lower()}_priority[{index - 1}]").upper()
            for category in broad_aliases.get(theme, (theme,)):
                existing = routes[direction].get(category)
                if existing is None or index < int(existing["priority"]):
                    routes[direction][category] = {
                        "alignment": "ALIGNED",
                        "priority": index,
                        "reason": f"USMI_V2_OPTIONS_MONETISATION:{theme}",
                    }

    add("CALL", calls)
    add("PUT", puts)
    return routes


def _normalise_sector_routing(state: Mapping[str, Any]) -> dict[str, Any]:
    structured = state.get("sector_routing")
    if isinstance(structured, Mapping) and (
        isinstance(structured.get("CALL"), Mapping) or isinstance(structured.get("PUT"), Mapping)
    ):
        return deepcopy(dict(structured))
    rotation = state.get("sector_rotation") if isinstance(state.get("sector_rotation"), Mapping) else {}
    routes: dict[str, dict[str, dict[str, Any]]] = {"CALL": {}, "PUT": {}}

    def add(direction: str, values: Any, alignment: str, start: int) -> None:
        if not isinstance(values, list):
            return
        for offset, value in enumerate(values):
            key = str(value).strip().upper()
            aliases = {
                "SOFTWARE_RELATIVE_WEAKNESS": "SOFTWARE",
                "RATE_SENSITIVE_REITS": "RATE_SENSITIVE_REITS",
                "WEAK_CONSUMER_DISCRETIONARY": "WEAK_CONSUMER_DISCRETIONARY",
                "FUEL_SENSITIVE_TRANSPORT_AND_TRAVEL": "TRANSPORT_TRAVEL",
                "OIL_BENEFICIARIES": "ENERGY",
            }
            key = aliases.get(key, key)
            routes[direction][key] = {
                "alignment": alignment,
                "priority": start + offset,
                "reason": "USMI_CAPITAL_FLOW_ROUTING",
            }

    add("CALL", rotation.get("priority_long_call_sectors"), "ALIGNED", 1)
    add("CALL", rotation.get("secondary_long_call_sectors"), "ALIGNED", 3)
    add("CALL", rotation.get("selective_long_call_sectors"), "NEUTRAL", 5)
    add("CALL", rotation.get("lower_priority_long_call_sectors"), "ADVERSE", 9)
    add("PUT", rotation.get("put_watch_sectors"), "ALIGNED", 1)
    return routes


def normalise_us_money_index_sidecar(
    state: Mapping[str, Any],
    *,
    source_path: str | Path | None = None,
) -> dict[str, Any]:
    if not isinstance(state, Mapping):
        raise USMoneyIndexValidationError("US Money Index sidecar must be a JSON object")
    version = str(state.get("contract_version") or "").strip()
    if version not in CONTRACT_VERSIONS:
        raise USMoneyIndexValidationError(f"unsupported contract_version: {version or 'MISSING'}")
    is_v2 = version == V2_CONTRACT_VERSION
    quality_issues: list[str] = []
    if is_v2:
        generated, market_as_of, quality_issues = _validate_v2(state)
    else:
        if str(state.get("packet_type") or "US_MONEY_INDEX_STATE").strip().upper() != "US_MONEY_INDEX_STATE":
            raise USMoneyIndexValidationError("packet_type must be US_MONEY_INDEX_STATE")
    permission = str(state.get("execution_permission") or EXECUTION_PERMISSION).strip().upper()
    if permission != EXECUTION_PERMISSION:
        raise USMoneyIndexValidationError("execution_permission must be NONE_INTELLIGENCE_ONLY")
    forbidden = _find_forbidden(state)
    if forbidden:
        raise USMoneyIndexValidationError("authority fields are forbidden: " + ", ".join(forbidden))
    if not is_v2:
        generated = _parse_timestamp(state.get("generated_at_local") or state.get("built_at_utc"), "generated_at_local")
        market_as_of = _parse_timestamp(state.get("market_data_as_of") or state.get("market_as_of_utc"), "market_data_as_of")
        if market_as_of > generated:
            raise USMoneyIndexValidationError("market_data_as_of cannot be after generated_at_local")

    raw = deepcopy(dict(state))
    content_hash = _canonical_hash(raw)
    state_block = state.get("current_state") if is_v2 else state.get("final_pipeline_state") if isinstance(state.get("final_pipeline_state"), Mapping) else {}
    if not state_block and isinstance(state.get("state"), Mapping):
        state_block = state.get("state")
    sources = state.get("source_references") if isinstance(state.get("source_references"), list) else []
    metrics = (
        _v2_metrics(state, market_as_of.isoformat())
        if is_v2
        else state.get("metrics") if isinstance(state.get("metrics"), Mapping)
        else _raw_metrics(state, market_as_of.isoformat())
    )
    unverified = [key for key, item in metrics.items() if not isinstance(item, Mapping) or not item.get("source")]
    quality = "VERIFIED" if metrics and not unverified and sources else "PARTIAL_UNVERIFIED"
    policy = state.get("tier_logic") if isinstance(state.get("tier_logic"), Mapping) else {}
    normalized = {
        "contract_version": "us_money_index_v1_0",
        "source_contract_version": version,
        "packet_type": "US_MONEY_INDEX_STATE",
        "packet_id": f"USMI:{market_as_of.date().isoformat()}:{content_hash[:16]}",
        "packet_sha256": content_hash,
        "authority": AUTHORITY,
        "execution_permission": EXECUTION_PERMISSION,
        "generated_at_utc": generated.isoformat(),
        "market_data_as_of_utc": market_as_of.isoformat(),
        "market_as_of_session": (
            _mapping(state.get("analysis_window"), "analysis_window").get("end")
            if is_v2 else market_as_of.date().isoformat()
        ),
        "market_status": (
            _mapping(state.get("analysis_window"), "analysis_window").get("market_context")
            if is_v2 else state.get("market_status", "UNKNOWN")
        ),
        "quality_status": quality,
        "quality_issues": quality_issues,
        "unverified_metrics": sorted(unverified),
        "source_references": deepcopy(sources),
        "source_path": str(Path(source_path).resolve()) if source_path else "",
        "state": deepcopy(dict(state_block)),
        "metrics": deepcopy(dict(metrics)),
        "sector_routing": _v2_sector_routing(state) if is_v2 else _normalise_sector_routing(state),
        "scenarios": deepcopy(state.get("scenarios") or state.get("decision_tree") or {}),
        "risk_flags": deepcopy(state.get("risk_flags") or []),
        "supportive_flags": deepcopy(state.get("supportive_flags") or []),
        "proposed_policy": deepcopy(dict(policy)),
        "policy_activation": "DISABLED_UNTIL_SEPARATELY_TESTED",
        "advisory_context": {
            key: deepcopy(state.get(key))
            for key in (
                "noise_filter", "timeline_since_monday", "cross_asset", "leadership",
                "options_monetisation", "forward_triggers", "data_quality",
                "geopolitical_escalation", "hormuz_flow",
                "risk_off_confirmation_matrix", "china_inflation_transmission",
                "risk_off_transmission_score",
            )
            if is_v2 and key in state
        },
        "source_payload": raw,
    }
    return normalized


def load_us_money_index_sidecar(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    with source.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    return normalise_us_money_index_sidecar(value, source_path=source)


def attach_us_money_index(macro: Mapping[str, Any], sidecar: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(macro))
    extras = result.get("extras") if isinstance(result.get("extras"), Mapping) else {}
    extras = deepcopy(dict(extras))
    packet = deepcopy(dict(sidecar))
    core_gex = extras.get("gex") if isinstance(extras.get("gex"), Mapping) else {}
    state = packet.get("state") if isinstance(packet.get("state"), Mapping) else {}
    external_gex = str(state.get("SPX_GEX") or state.get("spx_gex") or "").upper()
    core_regime = str(core_gex.get("regime") or "").upper()
    if core_regime and external_gex:
        external_sign = "POSITIVE" if "POSITIVE" in external_gex else "NEGATIVE" if "NEGATIVE" in external_gex else "UNKNOWN"
        packet["reconciliation"] = {
            "gex": {
                "canonical_spy_regime": core_regime,
                "external_spx_claim": external_gex,
                "status": (
                    "CONSISTENT_DIFFERENT_INSTRUMENTS"
                    if external_sign == core_regime
                    else "CONFLICT_DIFFERENT_INSTRUMENTS"
                    if external_sign != "UNKNOWN"
                    else "NOT_COMPARABLE"
                ),
                "authority": "CANONICAL_GEX_PRIMARY_EXTERNAL_USMI_ADVISORY",
            }
        }
    extras["us_money_index"] = packet
    result["extras"] = extras
    result["us_money_index_available"] = True
    result["us_money_index_packet_id"] = sidecar.get("packet_id", "")
    result["us_money_index_authority"] = AUTHORITY
    return result


__all__ = [
    "AUTHORITY", "CONTRACT_VERSIONS", "EXECUTION_PERMISSION",
    "FORBIDDEN_AUTHORITY_KEYS", "USMoneyIndexValidationError",
    "attach_us_money_index", "load_us_money_index_sidecar",
    "normalise_us_money_index_sidecar",
]
