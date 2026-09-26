"""INT-001 contracts for the cumulative hold-window move."""

from domain.pretrade_focus import project_evening_thesis
from contracts.lab_control import opportunity_book_row


def _ready_row(**overrides):
    row = {
        "pipeline_mode": "EOD", "direction": "CALL", "signal_price": 100.0,
        "invalidation_price": 90.0, "invalidation_state": "AVAILABLE",
        "target_price": 110.0, "target_price_source": "DISCOVERY_TARGET",
        "contract_symbol": "TEST261120C00100000", "contract_bid": 4.0,
        "contract_ask": 4.2, "selected_quote_dataset_id": "quote-1",
        "monetisability_quote_snapshot_id": "quote-1",
        "monetisability_contract_symbol": "TEST261120C00100000",
        "selected_quote_timestamp_utc": "2026-09-18T20:00:00Z",
        "evidence_session_date": "2026-09-18",
        "monetisability_state": "MONETISABLE",
        "direction_conflict_status": "NO_CONFLICT",
        "direction_resolution_call_score": 1.0,
        "direction_resolution_put_score": 0.0,
        "direction_resolution_evidence_json":
            '[{"family":"PRICE_FLOW","side":"CALL","direction_independent":true}]',
        "trigger_primary": "RANGE_BREAK", "trigger_price": 99.0,
        "wyckoff_execution_bias": "BULLISH",
        "garch_expected_move_1_5d": 5.0,
        "garch_expected_move_6_10d": 2.0,
        "garch_expected_move_11_20d": 2.0,
        "expected_move_5d_fraction": 0.05,
        "expected_move_10d_fraction": 0.07,
        "expected_move_20d_fraction": 0.09,
        "horizon_convention": "CUMULATIVE_1SIGMA",
    }
    row.update(overrides)
    return row


def test_six_to_ten_day_target_uses_cumulative_budget_not_band_increment():
    row = _ready_row(time_horizon="6_10d")
    result = project_evening_thesis(row)
    assert "TARGET_BEYOND_EXPECTED_MOVE_REVIEW_BAND" not in result["evening_evidence_flags"]
    assert result["evening_thesis_bucket"] == "EOD_ACTION_SETUP_READY"


def test_eleven_to_twenty_day_target_uses_cumulative_budget_not_band_increment():
    row = _ready_row(time_horizon="11_20d", target_price=115.0)
    result = project_evening_thesis(row)
    assert "TARGET_BEYOND_EXPECTED_MOVE_REVIEW_BAND" not in result["evening_evidence_flags"]
    assert result["evening_thesis_bucket"] == "EOD_ACTION_SETUP_READY"


def test_legacy_increments_are_summed_when_canonical_fraction_is_not_projected():
    row = _ready_row(time_horizon="6_10d", expected_move_10d_fraction=None)
    result = project_evening_thesis(row)
    assert result["evening_thesis_bucket"] == "EOD_ACTION_SETUP_READY"


def test_incomplete_legacy_path_does_not_fabricate_a_cumulative_move():
    row = _ready_row(time_horizon="6_10d", expected_move_10d_fraction=None,
                     garch_expected_move_1_5d=None)
    result = project_evening_thesis(row)
    assert result["evening_thesis_bucket"] == "EOD_TARGET_FEASIBILITY_REVIEW"
    assert "Horizon-matched expected move is missing" in result["evening_thesis_reason"]


def test_invalid_canonical_budget_does_not_silently_fall_back_to_legacy():
    row = _ready_row(time_horizon="6_10d", expected_move_10d_fraction=0)
    result = project_evening_thesis(row)
    assert result["evening_thesis_bucket"] == "EOD_TARGET_FEASIBILITY_REVIEW"


def test_conflicting_canonical_horizon_convention_does_not_get_used():
    row = _ready_row(time_horizon="6_10d", horizon_convention="INCREMENTAL")
    result = project_evening_thesis(row)
    assert result["evening_thesis_bucket"] == "EOD_TARGET_FEASIBILITY_REVIEW"


def test_lab_book_uses_the_same_cumulative_evening_horizon_rule():
    source = _ready_row(horizon_bucket="6_10d", expected_move_10d_fraction=None,
                        invalidation_spot=90.0)
    book_row = opportunity_book_row(source, "20260918_230000", 1)
    assert book_row["evening_thesis_bucket"] == "EOD_ACTION_SETUP_READY"
    assert "TARGET_BEYOND_EXPECTED_MOVE_REVIEW_BAND" not in book_row["evening_evidence_flags"]
    assert book_row["expected_move_10d_fraction"] in (None, "")


def test_lab_book_retains_source_qualified_cumulative_budget_when_present():
    source = _ready_row(horizon_bucket="6_10d", invalidation_spot=90.0)
    book_row = opportunity_book_row(source, "20260918_230000", 1)
    assert book_row["expected_move_10d_fraction"] == 0.07
    assert book_row["horizon_convention"] == "CUMULATIVE_1SIGMA"
