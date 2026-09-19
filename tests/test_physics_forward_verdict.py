"""physics_verdict: the physics engine's forward pressure, aligned with the trade direction (ACK, 19 Sep 2026).

EIL's no-current-edge veto routes a row to EOD_PROBE_CANDIDATE ("no current edge, forward evidence") when
physics_verdict is EARLY_PRESSURE_BUILDING or MONETISABLE_PRESSURE - but nothing ever produced physics_verdict, so the
route never fired and the flag was discarded. Physics owns the rule; it is applied where the final direction is
known. Display, measurement and review routing only: it grants no capital and does not rank tickets (rule 5).
On 18 Sep (with F8 inputs): 95 EARLY_PRESSURE_BUILDING, 190 MONETISABLE_PRESSURE, 655 NO_DIRECTIONAL_PRESSURE,
422 PRESSURE_AGAINST_DIRECTION, 137 non-directional; three of the five tickets had pressure against their direction.
"""

from __future__ import annotations

import inspect

import pytest

from vanguard.physics_state_engine import physics_forward_verdict


@pytest.mark.parametrize("label,direction,expected", [
    ("BALANCE_TO_UPSIDE_EXPANSION", "CALL", "EARLY_PRESSURE_BUILDING"),
    ("BALANCE_TO_DOWNSIDE_EXPANSION", "PUT", "EARLY_PRESSURE_BUILDING"),
    ("CONTINUATION_UP", "CALL", "MONETISABLE_PRESSURE"),
    ("CONTINUATION_DOWN", "PUT", "MONETISABLE_PRESSURE"),
    ("BALANCE_TO_DOWNSIDE_EXPANSION", "CALL", "PRESSURE_AGAINST_DIRECTION"),
    ("CONTINUATION_UP", "PUT", "PRESSURE_AGAINST_DIRECTION"),
    ("CHOP_CONTINUATION", "CALL", "NO_DIRECTIONAL_PRESSURE"),
    ("NO_TRANSITION_EDGE", "PUT", "NO_DIRECTIONAL_PRESSURE"),
    ("FAILED_BREAKOUT_RISK", "CALL", "NO_DIRECTIONAL_PRESSURE"),
])
def test_forward_pressure_is_read_against_the_trade_direction(label, direction, expected):
    assert physics_forward_verdict(label, direction) == expected


def test_non_directional_and_missing_physics_are_reported_not_defaulted():
    assert physics_forward_verdict("CONTINUATION_UP", "STRANGLE") == "NOT_APPLICABLE_NON_DIRECTIONAL"
    assert physics_forward_verdict(None, "CALL") == "PHYSICS_UNAVAILABLE"
    assert physics_forward_verdict("nan", "CALL") == "PHYSICS_UNAVAILABLE"


def _vetoed_row(label: str, direction: str) -> dict:
    return {"ticker": "ABC", "final_direction": direction, "state_transition_label": label,
            "signal_type": "NO_EDGE", "momentum_tier": "TIER_2"}


def test_eil_routes_a_no_edge_row_with_aligned_pressure_to_the_probe_queue():
    import execution_intelligence_runner as eil
    row = eil._apply_current_edge_hard_veto(eil._attach_physics_verdict(_vetoed_row("BALANCE_TO_UPSIDE_EXPANSION", "CALL")))
    assert row["physics_verdict"] == "EARLY_PRESSURE_BUILDING"
    assert row["pse_execution_mode"] == "EOD_PROBE_CANDIDATE"
    assert row["capital_permission"] == "EOD_CANDIDATE_ONLY" and row["pse_final_size"] == 0.0   # still no capital


def test_eil_keeps_a_no_edge_row_without_aligned_pressure_in_data_review():
    import execution_intelligence_runner as eil
    row = eil._apply_current_edge_hard_veto(eil._attach_physics_verdict(_vetoed_row("CONTINUATION_DOWN", "CALL")))
    assert row["physics_verdict"] == "PRESSURE_AGAINST_DIRECTION"
    assert row["pse_execution_mode"] == "EOD_DATA_INSUFFICIENT_REVIEW"


def test_eil_attaches_the_verdict_on_every_row_before_the_veto_reads_it():
    import execution_intelligence_runner as eil
    source = inspect.getsource(eil._process_row)
    assert source.index("_attach_physics_verdict(row)") < source.index("_apply_current_edge_hard_veto(row)")


def test_the_book_and_the_ticket_files_carry_the_verdict():
    from contracts.lab_control import FINAL_BOOK_FIELDS, opportunity_book_row
    from avshunter.c12_outcome import signal_service
    assert "physics_verdict" in FINAL_BOOK_FIELDS
    assert opportunity_book_row({"ticker": "ABC", "physics_verdict": "EARLY_PRESSURE_BUILDING"}, "RUN", 1)[
        "physics_verdict"] == "EARLY_PRESSURE_BUILDING"
    assert "physics_verdict" in signal_service.TICKET_DISPLAY_FIELDS
