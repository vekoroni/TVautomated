"""Pure US Money Index projection using the canonical macro-domain rules."""
from __future__ import annotations
from typing import Any, Mapping

from macro_domain.us_money_index import evaluate_scenarios, sector_advisory

MACRO_ADVISORY_VERSION = "usmi_routing_v1"
GICS_TO_ETF = {
    "ENERGY":"XLE", "FINANCIALS":"XLF", "INFORMATION TECHNOLOGY":"XLK",
    "INDUSTRIALS":"XLI", "CONSUMER DISCRETIONARY":"XLY", "MATERIALS":"XLB",
    "REAL ESTATE":"XLRE", "CONSUMER STAPLES":"XLP", "HEALTH CARE":"XLV",
    "UTILITIES":"XLU", "COMMUNICATION SERVICES":"XLC",
}

def _packet(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if value.get("contract_version") == "us_money_index_v1_0":
        return value
    direct = value.get("us_money_index")
    if isinstance(direct, Mapping):
        return direct
    extras = value.get("extras")
    if isinstance(extras, Mapping) and isinstance(extras.get("us_money_index"), Mapping):
        return extras["us_money_index"]
    return {}

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
    canonical = _packet(packet)
    key = _route_key(sector, industry, direction)
    advisory = sector_advisory(
        canonical, sector=sector, industry=industry, direction=direction
    )
    scenario = evaluate_scenarios(
        canonical.get("scenarios") if isinstance(canonical, Mapping) else {},
        canonical.get("metrics") if isinstance(canonical, Mapping) else {},
    )
    scenario_state = str(scenario.get("scenario") or "UNRESOLVED")
    failed = "" if scenario_state not in {"UNRESOLVED", "MULTIPLE_MATCH"} else (
        "SCENARIO_EVIDENCE_UNRESOLVED"
    )
    return {
        "usmi_sector_alignment": advisory["alignment"],
        "usmi_alignment_priority": advisory["priority"],
        "usmi_routing_key": key,
        "usmi_alignment_reason": advisory["reason"],
        "usmi_scenario": scenario_state,
        "usmi_scenario_failed_clause": failed,
        "usmi_authority": "ADVISORY_ONLY",
        "usmi_calculation_version": MACRO_ADVISORY_VERSION,
    }
