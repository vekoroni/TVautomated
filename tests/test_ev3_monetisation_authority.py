from __future__ import annotations

from avshunter_monetisation_policy import (
    DecisionState,
    MonetisationPolicy,
    PolicyInput,
    map_options_row_to_policy_input,
)


def test_shadow_ev3_state_is_advisory_and_cannot_block() -> None:
    mapped = map_options_row_to_policy_input(
        {
            "ev3_authority_active": "False",
            "ev3_authority_state": "NEGATIVE",
            "ev3_ev_lower_bound_return": -0.20,
        }
    )
    assert mapped.ev3_authority_active is False
    assert MonetisationPolicy().evaluate(mapped).state != DecisionState.BLOCK_ECONOMICS


def test_requested_negative_and_indeterminate_ev3_states_remain_advisory() -> None:
    engine = MonetisationPolicy()
    for state in ("NEGATIVE", "INDETERMINATE", "NOT_EVALUATED_MARKET_CONSTRAINT"):
        output = engine.evaluate(
            PolicyInput(
                ev3_authority_active=True,
                ev3_authority_state=state,
                ev3_lower_bound_return=-0.01,
            )
        )
        assert output.state not in {DecisionState.BLOCK_ECONOMICS, DecisionState.BLOCK_DATA}
        assert output.final_size_mult > 0.0
        assert any(event.rule_id == "EV3_ADVISORY" for event in output.rule_events)


def test_ev3_data_defect_is_advisory_but_structure_still_has_authority() -> None:
    engine = MonetisationPolicy()
    defect = engine.evaluate(
        PolicyInput(ev3_authority_active=True, ev3_authority_state="NOT_EVALUATED_DATA_DEFECT")
    )
    assert defect.state != DecisionState.BLOCK_DATA
    assert any(event.rule_id == "EV3_ADVISORY" for event in defect.rule_events)

    positive = engine.evaluate(
        PolicyInput(
            ev3_authority_active=True,
            ev3_authority_state="POSITIVE",
            ev3_lower_bound_return=0.08,
            thesis_valid=False,
        )
    )
    assert positive.state == DecisionState.BLOCK_STRUCTURE
