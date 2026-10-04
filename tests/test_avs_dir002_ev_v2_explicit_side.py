"""DIR-002 DWN-16: legacy EV v2 cannot silently price an absent side as CALL."""

import pytest

from ev_engine_v2 import EVInputs, ev_inputs_from_row


def test_ev_inputs_requires_direction_at_construction():
    with pytest.raises(TypeError):
        EVInputs()


@pytest.mark.parametrize("direction", [None, "", "UNRESOLVED", "STRANGLE", "BULL|BEAR"])
def test_missing_or_ambiguous_row_direction_has_no_ev_input(direction):
    with pytest.raises(ValueError, match="explicit CALL or PUT"):
        ev_inputs_from_row({"ticker": "TEST", "direction": direction})


def test_explicit_put_reaches_ev_input_unchanged():
    assert ev_inputs_from_row({"ticker": "TEST", "direction": "PUT"}).direction == "PUT"
