"""Advisory-only US Money Index interpretation helpers."""

from __future__ import annotations

from typing import Any, Mapping


SECTOR_ALIASES = {
    "INFORMATION TECHNOLOGY": "TECHNOLOGY",
    "TECHNOLOGY": "TECHNOLOGY",
    "SEMICONDUCTORS": "SEMICONDUCTORS",
    "SOFTWARE": "SOFTWARE",
    "ENERGY": "ENERGY",
    "REAL ESTATE": "RATE_SENSITIVE_REITS",
    "CONSUMER DISCRETIONARY": "WEAK_CONSUMER_DISCRETIONARY",
    "INDUSTRIALS": "INDUSTRIALS",
    "FINANCIALS": "FINANCIALS",
    "HEALTH CARE": "HEALTH_CARE",
    "HEALTHCARE": "HEALTH_CARE",
    "COMMUNICATION SERVICES": "COMMUNICATION_SERVICES",
    "XLK": "TECHNOLOGY",
    "XLE": "ENERGY",
    "XLRE": "RATE_SENSITIVE_REITS",
    "XLY": "WEAK_CONSUMER_DISCRETIONARY",
}


def _value(context: Mapping[str, Any], key: str) -> float | None:
    value = context.get(key)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _predicate(key: str, threshold: Any, context: Mapping[str, Any]) -> bool | None:
    operations = {
        "_gt": lambda left, right: left > right,
        "_lt": lambda left, right: left < right,
        "_gte": lambda left, right: left >= right,
        "_lte": lambda left, right: left <= right,
    }
    for suffix, operation in operations.items():
        if key.endswith(suffix):
            actual = _value(context, key[: -len(suffix)])
            expected = _value({"value": threshold}, "value")
            return None if actual is None or expected is None else operation(actual, expected)
    return None


def evaluate_scenarios(
    scenarios: Mapping[str, Any] | None,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate structured scenario predicates without producing authority."""

    if not isinstance(scenarios, Mapping):
        return {"scenario": "UNRESOLVED", "reason": "SCENARIOS_UNAVAILABLE", "authority": "ADVISORY_ONLY"}
    results: dict[str, Any] = {}
    matched: list[str] = []
    for name, definition in scenarios.items():
        if name in {"default", "evaluate_at"} or not isinstance(definition, Mapping):
            continue
        conditions = definition.get("all")
        if not isinstance(conditions, list):
            results[name] = {"status": "UNAVAILABLE", "reason": "UNSTRUCTURED_PREDICATES"}
            continue
        evaluations: list[bool | None] = []
        for condition in conditions:
            if not isinstance(condition, Mapping) or len(condition) != 1:
                evaluations.append(None)
                continue
            key, threshold = next(iter(condition.items()))
            evaluations.append(_predicate(str(key), threshold, context))
        status = "MATCH" if evaluations and all(value is True for value in evaluations) else "NO_MATCH" if all(value is not None for value in evaluations) else "UNAVAILABLE"
        results[name] = {"status": status, "predicates": evaluations}
        if status == "MATCH":
            matched.append(str(name))
    scenario = matched[0] if len(matched) == 1 else "MULTIPLE_MATCH" if matched else str(scenarios.get("default") or "UNRESOLVED")
    return {"scenario": scenario, "results": results, "authority": "ADVISORY_ONLY"}


def sector_advisory(
    packet: Mapping[str, Any] | None,
    *,
    sector: str,
    direction: str,
    industry: str = "",
) -> dict[str, Any]:
    """Return display/ranking context; never a verdict or permission."""

    if not isinstance(packet, Mapping):
        return {"alignment": "UNAVAILABLE", "priority": None, "reason": "USMI_UNAVAILABLE"}
    sector_text = str(sector).strip().upper()
    industry_text = str(industry).strip().upper()
    category = SECTOR_ALIASES.get(sector_text, sector_text)
    if "SEMICONDUCT" in industry_text:
        category = "SEMICONDUCTORS"
    elif "SOFTWARE" in industry_text:
        category = "SOFTWARE"
    elif "AI HARDWARE" in industry_text:
        category = "AI_HARDWARE"
    routes = packet.get("sector_routing")
    if isinstance(routes, Mapping):
        directional = routes.get(str(direction).strip().upper())
        if isinstance(directional, Mapping):
            route = directional.get(category)
            if not isinstance(route, Mapping) and category == "TECHNOLOGY":
                # A broad technology label cannot safely be assumed to be
                # semiconductors or software.
                route = directional.get("TECHNOLOGY")
            if isinstance(route, Mapping):
                return {
                    "alignment": str(route.get("alignment") or "NEUTRAL"),
                    "priority": route.get("priority"),
                    "reason": str(route.get("reason") or "USMI_SECTOR_ROUTING"),
                }
    return {"alignment": "NEUTRAL", "priority": None, "reason": "SECTOR_UNMAPPED"}


__all__ = ["SECTOR_ALIASES", "evaluate_scenarios", "sector_advisory"]
