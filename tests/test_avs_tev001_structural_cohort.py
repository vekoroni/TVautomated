"""S0/S3 cohort inclusion is determined before option selection."""

from audit.avs_tev001_structural_cohort import candidate_from_discovery
from domain.ticker_forecast import ForecastDirection


def _row(**overrides) -> dict:
    return {
        "ticker": "XYZ", "stock_price": "100", "direction": "CALL",
        "direction_authority": "DISCOVERY_GOVERNED",
        "structural_target": "110", "structural_target_source": "WYCKOFF",
        "governed_invalidation_spot": "95",
        "governed_invalidation_source": "WYCKOFF_VALIDATION",
        "sector": "Technology", **overrides,
    }


def test_sourced_discovery_geometry_becomes_option_neutral_research_start() -> None:
    result = candidate_from_discovery(
        _row(), run_id="R", evidence_session="2026-09-04",
        as_of_utc="2026-09-05T18:59:00Z",
    )
    assert result.reason == "SOURCED_PREOPTION_GEOMETRY"
    assert result.forecast is not None
    assert result.forecast.direction is ForecastDirection.BULL
    assert result.forecast.target_spot == 110
    assert result.target_source == "WYCKOFF"


def test_pending_option_target_is_not_a_predicted_move() -> None:
    result = candidate_from_discovery(
        _row(structural_target="", structural_target_source="PENDING_OI"),
        run_id="R", evidence_session="2026-09-04",
        as_of_utc="2026-09-05T18:59:00Z",
    )
    assert result.reason == "TARGET_NOT_SOURCED_PREOPTION"
    assert result.forecast is not None
    assert result.forecast.target_spot is None


def test_wrong_side_stop_is_counted_not_forced_into_training() -> None:
    result = candidate_from_discovery(
        _row(governed_invalidation_spot="105"), run_id="R",
        evidence_session="2026-09-04",
        as_of_utc="2026-09-05T18:59:00Z",
    )
    assert result.forecast is None
    assert result.reason == "INVALID_GEOMETRY"


def test_missing_authoritative_stop_marker_cannot_supply_geometry() -> None:
    result = candidate_from_discovery(
        _row(governed_invalidation_spot="95",
             governed_invalidation_source="MISSING_AUTHORITATIVE_INVALIDATION"),
        run_id="R", evidence_session="2026-09-04",
        as_of_utc="2026-09-05T18:59:00Z",
    )
    assert result.reason == "STOP_NOT_SOURCED_PREOPTION"
    assert result.forecast is not None
    assert result.forecast.invalidation_spot is None


def test_stale_or_wrong_session_price_cannot_become_frozen_start() -> None:
    stale = candidate_from_discovery(
        _row(is_stale="True", bar_data_asof="2026-09-03"), run_id="R",
        evidence_session="2026-09-04", as_of_utc="2026-09-05T18:59:00Z",
    )
    wrong_session = candidate_from_discovery(
        _row(is_stale="False", bar_data_asof="2026-09-03"), run_id="R",
        evidence_session="2026-09-04", as_of_utc="2026-09-05T18:59:00Z",
    )
    assert stale.reason == "STALE_BAR"
    assert wrong_session.reason == "BAR_SESSION_MISMATCH"
    assert stale.forecast is None and wrong_session.forecast is None
