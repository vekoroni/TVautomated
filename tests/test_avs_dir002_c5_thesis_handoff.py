"""DIR-002 DWN-04: the C5 packet reads the Thesis side, not a CALL/PUT token.

Business rules:
- thesis__side (BULL/BEAR/UNASSIGNED) is read first; legacy `direction` is the
  fallback for historical runs only, and a contradiction fails closed per row.
- UNASSIGNED theses stay visible with their explicit reason (R11).
- A declared target_state NONE is never repaired from a stale target field.
- A directed row with incomplete geometry remains descriptive but cannot claim
  a complete trade plan.
- Upside-only Vanguard context is never attached to a BEAR thesis.
- Both candidate geometries travel with the row; one row per ticker.
"""
import json

import pytest

from domain.descriptive_forecast_handoff import build_descriptive_packet


def row(ticker="XYZ", side="BULL", **changes):
    bull = side == "BULL"
    base = {
        "ticker": ticker, "direction": "CALL" if bull else "PUT",
        "direction_authority": "DISCOVERY_GOVERNED", "is_stale": "False",
        "bar_data_asof": "2026-09-25", "stock_price": "100",
        "structural_target": "110" if bull else "90", "structural_target_source": "WYCKOFF",
        "governed_invalidation_spot": "95" if bull else "105",
        "governed_invalidation_source": "WYCKOFF_VALIDATION",
        "thesis__side": side, "thesis__direction_status": "CONFIRMED_STRUCTURE",
        "thesis__unassigned_reason": "", "geometry_status": "COMPLETE", "target_state": "LEVEL",
        "bull_invalidation": "95", "bull_target": "110", "bull_target_state": "LEVEL",
        "bull_geometry_status": "COMPLETE",
        "bear_invalidation": "105", "bear_target": "90", "bear_target_state": "LEVEL",
        "bear_geometry_status": "COMPLETE",
    }
    base.update(changes)
    return base


def build(*rows, **kwargs):
    return build_descriptive_packet(
        "R", "2026-09-25", "2026-09-26T17:37:30Z", list(rows), discovery_sha256="c" * 64, **kwargs
    )["rows"]


@pytest.mark.parametrize("side,direction", [("BULL", "BULL"), ("BEAR", "BEAR")])
def test_thesis_side_drives_forecast_direction_with_status(side, direction):
    item = build(row(side=side))[0]
    assert item["forecast_direction"] == direction
    assert item["forecast_state"] == "DESCRIPTIVE_ONLY"
    assert item["forecast_thesis_status"] == "CONFIRMED_STRUCTURE"
    assert item["forecast_trade_plan_state"] == "COMPLETE_GEOMETRY"
    geometry = json.loads(item["forecast_candidate_geometry_json"])
    assert set(geometry) == {"BULL", "BEAR"}


def test_unassigned_thesis_is_visible_with_explicit_reason():
    item = build(row(thesis__side="UNASSIGNED", thesis__direction_status="TREND_ONLY",
                     thesis__unassigned_reason="TREND_ONLY", direction="UNRESOLVED",
                     geometry_status="NOT_ASSESSABLE", target_state="NONE"))[0]
    assert item["forecast_direction"] is None
    assert item["forecast_reason"] == "THESIS_UNASSIGNED:TREND_ONLY"
    assert item["forecast_thesis_status"] == "TREND_ONLY"


def test_contradicting_legacy_direction_fails_closed_for_the_row():
    item = build(row(side="BULL", direction="PUT"))[0]
    assert item["forecast_direction"] is None
    assert item["forecast_reason"] == "DIRECTION_FIELD_CONFLICT"


def test_declared_target_none_is_not_repaired_from_stale_target():
    item = build(row(target_state="NONE"))[0]
    assert item["forecast_target_spot"] is None
    assert item["forecast_reason"] == "TARGET_NOT_SOURCED_PREOPTION"


def test_directed_incomplete_geometry_keeps_side_but_not_trade_plan():
    item = build(row(geometry_status="INCOMPLETE_GEOMETRY", governed_invalidation_spot="",
                     governed_invalidation_source="MISSING_AUTHORITATIVE_INVALIDATION"))[0]
    assert item["forecast_direction"] == "BULL"
    assert item["forecast_invalidation_spot"] is None
    assert item["forecast_trade_plan_state"] == "INCOMPLETE_GEOMETRY"


def test_upside_only_vanguard_context_is_not_attached_to_bear():
    vanguard = [{"ticker": "BULLT", "layer2__edge_quality": "STRONG"},
                {"ticker": "BEART", "layer2__edge_quality": "STRONG"}]
    bull, bear = build(row("BULLT"), row("BEART", side="BEAR"),
                       vanguard_rows=vanguard, vanguard_sha256="d" * 64)
    assert bull["forecast_legacy_statistical_context"] == "STRONG"
    assert bull["forecast_legacy_statistical_basis"] == "BULL_ONLY_LEGACY"
    assert bear["forecast_legacy_statistical_context"] is None
    assert bear["forecast_legacy_statistical_basis"] == "NOT_APPLICABLE_BULL_ONLY_LEGACY"


def test_historical_row_without_thesis_side_keeps_legacy_mapping():
    legacy = row()
    for key in [k for k in legacy if k.startswith(("thesis__", "bull_", "bear_"))] + ["geometry_status", "target_state"]:
        legacy.pop(key)
    item = build(legacy)[0]
    assert item["forecast_direction"] == "BULL"
    assert item["forecast_thesis_status"] is None
    assert item["forecast_target_spot"] == 110.0
