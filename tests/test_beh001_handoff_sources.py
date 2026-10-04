"""BEH-001 §7 handoff: the behavioural invalidation level travels with an
explicit BEHAVIOURAL_STRUCTURE source through the adapter and the C5 packet,
never relabelled as another engine's level."""
from contracts.direction_governance import assess_thesis_geometry, legacy_direction_adapter_v1
from domain.descriptive_forecast_handoff import build_descriptive_packet


def test_adapter_accepts_and_echoes_behavioural_structure_source():
    geometry = assess_thesis_geometry(thesis_side="BEAR", reference_price=15.91, invalidation_price=17.96,
                                      invalidation_source="BEHAVIOURAL_STRUCTURE", target_price=None,
                                      target_source=None)
    assert geometry["geometry_status"] == "COMPLETE"
    legacy = legacy_direction_adapter_v1(thesis_side="BEAR", direction_status="ACTIVATED:SOW -> LPSY continuation",
                                         direction_basis="{}", unassigned_reason="", geometry=geometry)
    assert legacy["direction"] == "PUT"
    assert legacy["governed_invalidation_spot"] == 17.96
    assert legacy["governed_invalidation_source"] == "BEHAVIOURAL_STRUCTURE"


def test_c5_packet_keeps_a_behavioural_stop():
    row = {"ticker": "SOFI", "direction": "PUT", "direction_authority": "DISCOVERY_GOVERNED", "is_stale": "False",
           "bar_data_asof": "2026-09-29", "stock_price": "15.91", "thesis__side": "BEAR",
           "thesis__direction_status": "ACTIVATED:SOW -> LPSY continuation", "target_state": "NONE",
           "geometry_status": "COMPLETE", "governed_invalidation_spot": "17.96",
           "governed_invalidation_source": "BEHAVIOURAL_STRUCTURE"}
    item = build_descriptive_packet("R", "2026-09-29", "2026-09-30T08:00:00Z", [row], discovery_sha256="e" * 64)["rows"][0]
    assert item["forecast_invalidation_spot"] == 17.96
    assert item["forecast_trade_plan_state"] == "COMPLETE_GEOMETRY"
