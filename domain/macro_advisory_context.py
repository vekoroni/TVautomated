"""Pure US Money Index routing and scenario context (never authority)."""
from __future__ import annotations
from typing import Any, Mapping

MACRO_ADVISORY_VERSION = "usmi_routing_v1"
GICS_TO_ETF = {
    "ENERGY":"XLE", "FINANCIALS":"XLF", "INFORMATION TECHNOLOGY":"XLK",
    "INDUSTRIALS":"XLI", "CONSUMER DISCRETIONARY":"XLY", "MATERIALS":"XLB",
    "REAL ESTATE":"XLRE", "CONSUMER STAPLES":"XLP", "HEALTH CARE":"XLV",
    "UTILITIES":"XLU", "COMMUNICATION SERVICES":"XLC",
}

def _find(node: Any, key: str):
    if isinstance(node, Mapping):
        if key in node:
            return node[key]
        for child in node.values():
            value = _find(child, key)
            if value is not None:
                return value
    elif isinstance(node, list):
        for child in node:
            value = _find(child, key)
            if value is not None:
                return value
    return None

def _route_key(sector: str, industry: str, direction: str) -> str:
    sec, ind, side = sector.upper(), industry.upper(), direction.upper()
    if side == "PUT":
        if "AIR" in ind and any(x in ind for x in ("TRANSPORT", "AIRLINE", "SCHEDULED")): return "AIRLINES_PUT"
        if any(x in ind for x in ("RAILROAD", "TRUCKING", "FREIGHT", "LOGISTICS", "SHIPPING")): return "TRANSPORT_LOGISTICS_PUT"
        if sec == "REAL ESTATE" or "HOMEBUILD" in ind: return "HOMEBUILDERS_REITS_PUT"
        if sec in {"MATERIALS", "INDUSTRIALS"}: return "MATERIALS_INDUSTRIALS_PUT"
        if sec == "INFORMATION TECHNOLOGY" or "SOFTWARE" in ind: return "WEAK_TECH_PUT"
        if sec == "CONSUMER DISCRETIONARY": return "FUEL_SENSITIVE_DISCRETIONARY_PUT"
    if side == "CALL":
        if sec == "ENERGY" and any(x in ind for x in ("SERVICES", "DRILLING", "EQUIPMENT", "REFIN")): return "REFINERS_OIL_SERVICES_CALL"
        if sec == "ENERGY": return "ENERGY_PRODUCERS_CALL"
        if sec == "FINANCIALS": return "FINANCIALS_CALL"
        if sec == "INFORMATION TECHNOLOGY" and "SOFTWARE" in ind: return "AI_SOFTWARE_CLOUD_CALL"
        if sec == "INFORMATION TECHNOLOGY": return "AI_SEMICONDUCTOR_CALL"
        if sec == "INDUSTRIALS" and any(x in ind for x in ("AIRCRAFT", "DEFENSE", "ORDNANCE", "SHIPBUILD")): return "DEFENCE_CALL"
    return "NO_ROUTE"

def _mapping_value(route: Any) -> tuple[str, str]:
    if isinstance(route, Mapping):
        state = str(route.get("alignment") or route.get("state") or route.get("preferred_side") or "NEUTRAL").upper()
        return state, str(route.get("reason") or route.get("rationale") or "ROUTE_PRESENT")
    return str(route or "NEUTRAL").upper(), "ROUTE_PRESENT"

def project_usmi_context(*, packet: Mapping[str, Any], sector: str, industry: str, direction: str) -> dict[str, Any]:
    routing = _find(packet, "routing")
    key = _route_key(sector, industry, direction)
    route = routing.get(key) if isinstance(routing, Mapping) else None
    if route is None:
        alignment, reason = "UNAVAILABLE", f"{key}:ROUTE_UNAVAILABLE"
    else:
        raw, reason = _mapping_value(route)
        if raw in {"UNCERTAIN", "UNAVAILABLE"}: alignment = raw
        elif raw in {"ALIGNED", "SUPPORTIVE", "CALL", "PUT", "BULLISH", "BEARISH"}: alignment = "SUPPORTIVE"
        elif raw in {"OPPOSED", "HEADWIND"}: alignment = "OPPOSED"
        else: alignment = "NEUTRAL"
    scenarios = _find(packet, "scenarios")
    scenario_state = "UNRESOLVED"
    failed = "SCENARIOS_UNAVAILABLE"
    if isinstance(scenarios, list):
        matches = []
        for scenario in scenarios:
            if not isinstance(scenario, Mapping): continue
            conditions = scenario.get("conditions_all") or []
            passed = True
            for clause in conditions:
                if not isinstance(clause, Mapping): passed = False; continue
                observed = _find(packet, str(clause.get("metric") or ""))
                if observed is None: passed = False; failed = f"MISSING_METRIC:{clause.get('metric')}"; break
                try:
                    a, b = float(observed), float(clause.get("value"))
                    op = str(clause.get("op") or "=")
                    passed = {"<":a<b, "<=":a<=b, "≤":a<=b, ">":a>b, ">=":a>=b, "≥":a>=b, "=":a==b}.get(op, False)
                except (TypeError, ValueError): passed = False
                if not passed: failed = f"FAILED:{clause.get('metric')}:{observed}"; break
            if passed: matches.append(str(scenario.get("id") or scenario.get("scenario_id") or ""))
        if len(matches) == 1: scenario_state, failed = matches[0], ""
        elif len(matches) > 1: scenario_state, failed = "MULTIPLE", "|".join(matches)
    return {
        "usmi_sector_alignment": alignment,
        "usmi_alignment_priority": key,
        "usmi_alignment_reason": reason,
        "usmi_scenario": scenario_state,
        "usmi_scenario_failed_clause": failed,
        "usmi_authority": "ADVISORY_ONLY",
        "usmi_calculation_version": MACRO_ADVISORY_VERSION,
    }
