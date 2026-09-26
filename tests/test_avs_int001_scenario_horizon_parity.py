"""INT-001 scenario suite 2: one ticker, one volatility budget, every consumer.

Business rule under test (design §4.4, receipt AVS-INT-001_HORIZON_UNIT_REPAIR): the
5/10/20-session hold-window move has one owner and one meaning. Every consumer that reads
it, Evening thesis, EOD exit fallback, trigger EV, execution package, Morning exit plan, Lab
book and the run manifest, must resolve the same number for the same row, in its own units,
and must go to UNKNOWN together when the budget is incomplete or its convention conflicts.

The ticker is realistic: spot 48.20, annual forecast vol 42%. Legacy Layer 3 increments are
derived from the canonical checkpoints so the two conventions are consistent by construction.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.volatility_budget import checkpoint_fields, cumulative_expected_move_pct  # noqa: E402
from domain.pretrade_focus import project_evening_thesis  # noqa: E402
from contracts.lab_control import _thesis_geometry_completeness, opportunity_book_row  # noqa: E402
from eod_candidate_engine import _exit_intelligence_plan  # noqa: E402
from execution_decision_engine import _build_signal_pkg  # noqa: E402
from morning_validation import compute_exit_plan  # noqa: E402
from trigger_layer import _compute_ev  # noqa: E402

SPOT = 48.20
ANNUAL_VOL = 0.42
CANON = checkpoint_fields(ANNUAL_VOL)
MOVE5 = CANON["expected_move_5d_fraction"] * 100.0
MOVE10 = CANON["expected_move_10d_fraction"] * 100.0
MOVE20 = CANON["expected_move_20d_fraction"] * 100.0
LEGACY = {
    "garch_expected_move_1_5d": round(MOVE5, 4),
    "garch_expected_move_6_10d": round(MOVE10 - MOVE5, 4),
    "garch_expected_move_11_20d": round(MOVE20 - MOVE10, 4),
}
L3 = {k.replace("garch_", "l3_"): v for k, v in LEGACY.items()}


def _ticker_row(direction: str = "CALL", horizon: str = "6_10d", *, canonical: bool = True,
                legacy: bool = True, **overrides) -> dict:
    target = SPOT * (1.06 if direction == "CALL" else 0.94)
    stop = SPOT * (0.955 if direction == "CALL" else 1.045)
    row = {
        "ticker": "ACME", "pipeline_mode": "EOD", "direction": direction,
        "canonical_direction": direction, "signal_price": SPOT, "underlying_price": SPOT,
        "target_price": round(target, 2), "target_price_source": "DISCOVERY_TARGET",
        "invalidation_price": round(stop, 2), "invalidation_state": "AVAILABLE",
        "invalidation_source": "WYCKOFF_VALIDATION", "time_horizon": horizon,
        "horizon_bucket": horizon, "win_rate_10d": 0.58,
        "contract_symbol": "ACME261120C00048000" if direction == "CALL" else "ACME261120P00048000",
        "monetisability_contract_symbol": "ACME261120C00048000" if direction == "CALL" else "ACME261120P00048000",
        "contract_bid": 2.10, "contract_ask": 2.25, "selected_quote_dataset_id": "q-1",
        "monetisability_quote_snapshot_id": "q-1",
        "selected_quote_timestamp_utc": "2026-09-25T20:00:00Z", "evidence_session_date": "2026-09-25",
        "monetisability_state": "MONETISABLE", "direction_conflict_status": "NO_CONFLICT",
        "direction_resolution_call_score": 1.0 if direction == "CALL" else 0.0,
        "direction_resolution_put_score": 0.0 if direction == "CALL" else 1.0,
        "direction_resolution_evidence_json":
            f'[{{"family":"PRICE_FLOW","side":"{direction}","direction_independent":true}}]',
        "trigger_primary": "RANGE_BREAK",
        "trigger_price": SPOT * (0.99 if direction == "CALL" else 1.01),
        "wyckoff_execution_bias": "BULLISH" if direction == "CALL" else "BEARISH",
    }
    if canonical:
        row.update(CANON)
    if legacy:
        row.update(LEGACY)
        row.update(L3)
    row.update(overrides)
    return row


# ------------------------------------------------------------------ the two conventions agree
def test_canonical_and_legacy_conventions_resolve_the_same_hold_window_move():
    row = _ticker_row()
    assert cumulative_expected_move_pct(row, "1_5D") == pytest.approx(MOVE5, abs=1e-3)
    assert cumulative_expected_move_pct(row, "6_10D") == pytest.approx(MOVE10, abs=1e-3)
    assert cumulative_expected_move_pct(row, "11_20D") == pytest.approx(MOVE20, abs=1e-3)
    legacy_only = _ticker_row(canonical=False)
    assert cumulative_expected_move_pct(legacy_only, "6_10D") == pytest.approx(MOVE10, abs=1e-3)
    assert cumulative_expected_move_pct(legacy_only, "11_20D") == pytest.approx(MOVE20, abs=1e-3)
    # sanity on the realistic magnitude: 42% annual -> about 8.4% over ten sessions
    assert 7.5 < MOVE10 < 9.5


@pytest.mark.parametrize("direction", ["CALL", "PUT"])
@pytest.mark.parametrize("horizon,move", [("6_10d", MOVE10), ("11_20d", MOVE20)])
def test_every_evening_consumer_uses_the_same_cumulative_move(direction, horizon, move):
    row = _ticker_row(direction, horizon)
    sign = 1 if direction == "CALL" else -1

    # Evening thesis: the 6% / 6% target is inside the review band for both horizons.
    thesis = project_evening_thesis(row)
    assert thesis["evening_thesis_bucket"] == "EOD_ACTION_SETUP_READY", thesis
    assert "TARGET_BEYOND_EXPECTED_MOVE_REVIEW_BAND" not in thesis["evening_evidence_flags"]

    # EOD exit fallback target with no discovery target: spot * (1 +/- move)
    plan = _exit_intelligence_plan({k: v for k, v in row.items() if k != "target_price"},
                                   direction, row["invalidation_price"], 0.0, 0.0)
    assert plan["exit_t2"] == pytest.approx(SPOT * (1 + sign * move / 100.0), rel=1e-6)

    # Trigger EV and execution package read the ten-session move as a fraction.
    if horizon == "6_10d":
        assert _compute_ev(row) == pytest.approx(0.58 * move / 100.0, rel=1e-6)
        pkg = _build_signal_pkg(row)
        assert pkg["actuarial"]["expected_move_10d"] == pytest.approx(move / 100.0, rel=1e-6)

    # Lab book carries the same canonical fraction with its convention.
    book = opportunity_book_row(row, "20260925_230000", 1)
    assert book["expected_move_10d_fraction"] == pytest.approx(CANON["expected_move_10d_fraction"])
    assert book["horizon_convention"] == "CUMULATIVE_1SIGMA"
    assert book["evening_thesis_bucket"] == "EOD_ACTION_SETUP_READY"


@pytest.mark.parametrize("direction", ["CALL", "PUT"])
def test_morning_exit_plan_converts_the_same_budget_to_dollars_at_spot(direction):
    sign = 1 if direction == "CALL" else -1
    wall = SPOT * (1 + sign * 0.05)
    row = _ticker_row(direction, wbs_wall_price=round(wall, 2), wbs_grade="PROBABLE", wbs_f1_vanna=12.0)
    plan = compute_exit_plan(row)
    garch_5d_dollars = SPOT * MOVE5 / 100.0
    garch_10d_dollars = SPOT * MOVE10 / 100.0
    wall_dist = abs(round(wall, 2) - SPOT)
    assert plan["exit_garch_covers_pct"] == pytest.approx(garch_5d_dollars / wall_dist * 100.0, abs=0.02)
    assert plan["exit_mode"] == "RIDE_THROUGH_WALL"
    # t3 = wall +/- the ten-session dollar move, on the thesis side
    assert plan["exit_t3_price"] == pytest.approx(round(wall, 2) + sign * garch_10d_dollars, abs=1e-3)
    assert plan["exit_runner_target_state"] == "AVAILABLE"
    assert plan["exit_plan_complete"] is True
    if direction == "CALL":
        assert plan["exit_t1_price"] < plan["exit_t2_price"] < plan["exit_t3_price"]
    else:
        assert plan["exit_t1_price"] > plan["exit_t2_price"] > plan["exit_t3_price"]
    assert plan["exit_invalidation_label"] == "PLAN_REEVALUATION_TRIGGER_NOT_STOP_LOSS"


# ------------------------------------------------------------------ incomplete or conflicting budgets
def test_conflicting_convention_sends_every_consumer_to_unknown_together():
    row = _ticker_row(horizon_convention="INCREMENTAL")
    assert cumulative_expected_move_pct(row, "6_10D") is None
    assert project_evening_thesis(row)["evening_thesis_bucket"] == "EOD_TARGET_FEASIBILITY_REVIEW"
    plan = _exit_intelligence_plan({k: v for k, v in row.items() if k != "target_price"}, "CALL",
                                   row["invalidation_price"], 0.0, 0.0)
    assert plan["exit_t2"] in (0.0, None, "")
    assert _compute_ev(row) == 0.0
    assert _build_signal_pkg(row)["actuarial"]["expected_move_10d"] is None


def test_incomplete_legacy_path_is_unknown_not_a_shorter_horizon_in_evening_consumers():
    row = _ticker_row(canonical=False)
    for key in ("garch_expected_move_1_5d", "l3_expected_move_1_5d"):
        row.pop(key)
    assert cumulative_expected_move_pct(row, "6_10D") is None
    assert _compute_ev(row) == 0.0
    assert _build_signal_pkg(row)["actuarial"]["expected_move_10d"] is None
    assert project_evening_thesis(row)["evening_thesis_bucket"] == "EOD_TARGET_FEASIBILITY_REVIEW"


def test_morning_exit_does_not_price_the_runner_off_a_five_session_budget_when_ten_is_missing():
    wall = SPOT * 1.05
    row = _ticker_row("CALL", canonical=False, wbs_wall_price=round(wall, 2),
                      wbs_grade="PROBABLE", wbs_f1_vanna=12.0)
    for key in ("garch_expected_move_6_10d", "l3_expected_move_6_10d"):
        row.pop(key)
    plan = compute_exit_plan(row)
    assert plan["exit_mode"] == "RIDE_THROUGH_WALL"
    # With only a 5-session budget, no 10-session runner target or allocation exists.
    assert plan["exit_t3_price"] == ""
    assert plan["exit_t3_pct"] == 0
    assert plan["exit_runner_target_state"] == "HORIZON_BUDGET_MISSING"
    assert plan["exit_plan_complete"] is False


def test_morning_exit_rejects_a_conflicting_horizon_convention():
    row = _ticker_row(horizon_convention="INCREMENTAL", wbs_grade="PROBABLE", wbs_f1_vanna=12.0)
    plan = compute_exit_plan(row)
    assert plan["exit_t3_price"] == ""
    assert plan["exit_runner_target_state"] == "HORIZON_BUDGET_MISSING"


@pytest.mark.parametrize("direction", ["CALL", "PUT"])
@pytest.mark.parametrize(
    "grade,vanna,mode",
    [("PROBABLE", 12.0, "RIDE_THROUGH_WALL"), ("WEAK", 0.0, "SCALE_AT_WALL")],
)
def test_morning_runner_requires_its_own_budget_for_each_side_and_mode(direction, grade, vanna, mode):
    sign = 1 if direction == "CALL" else -1
    row = _ticker_row(
        direction, canonical=False,
        wbs_wall_price=round(SPOT * (1 + sign * 0.05), 2),
        wbs_grade=grade, wbs_f1_vanna=vanna,
    )
    for key in ("garch_expected_move_6_10d", "l3_expected_move_6_10d"):
        row.pop(key)
    plan = compute_exit_plan(row)
    assert plan["exit_mode"] == mode
    assert plan["exit_t3_price"] == ""
    assert plan["exit_t3_pct"] == 0
    assert plan["exit_runner_target_state"] == "HORIZON_BUDGET_MISSING"
    assert plan["exit_plan_complete"] is False


# ------------------------------------------------------------------ the manifest reads the same budget
def _candidate_rows(**overrides) -> list[dict]:
    row = _ticker_row(**overrides)
    row["morning_execution_route"] = "GO"
    return [row]


def test_manifest_geometry_uses_legacy_increments_when_both_conventions_are_present():
    counts = _thesis_geometry_completeness(_candidate_rows(), [])
    assert counts["population"] == 1
    assert counts["actionable_population"] == 1
    assert counts["complete"] == 1
    assert counts["degenerate_unassessed"] == 0
    assert counts["degenerate_vol_relative"] == 0
    assert counts["target_beyond_3x_expected_move"] == 0


def test_manifest_geometry_assesses_a_row_that_carries_only_the_canonical_budget():
    counts = _thesis_geometry_completeness(_candidate_rows(legacy=False), [])
    assert counts["population"] == 1
    assert counts["degenerate_unassessed"] == 0
    assert counts["expected_move_basis"] != "CUMULATIVE_SUM_OF_LEGACY_INCREMENTS_PCT"


def test_manifest_geometry_does_not_assess_a_conflicting_budget():
    counts = _thesis_geometry_completeness(_candidate_rows(horizon_convention="INCREMENTAL"), [])
    assert counts["degenerate_unassessed"] == 1
    assert counts["degenerate_vol_relative"] == 0


def test_manifest_degenerate_rule_is_vol_relative_not_a_fixed_percent():
    # A stop 1% away on a 42%-vol name is inside 0.25 x the 10-session move (about 2.1%).
    tight = _candidate_rows(invalidation_price=round(SPOT * 0.99, 2))
    assert _thesis_geometry_completeness(tight, [])["degenerate_vol_relative"] == 1
    # The same 1% stop on a 12%-vol name is not degenerate (0.25 x ~2.4% = 0.6%).
    calm = checkpoint_fields(0.12)
    calm_move5 = calm["expected_move_5d_fraction"] * 100
    calm_move10 = calm["expected_move_10d_fraction"] * 100
    rows = _candidate_rows(invalidation_price=round(SPOT * 0.99, 2), **calm,
                           garch_expected_move_1_5d=calm_move5,
                           garch_expected_move_6_10d=calm_move10 - calm_move5)
    assert _thesis_geometry_completeness(rows, [])["degenerate_vol_relative"] == 0


def test_volatility_budget_arithmetic_is_root_time_and_unit_safe():
    assert CANON["expected_move_10d_fraction"] == pytest.approx(ANNUAL_VOL * math.sqrt(10 / 252))
    assert CANON["expected_move_20d_fraction"] == pytest.approx(ANNUAL_VOL * math.sqrt(20 / 252))
    assert CANON["bias_multiplier_applied"] is False
    assert CANON["vol_validation_state"] == "UNVALIDATED"
    # A display percentage (8.4) smuggled into the fraction slot is rejected, not scaled.
    assert cumulative_expected_move_pct({"expected_move_10d_fraction": 8.4}, "6_10D") is None
    # A fraction exactly at the 300% guard is still a fraction; beyond it is a defect.
    assert cumulative_expected_move_pct({"expected_move_10d_fraction": 3.0}, "6_10D") == 300.0
    assert cumulative_expected_move_pct({"expected_move_10d_fraction": 3.01}, "6_10D") is None
