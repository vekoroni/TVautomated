"""XLU-D03 (ACK 2 Oct 2026): sector alignment was UNMAPPED on all 1,570 book rows.

Root causes (audit 1 Oct): (1) the placeholder gics_sector="ETF" hid sector_etf=XLU in every
resolver; (2) USMI routes were keyed by free-text priority themes matched only by exact name;
(3) no Utilities alias or route. Business rules:
- A placeholder sector resolves through the ETF to its sector (versioned map), in one owner.
- A priority theme routes every sector category its words name.
- Advisory only: alignment is displayed, never a gate or score.
"""
from contracts.us_money_index_contract import _v2_sector_routing
from domain.sector_resolution import resolve_sector
from macro_domain.us_money_index import sector_advisory


def test_placeholder_sector_resolves_through_the_etf():
    assert resolve_sector({"gics_sector": "ETF", "sector_etf": "XLU"}) == "UTILITIES"
    assert resolve_sector({"gics_sector": "Utilities", "sector_etf": "XLU"}) == "UTILITIES"
    assert resolve_sector({"gics_sector": "", "sector": "ETF", "sector_etf": "XLRE"}) == "REAL ESTATE"
    assert resolve_sector({"gics_sector": "Information Technology"}) == "INFORMATION TECHNOLOGY"
    assert resolve_sector({"gics_sector": "ETF", "sector_etf": "ZZZ"}) == ""
    assert resolve_sector({}) == ""


def _state(puts, calls=()):
    return {"options_monetisation": {"long_put_priority": list(puts), "long_call_priority": list(calls)}}


def test_themes_route_every_sector_they_name():
    routes = _v2_sector_routing(_state(["QQQ_HIGH_DURATION_GROWTH", "IWM_SMALL_CAPS", "RATE_SENSITIVE_UTILITIES_REITS_HOMEBUILDERS"]))
    assert routes["PUT"]["UTILITIES"]["priority"] == 3
    assert routes["PUT"]["RATE_SENSITIVE_REITS"]["priority"] == 3
    assert routes["PUT"]["HOMEBUILDERS"]["priority"] == 3
    assert routes["PUT"]["UTILITIES"]["reason"].endswith("RATE_SENSITIVE_UTILITIES_REITS_HOMEBUILDERS")


def test_xlu_put_is_aligned_with_the_money_index_put_priority():
    packet = {"sector_routing": _v2_sector_routing(_state(["A", "B", "C", "RATE_SENSITIVE_UTILITIES_REITS_HOMEBUILDERS"]))}
    sector = resolve_sector({"gics_sector": "ETF", "sector_etf": "XLU"})
    out = sector_advisory(packet, sector=sector, direction="PUT")
    assert out["alignment"] == "ALIGNED" and out["priority"] == 4
    assert sector_advisory(packet, sector=sector, direction="CALL")["reason"] == "SECTOR_NOT_IN_USMI_PRIORITIES"


def test_existing_exact_aliases_still_route():
    routes = _v2_sector_routing(_state([], ["SEMICONDUCTORS", "ENERGY"]))
    assert routes["CALL"]["SEMICONDUCTORS"]["priority"] == 1 and routes["CALL"]["ENERGY"]["priority"] == 2


def test_all_resolvers_use_the_single_owner():
    from pathlib import Path
    for path in ("contracts/lab_control.py", "contracts/interpreter_macro_context.py", "scripts/macro_quant_packet.py"):
        assert "resolve_sector(" in Path(path).read_text(encoding="utf-8"), path


def test_macro_quant_alignment_matches_the_sector_or_its_etf():
    import scripts.macro_quant_packet as mq
    row = {"gics_sector": "ETF", "sector_etf": "XLU"}
    assert mq._ticker_alignment({"avoid_sectors": ["XLU"]}, row)[0] == "CONFLICTED"
    assert mq._ticker_alignment({"avoid_sectors": ["Utilities"]}, row)[0] == "CONFLICTED"
    assert mq._ticker_alignment({"preferred_sectors": ["Energy"]}, row)[0] == "NEUTRAL"


def test_a_known_sector_absent_from_the_index_is_not_called_unmapped():
    packet = {"sector_routing": _v2_sector_routing(_state(["RATE_SENSITIVE_UTILITIES_REITS_HOMEBUILDERS"]))}
    assert sector_advisory(packet, sector="HEALTH CARE", direction="PUT")["reason"] == "SECTOR_NOT_IN_USMI_PRIORITIES"
    assert sector_advisory(packet, sector="", direction="PUT")["reason"] == "SECTOR_UNMAPPED"
