"""XLU-D11 (ACK 2 Oct 2026) and the Morning consequence of XLU-D01.

Business rules:
- A Morning move confirms the thesis only when it is material: at least
  morning_runway.confirmation_min_expected_move_fraction of the one-session expected move in
  the thesis direction. A smaller move confirms nothing (THESIS_ACTIVE).
- A material move against the thesis is THESIS_UNDER_PRESSURE: flagged, never relabelled
  EXECUTABLE_NOW, and never mapped to THESIS_CONFIRMED (it maps to PENDING_TRIGGER).
- With no structural target (D01: none is invented), the runway is measured to the
  volatility-reachable target and the basis is recorded; the row does not fail closed.
Evidence (run 20260930_083504): XLU PUT 39.71 -> 39.51 (-0.50%, 0.34 ATR) confirmed as
GAP_CONFIRMATION_WITH_RUNWAY; 299 of 463 THESIS_CONFIRMED rows had moved against the thesis.
"""
from domain.option_contract_liquidity import classify_remaining_runway
import morning_gate


def runway(side, origin, current, em, fraction=0.5):
    target, stop = (origin * 1.10, origin * 0.95) if side == "CALL" else (origin * 0.90, origin * 1.05)
    return classify_remaining_runway(side, thesis_spot=origin, current_spot=current, structural_target=target,
                                     invalidation_spot=stop, one_session_expected_move_abs=em,
                                     confirmation_min_expected_move_fraction=fraction)["remaining_runway_state"]


def test_xlu_drift_is_not_a_confirmation():
    # PUT 39.71 -> 39.51 is a 0.20 favourable drift against a ~0.59 one-session expected move.
    assert runway("PUT", 39.71, 39.51, em=0.59) == "THESIS_ACTIVE"


def test_material_favourable_move_confirms():
    assert runway("CALL", 100.0, 101.0, em=1.5) == "GAP_CONFIRMATION_WITH_RUNWAY"
    assert runway("PUT", 100.0, 99.0, em=1.5) == "GAP_CONFIRMATION_WITH_RUNWAY"


def test_moves_against_the_thesis_are_pressure_only_when_material():
    assert runway("CALL", 100.0, 99.9, em=1.5) == "THESIS_ACTIVE"
    assert runway("CALL", 100.0, 99.0, em=1.5) == "THESIS_UNDER_PRESSURE"


def test_without_an_expected_move_nothing_is_confirmed_and_adverse_stays_flagged():
    assert runway("CALL", 100.0, 101.0, em=None) == "THESIS_ACTIVE"
    assert runway("CALL", 100.0, 99.0, em=None) == "THESIS_UNDER_PRESSURE"


def _row(**over):
    row = {"ticker": "TEST", "final_direction": "CALL", "thesis_spot": 100.0, "signal_price": 100.0,
           "contract_strike": 100.0, "invalidation_price": 95.0, "contract_dte": 40, "planned_hold_sessions": 20,
           "hv_30d": 0.25, "contract_symbol": "TEST261120C00100000", "thesis_id": "T:CALL:2026-10-01",
           "lifecycle_contract_version": "v1", "target_price": 110.0}
    row.update(over)
    return row


LIVE = {"live_price": 99.0, "live_contract_bid": 3.0, "live_contract_ask": 3.1, "live_contract_delta": 0.5,
        # a fresh quote at test time (a fixed clock time goes stale and changes the liquidity state)
        "live_contract_provider_updated": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ")}


def test_adverse_move_is_not_relabelled_executable_now():
    out = morning_gate._morning_liquidity_lifecycle(_row(), dict(LIVE), contract_changed=False,
                                                    economics_recompute_complete=False)
    assert out["remaining_runway_state"] == "THESIS_UNDER_PRESSURE"
    assert out["morning_transition_state"] == "THESIS_UNDER_PRESSURE"


def test_runway_uses_the_reachable_target_when_no_structural_target_exists():
    out = morning_gate._morning_liquidity_lifecycle(_row(target_price=None, target_reachable=106.0), dict(LIVE),
                                                    contract_changed=False, economics_recompute_complete=False)
    assert out.get("thesis_state") != "DATA_INCOMPLETE"
    assert out["runway_target_basis"] == "REACHABLE"


def test_validation_maps_pressure_to_pending_never_confirmed():
    from orchestrator.dynamic_validation import validation_event_from_morning_row
    import inspect
    source = inspect.getsource(validation_event_from_morning_row)
    confirmed_block = source[source.index('"EXECUTABLE_NOW",'):source.index("ValidationTransition.THESIS_CONFIRMED.value")]
    assert "THESIS_UNDER_PRESSURE" not in confirmed_block
    pending_block = source[source.index('"CONTRACT_REPRICE_REQUIRED",'):source.index("ValidationTransition.PENDING_TRIGGER.value")]
    assert '"THESIS_UNDER_PRESSURE"' in pending_block


def test_eod_publishes_the_reachable_target_for_morning():
    from pathlib import Path
    source = Path("eod_candidate_engine.py").read_text(encoding="utf-8")
    assert '"target_reachable":     _optional_flt(row, "target_reachable"),' in source


def test_evening_options_lifecycle_uses_the_reachable_target_without_a_structural_one():
    """XLU-D01 consequence at Evening: Options' lifecycle must not fail closed on rows with no
    structural target (none is invented any more); it runs on the reachable target."""
    import scripts.avshunter_options_intelligence as oi
    from test_ev3_options_handoff import _context
    ctx = _context(direction="CALL")
    ctx.update({"structural_target": None, "target_reachable": 106.0})
    contract = {"symbol": "SERIES260918C00100000", "strike": 100.0, "dte": 21, "delta": 0.40,
                "bid": 1.90, "ask": 2.00, "quote_timestamp_utc": "2026-08-28T20:00:00Z", "mark_synthetic": False}
    lifecycle = oi._options_liquidity_lifecycle_fields(ctx, contract, {"hv_30d": 0.28, "atm_iv": 0.30})
    assert lifecycle.get("thesis_state") != "DATA_INCOMPLETE"
    assert "structural_target" not in str(lifecycle.get("liquidity_lifecycle_reason") or "")
